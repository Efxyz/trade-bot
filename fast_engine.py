"""
FAST Trading Bot Orchestrator - 1-Minute Micro-Scalping Multi-Agent System
High-frequency, high-volume trading engine running alongside the standard bot with an independent $1000 vault.
"""
import sys
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set

from fast_config import (
    FAST_PORTFOLIO_EQUITY_USDT,
    FAST_MAX_CONCURRENT_TRADES,
    FAST_MAX_POSITIONS_PER_DIRECTION,
    FAST_LEVERAGE,
    FAST_RISK_PER_TRADE_USDT,
    FAST_ALLOCATED_MARGIN_PER_TRADE,
    FAST_SCAN_INTERVAL_SECONDS,
    FAST_PRIMARY_TIMEFRAME,
    FAST_CONFIRMATION_TIMEFRAME,
    FAST_COINS_UNIVERSE,
    FAST_CIRCUIT_BREAKER_ENABLED,
    FAST_DAILY_MAX_DRAWDOWN_USDT,
    FAST_MAX_DAILY_TRADES,
    FAST_MAX_DAILY_FEE_USDT,
    FAST_MAX_DAILY_TRADES,
    FAST_MAX_DAILY_FEE_USDT,
    FAST_POST_LOSS_COOLDOWN_MINUTES,
    FAST_BLOCK_DEAD_CHOP,
    FAST_SIDE_GUARD_ENABLED,
    FAST_SIDE_MAX_CONSECUTIVE_LOSSES,
    FAST_SIDE_COOLDOWN_MINUTES
)
from core.binance_client import BinanceFuturesClient
from core.database import (
    save_fast_signal,
    get_fast_active_and_pending_signals,
    get_fast_performance_stats,
    add_fast_scanner_log_db,
    check_fast_side_stoploss_guard
)
from agents.fast_ta_agent import FastTechnicalAnalysisAgent
from agents.fast_tracker_agent import FastCounterfactualTrackerAgent
from agents.notifier_agent import NotifierAgent

