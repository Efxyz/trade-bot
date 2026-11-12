"""
SÜPER FAST Trading Bot Orchestrator - Saniyelik Mikro-Scalp & Yüksek Frekans (HFT) Motoru
High-frequency, second-level trading engine running alongside Standard and FAST bots with an independent $1000 vault.
"""
import sys
import time
import json
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set

from super_fast_config import (
    SUPER_FAST_PORTFOLIO_EQUITY_USDT,
    SUPER_FAST_MAX_CONCURRENT_TRADES,
    SUPER_FAST_MAX_POSITIONS_PER_DIRECTION,
    SUPER_FAST_LEVERAGE,
    SUPER_FAST_RISK_PER_TRADE_USDT,
    SUPER_FAST_ALLOCATED_MARGIN_PER_TRADE,
    SUPER_FAST_SCAN_INTERVAL_SECONDS,
    SUPER_FAST_COINS_UNIVERSE,
    SUPER_FAST_DAILY_MAX_DRAWDOWN_USDT,
    SUPER_FAST_POST_LOSS_COOLDOWN_MINUTES,
    SUPER_FAST_SIDE_GUARD_ENABLED,
    SUPER_FAST_SIDE_MAX_CONSECUTIVE_LOSSES,
    SUPER_FAST_SIDE_COOLDOWN_MINUTES
)
from core.binance_client import BinanceFuturesClient
from core.binance_streamer import get_live_price, add_stream_symbol
from core.database import (
    save_super_fast_signal,
    get_super_fast_active_and_pending_signals,
    get_super_fast_performance_stats,
    add_super_fast_scanner_log_db,
    check_super_fast_side_stoploss_guard
)
from agents.super_fast_ta_agent import SuperFastTechnicalAnalysisAgent
from agents.super_fast_tracker_agent import SuperFastCounterfactualTrackerAgent
from agents.notifier_agent import NotifierAgent

