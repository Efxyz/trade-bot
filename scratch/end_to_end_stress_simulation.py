"""
UÇTAN UCA PROJE DENETİMİ, SENTETİK PİYASA SİMÜLASYONU VE STRES TESTİ (DRY-RUN)
==============================================================================
Canlı Binance / Telegram API uç noktalarına ve ana veritabanına (data/trading_bot.db)
KESİNLİKLE dokunmaz. Geçici izole SQLite veritabanı ve sentetik piyasa üreteci
(SyntheticBinanceClient) kullanarak tüm modülleri uçtan uca test eder.
"""
import os
import sys
import time
import math
import json
import sqlite3
import tempfile
import threading
import traceback
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

# Proje kök dizinini sys.path'e ekle
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Canlı ortam değişkenlerini izole et (Telegram/Gemini çağrısı yapılmasın)
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import config

# Geçici izole veritabanı ve grafik dizini oluştur
TEMP_DIR = Path(tempfile.mkdtemp(prefix="tradebot_dryrun_"))
TEMP_DB_PATH = TEMP_DIR / "test_trading_bot.db"
TEMP_CHARTS_DIR = TEMP_DIR / "charts"
TEMP_ADAPTIVE_PATH = TEMP_DIR / "adaptive_hyperparams.json"
TEMP_CHARTS_DIR.mkdir(parents=True, exist_ok=True)

config.DB_PATH = TEMP_DB_PATH
config.CHARTS_DIR = TEMP_CHARTS_DIR

import core.database as db
db.DB_PATH = TEMP_DB_PATH

import core.self_tuning_engine as ste
ste.ADAPTIVE_CONFIG_PATH = TEMP_ADAPTIVE_PATH

from core.advanced_indicators import (
    calculate_linear_regression_channel,
    calculate_volume_profile,
    calculate_camarilla_pivots,
    detect_rsi_divergence as adv_detect_rsi_div,
    calculate_adx,
    calculate_fibonacci_golden_pocket,
    detect_swing_failure_pattern,
    calculate_supertrend,
    calculate_vwap_bands
)
from core.reflection import ReflectorEngine
from agents.scanner_agent import MarketScannerAgent
from agents.ta_agent import TechnicalAnalysisAgent
from agents.risk_agent import RiskOfficerAgent
from agents.quant_simulation_agent import QuantSimulationAgent
from agents.ai_analyst_agent import AIAnalystAgent
from agents.news_agent import NewsAgent
from agents.tracker_agent import CounterfactualTrackerAgent
from agents.pairs_stat_arb_agent import StatisticalArbitrageAgent
from agents.chart_agent import ChartAgent


def generate_synthetic_candles(
    base_price: float = 100.0,
    count: int = 100,
    interval_sec: int = 900,
    pattern: str = "BULLISH_SMC_SETUP"
):
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (count * interval_sec * 1000)
    candles = []
    price = base_price

    for i in range(count):
        ts = start_ms + (i * interval_sec * 1000)
        if pattern == "BULLISH_SMC_SETUP":
            if i < count - 6:
                wave = math.sin(i * 0.25) * (base_price * 0.004)
                drift = (i / count) * (base_price * 0.03)
                o = price
                c = base_price + drift + wave
                h = max(o, c) + (base_price * 0.0025)
                l = min(o, c) - (base_price * 0.0025)
                v = 10000.0
                tbv = 5500.0
            elif i == count - 6:
                o = price
                c = o * 0.996
                h = o * 1.001
                l = c * 0.997
                v = 14000.0
                tbv = 7000.0
            elif i == count - 5:
                o = price
                c = o * 1.009
                h = c * 1.001
                l = o * 0.999
                v = 28000.0
                tbv = 19000.0
            elif i == count - 4:
                o = price
                c = o * 1.006
                l = candles[-2]["high"] * 1.0015
                h = c * 1.002
                v = 32000.0
                tbv = 22000.0
            elif i in (count - 3, count - 2):
                fvg_top = candles[-1]["low"]
                o = price
                c = fvg_top * 1.0005
                h = max(o, c) * 1.002
                l = fvg_top * 0.9992
                v = 26000.0
                tbv = 16500.0
            else:
                o = price
                c = o * 1.001
                h = c * 1.001
                l = o * 0.999
                v = 18000.0
                tbv = 11500.0
        else:
            o = price
            c = price * 1.001
            h = c * 1.002
            l = o * 0.998
            v = 12000.0
            tbv = 6500.0

        price = c
        candles.append({
            "timestamp": ts,
            "open": round(o, 6),
            "high": round(h, 6),
            "low": round(l, 6),
            "close": round(c, 6),
            "volume": round(v, 2),
            "quote_volume": round(v * c, 2),
            "taker_buy_volume": round(tbv, 2)
        })
    return candles


class SyntheticBinanceClient:
    """Canlı ağa çıkmayan, uç durumları simüle eden sentetik Binance Futures istemcisi."""
    def __init__(self):
        self.mode = "NORMAL"
        self.live_prices = {
            "BTCUSDT": 85000.0,
            "ETHUSDT": 3200.0,
            "SOLUSDT": 180.0,
            "SUIUSDT": 3.40,
            "AVAXUSDT": 35.0,
            "XRPUSDT": 1.10,
            "DOGEUSDT": 0.25,
            "NEARUSDT": 6.50,
        }
        self.call_count = 0

    def get_24hr_tickers(self):
        self.call_count += 1
        if self.mode == "NETWORK_ERROR":
            return {}
        return {
            sym: {
                "symbol": sym,
                "lastPrice": px,
                "priceChangePercent": 4.5 if sym != "BTCUSDT" else 1.5,
                "quoteVolume": 85_000_000.0,
                "highPrice": px * 1.04,
                "lowPrice": px * 0.96,
                "count": 150000
            }
            for sym, px in self.live_prices.items()
        }

    def get_klines(self, symbol: str, interval: str = "15m", limit: int = 100):
        self.call_count += 1
        if self.mode == "NETWORK_ERROR":
            return []
        base_px = self.live_prices.get(symbol, 100.0)
        int_sec = 3600 if interval == "1h" else (1800 if interval == "30m" else (14400 if interval == "4h" else 900))
        candles = generate_synthetic_candles(base_price=base_px * 0.96, count=limit, interval_sec=int_sec, pattern="BULLISH_SMC_SETUP")
        self.live_prices[symbol] = candles[-1]["close"]
        return candles

    def get_btc_regime(self):
        if self.mode == "NETWORK_ERROR":
            return {"status": "NEUTRAL", "summary": "Ağ kesintisi fallback", "block_longs": False, "block_all_entries": False}
        return {
            "status": "BULLISH",
            "btc_price": self.live_prices["BTCUSDT"],
            "change_3h_pct": 0.95,
            "range_4h_pct": 1.45,
            "block_longs": False,
            "block_shorts": False,
            "block_all_entries": False,
            "summary": "BTC sağlıklı yükseliş trendinde."
        }

    def get_funding_rate(self, symbol: str):
        if self.mode == "TOXIC_FUNDING":
            return {"lastFundingRate": 0.0025, "markPrice": self.live_prices.get(symbol, 100.0), "indexPrice": self.live_prices.get(symbol, 100.0)}
        return {"lastFundingRate": 0.0001, "markPrice": self.live_prices.get(symbol, 100.0), "indexPrice": self.live_prices.get(symbol, 100.0)}

    def get_book_ticker(self, symbol: str):
        px = self.live_prices.get(symbol, 100.0)
        spread = 0.25 if self.mode == "WIDE_SPREAD" else 0.015
        bid = px * (1.0 - (spread / 200.0))
        ask = px * (1.0 + (spread / 200.0))
        return {
            "bidPrice": round(bid, 6),
            "askPrice": round(ask, 6),
            "bidQty": 500.0,
            "askQty": 500.0,
            "spread_pct": spread
        }

    def get_ticker_price(self, symbol: str):
        return {"symbol": symbol, "price": self.live_prices.get(symbol, 100.0)}

    def get_open_interest_delta(self, symbol: str, period: str = "15m", limit: int = 6):
        return {"oi_change_pct": 1.45, "latest_oi_val": 25_000_000.0}

    def get_all_premium_basis(self):
        return {
            sym: {"mark_price": px, "index_price": px, "basis_pct": 0.04, "funding_rate_pct": 0.01}
            for sym, px in self.live_prices.items()
        }

    def get_order_book_imbalance(self, symbol: str, limit: int = 20):
        return {"bid_notional": 450000.0, "ask_notional": 320000.0, "imbalance_ratio": 1.41, "bid_share_pct": 58.4}


