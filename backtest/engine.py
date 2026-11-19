"""
Olay güdümlü backtest motoru — canlı botun KENDİ kodunu simüle saatle çalıştırır.

Giriş tarafı (main.py'deki akışın veriyle yeniden üretilebilen kısmı):
  TechnicalAnalysisAgent.analyze_multi_horizon -> check_4h_macro_compass -> BTC rejim kalkanı
  -> RiskOfficerAgent.evaluate -> (opsiyonel) Monte Carlo kapısı -> (opsiyonel) turnuva kalite barajı
  -> vade kotaları, eşzamanlı pozisyon limiti, sembol+yön soğuma molası, günlük zarar sigortası.
Çıkış tarafı:
  Gerçek CounterfactualTrackerAgent; her 1 dakikalık mum için (open, high, low, close) tick'leri
  WebSocket önbelleğine yazılır ve takip ajanı çağrılır (fitil temasları muhafazakâr sırayla işlenir).

Geleceği görme (lookahead) koruması: t anındaki analiz yalnızca t'den önce KAPANMIŞ mumları ve
t anına kadarki 1m mumlardan oluşan "oluşmakta olan" mumu görür.

Yeniden üretilemeyen canlı filtreler (haber, OI/basis/OBI, Gemini AI uygunluk, pair arbitraj) atlanır.
"""
import bisect
import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import core.binance_streamer as streamer
from core import timeutil
from core.binance_client import BinanceFuturesClient
from backtest.data import INTERVAL_MS

TR_TZ = timezone(timedelta(hours=3))


@dataclass
class BacktestConfig:
    symbols: List[str]
    start_ms: int                     # simülasyonun başladığı an (ısınma sonrası)
    end_ms: int
    scan_every_minutes: int = 15
    max_concurrent: int = 8
    daily_quota: Dict[str, int] = field(default_factory=lambda: {"15m": 6, "30m": 5, "1h": 4})
    use_mc_gate: bool = True
    mc_simulations: int = 2000
    use_quality_gate: bool = True
    quality_threshold: float = 68.0
    use_btc_shield: bool = True
    use_4h_compass: bool = True
    funding_rate: float = 0.0001
    daily_max_loss_usd: float = 35.0
    post_loss_cooldown_min: int = 15
    allowed_timeframes: List[str] = field(default_factory=lambda: ["15m", "30m", "1h"])
    seed: int = 42


