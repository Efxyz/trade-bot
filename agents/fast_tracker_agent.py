"""
FAST Counterfactual Tracker Agent - 1-Minute Micro-Scalp Position & Profit Locking Engine
Tracks open fast positions in real-time, executing fast BE+ locks, TP, SL, and 15m timeout exits.
"""
from typing import Dict, List, Optional
from datetime import datetime, timezone
import time

from fast_config import (
    FAST_LADDER_STEPS,
    FAST_DYNAMIC_CHANNEL_PCT,
    FAST_MAX_HOLD_MINUTES,
    FAST_EARLY_INVALIDATION_ENABLED,
    FAST_EARLY_INVALIDATION_MINUTES,
    FAST_EARLY_INVALIDATION_LOSS_PCT,
    BINANCE_ROUNDTRIP_FEE_PCT
)
from core.database import (
    get_fast_active_and_pending_signals,
    update_fast_signal_status,
    add_fast_scanner_log_db
)
from core.binance_streamer import get_live_price, add_stream_symbol

class FastCounterfactualTrackerAgent:
    def __init__(self, client, notifier=None):
        self.client = client
        self.notifier = notifier

    def update_open_trades(self) -> List[Dict]:
        """Açık FAST işlemlerin fiyatlarını kontrol eder, merdiven kârlarını kilitler ve kapanışları yönetir."""
        active_signals = get_fast_active_and_pending_signals()
        if not active_signals:
            return []

        # Tüm vadeli çiftlerin fiyatlarını tek seferde güvenle çek (REST Fallback)
        cached_tickers = {}
        try:
            cached_tickers = self.client.get_24hr_tickers() or {}
        except Exception:
            pass

        resolved_signals = []
        now = datetime.now()

        for sig in active_signals:
            sig_id = sig["id"]
            symbol = sig["symbol"]
            direction = sig["direction"]
            entry_price = float(sig.get("actual_entry_price") or sig["entry_min"])
            stop_loss = float(sig["stop_loss"])
            tp1 = float(sig["take_profit_1"])
            leverage = int(sig.get("leverage") or 10)
            allocated_margin = float(sig.get("allocated_margin_usdt") or 75.0)

            # 1. Anlık Fiyat (Önce WebSocket, yoksa 24hr ticker, yoksa tekil REST API)
            live_price = None
            try:
                add_stream_symbol(symbol)
                live_price = get_live_price(symbol)
            except Exception:
                live_price = None

            if not live_price or live_price <= 0:
                ticker_data = cached_tickers.get(symbol, {})
                live_price = ticker_data.get("lastPrice")

            if not live_price or live_price <= 0:
                try:
                    price_info = self.client.get_ticker_price(symbol)
                    if price_info and "price" in price_info:
                        live_price = float(price_info["price"])
                except Exception:
                    pass

            if not live_price or live_price <= 0:
                continue

            highest_price = max(float(sig.get("highest_price") or entry_price), live_price)
            lowest_price = min(float(sig.get("lowest_price") or entry_price), live_price)

            entered_at_str = sig.get("entered_at") or sig.get("created_at")
            minutes_open = 0
            if entered_at_str:
                try:
                    entered_dt = datetime.strptime(str(entered_at_str)[:19], "%Y-%m-%d %H:%M:%S")
                    minutes_open = (now - entered_dt).total_seconds() / 60.0
                except Exception:
                    minutes_open = 0

            ladder_step = int(sig.get("ladder_step") or 0)
            trailing_stop = float(sig.get("trailing_stop") or stop_loss)
            current_sl = max(trailing_stop, stop_loss) if direction == "LONG" else min(trailing_stop, stop_loss)
            ladder_name = sig.get("ladder_name") or ""

            # 1. HIZLI MERDİVEN KÂR KİLİTLERİ (FAST STEP-LADDER)
            if direction == "LONG":
                peak_gain_pct = ((highest_price - entry_price) / entry_price) * 100.0
                for step in FAST_LADDER_STEPS:
                    if peak_gain_pct >= step["trigger_raw_pct"] and step["step"] > ladder_step:
                        locked_sl = entry_price * (1.0 + step["lock_raw_pct"] / 100.0)
                        if locked_sl > current_sl:
                            current_sl = locked_sl
                            ladder_step = step["step"]
                            ladder_name = step["name"]

                # Dinamik Takip Kanalı
                if peak_gain_pct >= 0.50:
                    ch_sl = highest_price * (1.0 - FAST_DYNAMIC_CHANNEL_PCT / 100.0)
                    if ch_sl > current_sl:
                        current_sl = ch_sl
            else: # SHORT
                peak_gain_pct = ((entry_price - lowest_price) / entry_price) * 100.0
                for step in FAST_LADDER_STEPS:
                    if peak_gain_pct >= step["trigger_raw_pct"] and step["step"] > ladder_step:
                        locked_sl = entry_price * (1.0 - step["lock_raw_pct"] / 100.0)
                        if locked_sl < current_sl:
                            current_sl = locked_sl
                            ladder_step = step["step"]
                            ladder_name = step["name"]

                if peak_gain_pct >= 0.50:
                    ch_sl = lowest_price * (1.0 + FAST_DYNAMIC_CHANNEL_PCT / 100.0)
                    if ch_sl < current_sl:
                        current_sl = ch_sl

            # 2. ÇIKIŞ KONTROLLERİ
            is_closed = False
            exit_price = live_price
            exit_status = ""

            if direction == "LONG":
                if live_price <= current_sl:
                    is_closed = True
                    exit_price = current_sl
                    if ladder_step >= 2:
                        exit_status = f"LADDER_STEP_{ladder_step}_LOCK"
                    elif ladder_step == 1:
                        exit_status = "CLOSED_BE"
                    else:
                        exit_status = "HIT_SL"
                elif live_price >= tp1:
                    is_closed = True
                    exit_price = tp1
                    exit_status = "HIT_TP"
                elif FAST_EARLY_INVALIDATION_ENABLED and ladder_step == 0 and minutes_open >= FAST_EARLY_INVALIDATION_MINUTES:
                    raw_diff = (live_price - entry_price) / entry_price
                    if raw_diff <= -(FAST_EARLY_INVALIDATION_LOSS_PCT / 100.0):
                        is_closed = True
                        exit_price = live_price
                        exit_status = "EARLY_INVALIDATION_EXIT"
                elif minutes_open >= FAST_MAX_HOLD_MINUTES:
                    raw_diff = (live_price - entry_price) / entry_price
                    is_closed = True
                    exit_price = live_price
                    exit_status = "TIMEOUT_PROFIT_EXIT" if raw_diff > 0.001 else "TIMEOUT_EXIT"

            else: # SHORT
                if live_price >= current_sl:
                    is_closed = True
                    exit_price = current_sl
                    if ladder_step >= 2:
                        exit_status = f"LADDER_STEP_{ladder_step}_LOCK"
                    elif ladder_step == 1:
                        exit_status = "CLOSED_BE"
                    else:
                        exit_status = "HIT_SL"
                elif live_price <= tp1:
                    is_closed = True
                    exit_price = tp1
                    exit_status = "HIT_TP"
                elif FAST_EARLY_INVALIDATION_ENABLED and ladder_step == 0 and minutes_open >= FAST_EARLY_INVALIDATION_MINUTES:
                    raw_diff = (entry_price - live_price) / entry_price
                    if raw_diff <= -(FAST_EARLY_INVALIDATION_LOSS_PCT / 100.0):
                        is_closed = True
                        exit_price = live_price
                        exit_status = "EARLY_INVALIDATION_EXIT"
                elif minutes_open >= FAST_MAX_HOLD_MINUTES:
                    raw_diff = (entry_price - live_price) / entry_price
                    is_closed = True
                    exit_price = live_price
                    exit_status = "TIMEOUT_PROFIT_EXIT" if raw_diff > 0.001 else "TIMEOUT_EXIT"

            # 3. VERİTABANI GÜNCELLEMESİ
            if is_closed:
                raw_gain_pct = ((exit_price - entry_price) / entry_price) * 100.0 if direction == "LONG" else ((entry_price - exit_price) / entry_price) * 100.0
                gross_margin = raw_gain_pct * leverage
                fee_pct = BINANCE_ROUNDTRIP_FEE_PCT * leverage
                net_margin = gross_margin - fee_pct

                closed_time = now.strftime("%Y-%m-%d %H:%M:%S")
                update_fast_signal_status(sig_id, {
                    "status": exit_status,
                    "closed_at": closed_time,
                    "exit_price": exit_price,
                    "highest_price": highest_price,
                    "lowest_price": lowest_price,
                    "gross_pnl_pct": round(gross_margin, 2),
                    "fee_pct": round(fee_pct, 2),
                    "simulated_pnl_pct": round(net_margin, 2),
                    "trailing_stop": current_sl,
                    "ladder_step": ladder_step,
                    "ladder_name": ladder_name
                })
                dollar_pnl = round(allocated_margin * (net_margin / 100.0), 2)
                resolved_signals.append({
                    "id": sig_id,
                    "symbol": symbol,
                    "direction": direction,
                    "exit_status": exit_status,
                    "net_pnl_pct": round(net_margin, 2),
                    "dollar_gain": dollar_pnl
                })

                # FAST Günlüğüne işle (Panelde görünür, Telegram'a tekil mesaj atılmaz)
                pnl_sign = "+" if net_margin >= 0 else ""
                pnl_emoji = "🟢" if net_margin > 0 else ("🔴" if net_margin < 0 else "⚪")
                add_fast_scanner_log_db(
                    symbol,
                    "CLOSED",
                    f"{pnl_emoji} {symbol} {direction} {exit_status}! Net: {pnl_sign}%{net_margin:.2f} ({pnl_sign}${dollar_pnl:.2f})",
                    f"Giriş: {entry_price} ➔ Çıkış: {exit_price}"
                )
            else:
                # Canlı fiyat ve trailing stop seviyesini güncelle
                update_fast_signal_status(sig_id, {
                    "highest_price": highest_price,
                    "lowest_price": lowest_price,
                    "trailing_stop": current_sl,
                    "ladder_step": ladder_step,
                    "ladder_name": ladder_name,
                    "status": "ACTIVE_LADDER" if ladder_step >= 2 else ("ACTIVE_BE" if ladder_step == 1 else "ACTIVE")
                })

        return resolved_signals