class SuperFastTradingBotOrchestrator:
    def __init__(self):
        print("⚡⚡ [SÜPER FAST Motoru Başlatılıyor] Saniyelik HFT Scalping Çoklu-Ajan Sistemi ($1000 Bağımsız Kasa)...")
        self.client = BinanceFuturesClient()
        self.ta_agent = SuperFastTechnicalAnalysisAgent()
        self.notifier = NotifierAgent()
        self.tracker = SuperFastCounterfactualTrackerAgent(self.client, notifier=self.notifier)
        self.cooldown_until: Dict[str, float] = {}
        self.last_reported_hour: Optional[str] = None
        self.is_running = False

    def run_cycle(self):
        """Tek bir saniyelik mikro tarama ve işlem açılış döngüsü yürütür."""
        now_ts = time.time()
        active_positions = get_super_fast_active_and_pending_signals() or []
        active_count = len(active_positions)

        # 1. Kasa Kalkanı: Maksimum 20 Eşzamanlı Pozisyon Sınırı
        if active_count >= SUPER_FAST_MAX_CONCURRENT_TRADES:
            return

        # 2. Günlük Devre Kesici (Circuit Breaker) Kontrolü
        stats = get_super_fast_performance_stats() or {}
        today_dollar_gain = float(stats.get("today_dollar_gain") or 0.0)
        if today_dollar_gain <= -SUPER_FAST_DAILY_MAX_DRAWDOWN_USDT:
            add_super_fast_scanner_log_db(
                "CIRCUIT_BREAKER",
                "STOPPED",
                f"Süper FAST Günlük Maksimum Zarar Sınırına (-${SUPER_FAST_DAILY_MAX_DRAWDOWN_USDT}) Ulaşıldı."
            )
            return

        # 2.5. BTC Piyasa Rejimi & Ölü Testere Kalkanı (Sermaye Koruma)
        btc_regime = self.client.get_btc_regime()
        if btc_regime.get("block_all_entries", False):
            add_super_fast_scanner_log_db("BTC_KALKANI", "PROTECTED", "BTC Ölü Testere Piyasada (İşlemler Donduruldu)")
            return

        active_symbols = {p["symbol"] for p in active_positions}
        long_count = sum(1 for p in active_positions if p["direction"] == "LONG")
        short_count = sum(1 for p in active_positions if p["direction"] == "SHORT")
        slots_left = SUPER_FAST_MAX_CONCURRENT_TRADES - active_count

        for symbol in SUPER_FAST_COINS_UNIVERSE:
            if slots_left <= 0:
                break

            if symbol in active_symbols:
                continue

            # Zarar soğuma süresi kontrolü
            if now_ts < self.cooldown_until.get(symbol, 0):
                continue

            try:
                add_stream_symbol(symbol)
                # 1m mumlar ve son fiyatlar
                candles_1m = self.client.get_klines(symbol, interval="1m", limit=20)
                if not candles_1m or len(candles_1m) < 10:
                    if self.client.is_rate_limited():
                        add_super_fast_scanner_log_db("ALL", "PROTECTED", "Binance API Dinlenme Modu (Rate-Limit Koruması)")
                        break
                    continue

                # Canlı WebSocket fiyatı ve book ticker
                ws_price = get_live_price(symbol)
                book_ticker = self.client.get_book_ticker(symbol)
                recent_prices = [ws_price] if ws_price else []

                # Teknik Analiz Değerlendirmesi
                setup, reason = self.ta_agent.analyze_super_fast_setup(
                    symbol, recent_prices, candles_1m, book_ticker
                )

                if not setup:
                    continue

                direction = setup["direction"]

                # BTC Yön Kalkanı Denetimi (Ayı/Düşüşte LONG Yasak, Rallide SHORT Yasak)
                if direction == "LONG" and btc_regime.get("block_longs", False):
                    add_super_fast_scanner_log_db(symbol, "BLOCKED", "BTC Düşüş/Ayı Kalkanı (LONG Engellendi)")
                    continue
                if direction == "SHORT" and btc_regime.get("block_shorts", False):
                    add_super_fast_scanner_log_db(symbol, "BLOCKED", "BTC Yükseliş/Ralli Kalkanı (SHORT Engellendi)")
                    continue

                # Yön Kalkanı Denetimi (Max 12 Long veya 12 Short)
                if direction == "LONG" and long_count >= SUPER_FAST_MAX_POSITIONS_PER_DIRECTION:
                    continue
                if direction == "SHORT" and short_count >= SUPER_FAST_MAX_POSITIONS_PER_DIRECTION:
                    continue

                # Seri Zarar Kalkanı Denetimi
                if SUPER_FAST_SIDE_GUARD_ENABLED:
                    is_locked, guard_reason = check_super_fast_side_stoploss_guard(
                        direction,
                        max_consecutive_losses=SUPER_FAST_SIDE_MAX_CONSECUTIVE_LOSSES,
                        cooldown_minutes=SUPER_FAST_SIDE_COOLDOWN_MINUTES
                    )
                    if is_locked:
                        add_super_fast_scanner_log_db(symbol, "BLOCKED", guard_reason)
                        continue

                # Pozisyonu Aç ve Süper FAST Veritabanına Kaydet
                signal_data = {
                    "symbol": symbol,
                    "direction": direction,
                    "leverage": SUPER_FAST_LEVERAGE,
                    "entry_min": setup["entry_min"],
                    "entry_max": setup["entry_max"],
                    "actual_entry_price": setup["current_price"],
                    "stop_loss": setup["stop_loss"],
                    "take_profit_1": setup["take_profit_1"],
                    "take_profit_2": setup["take_profit_2"],
                    "risk_reward": setup["risk_reward"],
                    "risk_grade": setup["risk_grade"],
                    "news_summary": f"⚡⚡ SÜPER FAST Saniyelik ({setup['confluence_score']}/100)",
                    "ta_reasons": setup["ta_reasons"],
                    "allocated_margin_usdt": SUPER_FAST_ALLOCATED_MARGIN_PER_TRADE,
                    "risk_usd": SUPER_FAST_RISK_PER_TRADE_USDT,
                    "super_fast_meta": {"timeframe": "1s", "score": setup["confluence_score"]}
                }

                sig_id = save_super_fast_signal(signal_data)
                active_symbols.add(symbol)
                slots_left -= 1
                if direction == "LONG":
                    long_count += 1
                else:
                    short_count += 1

                add_super_fast_scanner_log_db(
                    symbol,
                    "APPROVED",
                    f"⚡⚡ {SUPER_FAST_LEVERAGE}x {direction} Süper FAST Mikro Scalp Açıldı! (Marjin: ${SUPER_FAST_ALLOCATED_MARGIN_PER_TRADE})",
                    f"TP: +%{setup['tp1_pct']} | SL: -%{setup['sl_pct']}"
                )

            except Exception as e:
                add_super_fast_scanner_log_db(symbol, "ERROR", f"Tarama Hatası: {str(e)[:50]}")
            finally:
                time.sleep(0.08)

    def run_forever(self):
        """Süper FAST Botun 7/24 Kesintisiz Arka Plan Motoru (1sn Takip + 5sn Tarama)."""
        self.is_running = True
        last_scan_time = 0.0

        while self.is_running:
            try:
                # 1. Hızlı Açık Pozisyon Takibi (Her saniye merdiven kârlarını kontrol et)
                resolved = self.tracker.update_open_trades()
                for r in resolved:
                    if r.get("dollar_gain", 0) < 0:
                        self.cooldown_until[r["symbol"]] = time.time() + (SUPER_FAST_POST_LOSS_COOLDOWN_MINUTES * 60)

                # 2. Saniyelik Hızlı Tarama Döngüsü (Her 5 saniyede bir)
                now = time.time()
                if now - last_scan_time >= SUPER_FAST_SCAN_INTERVAL_SECONDS:
                    self.run_cycle()
                    last_scan_time = now

                # 3. Her Saat Başı Otomatik Telegram Raporu (İşlemler, PnL, Toplam Sonuç)
                now_dt = datetime.now(timezone(timedelta(hours=3)))
                current_hour_key = now_dt.strftime("%Y-%m-%d %H")
                if current_hour_key != self.last_reported_hour and now_dt.minute <= 2:
                    try:
                        self.notifier.send_super_fast_hourly_report()
                        self.last_reported_hour = current_hour_key
                    except Exception as rep_err:
                        print(f"⚠️ [Süper FAST Saatlik Rapor Hatası]: {rep_err}")

            except Exception as err:
                print(f"⚠️ [Süper FAST Bot Döngü Hatası]: {err}")

            time.sleep(1.0)

