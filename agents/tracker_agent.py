"""
Counterfactual Tracker Agent - Vur-Kaç Mikro Scalp & Merdiven Kâr Sistemi
Instantly takes profit upon reaching Target (0.8% - 1.2% price move = +10% to +22% margin).
Includes:
- 45-Minute Stagnation Exit: Closes trades if they don't move fast, keeping capital liquid!
- Merdiven Kâr Sistemi (Step-Ladder Profit Locking): Stop kademeli olarak kâra çekilir.
  * Basamak 1 (+%0.30 fiyatta): Stop komisyon kurtaran seviyeye çekilir (+%0.12).
  * Basamak 2 (+%0.55 fiyatta): Stop +%0.35 kâra çekilir (10x'te net +%2.5).
  * Basamak 3 (+%0.80 fiyatta): Stop +%0.60 kâra çekilir (10x'te net +%5.0).
  * Basamak 4 (+%1.05 fiyatta): Stop +%0.85 kâra çekilir.
  * Dinamik Kanal: Zirvenin %0.20 arkasından takip eder.
- Realistic Binance Futures Net Fee Accounting (Deducts 0.10% roundtrip Taker fee * leverage).
"""
import os
from datetime import datetime
from typing import Dict, List, Optional
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

from core.database import (
    get_active_and_pending_signals,
    update_signal_status,
    get_performance_stats
)
from core.binance_client import BinanceFuturesClient
from config import (
    CHARTS_DIR,
    MAX_HOLD_MINUTES,
    BINANCE_ROUNDTRIP_FEE_PCT,
    ENABLE_LADDER_PROFIT,
    LADDER_STEPS,
    LADDER_DYNAMIC_CHANNEL_PCT
)

