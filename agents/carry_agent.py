"""
v3 Çok Faktörlü Motor — trend + kesitsel momentum + fonlama faktörü, eşit riskli kollar, günlük 1/7 dilim.

Bileşenler:
  - CarryEngine: saf iş mantığı (fonlama tahakkuku, kesici, yeniden dengeleme, muhasebe).
    Veri kaynağı ve depolama dışarıdan verilir; canlı bot ve backtest aynı motoru çalıştırır.
  - LiveCarryData: Binance REST verisi.
  - SQLiteCarryStore / MemoryCarryStore: durum, dolumlar ve özsermaye geçmişi.

Muhasebe (lineer USDT-M perp): equity = cash + Σ qty·fiyat.
  Alım dq @ p:  cash -= dq·p_dolum + komisyon     (dq < 0 satış/short)
  Fonlama:      cash -= qty·fiyat·oran            (pozitif oranda LONG öder, SHORT alır)
Bu, Σ qty·(fiyat - giriş) PnL'ine birebir denktir.
"""
from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Protocol

import config
from core.carry_strategy import (combine_sleeves, compute_target_weights, drawdown_scale, funding_weights,
                                 plan_orders, realized_vol_ann, tsmom_weights, xsmom_weights)

HOUR_MS = 3_600_000
WEEK_MS = 7 * 24 * HOUR_MS
# v3.1'in ilk canlı sürümü bu risk seviyesiyle çalıştı; durumda "target_vol_used" yoksa o sürümde oluşturulmuştur.
LEGACY_TARGET_VOL = 0.10


# --------------------------------------------------------------------------------------
# Arayüzler
# --------------------------------------------------------------------------------------
class CarryData(Protocol):
    def now_ms(self) -> int: ...
    def hourly_closes(self, symbol: str, n: int) -> List[float]: ...       # yalnızca KAPANMIŞ mumlar
    def funding_history(self, symbol: str, start_ms: int, end_ms: int) -> List[Dict]: ...  # [{'time','rate'}]
    def prices(self, symbols: List[str]) -> Dict[str, float]: ...


@dataclass
class CarryParams:
    universe: List[str] = field(default_factory=lambda: list(config.CARRY_UNIVERSE))
    capital: float = config.CARRY_CAPITAL_USDT
    k: int = config.CARRY_K
    funding_lookback_h: int = config.CARRY_FUNDING_LOOKBACK_H
    vol_lookback_h: int = config.CARRY_VOL_LOOKBACK_H
    target_vol: float = config.CARRY_TARGET_VOL
    gross_cap: float = config.CARRY_GROSS_CAP
    rebalance_weekday: int = config.CARRY_REBALANCE_WEEKDAY
    rebalance_hour: int = config.CARRY_REBALANCE_HOUR_UTC
    sleeves: tuple = tuple(config.CARRY_SLEEVES)   # ("trend", "xsmom", "funding") ya da yalnızca ("funding",)
    tsmom_lookback_h: int = config.CARRY_TSMOM_LOOKBACK_H
    xsmom_lookback_h: int = config.CARRY_XSMOM_LOOKBACK_H
    portfolio_target_vol: float = config.CARRY_PORTFOLIO_TARGET_VOL
    tranches: int = config.CARRY_TRANCHES          # >1: her gün bir dilim; hedef = son N günlük sinyalin ortalaması
    max_universe: int = config.CARRY_MAX_UNIVERSE   # >0: adaylardan son 30 günün en likit N coini (o günün verisiyle)
    k_quantile: float = config.CARRY_K_QUANTILE     # >0: bacak başına coin sayısı = seçilen evren x oran
    liquidity_lookback_h: int = 24 * 30
    min_trade_usdt: float = config.CARRY_MIN_TRADE_USDT
    fee_rate: float = config.CARRY_FEE_RATE
    slippage_rate: float = config.CARRY_SLIPPAGE_RATE
    dd_cut: float = config.CARRY_DD_CUT
    dd_restore: float = config.CARRY_DD_RESTORE