class SimMarket:
    """Önceden yüklenmiş mumlardan simüle saate göre veri sunar."""

    def __init__(self, data: Dict[str, Dict[str, List[Dict]]]):
        self.data = data
        self.ts_index = {s: {iv: [c["timestamp"] for c in rows] for iv, rows in ivs.items()} for s, ivs in data.items()}
        self.now_ms = 0

    def closed(self, symbol: str, interval: str, limit: int) -> List[Dict]:
        rows = self.data.get(symbol, {}).get(interval)
        if not rows:
            return []
        step = INTERVAL_MS[interval]
        # kapanış zamanı <= now olan mumlar: timestamp + step <= now
        idx = bisect.bisect_right(self.ts_index[symbol][interval], self.now_ms - step)
        return rows[max(0, idx - limit):idx]

    def forming(self, symbol: str, interval: str) -> Optional[Dict]:
        """Şu an oluşmakta olan mumu 1m verisinden üretir (yalnızca geçmiş dakikalar)."""
        step = INTERVAL_MS[interval]
        open_ms = (self.now_ms // step) * step
        m1 = self.data.get(symbol, {}).get("1m")
        if not m1:
            return None
        ts = self.ts_index[symbol]["1m"]
        i0 = bisect.bisect_left(ts, open_ms)
        i1 = bisect.bisect_right(ts, self.now_ms - 60_000)
        bars = m1[i0:i1]
        if not bars:
            prev = m1[max(0, i0 - 1)] if i0 > 0 else None
            if prev is None:
                return None
            px = prev["close"]
            return {"timestamp": open_ms, "open": px, "high": px, "low": px, "close": px,
                    "volume": 0.0, "quote_volume": 0.0, "taker_buy_volume": 0.0}
        return {
            "timestamp": open_ms, "open": bars[0]["open"], "high": max(b["high"] for b in bars),
            "low": min(b["low"] for b in bars), "close": bars[-1]["close"],
            "volume": sum(b["volume"] for b in bars), "quote_volume": sum(b["quote_volume"] for b in bars),
            "taker_buy_volume": sum(b["taker_buy_volume"] for b in bars),
        }

    def klines(self, symbol: str, interval: str, limit: int) -> List[Dict]:
        """Canlı API ile aynı biçim: kapanmış mumlar + sonda oluşmakta olan mum."""
        rows = self.closed(symbol, interval, max(1, limit - 1))
        f = self.forming(symbol, interval)
        return rows + ([f] if f else [])

    def last_price(self, symbol: str) -> Optional[float]:
        f = self.forming(symbol, "1m")
        return f["close"] if f else None


class SimClient(BinanceFuturesClient):
    """BinanceFuturesClient'ın ağ yerine SimMarket kullanan sürümü (get_btc_regime vb. aynen çalışır)."""

    def __init__(self, market: SimMarket, funding_rate: float = 0.0001):
        super().__init__()
        self.market = market
        self.funding_rate = funding_rate

    def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> List[Dict]:
        return self.market.klines(symbol, interval, limit)

    def get_24hr_tickers(self) -> Dict[str, Dict]:
        out = {}
        for s in self.market.data:
            px = self.market.last_price(s)
            if px:
                out[s] = {"symbol": s, "lastPrice": px, "quoteVolume": 1e9, "priceChangePercent": 0.0}
        return out

    def get_funding_rate(self, symbol: str):
        return {"lastFundingRate": self.funding_rate, "markPrice": 0.0, "indexPrice": 0.0}

    def get_book_ticker(self, symbol: str):
        return None

    def get_order_book_imbalance(self, symbol: str, limit: int = 20):
        return None

    def get_open_interest_delta(self, symbol: str, period: str = "15m", limit: int = 6):
        return None

    def get_all_premium_basis(self):
        return {}


def committee_confidence(score: float, mc_win_pct: float, min_score: float) -> float:
    """ai_analyst_agent.run_committee_debate'deki deterministik onay skorunun aynısı."""
    bonus = 0.3 if mc_win_pct >= 55.0 else 0.0
    return round(min(9.8, 7.8 + (score - min_score) * 0.1 + bonus), 1)


def quality_score(mc_win_pct: float, ai_conf: float, rr: float, risk_grade: str) -> float:
    from main import grade_to_score
    mc = (mc_win_pct / 100.0) * 35.0
    ai = (ai_conf / 10.0) * 25.0
    rr_c = max(1.5, min(rr, 4.0))
    rr_s = ((rr_c - 1.5) / 2.5) * 20.0
    return round(mc + ai + rr_s + grade_to_score(risk_grade), 1)


class BacktestEngine:
    def __init__(self, cfg: BacktestConfig, data: Dict[str, Dict[str, List[Dict]]], quiet: bool = True):
        self.cfg = cfg
        self.market = SimMarket(data)
        self.client = SimClient(self.market, cfg.funding_rate)
        self.quiet = quiet
        self.rejections = defaultdict(int)

    # ---------- yardımcılar ----------
    def _now(self) -> datetime:
        return datetime.fromtimestamp(self.market.now_ms / 1000, tz=timezone.utc)

    def _tr_day(self) -> str:
        return self._now().astimezone(TR_TZ).strftime("%Y-%m-%d")

    def _feed_minute(self, symbols, bar_ms: int):
        """bar_ms açılışlı 1m mumun tick'lerini (O, H, L, C) WebSocket önbelleğine yazar."""
        for s in symbols:
            ts = self.market.ts_index[s].get("1m")
            if not ts:
                continue
            i = bisect.bisect_left(ts, bar_ms)
            if i < len(ts) and ts[i] == bar_ms:
                b = self.market.data[s]["1m"][i]
                for px in (b["open"], b["high"], b["low"], b["close"]):
                    streamer._record_tick_for_test(s, px)

    # ---------- ana döngü ----------
    def run(self) -> Dict:
        import random
        import numpy as np
        random.seed(self.cfg.seed)
        np.random.seed(self.cfg.seed)

        tmp = tempfile.mkdtemp(prefix="tradebot_bt_")
        import core.database as db
        old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(tmp, "backtest.db")
        db._THREAD_LOCAL.conn = None
        timeutil.set_clock(self._now)

        from agents.ta_agent import TechnicalAnalysisAgent
        from agents.risk_agent import RiskOfficerAgent
        from agents.quant_simulation_agent import QuantSimulationAgent
        from agents.tracker_agent import CounterfactualTrackerAgent
        import core.reflection as refl

        orig_chart = CounterfactualTrackerAgent.generate_outcome_chart
        orig_reflect = refl.ReflectorEngine.reflect_on_trade
        CounterfactualTrackerAgent.generate_outcome_chart = lambda *a, **k: ""
        refl.ReflectorEngine.reflect_on_trade = staticmethod(lambda d: {"lesson": ""})
        try:
            db.init_db()
            ta = TechnicalAnalysisAgent()
            risk = RiskOfficerAgent()
            mc = QuantSimulationAgent(default_simulations=self.cfg.mc_simulations, win_threshold_pct=48.0)
            tracker = CounterfactualTrackerAgent(self.client)
            self._simulate(db, ta, risk, mc, tracker)
            trades = [dict(r) for r in db.get_db_connection().execute(
                "SELECT * FROM signals ORDER BY id").fetchall()]
        finally:
            CounterfactualTrackerAgent.generate_outcome_chart = orig_chart
            refl.ReflectorEngine.reflect_on_trade = orig_reflect
            timeutil.set_clock(None)
            try:
                db.get_db_connection().close()
            except Exception:
                pass
            db._THREAD_LOCAL.conn = None
            db.DB_PATH = old_db_path
            streamer._TICK_EXTREMES.clear()
            streamer._LIVE_PRICES.clear()
        return {"trades": trades, "rejections": dict(self.rejections)}

    def _simulate(self, db, ta, risk, mc, tracker):
        cfg = self.cfg
        scan_step = cfg.scan_every_minutes * 60_000
        quotas_used = defaultdict(lambda: defaultdict(int))
        last_loss = {}
        t = cfg.start_ms
        while t < cfg.end_ms:
            # 1) Açık pozisyonları dakika dakika takip et
            open_rows = db.get_active_and_pending_signals()
            if open_rows:
                syms = sorted({r["symbol"] for r in open_rows})
                self._feed_minute(syms, t - 60_000)
                self.market.now_ms = t
                tracker.update_tracked_trades(evaluate_shadows=False)
            self.market.now_ms = t
            # 2) Tarama zamanı mı?
            if t % scan_step == 0:
                self._scan(db, ta, risk, mc, quotas_used, last_loss)
            t += 60_000

    def _record_losses(self, db, last_loss):
        for r in db.get_db_connection().execute(
                "SELECT symbol, direction, closed_at FROM signals WHERE simulated_pnl_pct < 0 AND closed_at IS NOT NULL").fetchall():
            last_loss[(r["symbol"], r["direction"])] = max(last_loss.get((r["symbol"], r["direction"]), ""), r["closed_at"])

    def _today_realized(self, db) -> float:
        start = (self._now().astimezone(TR_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
                 .astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        row = db.get_db_connection().execute(
            "SELECT COALESCE(SUM(allocated_margin_usdt * simulated_pnl_pct / 100.0), 0) FROM signals "
            "WHERE closed_at >= ? AND simulated_pnl_pct IS NOT NULL", (start,)).fetchone()
        return float(row[0] or 0.0)

    def _equity(self, db) -> float:
        row = db.get_db_connection().execute(
            "SELECT COALESCE(SUM(allocated_margin_usdt * simulated_pnl_pct / 100.0), 0) FROM signals "
            "WHERE closed_at IS NOT NULL AND simulated_pnl_pct IS NOT NULL").fetchone()
        return 1000.0 + float(row[0] or 0.0)

    def _reject(self, key):
        self.rejections[key] += 1

    def _scan(self, db, ta, risk, mc, quotas_used, last_loss):
        cfg = self.cfg
        active = db.get_active_and_pending_signals() or []
        if len(active) >= cfg.max_concurrent:
            return self._reject("max_concurrent")
        equity = self._equity(db)
        if -self._today_realized(db) >= max(cfg.daily_max_loss_usd, equity * 0.035):
            return self._reject("circuit_breaker")
        day = self._tr_day()
        allowed = [tf for tf in cfg.allowed_timeframes if quotas_used[day][tf] < cfg.daily_quota.get(tf, 0)]
        if not allowed:
            return self._reject("daily_quota")

        btc_regime = self.client.get_btc_regime() if cfg.use_btc_shield else None
        if btc_regime and btc_regime.get("block_all_entries"):
            return self._reject("btc_dead_chop")

        self._record_losses(db, last_loss)
        open_syms = {a["symbol"] for a in active}
        now_str = self._now().strftime("%Y-%m-%d %H:%M:%S")
        candidates = []
        for sym in cfg.symbols:
            if sym in open_syms:
                continue
            c15 = self.market.klines(sym, "15m", 100) if "15m" in allowed else []
            c30 = self.market.klines(sym, "30m", 80) if "30m" in allowed else []
            c1h = self.market.klines(sym, "1h", 80)
            if len(c1h) < 35:
                continue
            setup, reason = ta.analyze_multi_horizon(sym, c15, c30, c1h, allowed_timeframes=allowed)
            if not setup:
                self._reject("ta")
                continue
            if cfg.use_4h_compass:
                ok, _, _ = ta.check_4h_macro_compass(setup, self.market.klines(sym, "4h", 60))
                if not ok:
                    self._reject("4h_compass")
                    continue
            ll = last_loss.get((sym, setup["direction"]))
            if ll and (self._now().replace(tzinfo=None) - datetime.strptime(ll[:19], "%Y-%m-%d %H:%M:%S")).total_seconds() < cfg.post_loss_cooldown_min * 60:
                self._reject("post_loss_cooldown")
                continue
            approved, report = risk.evaluate(setup, {}, {"symbol": sym}, btc_regime, funding_data=None, book_ticker=None,
                                             active_signals=active, current_equity=equity, client=self.client)
            if not approved:
                self._reject("risk")
                continue
            tf = setup.get("timeframe", "15m")
            sim_c = c1h if tf == "1h" else (c30 if tf == "30m" else c15)
            horizon = 48 if tf == "1h" else (36 if tf == "30m" else 24)
            mc_win = 50.0
            if cfg.use_mc_gate or cfg.use_quality_gate:
                q = mc.simulate_setup(sym, setup, sim_c, num_simulations=cfg.mc_simulations, horizon_bars=horizon)
                mc_win = float(q.get("win_probability_pct", 0.0))
                if cfg.use_mc_gate and not q.get("is_approved"):
                    self._reject("monte_carlo")
                    continue
            from config import MIN_CONFLUENCE_SCORE
            conf = committee_confidence(setup.get("confluence_score", 0), mc_win, MIN_CONFLUENCE_SCORE)
            qs = quality_score(mc_win, conf, float(setup.get("risk_reward", 2.0)), report.get("risk_grade", ""))
            if cfg.use_quality_gate and qs < cfg.quality_threshold:
                self._reject("quality_gate")
                continue
            candidates.append((qs, setup, report))

        if not candidates:
            return
        candidates.sort(key=lambda x: x[0], reverse=True)
        qs, setup, report = candidates[0]  # canlı bot gibi: döngü başına 1 işlem
        from config import ESTIMATED_SLIPPAGE_PCT, STRATEGY_VERSION
        px = float(setup["current_price"])
        slip = ESTIMATED_SLIPPAGE_PCT / 100.0
        fill = px * (1 + slip) if setup["direction"] == "LONG" else px * (1 - slip)
        db.save_signal({
            **setup,
            "actual_entry_price": round(fill, 8),
            "allocated_margin_usdt": report["allocated_margin_usdt"],
            "risk_usd": report["risk_usd"],
            "risk_grade": report["risk_grade"],
            "strategy_version": STRATEGY_VERSION + "-backtest",
        })
        quotas_used[self._tr_day()][setup.get("timeframe", "15m")] += 1
        if not self.quiet:
            print(f"[{now_str}] OPEN {setup['symbol']} {setup['direction']} {setup.get('timeframe')} q={qs}")