class CounterfactualTrackerAgent:
    def __init__(self, client: BinanceFuturesClient, output_dir=CHARTS_DIR):
        self.client = client
        self.output_dir = output_dir

    def update_tracked_trades(self, notifier=None) -> List[Dict]:
        """
        Vur-kaç mikro scalpleri kontrol eder.
        - Merdiven Kâr Sistemi ile stop'u kademe kademe kâra taşır.
        - Komisyonları daima stop seviyesine dahil ederek net sıfır zarar / garantili kâr sağlar.
        - 45 dakikayı geçen pozisyonları kapatıp sermayeyi boşaltır.
        """
        signals = get_active_and_pending_signals()
        if not signals:
            return []

        tickers = self.client.get_24hr_tickers()
        resolved_trades = []
        now = datetime.now()

        for sig in signals:
            sig_id = sig["id"]
            symbol = sig["symbol"]
            ticker = tickers.get(symbol)
            if not ticker:
                continue

            current_price = ticker["lastPrice"]
            direction = sig["direction"]
            is_long = (direction == "LONG")
            status = sig["status"]
            leverage = sig.get("leverage", 10)
            entry_price = sig.get("actual_entry_price") or sig["entry_min"]
            sl = sig.get("stop_loss")
            tp = sig.get("take_profit_1")

            # 1. ZİRVE / DİP FİYAT VE ANLIK KÂR TAKİBİ
            highest_price = sig.get("highest_price") or entry_price
            lowest_price = sig.get("lowest_price") or entry_price

            if current_price > highest_price:
                highest_price = current_price
                update_signal_status(sig_id, {"highest_price": highest_price})

            if current_price < lowest_price:
                lowest_price = current_price
                update_signal_status(sig_id, {"lowest_price": lowest_price})

            raw_profit_pct = ((current_price - entry_price) / entry_price * 100) if is_long else ((entry_price - current_price) / entry_price * 100)
            peak_profit_pct = ((highest_price - entry_price) / entry_price * 100) if is_long else ((entry_price - lowest_price) / entry_price * 100)

            # 2. MERDİVEN KÂR SİSTEMİ (STEP-LADDER PROFIT LOCKING)
            current_sl = sl
            current_ladder_step = sig.get("ladder_step") or 0
            ladder_name = sig.get("ladder_name") or ""

            if ENABLE_LADDER_PROFIT:
                for rung in LADDER_STEPS:
                    step_num = rung["step"]
                    trigger_pct = rung["trigger_raw_pct"]
                    lock_pct = rung["lock_raw_pct"]
                    name = rung["name"]

                    # Fiyat bu basamağın tetik seviyesine ulaştıysa ve henüz bu basamak uygulanmadıysa
                    if peak_profit_pct >= trigger_pct and step_num > current_ladder_step:
                        # Long ise girişin üzerine (+), Short ise girişin altına (-) çek
                        if is_long:
                            candidate_sl = round(entry_price * (1.0 + (lock_pct / 100.0)), 8)
                            if candidate_sl > current_sl:
                                current_sl = candidate_sl
                                current_ladder_step = step_num
                                ladder_name = name
                                update_signal_status(sig_id, {
                                    "stop_loss": current_sl,
                                    "ladder_step": current_ladder_step,
                                    "ladder_name": ladder_name,
                                    "status": "ACTIVE_BE" if current_ladder_step == 1 else "ACTIVE_LADDER"
                                })
                                print(f"🪜 [{symbol}] {name} devrede! Stop yukarı çekildi: {current_sl} (Komisyon güvende!)")
                        else:
                            candidate_sl = round(entry_price * (1.0 - (lock_pct / 100.0)), 8)
                            if candidate_sl < current_sl:
                                current_sl = candidate_sl
                                current_ladder_step = step_num
                                ladder_name = name
                                update_signal_status(sig_id, {
                                    "stop_loss": current_sl,
                                    "ladder_step": current_ladder_step,
                                    "ladder_name": ladder_name,
                                    "status": "ACTIVE_BE" if current_ladder_step == 1 else "ACTIVE_LADDER"
                                })
                                print(f"🪜 [{symbol}] {name} devrede! Stop aşağı çekildi: {current_sl} (Komisyon güvende!)")

                # 3. DİNAMİK İZ SÜREN KANAL (Basamak 4 Ötesi Runner İz Sürme)
                if peak_profit_pct >= 1.05:
                    if is_long:
                        channel_sl = round(highest_price * (1.0 - LADDER_DYNAMIC_CHANNEL_PCT / 100.0), 8)
                        if channel_sl > current_sl:
                            current_sl = channel_sl
                            ladder_name = "⚡ Dinamik Kanal"
                            update_signal_status(sig_id, {
                                "stop_loss": current_sl,
                                "trailing_stop": current_sl,
                                "ladder_name": ladder_name
                            })
                    else:
                        channel_sl = round(lowest_price * (1.0 + LADDER_DYNAMIC_CHANNEL_PCT / 100.0), 8)
                        if channel_sl < current_sl:
                            current_sl = channel_sl
                            ladder_name = "⚡ Dinamik Kanal"
                            update_signal_status(sig_id, {
                                "stop_loss": current_sl,
                                "trailing_stop": current_sl,
                                "ladder_name": ladder_name
                            })

            # 4. ZAMAN BOZULMASI VE KÂR KİLİDİ (TIME-DECAY ROI & 45 DAKİKA KURALI)
            entered_at_str = sig.get("entered_at") or sig.get("created_at")
            minutes_open = 0
            if entered_at_str:
                try:
                    entered_time = datetime.strptime(entered_at_str[:19], "%Y-%m-%d %H:%M:%S")
                    minutes_open = (now - entered_time).total_seconds() / 60
                except Exception:
                    pass

            is_closed = False
            final_status = ""
            exit_price = current_price
            raw_change = 0.0

            # 4a. Time-Decay Erken Kâr Kilidi (Freqtrade Minimal ROI Prensibi)
            # Eğer pozisyon 30 dakikayı geçmişse ve net kârda ise (%2.5+ marjin), kârın erimesine izin verme:
            net_unrealized_margin = (raw_profit_pct * leverage) - (0.10 * leverage)
            if minutes_open >= 30 and net_unrealized_margin >= 2.5:
                protect_sl = round(entry_price * (1.0 + 0.0025), 8) if is_long else round(entry_price * (1.0 - 0.0025), 8)
                if (is_long and protect_sl > current_sl) or (not is_long and protect_sl < current_sl):
                    current_sl = protect_sl
                    update_signal_status(sig_id, {"stop_loss": current_sl, "ladder_name": "⏱️ 30dk Kâr Kilidi"})

            if minutes_open >= MAX_HOLD_MINUTES:
                is_closed = True
                final_status = "TIMEOUT_EXIT"
                exit_price = current_price
                raw_change = ((current_price - entry_price) / entry_price) if is_long else ((entry_price - current_price) / entry_price)
                print(f"⏱️ [{symbol}] 45 dakika doldu! Hareketsiz pozisyon {current_price} seviyesinden kapatıldı.")

            # 5. HEDEF (TP) VE MERDİVEN STOP KONTROLLERİ
            elif not is_closed:
                # Hedefe (TP) ulaştı mı?
                if (is_long and current_price >= tp) or (not is_long and current_price <= tp):
                    is_closed = True
                    final_status = "HIT_TP"
                    exit_price = tp
                    raw_change = ((tp - entry_price) / entry_price) if is_long else ((entry_price - tp) / entry_price)

                # Stop veya Merdiven Kâr Stopuna çarptı mı?
                elif (is_long and current_price <= current_sl) or (not is_long and current_price >= current_sl):
                    is_closed = True
                    exit_price = current_sl
                    raw_change = ((current_sl - entry_price) / entry_price) if is_long else ((entry_price - current_sl) / entry_price)
                    
                    if current_ladder_step >= 2 or peak_profit_pct >= 0.55:
                        final_status = f"LADDER_STEP_{current_ladder_step}_EXIT" if current_ladder_step > 0 else "LADDER_PROFIT_EXIT"
                    elif current_ladder_step == 1 or (status in ("ACTIVE_BE", "ACTIVE_LADDER") and raw_change >= 0):
                        final_status = "CLOSED_BE"
                    else:
                        final_status = "HIT_SL"

            # 6. İŞLEM KAPANDIYSA NET MARJİN PnL'İ HESAPLA VE VERİTABANINA YAZ
            if is_closed:
                gross_pnl_pct = round(raw_change * leverage * 100, 2)
                # Borsa komisyon kesintisi: Giriş (%0.05) + Çıkış (%0.05) = %0.10 raw price * kaldıraç
                fee_pct = round(BINANCE_ROUNDTRIP_FEE_PCT * leverage, 2)
                net_pnl_pct = round(gross_pnl_pct - fee_pct, 2)

                candles = self.client.get_klines(symbol, interval="15m", limit=40)
                exit_png_path = self.generate_outcome_chart(sig, candles, final_status, exit_price, net_pnl_pct, leverage)

                update_signal_status(sig_id, {
                    "status": final_status,
                    "closed_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "exit_price": exit_price,
                    "simulated_pnl_pct": net_pnl_pct,
                    "gross_pnl_pct": gross_pnl_pct,
                    "fee_pct": fee_pct,
                    "chart_exit_png": exit_png_path
                })

                resolved_info = {
                    "signal_id": sig_id,
                    "symbol": symbol,
                    "direction": direction,
                    "leverage": leverage,
                    "status": final_status,
                    "ladder_step": current_ladder_step,
                    "ladder_name": ladder_name,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl_pct": net_pnl_pct,
                    "gross_pnl_pct": gross_pnl_pct,
                    "fee_pct": fee_pct,
                    "chart_exit_png": exit_png_path
                }
                resolved_trades.append(resolved_info)

                # 7. TAURIC RESEARCH (TRADINGAGENTS) POST-TRADE REFLECTION ENGINE
                try:
                    from core.reflection import ReflectorEngine
                    trade_reflect_data = {
                        "signal_id": sig_id,
                        "symbol": symbol,
                        "direction": direction,
                        "status": final_status,
                        "pnl_pct": net_pnl_pct,
                        "gross_pnl_pct": gross_pnl_pct,
                        "fee_pct": fee_pct,
                        "leverage": leverage,
                        "ladder_step": current_ladder_step,
                        "ladder_name": ladder_name,
                        "minutes_open": minutes_open
                    }
                    reflection = ReflectorEngine.reflect_on_trade(trade_reflect_data)
                    resolved_info["lesson"] = reflection.get("lesson")
                    print(f"🧠 [Reflector Hafıza] {symbol} için ders kaydedildi: {reflection.get('lesson')}")
                except Exception as e:
                    print(f"⚠️ [Reflector] Refleksiyon hatası: {e}")

                print(
                    f"🏁 [{symbol}] İşlem kapandı ({final_status}): Net PnL: {'+' if net_pnl_pct >= 0 else ''}{net_pnl_pct}% "
                    f"(Brüt: {'+' if gross_pnl_pct >= 0 else ''}{gross_pnl_pct}%, Komisyon: -{fee_pct}%)"
                )

                if notifier:
                    notifier.send_outcome_report(resolved_info)

        return resolved_trades

    def generate_outcome_chart(self, sig: Dict, candles: List[Dict], outcome: str, exit_price: float, pnl_pct: float, leverage: int = 10) -> str:
        symbol = sig["symbol"]
        direction = sig["direction"]
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{symbol}_{direction}_{leverage}x_SCALP_{timestamp_str}.png"
        filepath = os.path.join(self.output_dir, filename)

        plot_candles = candles[-35:]
        n = len(plot_candles)
        indices = list(range(n))

        fig, ax = plt.subplots(figsize=(10, 5), facecolor="#131722")
        ax.set_facecolor("#1e222d")
        ax.grid(True, color="#2a2e39", linestyle="--", alpha=0.6)
        ax.tick_params(colors="#848e9c", labelsize=9)

        # 1. ÇİZGİ GRAFİĞİ ÇİZİMİ (Line Chart)
        closes = [c["close"] for c in plot_candles]
        line_color = "#38bdf8" if direction == "LONG" else "#fb923c"
        ax.plot(indices, closes, color=line_color, linewidth=2.3, label=f"{symbol} Fiyat Çizgisi", zorder=3)
        min_p = min(closes)
        ax.fill_between(indices, closes, min_p * 0.999, color=line_color, alpha=0.12, zorder=2)

        is_win = pnl_pct > 0
        outcome_color = "#10b981" if is_win else "#ef4444"

        # Çıkış Noktası (Marker)
        last_idx = indices[-1]
        ax.scatter([last_idx], [exit_price], color=outcome_color, s=50, zorder=5, label=f"Çıkış: {exit_price}")

        entry_p = sig.get("actual_entry_price") or sig["entry_min"]
        ax.axhline(entry_p, color="#38bdf8", linestyle="--", linewidth=1.4, label=f"Giriş: {entry_p}")
        ax.axhline(sig["stop_loss"], color="#ef4444", linestyle="-", linewidth=1.4, label=f"SL: {sig['stop_loss']}")
        ax.axhline(sig["take_profit_1"], color="#10b981", linestyle="-", linewidth=1.4, label=f"Kar Hedefi (TP): {sig['take_profit_1']}")

        if outcome == "HIT_TP":
            outcome_title = "[🎯 VUR-KAÇ HEDEFİ ALINDI]"
        elif outcome.startswith("LADDER_STEP_") or outcome == "LADDER_PROFIT_EXIT":
            outcome_title = "[🪜 MERDİVEN KÂR KİLİDİ]"
        elif outcome == "TRAILING_STOP_EXIT":
            outcome_title = "[⚡ İZ SÜREN DİNAMİK KANAL]"
        elif outcome == "CLOSED_BE":
            outcome_title = "[🛡️ KOMİSYON KORUMALI BE+]"
        elif outcome == "TIMEOUT_EXIT":
            outcome_title = "[⏱️ ZAMAN AŞIMI - 45dk]"
        elif outcome == "MANUAL_CLOSE":
            outcome_title = "[🛑 EL İLE KAPATILDI]"
        else:
            outcome_title = "[🛑 STOP LOSS]"

        outcome_text = f"{outcome_title}: {'+' if pnl_pct > 0 else ''}{pnl_pct}% PnL ({leverage}x)"

        ax.set_title(
            f"{symbol} ({direction} {leverage}x) | {outcome_text}",
            fontsize=11, fontweight="bold", color=outcome_color, pad=10
        )
        ax.legend(loc="upper left", facecolor="#131722", edgecolor="#2a2e39", labelcolor="#d1d4dc", fontsize=8)

        step = max(1, n // 5)
        x_ticks = indices[::step]
        x_labels = [datetime.fromtimestamp(plot_candles[i]["timestamp"] / 1000).strftime("%H:%M") for i in x_ticks]
        ax.set_xticks(x_ticks)
        ax.set_xticklabels(x_labels, color="#848e9c", fontsize=8)

        plt.tight_layout()
        fig.savefig(filepath, dpi=120, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)

        # Otomatik Çöp Toplama (Garbage Collection): En fazla son 50 grafik tutulur, disk şişmesi engellenir
        try:
            from pathlib import Path
            png_list = sorted(Path(self.output_dir).glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
            for old_chart in png_list[50:]:
                old_chart.unlink(missing_ok=True)
        except Exception:
            pass

        return filepath