def default_state(capital: float) -> Dict:
    return {
        "version": config.CARRY_STRATEGY_VERSION,
        "cash": capital, "capital": capital,
        "positions": {},              # sym -> {"qty", "avg_price", "opened_ms"}
        "last_rebalance_ms": None,
        "qty_history": [], "funding_seen_ms": {}, "last_funding_query_slot": None,
        "peak_equity": capital, "scale": 1.0,
        "last_snapshot_hour": None,
        "fees_paid": 0.0, "funding_paid": 0.0, "realized_pnl": 0.0,
        "n_fills": 0, "n_rebalances": 0,
        "last_targets": {}, "last_signal": {}, "tranche_weights": [], "tranche_contribs": [],
        "target_vol_used": None, "risk_changes": [],
    }


# --------------------------------------------------------------------------------------
# Depolama
# --------------------------------------------------------------------------------------
class MemoryCarryStore:
    def __init__(self):
        self.state: Optional[Dict] = None
        self.fills: List[Dict] = []
        self.equity: List[Dict] = []
        self.rebalances: List[Dict] = []

    def load(self) -> Optional[Dict]:
        return json.loads(json.dumps(self.state)) if self.state else None

    def save(self, state: Dict) -> None:
        self.state = json.loads(json.dumps(state))

    def record_fill(self, fill: Dict) -> None:
        self.fills.append(fill)

    def record_equity(self, row: Dict) -> None:
        self.equity.append(row)

    def record_rebalance(self, row: Dict) -> None:
        self.rebalances.append(row)

    def between(self, table: str, start_ms: int, end_ms: int) -> List[Dict]:
        src = {"carry_fills": self.fills, "carry_equity": self.equity, "carry_rebalances": self.rebalances}[table]
        return sorted((r for r in src if start_ms <= r["ts_ms"] < end_ms), key=lambda r: r["ts_ms"])

    def equity_at_or_before(self, ts_ms: int) -> Optional[Dict]:
        rows = [r for r in self.equity if r["ts_ms"] <= ts_ms]
        return max(rows, key=lambda r: r["ts_ms"]) if rows else None


class SQLiteCarryStore:
    """Bot veritabanında carry_* tabloları."""

    def __init__(self, db_path=None):
        self.db_path = str(db_path or config.DB_PATH)
        self._lock = threading.Lock()
        self._init()

    def _conn(self):
        import sqlite3
        c = sqlite3.connect(self.db_path, timeout=60.0)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._lock, self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS carry_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            c.execute("""CREATE TABLE IF NOT EXISTS carry_fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, ts_ms INTEGER, symbol TEXT, side TEXT,
                qty REAL, price REAL, notional REAL, fee REAL, realized_pnl REAL, reason TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS carry_equity (
                ts_ms INTEGER PRIMARY KEY, ts TEXT, equity REAL, gross_exposure REAL, net_exposure REAL,
                n_positions INTEGER, scale REAL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS carry_rebalances (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, ts_ms INTEGER, equity REAL, n_orders INTEGER,
                turnover_usdt REAL, fees REAL, scale REAL, reason TEXT, signal_json TEXT)""")
            cols = {r[1] for r in c.execute("PRAGMA table_info(carry_equity)")}
            for col in ("fees_paid", "funding_paid", "realized_pnl"):
                if col not in cols:
                    c.execute(f"ALTER TABLE carry_equity ADD COLUMN {col} REAL")

    def load(self) -> Optional[Dict]:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT value FROM carry_state WHERE key='state'").fetchone()
        return json.loads(r["value"]) if r else None

    def save(self, state: Dict) -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO carry_state(key, value) VALUES('state', ?)", (json.dumps(state),))

    def record_fill(self, f: Dict) -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO carry_fills(ts, ts_ms, symbol, side, qty, price, notional, fee, realized_pnl, reason) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (f["ts"], f["ts_ms"], f["symbol"], f["side"], f["qty"], f["price"], f["notional"], f["fee"],
                       f["realized_pnl"], f["reason"]))

    def record_equity(self, r: Dict) -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO carry_equity(ts_ms, ts, equity, gross_exposure, net_exposure, n_positions, scale, "
                      "fees_paid, funding_paid, realized_pnl) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (r["ts_ms"], r["ts"], r["equity"], r["gross_exposure"], r["net_exposure"], r["n_positions"], r["scale"],
                       r.get("fees_paid"), r.get("funding_paid"), r.get("realized_pnl")))

    def record_rebalance(self, r: Dict) -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO carry_rebalances(ts, ts_ms, equity, n_orders, turnover_usdt, fees, scale, reason, signal_json) "
                      "VALUES(?,?,?,?,?,?,?,?,?)",
                      (r["ts"], r["ts_ms"], r["equity"], r["n_orders"], r["turnover_usdt"], r["fees"], r["scale"], r["reason"],
                       json.dumps(r.get("signal", {}))))

    def between(self, table: str, start_ms: int, end_ms: int) -> List[Dict]:
        """start_ms <= ts_ms < end_ms aralığındaki kayıtlar (eskiden yeniye)."""
        assert table in ("carry_fills", "carry_equity", "carry_rebalances")
        with self._lock, self._conn() as c:
            rows = c.execute(f"SELECT * FROM {table} WHERE ts_ms >= ? AND ts_ms < ? ORDER BY ts_ms",
                             (int(start_ms), int(end_ms))).fetchall()
        return [dict(r) for r in rows]

    def equity_at_or_before(self, ts_ms: int) -> Optional[Dict]:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM carry_equity WHERE ts_ms <= ? ORDER BY ts_ms DESC LIMIT 1", (int(ts_ms),)).fetchone()
        return dict(r) if r else None

    # Dashboard okumaları
    def recent(self, table: str, limit: int = 200, order: str = "ts_ms DESC") -> List[Dict]:
        assert table in ("carry_fills", "carry_equity", "carry_rebalances")
        with self._lock, self._conn() as c:
            rows = c.execute(f"SELECT * FROM {table} ORDER BY {order} LIMIT ?", (int(limit),)).fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------------------