def run_all_stress_tests():
    results = []

    def record(test_name: str, passed: bool, finding_type: str, details: str):
        status_icon = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status_icon} | [{finding_type}] {test_name}\n    ↳ {details}")
        results.append({
            "test_name": test_name,
            "passed": passed,
            "finding_type": finding_type,
            "details": details
        })

    print("=" * 80)
    print("🔬 AŞAMA 4 REGRESYON & STRES DOĞRULAMA PAKETİ BAŞLIYOR (DRY-RUN)")
    print(f"📁 İzole Test Veritabanı: {TEMP_DB_PATH}")
    print("=" * 80)

    db.init_db()
    mock_client = SyntheticBinanceClient()

    # 1. Uçtan Uca Ajan Boru Hattı
    try:
        scanner = MarketScannerAgent(mock_client)
        ta_agent = TechnicalAnalysisAgent()
        risk_agent = RiskOfficerAgent()
        quant_agent = QuantSimulationAgent(default_simulations=2000, win_threshold_pct=40.0)
        ai_agent = AIAnalystAgent()
        chart_agent = ChartAgent(output_dir=TEMP_CHARTS_DIR)
        tracker = CounterfactualTrackerAgent(mock_client, output_dir=TEMP_CHARTS_DIR)

        candidates = scanner.scan_opportunities(limit=5)
        sym = "SOLUSDT"
        kl_15m = mock_client.get_klines(sym, "15m", 100)
        kl_30m = mock_client.get_klines(sym, "30m", 80)
        kl_1h = mock_client.get_klines(sym, "1h", 80)
        kl_4h = mock_client.get_klines(sym, "4h", 60)

        ta_setup, _ = ta_agent.analyze_multi_horizon(sym, kl_15m, kl_30m, kl_1h, allowed_timeframes=["15m", "30m", "1h"])
        if not ta_setup:
            ta_setup, _ = ta_agent.analyze_setup(sym, kl_15m, kl_1h, timeframe="15m")

        ta_agent.check_4h_macro_compass(ta_setup or {"current_price": 180.0, "direction": "LONG", "confluence_score": 78}, kl_4h)

        synth_setup = ta_setup or {
            "symbol": sym, "direction": "LONG", "timeframe": "15m", "trade_horizon": "Kısa Vade (15m)",
            "leverage": 10, "risk_grade": "Grade A", "confluence_score": 78,
            "current_price": 180.0, "entry_min": 179.9, "entry_max": 180.1, "actual_entry_price": 180.0,
            "entry_limit_2": 179.3, "stop_loss": 178.2, "take_profit_1": 183.6, "take_profit_2": 185.76,
            "risk_reward": 2.0, "sl_pct": 1.0, "tp1_pct": 2.0, "tp2_pct": 3.2,
            "ta_reasons": "Test SMC Kurulumu", "indicators": {"rsi": [55.0], "vwap": [179.5]}
        }

        news_data = {"verdict": "POZİTİF", "summary": "Sentetik test akışı", "is_vetoed": False, "pos_multiplier": 1.0, "funding_rate_pct": 0.01}
        ticker_info = mock_client.get_24hr_tickers()[sym]
        btc_reg = mock_client.get_btc_regime()
        funding_info = mock_client.get_funding_rate(sym)
        book_info = mock_client.get_book_ticker(sym)

        is_app, risk_rep = risk_agent.evaluate(
            synth_setup, news_data, ticker_info, btc_reg,
            funding_data=funding_info, book_ticker=book_info,
            active_signals=[], current_equity=1000.0, client=mock_client
        )
        q_res = quant_agent.simulate_setup(sym, synth_setup, kl_15m, num_simulations=2000, horizon_bars=24)
        ai_res = ai_agent.evaluate_setup(synth_setup, risk_rep, news_data, btc_reg, ticker_info, funding_info, quant_sim=q_res)
        chart_path = chart_agent.generate_chart(synth_setup, kl_15m, suffix="dryrun")

        sig_id = db.save_signal({
            **synth_setup,
            "allocated_margin_usdt": risk_rep["allocated_margin_usdt"],
            "risk_usd": risk_rep["risk_usd"],
            "news_summary": news_data["summary"],
            "chart_entry_png": chart_path,
            "debate_json": ai_res.get("debate_data", {})
        })

        record(
            "Uçtan Uca Ajan Boru Hattı (Scanner -> TA -> Risk -> Quant -> AI -> DB -> Chart)",
            bool(candidates and is_app and sig_id > 0 and os.path.exists(chart_path)),
            "PIPELINE",
            f"Sinyal #{sig_id} kaydedildi | Marjin: ${risk_rep['allocated_margin_usdt']} | MC Win: %{q_res['win_probability_pct']} | Komite: {ai_res['ai_confidence']}/10"
        )
    except Exception as e:
        record("Uçtan Uca Ajan Boru Hattı", False, "PIPELINE_EXCEPTION", f"{e}\n{traceback.format_exc()}")

    # 2. Merdiven Kâr Kilidi vs TP1 Break-Even Çakışması
    try:
        sig_id_t2 = db.save_signal({
            "symbol": "ETHUSDT", "direction": "LONG", "timeframe": "15m", "trade_horizon": "Kısa Vade (15m)",
            "leverage": 10, "entry_min": 100.0, "entry_max": 100.0, "actual_entry_price": 100.0,
            "stop_loss": 99.0, "take_profit_1": 102.0, "take_profit_2": 103.5,
            "risk_reward": 2.0, "risk_grade": "Grade A", "allocated_margin_usdt": 200.0, "risk_usd": 20.0
        })

        tracker = CounterfactualTrackerAgent(mock_client, output_dir=TEMP_CHARTS_DIR)
        with patch("core.binance_streamer.get_live_price", return_value=101.70):
            mock_client.live_prices["ETHUSDT"] = 101.70
            tracker.update_tracked_trades()

        sigs_after_step4 = [s for s in db.get_active_and_pending_signals() if s["id"] == sig_id_t2]
        sl_after_step4 = sigs_after_step4[0]["stop_loss"]

        with patch("core.binance_streamer.get_live_price", return_value=102.05):
            mock_client.live_prices["ETHUSDT"] = 102.05
            tracker.update_tracked_trades()

        sigs_after_tp1 = [s for s in db.get_active_and_pending_signals() if s["id"] == sig_id_t2]
        sl_after_tp1 = sigs_after_tp1[0]["stop_loss"]

        sl_preserved = sl_after_tp1 >= sl_after_step4
        record(
            "Merdiven Kâr Kilidi vs TP1 Break-Even Çakışması (Stop Koruması Testi)",
            sl_preserved,
            "LOGIC_FIX",
            f"Basamak 4 sonrası kilitli SL={sl_after_step4}, TP1 (102.05) vurulunca SL={sl_after_tp1} olarak korundu (geriye gevşeme yok)."
        )
    except Exception as e:
        record("Merdiven Kâr Kilidi vs TP1 Testi", False, "EXCEPTION", str(e))

    # 3. Ani Fiyat Sıçramasında (Flash Pump) TP1 + TP2 Aynı Anda Aşılınca Kapanış
    try:
        sig_id_t3 = db.save_signal({
            "symbol": "AVAXUSDT", "direction": "LONG", "timeframe": "15m", "trade_horizon": "Kısa Vade (15m)",
            "leverage": 10, "entry_min": 100.0, "entry_max": 100.0, "actual_entry_price": 100.0,
            "stop_loss": 99.0, "take_profit_1": 102.0, "take_profit_2": 103.2,
            "risk_reward": 2.0, "risk_grade": "Grade A", "allocated_margin_usdt": 200.0, "risk_usd": 20.0
        })

        with patch("core.binance_streamer.get_live_price", return_value=104.50):
            mock_client.live_prices["AVAXUSDT"] = 104.50
            tracker.update_tracked_trades()

        all_sigs_t3 = [s for s in db.get_all_signals(limit=20) if s["id"] == sig_id_t3]
        st_t3 = all_sigs_t3[0]["status"]
        record(
            "Ani Fiyat Sıçramasında (Flash Pump) TP1 + TP2 Aynı Anda Aşılınca Kapanış Testi",
            st_t3 == "HIT_TP2_RUNNER",
            "LOGIC_FIX",
            f"Fiyat 104.50 (> TP1=102.0 ve TP2=103.2) olduğunda tek döngüde TP1 %50 realize edilip kalan %50 '{st_t3}' olarak kapatıldı."
        )
    except Exception as e:
        record("Ani Fiyat Sıçraması TP1+TP2 Testi", False, "EXCEPTION", str(e))

    # 4. Kısmi Kâr Almış Pozisyonun 'Zarardakileri Kapat' Filtresi
    try:
        db.close_all_active_signals_db(mock_client)
        sig_id_t4 = db.save_signal({
            "symbol": "SUIUSDT", "direction": "LONG", "timeframe": "15m", "trade_horizon": "Kısa Vade (15m)",
            "leverage": 10, "entry_min": 100.0, "entry_max": 100.0, "actual_entry_price": 100.0,
            "stop_loss": 99.0, "take_profit_1": 102.0, "take_profit_2": 103.5,
            "risk_reward": 2.0, "risk_grade": "Grade A", "allocated_margin_usdt": 200.0, "risk_usd": 20.0
        })
        with patch("core.binance_streamer.get_live_price", return_value=100.60):
            mock_client.live_prices["SUIUSDT"] = 100.60
            tracker.update_tracked_trades()

        with patch("core.binance_streamer.get_live_price", return_value=100.00):
            mock_client.live_prices["SUIUSDT"] = 100.00
            res_loss_close = db.close_positions_by_outcome_db("loss", client=mock_client)

        closed_ids = [c["id"] for c in res_loss_close.get("closed", [])]
        not_wrongly_closed = sig_id_t4 not in closed_ids
        still_active = any(s["id"] == sig_id_t4 for s in db.get_active_and_pending_signals())
        record(
            "Kısmi Kâr (Partial TP) Almış Pozisyonun 'Zarardakileri Kapat' Filtresi Testi",
            not_wrongly_closed and still_active,
            "LOGIC_FIX",
            f"Basamak 1'de realize kâr almış toplamda kârlı pozisyon 'loss' grubu kapatmasında korunup açık kaldı (kapatılan={closed_ids})."
        )
    except Exception as e:
        record("Kısmi Kâr Grup Kapatma Testi", False, "EXCEPTION", str(e))

    # 5. NewsAgent DB Hatası Yakalama
    try:
        na = NewsAgent()
        with patch.object(na, "fetch_coin_specific_news", return_value=[{"title": "SOL partnership announcement", "source": "CoinDesk", "link": "", "date": ""}]):
            with patch("core.database.save_coin_news_investigation_db", side_effect=sqlite3.OperationalError("database is locked")):
                res_na = na.investigate_coin_news("SOLUSDT", "LONG")
        record("NewsAgent DB Hatası Yakalama Testi", bool(res_na and res_na.get("symbol") == "SOLUSDT"), "ERROR_HANDLING", "DB kilitlenme hatasında NameError fırlatılmadı, güvenli analiz sonucu döndü.")
    except Exception as e:
        record("NewsAgent DB Hatası Yakalama Testi", False, "EXCEPTION", str(e))

    # 6. QuantSimulationAgent Sıfır/NaN Mum Fiyatı Dayanıklılık Testi
    try:
        q_agent = QuantSimulationAgent(default_simulations=1000)
        bad_candles = generate_synthetic_candles(100.0, 30)
        bad_candles[10]["close"] = 0.0
        bad_candles[11]["close"] = float("nan")
        q_bad = q_agent.simulate_setup(
            "SOLUSDT",
            {"current_price": 100.0, "direction": "LONG", "take_profit_1": 102.0, "stop_loss": 99.0, "sl_pct": 1.0, "tp1_pct": 2.0},
            bad_candles
        )
        all_finite = math.isfinite(q_bad.get("historical_volatility", float("nan"))) and all(
            math.isfinite(x) for x in q_bad.get("sample_paths", {}).get("median", [])
        )
        record(
            "QuantSimulationAgent Sıfır/NaN Mum Fiyatı Dayanıklılık Testi",
            all_finite,
            "DATA_VALIDATION",
            f"0.0 ve NaN mum değerleri filtrelendi -> historical_volatility={q_bad.get('historical_volatility')}, sample_median={q_bad.get('sample_paths', {}).get('median', [])[:3]}"
        )
    except Exception as e:
        record("QuantSimulationAgent Sıfır/NaN Mum Testi", False, "CRASH", str(e))

    # 7. Veritabanı Zaman Damgası (UTC vs TSİ) ve Günlük Arşiv Kayması
    try:
        with db.get_db_connection() as conn:
            conn.execute("DELETE FROM signals")
            conn.execute("DELETE FROM daily_pnl_archive")
            conn.commit()

        test_sig_id = db.save_signal({
            "symbol": "BTCUSDT", "direction": "LONG", "leverage": 10,
            "entry_min": 80000.0, "entry_max": 80000.0, "actual_entry_price": 80000.0,
            "stop_loss": 79000.0, "take_profit_1": 82000.0, "take_profit_2": 83000.0,
            "risk_reward": 2.0, "risk_grade": "Grade A", "allocated_margin_usdt": 200.0, "risk_usd": 20.0
        })
        db.update_signal_status(test_sig_id, {
            "status": "HIT_TP",
            "closed_at": "2026-11-18 22:30:00",
            "exit_price": 82000.0,
            "simulated_pnl_pct": 19.0,
            "gross_pnl_pct": 20.0,
            "fee_pct": 1.0
        })
        db.check_and_auto_archive_daily_pnl()
        archives = db.get_daily_pnl_archive_db()
        archived_dates = [a["date_str"] for a in archives]
        ok_date = ("2026-11-18" in archived_dates) and ("2026-11-19" not in archived_dates)
        record(
            "Veritabanı Zaman Damgası (UTC vs TSİ) ve Günlük Arşiv Kayması Testi",
            ok_date,
            "TIMESTAMP_SYNC",
            f"2026-11-18 22:30:00 kapanışı doğru gün olan {archived_dates} içine arşivlendi."
        )
    except Exception as e:
        record("Veritabanı Zaman Damgası Testi", False, "EXCEPTION", str(e))

    # 8. SelfTuningEngine Kademeli Confluence Gevşetme
    try:
        with open(TEMP_ADAPTIVE_PATH, "w", encoding="utf-8") as f:
            json.dump({"schema_version": 2, "min_confluence_score": 72}, f)

        for i in range(6):
            sid = db.save_signal({
                "symbol": f"COIN{i}USDT", "direction": "LONG", "leverage": 10,
                "entry_min": 10.0, "entry_max": 10.0, "actual_entry_price": 10.0,
                "stop_loss": 9.9, "take_profit_1": 10.2, "take_profit_2": 10.3,
                "risk_reward": 2.0, "risk_grade": "Grade A", "allocated_margin_usdt": 100.0, "risk_usd": 10.0
            })
            db.update_signal_status(sid, {
                "status": "HIT_TP", "closed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "exit_price": 10.2, "simulated_pnl_pct": 15.0, "gross_pnl_pct": 16.0, "fee_pct": 1.0
            })

        tune_res = ste.SelfTuningEngine.run_autonomous_training_cycle(min_trades_required=5, auto_commit=True)
        new_score = tune_res["tuned_params"]["min_confluence_score"]
        record(
            "SelfTuningEngine Kademeli Confluence Gevşetme Testi (72 -> 71)",
            new_score == 71,
            "LOGIC_FIX",
            f"Confluence skoru 72'den tek adımda {new_score} seviyesine kademeli gevşetildi."
        )
    except Exception as e:
        record("SelfTuningEngine Confluence Testi", False, "EXCEPTION", str(e))

    # 9. Eşzamanlı Tracker Race Condition Testi
    try:
        with db.get_db_connection() as conn:
            conn.execute("DELETE FROM signals")
            conn.execute("DELETE FROM trade_reflections")
            conn.commit()

        db.save_signal({
            "symbol": "XRPUSDT", "direction": "LONG", "leverage": 10,
            "entry_min": 1.0, "entry_max": 1.0, "actual_entry_price": 1.0,
            "stop_loss": 0.99, "take_profit_1": 1.02, "take_profit_2": 1.03,
            "risk_reward": 2.0, "risk_grade": "Grade A", "allocated_margin_usdt": 100.0, "risk_usd": 10.0
        })

        mock_client.live_prices["XRPUSDT"] = 0.98
        barrier = threading.Barrier(2)
        resolved_counts = []

        def worker_track():
            barrier.wait()
            with patch("core.binance_streamer.get_live_price", return_value=0.98):
                res = tracker.update_tracked_trades()
                resolved_counts.append(len(res))

        t1 = threading.Thread(target=worker_track)
        t2 = threading.Thread(target=worker_track)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        refls = db.get_recent_reflections_db(limit=10, symbol="XRPUSDT")
        single_closed = (sum(resolved_counts) == 1) and (len(refls) == 1)
        record(
            "Eşzamanlı Tracker / Orchestrator Race Condition Testi (2 Thread)",
            single_closed,
            "CONCURRENCY_FIX",
            f"2 eşzamanlı thread çalıştığında pozisyon tam {sum(resolved_counts)} kez kapatıldı ve {len(refls)} reflection kaydı oluşturuldu."
        )
    except Exception as e:
        record("Eşzamanlı Tracker Race Condition Testi", False, "EXCEPTION", str(e))

    # 10. Stres Senaryoları: Geniş Spread + Zehirli Fonlama + Ağ Kopması
    try:
        mock_client.mode = "WIDE_SPREAD"
        app_spread, _ = risk_agent.evaluate(
            synth_setup, news_data, ticker_info, btc_reg,
            funding_data=mock_client.get_funding_rate("SOLUSDT"),
            book_ticker=mock_client.get_book_ticker("SOLUSDT"),
            active_signals=[], current_equity=1000.0, client=mock_client
        )
        mock_client.mode = "TOXIC_FUNDING"
        app_fund, _ = risk_agent.evaluate(
            synth_setup, news_data, ticker_info, btc_reg,
            funding_data=mock_client.get_funding_rate("SOLUSDT"),
            book_ticker={"bidPrice": 180.0, "askPrice": 180.02, "spread_pct": 0.01},
            active_signals=[], current_equity=1000.0, client=mock_client
        )
        mock_client.mode = "NETWORK_ERROR"
        empty_cands = scanner.scan_opportunities(limit=5)
        fallback_btc = mock_client.get_btc_regime()
        mock_client.mode = "NORMAL"

        stress_ok = (not app_spread) and (not app_fund) and (empty_cands == []) and (fallback_btc["status"] == "NEUTRAL")
        record(
            "Stres Testi: Geniş Spread Vetosu + Zehirli Fonlama Vetosu + Ağ Kesintisi Fallback",
            stress_ok,
            "STRESS_RESILIENCE",
            f"Geniş Spread Onay={app_spread} | Zehirli Fonlama Onay={app_fund} | Ağ Kopması Aday={len(empty_cands)}"
        )
    except Exception as e:
        record("Stres Senaryoları Testi", False, "EXCEPTION", str(e))

    # 11. Dashboard API Regresyon Testi (/api/superfast/scan, /api/audit/live, /api/data, /api/tuning/reports)
    try:
        import dashboard
        test_app = dashboard.app.test_client()
        resp_sf = test_app.post("/api/superfast/scan")
        resp_f = test_app.post("/api/fast/scan")
        resp_data = test_app.get("/api/data")
        resp_reps = test_app.get("/api/tuning/reports")
        resp_audit = test_app.get("/api/audit/live", headers={"X-Admin-Pin": dashboard.ADMIN_PIN})
        audit_json = resp_audit.get_json() or {}
        home_html = test_app.get("/").get_data(as_text=True)
        scan_tabs_ok = (
            "switchScanTab" in home_html
            and "tabScanAll" in home_html
            and "tabScan15" in home_html
            and "tabScan30" in home_html
            and "tabScan1h" in home_html
        )
        dash_ok = (
            resp_sf.status_code == 200
            and resp_f.status_code == 200
            and resp_data.status_code == 200
            and resp_reps.status_code == 200
            and resp_audit.status_code == 200
            and "equities" in audit_json
            and "fast" in audit_json["equities"]
            and scan_tabs_ok
        )
        record(
            "Dashboard Endpoint Regresyon Testi (/api/superfast/scan, /api/audit/live, /api/data & Scan Tabs)",
            dash_ok,
            "API_REGRESSION",
            f"superfast/scan={resp_sf.status_code}, audit/live={resp_audit.status_code}, scan_tabs_ok={scan_tabs_ok}"
        )
    except Exception as e:
        record("Dashboard Endpoint Regresyon Testi", False, "EXCEPTION", str(e))

    # 12. Advanced Indicators Regresyon Testi (core/advanced_indicators.py)
    try:
        ind_candles = generate_synthetic_candles(100.0, 60)
        lr = calculate_linear_regression_channel(ind_candles)
        vp = calculate_volume_profile(ind_candles)
        cam = calculate_camarilla_pivots(ind_candles)
        adx = calculate_adx(ind_candles)
        fib = calculate_fibonacci_golden_pocket(ind_candles)
        sfp = detect_swing_failure_pattern(ind_candles)
        st = calculate_supertrend(ind_candles)
        vb = calculate_vwap_bands(ind_candles)
        r_div = adv_detect_rsi_div(ind_candles, [50.0] * len(ind_candles))
        ind_ok = all([
            "trend" in lr,
            "poc" in vp,
            "r4" in cam,
            "adx" in adx,
            "fib_618" in fib,
            "bullish_sfp" in sfp,
            "trend" in st,
            "vwap" in vb,
            "description" in r_div
        ])
        record(
            "Gelişmiş İndikatör Motoru Regresyon Testi (core/advanced_indicators.py)",
            ind_ok,
            "INDICATORS_REGRESSION",
            f"LR={lr.get('trend')}, POC={vp.get('poc')}, ADX={adx.get('adx')}, ST={st.get('trend')}, VWAP={vb.get('vwap')}"
        )
    except Exception as e:
        record("Gelişmiş İndikatör Motoru Regresyon Testi", False, "EXCEPTION", str(e))

    # 13. ReflectorEngine Tüm Yeni Statüler Testi
    try:
        expected_outcomes = {
            "HIT_TP2_RUNNER": "WIN",
            "TIMEOUT_PROFIT_EXIT": "WIN",
            "RUNNER_BE_EXIT": "BE",
            "EARLY_INVALIDATION_EXIT": "LOSS",
            "MOMENTUM_STAGNATION_EXIT": "TIMEOUT",
            "PAIR_MEAN_REVERSION_EXIT": "PAIR_EXIT",
        }
        actual_outcomes = {}
        for st_name in expected_outcomes:
            r_out = ReflectorEngine.reflect_on_trade({
                "signal_id": 888, "symbol": "SOLUSDT", "direction": "LONG",
                "status": st_name, "pnl_pct": 5.0 if "TP" in st_name or "PROFIT" in st_name else -2.0,
                "leverage": 10, "minutes_open": 25
            })
            actual_outcomes[st_name] = r_out["outcome_type"]
        refl_ok = actual_outcomes == expected_outcomes
        record(
            "ReflectorEngine Yeni Kapanış Statüleri Doğrulama Testi",
            refl_ok,
            "REFLECTION_SYNC",
            f"Çıktılar: {actual_outcomes}"
        )
    except Exception as e:
        record("ReflectorEngine Statü Testi", False, "EXCEPTION", str(e))

    # 14. PairsStatArbAgent & RiskOfficerAgent Timestamp Hizalama Testi
    try:
        c_a = generate_synthetic_candles(100.0, 40)
        c_b = generate_synthetic_candles(50.0, 40)
        # c_b'nin ilk 3 mumunu çıkarıp farklı uzunluk/kaymış indeks oluştur -> timestamp hizalaması devreye girmeli
        c_b_shifted = c_b[3:]
        stat_agent = StatisticalArbitrageAgent()
        sp_res = stat_agent.calculate_pair_spread(c_a, c_b_shifted, lookback=30)
        rho = RiskOfficerAgent._calc_return_correlation(c_a, c_b_shifted, lookback=24)
        align_ok = ("z_score" in sp_res) and (rho >= 0.99)
        record(
            "Timestamp Hizalama Testi (PairsStatArbAgent & RiskOfficerAgent)",
            align_ok,
            "TIMESTAMP_ALIGNMENT",
            f"Kaymış mum dizilerinde timestamp eşleşmesiyle korelasyon={rho}, Z-Score={sp_res.get('z_score')}"
        )
    except Exception as e:
        record("Timestamp Hizalama Testi", False, "EXCEPTION", str(e))

    # 15. close_all_active_signals_db Sıfır Entry & WebSocket Fiyat Koruması Testi
    try:
        z_id = db.save_signal({
            "symbol": "DOGEUSDT", "direction": "LONG", "leverage": 10,
            "entry_min": 0.0, "entry_max": 0.0, "actual_entry_price": 0.0,
            "stop_loss": 0.0, "take_profit_1": 0.0, "take_profit_2": 0.0,
            "risk_reward": 2.0, "risk_grade": "Grade A", "allocated_margin_usdt": 100.0, "risk_usd": 10.0
        })
        with patch("core.binance_streamer.get_live_price", return_value=0.25):
            closed_cnt = db.close_all_active_signals_db(mock_client)

        # Pair Partner kapanışında close_status="PAIR_PARTNER_CLOSED_EXIT" ve init_db() geçmiş veri düzeltmesi
        pair_xrp_id = db.save_signal({
            "symbol": "XRPUSDT", "direction": "SHORT", "leverage": 10,
            "timeframe": "15m", "trade_horizon": "Kısa Vade (15m Pair)",
            "entry_min": 0.97, "entry_max": 0.98, "actual_entry_price": 0.9777,
            "stop_loss": 0.99, "take_profit_1": 0.95, "take_profit_2": 0.94,
            "risk_reward": 1.8, "risk_grade": "Grade A", "allocated_margin_usdt": 64.8, "risk_usd": 8.42,
            "is_pair_trade": 1, "pair_symbol": "DOGEUSDT"
        })
        with patch("core.binance_streamer.get_live_price", return_value=0.9805):
            partner_res = db.close_single_signal_db("XRPUSDT", client=mock_client, close_status="PAIR_PARTNER_CLOSED_EXIT")
        with sqlite3.connect(TEMP_DB_PATH) as p_conn:
            xrp_db_status = p_conn.execute("SELECT status FROM signals WHERE id = ?", (pair_xrp_id,)).fetchone()[0]

        legacy_pair_id = db.save_signal({
            "symbol": "LINKUSDT", "direction": "SHORT", "leverage": 10,
            "entry_min": 12.0, "entry_max": 12.1, "actual_entry_price": 12.05,
            "stop_loss": 12.5, "take_profit_1": 11.5, "take_profit_2": 11.0,
            "risk_reward": 1.8, "risk_grade": "Grade A", "allocated_margin_usdt": 65.0, "risk_usd": 8.0,
            "is_pair_trade": 1, "pair_symbol": "AVAXUSDT"
        })
        db.update_signal_status(legacy_pair_id, {"status": "MANUAL_CLOSE", "closed_at": "2026-11-18 05:13:05"})
        real_manual_id = db.save_signal({
            "symbol": "ADAUSDT", "direction": "LONG", "leverage": 10,
            "entry_min": 0.5, "entry_max": 0.51, "actual_entry_price": 0.505,
            "stop_loss": 0.48, "take_profit_1": 0.54, "take_profit_2": 0.56,
            "risk_reward": 2.0, "risk_grade": "Grade A", "allocated_margin_usdt": 100.0, "risk_usd": 10.0,
            "is_pair_trade": 0
        })
        db.update_signal_status(real_manual_id, {"status": "MANUAL_CLOSE", "closed_at": "2026-11-18 05:13:05"})
        db.init_db()
        with sqlite3.connect(TEMP_DB_PATH) as p_conn:
            migrated_pair_st = p_conn.execute("SELECT status FROM signals WHERE id = ?", (legacy_pair_id,)).fetchone()[0]
            preserved_manual_st = p_conn.execute("SELECT status FROM signals WHERE id = ?", (real_manual_id,)).fetchone()[0]

        pair_close_ok = (
            partner_res is not None
            and partner_res.get("status") == "PAIR_PARTNER_CLOSED_EXIT"
            and xrp_db_status == "PAIR_PARTNER_CLOSED_EXIT"
            and migrated_pair_st == "PAIR_PARTNER_CLOSED_EXIT"
            and preserved_manual_st == "MANUAL_CLOSE"
        )
        record(
            "close_all_active_signals_db & Pair Partner Kapanış Statüsü Testi",
            closed_cnt >= 1 and z_id > 0 and pair_close_ok,
            "ZERO_DIV_FIX",
            f"closed_cnt={closed_cnt}, xrp_status={xrp_db_status}, migrated_pair={migrated_pair_st}, real_manual={preserved_manual_st}"
        )
    except Exception as e:
        record("close_all_active_signals_db Sıfır Entry Testi", False, "EXCEPTION", str(e))

    # 16. Günlük İşlem Kotası Sıfırlama, Kilit Temizliği & /api/reset-quota + UI Buton Testi
    try:
        import dashboard
        loss_sig_id = db.save_signal({
            "symbol": "AVAXUSDT", "direction": "SHORT", "leverage": 10,
            "timeframe": "15m", "trade_horizon": "15m SCALP",
            "entry_min": 25.0, "entry_max": 25.2, "actual_entry_price": 25.1,
            "stop_loss": 26.0, "take_profit_1": 24.0, "take_profit_2": 23.0,
            "risk_reward": 2.0, "risk_grade": "Grade A", "allocated_margin_usdt": 100.0, "risk_usd": 10.0
        })
        db.update_signal_status(loss_sig_id, {
            "status": "HIT_SL",
            "simulated_pnl_pct": -25.0,
            "closed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        db.get_and_update_today_peak_profit(40.0)

        q_sig_id = db.save_signal({
            "symbol": "SOLUSDT", "direction": "LONG", "leverage": 10,
            "timeframe": "15m", "trade_horizon": "15m SCALP",
            "entry_min": 140.0, "entry_max": 141.0, "actual_entry_price": 140.5,
            "stop_loss": 135.0, "take_profit_1": 145.0, "take_profit_2": 150.0,
            "risk_reward": 2.0, "risk_grade": "Grade A", "allocated_margin_usdt": 100.0, "risk_usd": 10.0
        })
        with sqlite3.connect(TEMP_DB_PATH) as q_conn:
            before_rows = q_conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        before_15m = db.get_today_trades_count("15m")
        before_loss = db.get_today_net_dollar_loss()
        before_last_sig = db.get_last_signal_created_at()

        test_app = dashboard.app.test_client()
        home_resp = test_app.get("/")
        home_html = home_resp.get_data(as_text=True)
        ui_buttons_ok = (
            home_resp.status_code == 200
            and "resetDailyQuota()" in home_html
            and 'id="btnResetQuotaTop"' in home_html
            and 'id="btnResetQuotaBar"' in home_html
        )

        unauth_resp = test_app.post("/api/reset-quota")
        auth_resp = test_app.post("/api/reset-quota", headers={"X-Admin-Pin": dashboard.ADMIN_PIN})
        auth_json = auth_resp.get_json() or {}

        with sqlite3.connect(TEMP_DB_PATH) as q_conn:
            after_rows = q_conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
            peak_rows = q_conn.execute("SELECT COUNT(*) FROM system_state WHERE key LIKE 'peak_pnl_%'").fetchone()[0]
        after_tf = db.get_today_trades_count_by_timeframe()
        after_total = db.get_today_trades_count()
        after_loss = db.get_today_net_dollar_loss()
        after_last_sig = db.get_last_signal_created_at()

        reset_ok = (
            q_sig_id > 0
            and before_15m >= 1
            and before_loss > 0
            and before_last_sig is not None
            and ui_buttons_ok
            and unauth_resp.status_code == 401
            and auth_resp.status_code == 200
            and auth_json.get("status") == "reset"
            and auth_json.get("timeline_quotas", {}).get("total") == {"used": 0, "max": config.DAILY_BASE_MAX_TRADES}
            and auth_json.get("timeline_quotas", {}).get("15m") == {"used": 0, "max": config.DAILY_MAX_TRADES_15M}
            and after_rows == before_rows
            and peak_rows == 0
            and after_total == 0
            and after_tf == {"15m": 0, "30m": 0, "1h": 0}
            and after_loss == 0.0
            and after_last_sig is None
        )
        record(
            "Günlük İşlem Kotası Sıfırlama, Kilit Temizliği & /api/reset-quota Testi",
            reset_ok,
            "QUOTA_RESET_ENDPOINT",
            f"before_15m={before_15m}, before_loss=${before_loss}, after_loss=${after_loss}, after_last_sig={after_last_sig}, ui_buttons_ok={ui_buttons_ok}, rows_preserved={after_rows == before_rows}"
        )
    except Exception as e:
        record("Günlük İşlem Kotası Sıfırlama Testi", False, "EXCEPTION", str(e))

    # 17. Stat-Arb (Pair Trade) Kombine Kâr Çıkışı, Tek-Bacak BE Muafiyeti & Günlük 2-Çift Kotası Testi
    try:
        from main import TradingBotOrchestrator
        # Senaryo 16'daki acik SOLUSDT pozisyonunu temizle
        with patch("core.binance_streamer.get_live_price", return_value=141.0):
            db.close_all_active_signals_db(mock_client)

        entered_35m_ago = (datetime.now() - timedelta(minutes=35)).strftime("%Y-%m-%d %H:%M:%S")
        leg_eth_id = db.save_signal({
            "symbol": "ETHUSDT", "direction": "LONG", "leverage": 10,
            "timeframe": "15m", "trade_horizon": "Kısa Vade (15m Pair)",
            "entry_min": 1799.0, "entry_max": 1801.0, "actual_entry_price": 1800.0,
            "stop_loss": 1778.4, "take_profit_1": 1839.6, "take_profit_2": 1863.0,
            "risk_reward": 1.83, "risk_grade": "Grade A (Piyasa-Nötr Pair)",
            "allocated_margin_usdt": 65.0, "risk_usd": 8.45,
            "is_pair_trade": 1, "pair_symbol": "BNBUSDT"
        })
        leg_bnb_id = db.save_signal({
            "symbol": "BNBUSDT", "direction": "SHORT", "leverage": 10,
            "timeframe": "15m", "trade_horizon": "Kısa Vade (15m Pair)",
            "entry_min": 599.5, "entry_max": 600.5, "actual_entry_price": 600.0,
            "stop_loss": 607.2, "take_profit_1": 586.8, "take_profit_2": 579.0,
            "risk_reward": 1.83, "risk_grade": "Grade A (Piyasa-Nötr Pair)",
            "allocated_margin_usdt": 65.0, "risk_usd": 8.45,
            "is_pair_trade": 1, "pair_symbol": "ETHUSDT"
        })
        db.update_signal_status(leg_eth_id, {"entered_at": entered_35m_ago})
        db.update_signal_status(leg_bnb_id, {"entered_at": entered_35m_ago})

        # Durum A: ETH +%0.55 kârda (+$2.92), BNB -%0.35 zararda (-$2.92) -> Kombine $0 -> 30dk Kâr Kilidi ve merdiven DEVREYE GİRMEMELİ
        price_map_a = {"ETHUSDT": 1809.9, "BNBUSDT": 602.1}
        with patch("core.binance_streamer.get_live_price", side_effect=lambda s: price_map_a.get(s)), \
             patch("agents.pairs_stat_arb_agent.StatisticalArbitrageAgent.get_pair_live_zscore", return_value=1.20):
            res_a = tracker.update_tracked_trades()

        with sqlite3.connect(TEMP_DB_PATH) as p_conn:
            row_eth_a = p_conn.execute("SELECT status, stop_loss FROM signals WHERE id = ?", (leg_eth_id,)).fetchone()

        no_premature_lock = (
            len(res_a) == 0
            and row_eth_a[0] == "ACTIVE"
            and abs(float(row_eth_a[1]) - 1778.4) < 1e-4
        )

        # Durum B: ETH 1814.4 (+%0.80 -> net +$4.55), BNB 600.6 (-$1.30) -> Kombine +$3.25 >= $2.28 -> EŞZAMANLI KÂRLI ÇIKIŞ
        price_map_b = {"ETHUSDT": 1814.4, "BNBUSDT": 600.6}
        with patch("core.binance_streamer.get_live_price", side_effect=lambda s: price_map_b.get(s)), \
             patch("agents.pairs_stat_arb_agent.StatisticalArbitrageAgent.get_pair_live_zscore", return_value=1.10):
            res_b = tracker.update_tracked_trades()

        with sqlite3.connect(TEMP_DB_PATH) as p_conn:
            st_eth_b = p_conn.execute("SELECT status, simulated_pnl_pct FROM signals WHERE id = ?", (leg_eth_id,)).fetchone()
            st_bnb_b = p_conn.execute("SELECT status, simulated_pnl_pct FROM signals WHERE id = ?", (leg_bnb_id,)).fetchone()

        combined_exit_ok = (
            len(res_b) >= 1
            and st_eth_b[0] == "PAIR_MEAN_REVERSION_EXIT"
            and st_bnb_b[0] == "PAIR_PARTNER_CLOSED_EXIT"
            and (float(st_eth_b[1]) + float(st_bnb_b[1])) > 0
        )

        # Durum C: Günlük 2-Çift (4 bacak) Pair Kotası Kalkanı testi
        # İkinci çifti (2 bacak daha -> toplam 4 bacak) bugün watermark sonrası oluştur
        wm_now = db.get_quota_reset_watermark_utc()
        for sym_extra, p_extra, d_extra in [("SOLUSDT", "AVAXUSDT", "LONG"), ("AVAXUSDT", "SOLUSDT", "SHORT")]:
            ex_id = db.save_signal({
                "symbol": sym_extra, "direction": d_extra, "leverage": 10,
                "timeframe": "15m", "trade_horizon": "Kısa Vade (15m Pair)",
                "entry_min": 50.0, "entry_max": 50.1, "actual_entry_price": 50.0,
                "stop_loss": 49.0, "take_profit_1": 51.0, "take_profit_2": 52.0,
                "risk_reward": 1.8, "risk_grade": "Grade A", "allocated_margin_usdt": 65.0, "risk_usd": 8.0,
                "is_pair_trade": 1, "pair_symbol": p_extra
            })
            db.update_signal_status(ex_id, {"status": "PAIR_MEAN_REVERSION_EXIT", "created_at": wm_now, "closed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        db.update_signal_status(leg_eth_id, {"created_at": wm_now})
        db.update_signal_status(leg_bnb_id, {"created_at": wm_now})

        orch = TradingBotOrchestrator.__new__(TradingBotOrchestrator)
        orch.client = mock_client
        cap_blocked = (orch._try_open_stat_arb_pair(slots_left=4, allowed_timeframes=["15m", "30m", "1h"]) is False)

        record(
            "Stat-Arb Kombine Kâr Çıkışı, Tek-Bacak BE Muafiyeti & 2-Çift Kotası Testi",
            no_premature_lock and combined_exit_ok and cap_blocked,
            "PAIR_LIFECYCLE_FIX",
            f"no_premature_lock={no_premature_lock}, combined_exit_ok={combined_exit_ok} (eth={st_eth_b}, bnb={st_bnb_b}), cap_blocked={cap_blocked}"
        )
    except Exception as e:
        record("Stat-Arb Kombine Kâr Çıkışı Testi", False, "EXCEPTION", str(e))

    # 18. Gerçek AI (Gemini 2.5 Flash LLM + Vision) Komite, Refleksiyon & /api/ai/* Endpoint Testi
    try:
        import io
        import dashboard
        db.set_gemini_api_key_db("")
        ai_app = dashboard.app.test_client()

        home_html = ai_app.get("/").get_data(as_text=True)
        ui_ai_ok = all(tok in home_html for tok in ("tabAnalyzerBtn", "analyzerContainer", "sendAiChatMessage", "aiChatBox", "saveAiLessonToMemory", "configureGeminiApiKey"))

        st_before = ai_app.get("/api/ai/status").get_json() or {}
        unauth_cfg = ai_app.post("/api/ai/config", json={"api_key": "AIzaSyTestFakeKey12345"})
        auth_cfg = ai_app.post(
            "/api/ai/config",
            headers={"X-Admin-Pin": dashboard.ADMIN_PIN},
            json={"api_key": "AIzaSyTestFakeKey12345"}
        )
        st_after = ai_app.get("/api/ai/status").get_json() or {}

        class _FakeResp:
            def __init__(self, body_dict):
                self._raw = json.dumps(body_dict).encode("utf-8")
            def read(self):
                return self._raw
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        fake_chat_payload = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": "Son işlemlerde #105 ETHUSDT kazandırırken 1h #99 BTCUSDT tepkiye yakalanmış. Açık pozisyon yok; 15m ETHUSDT için $1800 üzeri kalıcılık aranmalı.\n\n📌 Çıkarılan Ders: Direnç altında erken short yerine kapanış teyidi bekle."
                    }]
                }
            }]
        }
        with patch("dashboard.client", mock_client), \
             patch("urllib.request.urlopen", return_value=_FakeResp(fake_chat_payload)):
            chat_resp = ai_app.post("/api/ai/chat", json={
                "message": "Son işlemlerimi değerlendir, ETH 1d mantıklı mı?",
                "history": [{"role": "user", "text": "Merhaba"}],
                "symbol": "ETH",
                "timeframe": "1d"
            })
        chat_json = chat_resp.get_json() or {}

        lesson_unauth = ai_app.post("/api/ai/save-lesson", json={"symbol": "ETHUSDT", "lesson": "Test"})
        lesson_auth = ai_app.post(
            "/api/ai/save-lesson",
            headers={"X-Admin-Pin": dashboard.ADMIN_PIN},
            json={"symbol": "ETHUSDT", "lesson": "Direnç altında erken short yerine kapanış teyidi bekle."}
        )
        lesson_json = lesson_auth.get_json() or {}
        db.set_gemini_api_key_db("")

        ai_ok = (
            ui_ai_ok
            and st_before.get("configured") is False
            and unauth_cfg.status_code == 401
            and auth_cfg.status_code == 200
            and st_after.get("configured") is True
            and st_after.get("masked_key") == "AIza...2345"
            and chat_resp.status_code == 200
            and chat_json.get("status") == "ok"
            and "gemini-" in (chat_json.get("source") or "").lower()
            and "#105" in (chat_json.get("reply") or "")
            and lesson_unauth.status_code == 401
            and lesson_auth.status_code == 200
            and lesson_json.get("status") == "saved"
        )
        record(
            "Gerçek AI Baş Stratejist Çok Turlu Sohbet & Hafıza Kayıt Testi",
            ai_ok,
            "REAL_AI_STRATEGIST_CHAT",
            f"ui_ai_ok={ui_ai_ok}, cfg_mask={st_after.get('masked_key')}, source={chat_json.get('source')}, lesson_saved={lesson_json.get('status')}"
        )
    except Exception as e:
        record("Gerçek AI Endpoint Testi", False, "EXCEPTION", str(e))

    # =========================================================================
    # SENARYO 19: AI POZİSYON KARAR & PORTFÖY UYGUNLUK KAPISI (ENTRY + AÇIK POZİSYON)
    # =========================================================================
    try:
        ai_agent_suit = AIAnalystAgent()
        cand_setup = {
            "symbol": "SOLUSDT",
            "direction": "LONG",
            "timeframe": "15m",
            "current_price": 150.0,
            "stop_loss": 148.5,
            "take_profit_1": 153.0,
            "take_profit_2": 156.0,
            "risk_reward": 2.0,
            "leverage": 10,
            "confluence_score": 82,
        }
        cand_risk = {"allocated_margin_usdt": 120.0, "risk_usd": 12.0, "leverage": 10}

        # 1) Aynı coin zaten açıksa REJECT
        dup_res = ai_agent_suit.evaluate_position_suitability(
            cand_setup, cand_risk,
            active_positions=[{"id": 1, "symbol": "SOLUSDT", "direction": "LONG", "allocated_margin_usdt": 100.0}],
            account_equity=1000.0
        )
        # 2) Aynı yönde >=2 pozisyon açıksa REDUCE_SIZE (0.7x)
        crowd_res = ai_agent_suit.evaluate_position_suitability(
            cand_setup, cand_risk,
            active_positions=[
                {"id": 2, "symbol": "BTCUSDT", "direction": "LONG", "allocated_margin_usdt": 100.0},
                {"id": 3, "symbol": "ETHUSDT", "direction": "LONG", "allocated_margin_usdt": 100.0},
            ],
            account_equity=1000.0
        )
        # 3) Açık pozisyon uygunluk tarama endpoint'i ve UI butonu
        rev_resp = dashboard.app.test_client().post("/api/ai/review-positions", json={})
        rev_json = rev_resp.get_json() or {}
        home_suit_html = dashboard.app.test_client().get("/").get_data(as_text=True)

        suit_ok = (
            dup_res.get("suitable") is False
            and dup_res.get("verdict") == "REJECT"
            and crowd_res.get("verdict") == "REDUCE_SIZE"
            and abs(float(crowd_res.get("recommended_margin_multiplier") or 0) - 0.7) < 0.05
            and rev_resp.status_code == 200
            and rev_json.get("status") == "ok"
            and "runOpenPositionsSuitabilityReview" in home_suit_html
        )
        record(
            "AI Pozisyon Karar Alma & Portföy Uygunluk Denetimi",
            suit_ok,
            "AI_POSITION_SUITABILITY",
            f"dup={dup_res.get('verdict')}, crowd={crowd_res.get('verdict')}(x{crowd_res.get('recommended_margin_multiplier')}), review_status={rev_json.get('status')}, msg={rev_json.get('message')}"
        )
    except Exception as e:
        record("AI Pozisyon Uygunluk Testi", False, "EXCEPTION", str(e))

    # =========================================================================
    # SENARYO 20: GEÇMİŞ İŞLEMLERDEN TOPLU EĞİTİM & SABİT PATRON ANAYASASI
    # =========================================================================
    try:
        train_unauth = dashboard.app.test_client().post("/api/ai/train-history", json={"limit": 30})
        train_auth = dashboard.app.test_client().post(
            "/api/ai/train-history",
            headers={"X-Admin-Pin": dashboard.ADMIN_PIN},
            json={"limit": 30}
        )
        train_json = train_auth.get_json() or {}
        past_ctx_with_pinned = ReflectorEngine.get_past_context_for_committee("BTCUSDT", limit=4)
        home_train_html = dashboard.app.test_client().get("/").get_data(as_text=True)

        train_ok = (
            train_unauth.status_code == 401
            and train_auth.status_code == 200
            and train_json.get("status") == "ok"
            and int(train_json.get("trades_analyzed") or 0) >= 1
            and len(train_json.get("rules_learned") or []) >= 1
            and "SABİT PATRON & EĞİTİM KURALLARI" in past_ctx_with_pinned
            and "trainAiFromHistory" in home_train_html
        )
        record(
            "Geçmiş İşlemlerden Toplu AI Eğitimi & Sabit Kurallar Testi",
            train_ok,
            "AI_HISTORICAL_TRAINING",
            f"analyzed={train_json.get('trades_analyzed')}, rules={len(train_json.get('rules_learned') or [])}, pinned_injected={'SABİT PATRON' in past_ctx_with_pinned}"
        )
    except Exception as e:
        record("AI Toplu Eğitim Testi", False, "EXCEPTION", str(e))

    print("\n" + "=" * 80)
    passed_cnt = sum(1 for r in results if r["passed"])
    failed_cnt = sum(1 for r in results if not r["passed"])
    print(f"📊 REGRESYON & STRES ÖZETİ: Toplam {len(results)} Senaryo Koşturuldu -> {passed_cnt} Başarılı | {failed_cnt} Hata")
    print("=" * 80)

    report_file = TEMP_DIR / "stress_test_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"📄 Detaylı JSON Log Kaydedildi: {report_file}")

    if failed_cnt > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_all_stress_tests()