class FastTradingBotOrchestrator:
    def __init__(self):
        print("⚡ [FAST Motoru Başlatılıyor] 1-Dakikalık Hızlı Scalping Çoklu-Ajan Sistemi ($1000 Bağımsız Kasa)...")
        self.client = BinanceFuturesClient()
        self.ta_agent = FastTechnicalAnalysisAgent()
        self.notifier = NotifierAgent()
        self.tracker = FastCounterfactualTrackerAgent(self.client, notifier=self.notifier)
        self.cooldown_until: Dict[str, float] = {}
        self.last_reported_hour: Optional[str] = None
        self.is_running = False

    def run_cycle(self):
        """Tek bir 1m hızlı tarama ve işlem açılış döngüsü yürütür."""
        now_ts = time.time()
        active_positions = get_fast_active_and_pending_signals() or []
        active_count = len(active_positions)

        # 1. Kasa Kalkanı: Maksimum Eşzamanlı Pozisyon Sınırı
        if active_count >= FAST_MAX_CONCURRENT_TRADES:
            return

        # 2. Günlük Devre Kesici & Sert İşlem/Komisyon Kotası (Anti-Overtrading Guard)
        fast_stats = get_fast_performance_stats() or {}
        today_trades = int(fast_stats.get("today_trades") or 0)
        today_dollar_gain = float(fast_stats.get("today_dollar_gain") or 0.0)
        today_fee_pct = float(fast_stats.get("today_fee_pct") or 0.0)
        today_fee_usd = (today_fee_pct / 100.0) * FAST_ALLOCATED_MARGIN_PER_TRADE

        # A) Sert Günlük İşlem Kotası (Maks 15 İşlem)
        if today_trades >= FAST_MAX_DAILY_TRADES:
            add_fast_scanner_log_db("ALL", "BLOCKED", f"⚡ FAST Günlük İşlem Kotası ({today_trades}/{FAST_MAX_DAILY_TRADES}) Doldu. Komisyon Koruma Kilidi Aktif.")
            return

        # B) Günlük Komisyon Tavanı (Maks $15)
        if today_fee_usd >= FAST_MAX_DAILY_FEE_USDT:
            add_fast_scanner_log_db("ALL", "BLOCKED", f"⚡ FAST Günlük Komisyon Tavanı (${today_fee_usd:.2f} >= ${FAST_MAX_DAILY_FEE_USDT}) Aşıldı. Komisyon Kilidi.")
            return

        # C) Günlük Zarar Limiti Devre Kesici
        if FAST_CIRCUIT_BREAKER_ENABLED and today_dollar_gain <= -FAST_DAILY_MAX_DRAWDOWN_USDT:
            add_fast_scanner_log_db("ALL", "BLOCKED", f"FAST Günlük Devre Kesici (-${abs(today_dollar_gain):.2f} >= -${FAST_DAILY_MAX_DRAWDOWN_USDT})")
            return

        # 2.5. BTC Piyasa Rejimi & Ölü Testere Kalkanı (Sermaye Koruma)
        btc_regime = self.client.get_btc_regime()
        if FAST_BLOCK_DEAD_CHOP and btc_regime.get("block_all_entries", False):
            add_fast_scanner_log_db("BTC_KALKANI", "PROTECTED", "BTC Ölü Testere Piyasada (İşlemler Donduruldu)")
            return

        active_symbols = {p["symbol"] for p in active_positions}
        long_count = sum(1 for p in active_positions if p["direction"] == "LONG")
        short_count = sum(1 for p in active_positions if p["direction"] == "SHORT")

        slots_left = FAST_MAX_CONCURRENT_TRADES - active_count

        for symbol in FAST_COINS_UNIVERSE:
            if slots_left <= 0:
                break
            if symbol in active_symbols:
                continue
            if now_ts < self.cooldown_until.get(symbol, 0):
                continue

            try:
                # 1m Hızlı ve 5m Teyit Mumlarını Çek
                candles_1m = self.client.get_klines(symbol, interval=FAST_PRIMARY_TIMEFRAME, limit=45)
                if len(candles_1m) < 25:
                    if self.client.is_rate_limited():
                        add_fast_scanner_log_db("ALL", "PROTECTED", "Binance API Dinlenme Modu (Rate-Limit Koruması)")
                        break
                    add_fast_scanner_log_db(symbol, "REJECTED", "Yetersiz 1m veri")
                    continue

                candles_5m = self.client.get_klines(symbol, interval=FAST_CONFIRMATION_TIMEFRAME, limit=20)

                # 1m Hızlı TA Analizi
                setup, reason = self.ta_agent.analyze_fast_setup(symbol, candles_1m, candles_5m)
                if not setup:
                    add_fast_scanner_log_db(symbol, "REJECTED", reason)
                    continue

                direction = setup["direction"]

                # BTC Yön Kalkanı Denetimi (Ayı/Düşüşte LONG Yasak, Rallide SHORT Yasak)
                if direction == "LONG" and btc_regime.get("block_longs", False):
                    add_fast_scanner_log_db(symbol, "BLOCKED", "BTC Düşüş/Ayı Kalkanı (LONG Engellendi)")
                    continue
                if direction == "SHORT" and btc_regime.get("block_shorts", False):
                    add_fast_scanner_log_db(symbol, "BLOCKED", "BTC Yükseliş/Ralli Kalkanı (SHORT Engellendi)")
                    continue

                # Yön Kalkanı Denetimi (Max 6 Long veya 6 Short)
                if direction == "LONG" and long_count >= FAST_MAX_POSITIONS_PER_DIRECTION:
                    add_fast_scanner_log_db(symbol, "BLOCKED", f"Maksimum LONG Sınırı ({FAST_MAX_POSITIONS_PER_DIRECTION}) Dolu")
                    continue
                if direction == "SHORT" and short_count >= FAST_MAX_POSITIONS_PER_DIRECTION:
                    add_fast_scanner_log_db(symbol, "BLOCKED", f"Maksimum SHORT Sınırı ({FAST_MAX_POSITIONS_PER_DIRECTION}) Dolu")
                    continue

                # Freqtrade FAST Yön Bazlı Seri Zarar Kalkanı
                if FAST_SIDE_GUARD_ENABLED:
                    is_locked, guard_reason = check_fast_side_stoploss_guard(
                        direction,
                        max_consecutive_losses=FAST_SIDE_MAX_CONSECUTIVE_LOSSES,
                        cooldown_minutes=FAST_SIDE_COOLDOWN_MINUTES
                    )
                    if is_locked:
                        add_fast_scanner_log_db(symbol, "BLOCKED", guard_reason)
                        continue

                # Pozisyonu Aç ve FAST Veritabanına Kaydet
                signal_data = {
                    "symbol": symbol,
                    "direction": direction,
                    "leverage": FAST_LEVERAGE,
                    "entry_min": setup["entry_min"],
                    "entry_max": setup["entry_max"],
                    "actual_entry_price": setup["current_price"],
                    "stop_loss": setup["stop_loss"],
                    "take_profit_1": setup["take_profit_1"],
                    "take_profit_2": setup["take_profit_2"],
                    "risk_reward": setup["risk_reward"],
                    "risk_grade": setup["risk_grade"],
                    "news_summary": f"⚡ FAST 1m Scalp ({setup['confluence_score']}/100)",
                    "ta_reasons": setup["ta_reasons"],
                    "allocated_margin_usdt": FAST_ALLOCATED_MARGIN_PER_TRADE,
                    "risk_usd": FAST_RISK_PER_TRADE_USDT,
                    "fast_meta": {"timeframe": "1m", "score": setup["confluence_score"]}
                }

                sig_id = save_fast_signal(signal_data)
                active_symbols.add(symbol)
                slots_left -= 1
                if direction == "LONG":
                    long_count += 1
                else:
                    short_count += 1

                add_fast_scanner_log_db(
                    symbol,
                    "APPROVED",
                    f"⚡ {FAST_LEVERAGE}x {direction} FAST Scalp Açıldı! (Marjin: ${FAST_ALLOCATED_MARGIN_PER_TRADE})",
                    f"TP: +%{setup['tp1_pct']} | SL: -%{setup['sl_pct']}"
                )

            except Exception as e:
                add_fast_scanner_log_db(symbol, "ERROR", f"Tarama Hatası: {str(e)[:50]}")
            finally:
                time.sleep(0.10)

    def run_forever(self):
        """FAST Botun 7/24 Kesintisiz Arka Plan Motoru (2sn Takip + 20sn Tarama)."""
        self.is_running = True
        last_scan_time = 0.0

        while self.is_running:
            try:
                # 1. Hızlı Açık Pozisyon Takibi (Her 2-3 saniyede bir merdiven kârlarını kontrol et)
                resolved = self.tracker.update_open_trades()
                for r in resolved:
                    # Kapanan zararlı pariteye kısa mola ata
                    if r.get("dollar_gain", 0) < 0:
                        self.cooldown_until[r["symbol"]] = time.time() + (FAST_POST_LOSS_COOLDOWN_MINUTES * 60)

                # 2. Hızlı Tarama Döngüsü (Her 20 saniyede bir)
                now = time.time()
                if now - last_scan_time >= FAST_SCAN_INTERVAL_SECONDS:
                    self.run_cycle()
                    last_scan_time = now

                # 3. Her Saat Başı Telegram Raporu (İşlemler, PnL, Toplam Sonuç)
                now_dt = datetime.now(timezone(timedelta(hours=3)))
                current_hour_key = now_dt.strftime("%Y-%m-%d %H")
                if current_hour_key != self.last_reported_hour and now_dt.minute <= 2:
                    try:
                        self.notifier.send_fast_hourly_report()
                        self.last_reported_hour = current_hour_key
                    except Exception as rep_err:
                        print(f"⚠️ [FAST Saatlik Rapor Hatası]: {rep_err}")

            except Exception as err:
                print(f"⚠️ [FAST Bot Döngü Hatası]: {err}")

            time.sleep(2.0)