# Motor
# --------------------------------------------------------------------------------------
def _fmt(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def last_scheduled_rebalance(now_ms: int, weekday: int, hour: int) -> int:
    """now_ms'ye eşit veya ondan önceki en son planlı yeniden dengeleme anı (ms)."""
    now = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
    cand = now.replace(minute=0, second=0, microsecond=0, hour=hour)
    cand -= timedelta(days=(cand.weekday() - weekday) % 7)
    if cand > now:
        cand -= timedelta(days=7)
    return int(cand.timestamp() * 1000)


class CarryEngine:
    def __init__(self, data: CarryData, store, params: Optional[CarryParams] = None, notifier=None, verbose=False):
        self.data = data
        self.store = store
        self.p = params or CarryParams()
        self.notifier = notifier
        self.verbose = verbose
        self.state = store.load() or default_state(self.p.capital)
        self._lock = threading.Lock()

    # ---- yardımcılar ----
    def equity(self, prices: Dict[str, float]) -> float:
        eq = self.state["cash"]
        for s, pos in self.state["positions"].items():
            px = prices.get(s) or pos["avg_price"]
            eq += pos["qty"] * px
        return eq

    def exposures(self, prices: Dict[str, float]):
        g = n = 0.0
        for s, pos in self.state["positions"].items():
            v = pos["qty"] * (prices.get(s) or pos["avg_price"])
            g += abs(v)
            n += v
        return g, n

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    # ---- fonlama ----
    def _qty_at(self, sym: str, t_ms: int) -> float:
        """Ödeme anında geçerli miktar: t'den ÖNCEKİ son pozisyon kaydı (aynı anda dengeleme ödemeden sonra sayılır)."""
        q = 0.0
        for ts, snap in self.state["qty_history"]:
            if ts < t_ms:
                q = snap.get(sym, 0.0)
            else:
                break
        return q

    def _push_qty_history(self, now_ms: int):
        h = self.state["qty_history"]
        h.append([now_ms, {s: p["qty"] for s, p in self.state["positions"].items()}])
        keep_from = now_ms - 21 * 24 * HOUR_MS
        while len(h) > 2 and h[1][0] < keep_from:
            h.pop(0)

    def accrue_funding(self, now_ms: int, prices: Dict[str, float]) -> float:
        """
        Gerçekleşmiş fonlama ödemelerini, ödeme anında tutulan miktarla uygular.
        Sembol başına son işlenen ödeme zamanı saklanır; Binance kaydı geç yayınlasa bile sonraki adımda yakalanır.
        """
        if not self.state["qty_history"]:
            return 0.0
        slot = now_ms // (10 * 60_000)
        if self.state.get("last_funding_query_slot") == slot:
            return 0.0
        self.state["last_funding_query_slot"] = slot
        seen = self.state["funding_seen_ms"]
        first_ts = self.state["qty_history"][0][0]
        syms = set()
        for _, snap in self.state["qty_history"]:
            syms |= {k for k, v in snap.items() if v}
        total = 0.0
        for s in sorted(syms):
            start = max(seen.get(s, first_ts), first_ts)
            for ev in self.data.funding_history(s, start + 1, now_ms):
                t = ev["time"]
                if t <= start or t > now_ms:
                    continue
                q = self._qty_at(s, t)
                if q:
                    px = prices.get(s) or self.state["positions"].get(s, {}).get("avg_price", 0.0)
                    total += q * px * ev["rate"]
                seen[s] = max(seen.get(s, 0), t)
        self.state["cash"] -= total
        self.state["funding_paid"] += total
        return total

    # ---- dolum ----
    def _fill(self, s: str, dq: float, px: float, now_ms: int, reason: str) -> Dict:
        side = "BUY" if dq > 0 else "SELL"
        fill_px = px * (1 + self.p.slippage_rate) if dq > 0 else px * (1 - self.p.slippage_rate)
        fee = abs(dq) * fill_px * self.p.fee_rate
        self.state["cash"] -= dq * fill_px + fee
        self.state["fees_paid"] += fee
        pos = self.state["positions"].get(s, {"qty": 0.0, "avg_price": fill_px, "opened_ms": now_ms})
        q0, a0 = pos["qty"], pos["avg_price"]
        q1 = q0 + dq
        realized = 0.0
        if q0 == 0 or (q0 > 0) == (dq > 0):            # açma / artırma
            pos["avg_price"] = (abs(q0) * a0 + abs(dq) * fill_px) / abs(q1) if q1 else fill_px
            if q0 == 0:
                pos["opened_ms"] = now_ms
        else:                                            # azaltma / kapatma / yön değiştirme
            closed = min(abs(dq), abs(q0))
            realized = closed * (fill_px - a0) * (1 if q0 > 0 else -1)
            if abs(dq) > abs(q0) + 1e-12:                # yön değişti: kalan kısım yeni girişte
                pos["avg_price"] = fill_px
                pos["opened_ms"] = now_ms
        self.state["realized_pnl"] += realized
        pos["qty"] = q1
        if abs(q1) * fill_px < 1e-6:
            self.state["positions"].pop(s, None)
        else:
            self.state["positions"][s] = pos
        self.state["n_fills"] += 1
        f = {"ts": _fmt(now_ms), "ts_ms": now_ms, "symbol": s, "side": side, "qty": abs(dq), "price": fill_px,
             "notional": abs(dq) * fill_px, "fee": fee, "realized_pnl": realized, "reason": reason}
        self.store.record_fill(f)
        return f

    # ---- yeniden dengeleme ----
    def select_universe(self) -> List[str]:
        """
        Sabit liste (max_universe=0) ya da adaylar arasından son 30 günün ortalama işlem hacmine göre en likit N coin.
        Seçim yalnızca o ana kadarki veriyle yapılır (geleceği bilmeden), yeni listelenen coinler yeterli geçmiş olunca girer.
        """
        if self.p.max_universe <= 0:
            return list(self.p.universe)
        liq = getattr(self.data, "liquidity", None)
        if liq is None:
            return list(self.p.universe)
        scored = []
        for sym in self.p.universe:
            q = liq(sym, self.p.liquidity_lookback_h)
            if q and q > 0:
                scored.append((q, sym))
        scored.sort(reverse=True)
        return [sym for _, sym in scored[: self.p.max_universe]]

    def legs_k(self, n_selected: int) -> int:
        if self.p.k_quantile > 0:
            return max(1, int(round(n_selected * self.p.k_quantile)))
        return self.p.k

    def compute_signal(self, now_ms: int):
        """Hedef ağırlıklar (özsermaye oranı) ve teşhis için fonlama toplamları."""
        closes, fsums = {}, {}
        start = now_ms - self.p.funding_lookback_h * HOUR_MS
        n_bars = max(self.p.vol_lookback_h, self.p.xsmom_lookback_h, self.p.tsmom_lookback_h) + 1
        universe = self.select_universe()
        self.state["active_universe"] = universe
        for s in universe:
            c = self.data.hourly_closes(s, n_bars)
            if len(c) < 24 * 10:
                continue
            closes[s] = c
            fh = self.data.funding_history(s, start + 1, now_ms)
            if fh:
                fsums[s] = sum(e["rate"] for e in fh if start < e["time"] <= now_ms)
        n_univ = len(universe) if self.p.max_universe > 0 else len(self.p.universe)
        k = self.legs_k(len(universe))
        sleeves = tuple(self.p.sleeves)
        if sleeves == ("funding",):
            # Tek faktör (v3.0): araştırmadaki birebir kural
            w = compute_target_weights({s: closes[s] for s in fsums}, fsums, k=k,
                                       vol_lookback_h=self.p.vol_lookback_h, target_vol_ann=self.p.target_vol,
                                       gross_cap=self.p.gross_cap, universe_size=n_univ, scale=1.0)
            self._last_sleeves = {"funding": w}
            self._last_contrib = {"funding": dict(w)}
            return w, fsums
        vols = {s: realized_vol_ann(c, self.p.vol_lookback_h) for s, c in closes.items()}
        vols = {s: v for s, v in vols.items() if v}
        parts: Dict[str, Dict[str, float]] = {}
        if "trend" in sleeves:
            parts["trend"] = tsmom_weights(closes, vols, self.p.tsmom_lookback_h, self.p.target_vol, n_univ)
        if "xsmom" in sleeves:
            parts["xsmom"] = xsmom_weights(closes, vols, k, self.p.xsmom_lookback_h, 24, self.p.target_vol, n_univ)
        if "funding" in sleeves:
            parts["funding"] = funding_weights(fsums, vols, k, self.p.target_vol, n_univ)
        contrib: Dict[str, Dict[str, float]] = {}
        w = combine_sleeves(parts, closes, self.p.portfolio_target_vol, self.p.vol_lookback_h, self.p.gross_cap,
                            details=contrib)
        self._last_sleeves = parts
        self._last_contrib = contrib
        # Panel için ham kol sinyalleri (+1 LONG / -1 SHORT)
        self.state["sleeve_signals"] = {k: {s: (1 if v > 0 else -1) for s, v in d.items() if v}
                                        for k, d in parts.items()}
        return w, fsums

    def _combined_target(self) -> Dict[str, float]:
        hist = self.state.get("tranche_weights") or []
        if not hist:
            return {}
        tot: Dict[str, float] = {}
        for w in hist:
            for s, v in w.items():
                tot[s] = tot.get(s, 0.0) + v
        n = len(hist)
        sc = self.state["scale"]
        out = {s: v / n * sc for s, v in tot.items() if abs(v) > 1e-12}
        gross = sum(abs(v) for v in out.values())
        if gross > self.p.gross_cap > 0:              # risk ölçeklemesinden sonra da kaldıraç tavanı korunur
            out = {s: v * self.p.gross_cap / gross for s, v in out.items()}
        return out

    def apply_risk_level(self, now_ms: int) -> Optional[Dict]:
        """
        Risk seviyesi (portfolio_target_vol) değiştiyse kayıtlı 7 günlük dilimleri yeni seviyeye ölçekler.
        Böylece değişiklik 7 gün beklemeden bir sonraki dengelemede tam olarak uygulanır.
        """
        new = float(self.p.portfolio_target_vol)
        if not self.state.get("tranche_weights"):
            self.state["target_vol_used"] = new       # henüz portföy yok: ölçeklenecek bir şey yok
            return None
        old = float(self.state.get("target_vol_used") or LEGACY_TARGET_VOL)
        if abs(old - new) < 1e-9:
            self.state["target_vol_used"] = new
            return None
        f = new / old
        self.state["tranche_weights"] = [{s: v * f for s, v in w.items()} for w in self.state["tranche_weights"]]
        self.state["tranche_contribs"] = [{k: {s: v * f for s, v in d.items()} for k, d in c.items()}
                                          for c in (self.state.get("tranche_contribs") or [])]
        self.state["target_vol_used"] = new
        change = {"from": old, "to": new, "at": _fmt(now_ms), "factor": round(f, 4)}
        self.state.setdefault("risk_changes", []).append(change)
        self._log(f"🎚️ [Carry] Risk seviyesi %{old * 100:.0f} -> %{new * 100:.0f}: dilimler {f:.2f}x ölçeklendi, "
                  f"bir sonraki dengelemede uygulanacak.")
        if self.notifier is not None and getattr(self.notifier, "has_telegram", False):
            try:
                from agents.v3_telegram import risk_change_message
                self.notifier.send_text_message(risk_change_message(change, self.p, self.snapshot_light()))
            except Exception as tg_err:
                print(f"⚠️ [Carry] Risk bildirimi gönderilemedi: {tg_err}")
        return change

    def snapshot_light(self) -> Dict:
        """Bildirimler için hafif özet (fiyat çekmeden)."""
        nxt = self._last_due(self.data.now_ms()) + (24 * HOUR_MS if self.p.tranches > 1 else WEEK_MS)
        return {"next_rebalance": _fmt(nxt), "n_positions": len(self.state["positions"])}

    def factor_contrib(self) -> Dict[str, Dict[str, float]]:
        """Sembol -> kol -> hedef ağırlık katkısı (dilim ortalaması × risk ölçeği)."""
        hist = self.state.get("tranche_contribs") or []
        if not hist:
            return {}
        out: Dict[str, Dict[str, float]] = {}
        for d in hist:
            for k, ws in d.items():
                for s, v in ws.items():
                    out.setdefault(s, {}).setdefault(k, 0.0)
                    out[s][k] += v
        n, sc = len(hist), self.state["scale"]
        return {s: {k: v / n * sc for k, v in ks.items()} for s, ks in out.items()}

    def rebalance(self, now_ms: int, prices: Dict[str, float], reason: str) -> Dict:
        fsums = None
        if reason != "dusus_kesici":
            w_new, fsums = self.compute_signal(now_ms)
            if not w_new:
                self._log("⚠️ [Carry] Sinyal üretilemedi (veri eksik), yeniden dengeleme ertelendi.")
                return {}
            hist = self.state.setdefault("tranche_weights", [])
            hist.append(w_new)
            del hist[:-max(1, self.p.tranches)]
            ch = self.state.setdefault("tranche_contribs", [])
            ch.append({k: {s: round(v, 6) for s, v in d.items()} for k, d in getattr(self, "_last_contrib", {}).items()})
            del ch[:-max(1, self.p.tranches)]
        w = self._combined_target()
        if not w:
            return {}
        need = sorted(set(w) - set(prices))
        if need:
            prices = {**prices, **self.data.prices(need)}
        eq = self.equity(prices)
        qty = {s: p["qty"] for s, p in self.state["positions"].items()}
        orders = plan_orders(w, qty, prices, eq, self.p.min_trade_usdt)
        fees0 = self.state["fees_paid"]
        turnover = 0.0
        # Önce azaltmalar/kapanışlar, sonra açılışlar (marjin mantığı)
        for s, dq in sorted(orders.items(), key=lambda kv: 0 if abs(qty.get(kv[0], 0) + kv[1]) < abs(qty.get(kv[0], 0)) else 1):
            f = self._fill(s, dq, prices[s], now_ms, reason)
            turnover += f["notional"]
        self.state["last_rebalance_ms"] = now_ms
        self.state["n_rebalances"] += 1
        self._push_qty_history(now_ms)
        self.state["last_targets"] = {s: round(v, 5) for s, v in w.items()}
        if fsums is not None:
            self.state["last_signal"] = {s: round(v * 100, 4) for s, v in sorted(fsums.items(), key=lambda kv: kv[1])}
        row = {"ts": _fmt(now_ms), "ts_ms": now_ms, "equity": self.equity(prices), "n_orders": len(orders),
               "turnover_usdt": turnover, "fees": self.state["fees_paid"] - fees0, "scale": self.state["scale"],
               "reason": reason, "signal": self.state["last_signal"]}
        self.store.record_rebalance(row)
        self._log(f"🔁 [Carry] Yeniden dengeleme ({reason}): {len(orders)} emir, devir ${turnover:,.0f}, özsermaye ${row['equity']:,.2f}")
        if orders and self.notifier is not None and getattr(self.notifier, "has_telegram", False):
            try:
                from agents.v3_telegram import rebalance_message
                after = {s: p["qty"] for s, p in self.state["positions"].items()}
                self.notifier.send_text_message(rebalance_message(row, qty, after, self.equity(prices), self.state))
            except Exception as tg_err:
                print(f"⚠️ [Carry] Dengeleme bildirimi gönderilemedi: {tg_err}")
        return row

    def _last_due(self, now_ms: int) -> int:
        if self.p.tranches > 1:
            d = now_ms - ((now_ms - self.p.rebalance_hour * HOUR_MS) % (24 * HOUR_MS))
            return d
        return last_scheduled_rebalance(now_ms, self.p.rebalance_weekday, self.p.rebalance_hour)

    # ---- ana adım ----
    def step(self) -> Dict:
        with self._lock:
            now_ms = self.data.now_ms()
            syms = sorted(self.state["positions"])
            prices = self.data.prices(syms) if syms else {}
            missing = [s for s in self.state["positions"] if not prices.get(s)]
            if missing:
                self._log(f"⚠️ [Carry] Fiyat yok: {missing}; adım atlandı.")
                return {"skipped": True}
            self.state.setdefault("started_ms", now_ms)
            self.state["last_step_ms"] = now_ms
            self.apply_risk_level(now_ms)
            self.accrue_funding(now_ms, prices)
            eq = self.equity(prices)
            self.state["peak_equity"] = max(self.state["peak_equity"], eq)
            old_scale = self.state["scale"]
            self.state["scale"] = drawdown_scale(eq, self.state["peak_equity"], old_scale,
                                                 self.p.dd_cut, self.p.dd_restore)
            result = {"equity": eq, "rebalanced": False}
            due = self._last_due(now_ms)
            last = self.state.get("last_rebalance_ms")
            reason = None
            if last is None:
                reason = "ilk_kurulum"
            elif due > last:
                reason = "gunluk_dilim" if self.p.tranches > 1 else "haftalik"
            elif self.state["scale"] < old_scale:
                reason = "dusus_kesici"
            if reason:
                row = self.rebalance(now_ms, prices, reason)
                result["rebalanced"] = bool(row)
                eq = self.equity(prices)
            hour = now_ms // HOUR_MS
            if self.state.get("last_snapshot_hour") != hour:
                g, n = self.exposures(prices)
                self.store.record_equity({"ts_ms": hour * HOUR_MS, "ts": _fmt(hour * HOUR_MS), "equity": eq,
                                          "gross_exposure": g, "net_exposure": n,
                                          "n_positions": len(self.state["positions"]), "scale": self.state["scale"],
                                          "fees_paid": self.state["fees_paid"], "funding_paid": self.state["funding_paid"],
                                          "realized_pnl": self.state["realized_pnl"]})
                self.state["last_snapshot_hour"] = hour
            self.store.save(self.state)
            result["equity"] = eq
            return result

    # ---- dashboard ----
    def snapshot(self) -> Dict:
        syms = sorted(self.state["positions"])
        prices = self.data.prices(syms) if syms else {}
        eq = self.equity(prices)
        g, n = self.exposures(prices)
        pos = []
        for s in syms:
            p = self.state["positions"][s]
            px = prices.get(s) or p["avg_price"]
            pos.append({"symbol": s, "side": "LONG" if p["qty"] > 0 else "SHORT", "qty": p["qty"],
                        "avg_price": p["avg_price"], "price": px, "notional": p["qty"] * px,
                        "upnl": p["qty"] * (px - p["avg_price"]), "opened": _fmt(p["opened_ms"])})
        st = self.state
        nxt = self._last_due(self.data.now_ms()) + (24 * HOUR_MS if self.p.tranches > 1 else WEEK_MS)
        return {
            "version": st.get("version"), "capital": st["capital"], "equity": eq,
            "pnl": eq - st["capital"], "pnl_pct": (eq / st["capital"] - 1) * 100 if st["capital"] else 0.0,
            "peak_equity": st["peak_equity"], "drawdown_pct": (eq / st["peak_equity"] - 1) * 100 if st["peak_equity"] else 0.0,
            "scale": st["scale"], "fees_paid": st["fees_paid"], "funding_paid": st["funding_paid"],
            "realized_pnl": st["realized_pnl"], "gross_exposure": g, "net_exposure": n,
            "n_fills": st["n_fills"], "n_rebalances": st["n_rebalances"],
            "last_rebalance": _fmt(st["last_rebalance_ms"]) if st.get("last_rebalance_ms") else None,
            "next_rebalance": _fmt(nxt), "tranches": self.p.tranches,
            "targets": st.get("last_targets", {}), "positions": pos, "last_signal": st.get("last_signal", {}),
            "factor_contrib": {s: {k: round(v, 5) for k, v in d.items()} for s, d in self.factor_contrib().items()},
            "sleeve_signals": st.get("sleeve_signals", {}), "sleeves": list(self.p.sleeves),
            "universe": list(st.get("active_universe") or self.p.universe),
            "started": _fmt(st["started_ms"]) if st.get("started_ms") else None,
            "last_step": _fmt(st["last_step_ms"]) if st.get("last_step_ms") else None,
            "server_time": _fmt(self.data.now_ms()),
            "unrealized_pnl": sum(x["upnl"] for x in pos),
            "risk_changes": st.get("risk_changes", [])[-5:],
            "params": {"k": self.p.k, "target_vol": self.p.portfolio_target_vol, "gross_cap": self.p.gross_cap,
                       "dd_cut": self.p.dd_cut, "dd_restore": self.p.dd_restore, "fee_rate": self.p.fee_rate,
                       "slippage_rate": self.p.slippage_rate, "tranches": self.p.tranches},
        }


# --------------------------------------------------------------------------------------
# Canlı veri kaynağı
# --------------------------------------------------------------------------------------
class LiveCarryData:
    def __init__(self, client=None):
        from core.binance_client import BinanceFuturesClient
        self.client = client or BinanceFuturesClient()

    def now_ms(self) -> int:
        from core.timeutil import wall_utc
        return int(wall_utc().timestamp() * 1000)

    def _closed_klines(self, symbol: str, n: int) -> List[Dict]:
        kl = self.client.get_klines(symbol, "1h", limit=min(1500, max(n, 24 * 31) + 2))
        now = self.now_ms()
        return [k for k in kl if k["timestamp"] + HOUR_MS <= now]

    def hourly_closes(self, symbol: str, n: int) -> List[float]:
        return [k["close"] for k in self._closed_klines(symbol, n)][-n:]

    def liquidity(self, symbol: str, lookback_h: int) -> Optional[float]:
        """Son `lookback_h` kapanmış saatin ortalama USDT işlem hacmi (yetersiz geçmişte None)."""
        q = [k.get("quote_volume", 0.0) for k in self._closed_klines(symbol, lookback_h)][-lookback_h:]
        return sum(q) / len(q) if len(q) >= 24 * 10 else None

    def funding_history(self, symbol: str, start_ms: int, end_ms: int) -> List[Dict]:
        return self.client.get_funding_history(symbol, start_ms, end_ms)

    def prices(self, symbols: List[str]) -> Dict[str, float]:
        allp = self.client.get_all_prices()
        return {s: allp[s] for s in symbols if allp.get(s)}


_ENGINE: Optional[CarryEngine] = None


def get_live_engine(notifier=None) -> CarryEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = CarryEngine(LiveCarryData(), SQLiteCarryStore(), notifier=notifier, verbose=True)
    return _ENGINE
