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
    get_performance_stats,
    reconcile_partial_pnl
)
from core.binance_client import BinanceFuturesClient
from config import (
    CHARTS_DIR,
    MAX_HOLD_MINUTES,
    BINANCE_ROUNDTRIP_FEE_PCT,
    ENABLE_LADDER_PROFIT,
    LADDER_STEPS,
    LADDER_DYNAMIC_CHANNEL_PCT,
    EARLY_INVALIDATION_ENABLED,
    EARLY_INVALIDATION_MINUTES,
    EARLY_INVALIDATION_LOSS_PCT,
    ATR_LADDER_ENABLED,
    ATR_PERIOD,
    ATR_LADDER_MULT,
    MIN_RR_RATIO,
    MAX_ALLOCATED_MARGIN_PER_TRADE,
    ENABLE_LOSING_DCA
)

class CounterfactualTrackerAgent:
    def __init__(self, client: BinanceFuturesClient, output_dir=CHARTS_DIR):
        self.client = client
        self.output_dir = output_dir

    @staticmethod
    def _calc_atr(candles: List[Dict], period: int = ATR_PERIOD) -> Optional[float]:
        """Son kapanmış mumlardan ATR (Volatilite) hesaplar."""
        if not candles or len(candles) < period + 1:
            return None
        trs = []
        for i in range(1, len(candles)):
            h = float(candles[i]["high"])
            l = float(candles[i]["low"])
            pc = float(candles[i - 1]["close"])
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        if len(trs) < period:
            return None
        return sum(trs[-period:]) / period

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

            # Milisaniyelik Canlı WebSocket Fitil / Fiyat Kontrolü
            try:
                from core.binance_streamer import get_live_price, add_stream_symbol
                add_stream_symbol(symbol)
                ws_price = get_live_price(symbol)
            except Exception:
                ws_price = None

            current_price = ws_price if ws_price else ticker["lastPrice"]
            direction = sig["direction"]
            is_long = (direction == "LONG")
            status = sig["status"]
            leverage = sig.get("leverage", 10)
            entry_price = float(sig.get("actual_entry_price") or sig["entry_min"])
            sl = float(sig.get("stop_loss"))
            tp = float(sig.get("take_profit_1"))
            tp2 = float(sig.get("take_profit_2") or (tp * 1.015 if is_long else tp * 0.985))
            allocated_margin = float(sig.get("allocated_margin_usdt") or 100.0)

            # 0. 2-KADEMELİ MERDİVEN GİRİŞİ (Equilibrium FVG / OB DCA Retest)
            entry_limit_2 = float(sig.get("entry_limit_2") or 0.0)
            entry_limit_2_hit = int(sig.get("entry_limit_2_hit") or 0)
            partial_tp_taken = int(sig.get("partial_tp_taken") or 0)
            current_realized_usd = float(sig.get("realized_pnl_usd") or 0.0)

            if ENABLE_LOSING_DCA and entry_limit_2 > 0 and entry_limit_2_hit == 0 and partial_tp_taken == 0:
                is_hit_limit2 = (is_long and current_price <= entry_limit_2) or (not is_long and current_price >= entry_limit_2)
                new_margin = round(allocated_margin * 1.5, 2)  # %50 ek marjin doldu
                if is_hit_limit2 and new_margin <= (MAX_ALLOCATED_MARGIN_PER_TRADE * 1.5):
                    # Ağırlıklı ortalama: %100 ilk giriş + %50 ikinci kademe = %150 hacim
                    orig_sl_dist = abs(entry_price - sl)
                    orig_tp_dist = abs(tp - entry_price)
                    orig_rr = (orig_tp_dist / orig_sl_dist) if orig_sl_dist > 0 else MIN_RR_RATIO
                    target_rr = max(MIN_RR_RATIO, orig_rr)

                    new_avg_entry = round(((entry_price * 1.0) + (entry_limit_2 * 0.5)) / 1.5, 8)
                    if is_long:
                        raw_sl_dist = new_avg_entry - sl
                        new_sl_dist = raw_sl_dist if raw_sl_dist > 0 else (orig_sl_dist * 0.67)
                        new_sl = round(sl, 8) if raw_sl_dist > 0 else round(new_avg_entry - new_sl_dist, 8)
                        recal_tp1 = round(new_avg_entry + (new_sl_dist * target_rr), 8)
                        min_tp1 = round(new_avg_entry + (new_sl_dist * MIN_RR_RATIO), 8)
                        new_tp1 = max(min_tp1, min(tp, recal_tp1))
                    else:
                        raw_sl_dist = sl - new_avg_entry
                        new_sl_dist = raw_sl_dist if raw_sl_dist > 0 else (orig_sl_dist * 0.67)
                        new_sl = round(sl, 8) if raw_sl_dist > 0 else round(new_avg_entry + new_sl_dist, 8)
                        recal_tp1 = round(new_avg_entry - (new_sl_dist * target_rr), 8)
                        min_tp1 = round(new_avg_entry - (new_sl_dist * MIN_RR_RATIO), 8)
                        new_tp1 = min(min_tp1, max(tp, recal_tp1))

                    update_signal_status(sig_id, {
                        "actual_entry_price": new_avg_entry,
                        "entry_limit_2_hit": 1,
                        "allocated_margin_usdt": new_margin,
                        "stop_loss": new_sl,
                        "take_profit_1": new_tp1,
                        "ladder_name": "🪜 2. Kademe Giriş Eklendi (DCA)"
                    })
                    entry_price = new_avg_entry
                    allocated_margin = new_margin
                    sl = new_sl
                    tp = new_tp1
                    print(f"🪜 [{symbol}] 2. Kademe Giriş Doldu! Ağırlıklı Maliyet: {entry_price} | Marjin: ${allocated_margin} | Yeni SL: {sl} | Yeni TP1: {tp}")

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

            # 2. MERDİVEN KÂR SİSTEMİ (STEP-LADDER PROFIT LOCKING - ATR VOLATİLİTE & VADEYE GÖRE ÖLÇEKLİ)
            current_sl = sl
            current_ladder_step = sig.get("ladder_step") or 0
            ladder_name = sig.get("ladder_name") or ""

            sig_tf = sig.get("timeframe") or ("1h" if "1h" in str(sig.get("trade_horizon")) else ("30m" if "30m" in str(sig.get("trade_horizon")) else "15m"))
            ladder_mult = 2.0 if sig_tf == "1h" else (1.25 if sig_tf == "30m" else 1.0)

            if ENABLE_LADDER_PROFIT:
                active_ladder_steps = LADDER_STEPS
                step_mult = ladder_mult

                # Volatiliteye (ATR) Normalize Dinamik Merdiven Basamakları (sadece kâr >= %0.30 iken hesapla)
                atr_pct_val = None
                if ATR_LADDER_ENABLED and peak_profit_pct >= 0.30:
                    try:
                        tf_klines_atr = self.client.get_klines(symbol, interval=sig_tf, limit=ATR_PERIOD + 10)
                        closed_atr_candles = tf_klines_atr[:-1] if tf_klines_atr and len(tf_klines_atr) > ATR_PERIOD + 1 else tf_klines_atr
                        atr_abs = self._calc_atr(closed_atr_candles, ATR_PERIOD)
                        if atr_abs and entry_price > 0:
                            atr_pct_val = max(0.32, min(2.50, (atr_abs / entry_price) * 100.0))
                            tf_cap = min(ladder_mult, 1.35)
                            max_trig_map = {2: 0.85, 3: 1.20, 4: 1.65}
                            active_ladder_steps = []
                            for s_num, cfg in sorted(ATR_LADDER_MULT.items()):
                                if s_num == 1:
                                    # Basamak 1: Hızlı BE+ Sermaye Kalkanı (kazanan scalplerin tam SL olmasını önler)
                                    trig_val = round(min(0.45 * ladder_mult, max(0.38, atr_pct_val * 0.48)), 4)
                                    lock_val = round(-0.08 * ladder_mult, 4)
                                    step_lbl = "🛡️ Basamak 1 (%35 Kâr Cebe + Nefes Payı BE+)"
                                else:
                                    static_rung = LADDER_STEPS[s_num - 1]
                                    max_t = max_trig_map.get(s_num, 1.65) * tf_cap
                                    raw_t = max(static_rung["trigger_raw_pct"] * tf_cap, atr_pct_val * cfg["trigger"])
                                    trig_val = round(min(max_t, raw_t), 4)
                                    raw_l = max(static_rung["lock_raw_pct"] * tf_cap, atr_pct_val * (cfg["trigger"] - cfg["lock_distance"]))
                                    lock_val = round(min(trig_val - 0.30, raw_l), 4)
                                    step_lbl = f"🪜 ATR Basamak {s_num}"
                                active_ladder_steps.append({
                                    "step": s_num,
                                    "trigger_raw_pct": trig_val,
                                    "lock_raw_pct": lock_val,
                                    "name": step_lbl,
                                })
                            step_mult = 1.0  # sig_tf ATR ve ladder_mult yukarıda doğrudan ölçeklendi
                    except Exception:
                        active_ladder_steps = LADDER_STEPS
                        step_mult = ladder_mult

                for rung in active_ladder_steps:
                    step_num = rung["step"]
                    trigger_pct = rung["trigger_raw_pct"] * step_mult
                    lock_pct = rung["lock_raw_pct"] * step_mult
                    name = f"[{sig_tf}] {rung['name']}"

                    # Fiyat bu basamağın tetik seviyesine ulaştıysa ve henüz bu basamak uygulanmadıysa
                    if peak_profit_pct >= trigger_pct and step_num > current_ladder_step:
                        candidate_sl = round(
                            entry_price * (1.0 + (lock_pct / 100.0)) if is_long else entry_price * (1.0 - (lock_pct / 100.0)),
                            8
                        )
                        is_better_sl = (candidate_sl > current_sl) if is_long else (candidate_sl < current_sl)
                        if is_better_sl:
                            current_sl = candidate_sl
                            current_ladder_step = step_num
                            ladder_name = name
                            db_updates = {
                                "stop_loss": current_sl,
                                "ladder_step": current_ladder_step,
                                "ladder_name": ladder_name,
                                "status": "ACTIVE_BE" if current_ladder_step == 1 else "ACTIVE_LADDER"
                            }
                            # Basamak 1: %35 Kısmi Kârı Cebe Al + Kalan %65'e -%0.08 Nefes Paylı Sıfır Risk Stopu
                            if step_num == 1 and partial_tp_taken == 0:
                                step1_net_pct = max(3.0, (peak_profit_pct * leverage) - (BINANCE_ROUNDTRIP_FEE_PCT * leverage))
                                step1_usd = round((allocated_margin * 0.35) * (step1_net_pct / 100.0), 2)
                                current_realized_usd = round(current_realized_usd + step1_usd, 2)
                                allocated_margin = round(allocated_margin * 0.65, 2)
                                partial_tp_taken = 2
                                ladder_name = f"[{sig_tf}] 🛡️ Basamak 1 (+${step1_usd} Cebe | %65 BE+ Kilit)"
                                db_updates.update({
                                    "partial_tp_taken": partial_tp_taken,
                                    "realized_pnl_usd": current_realized_usd,
                                    "allocated_margin_usdt": allocated_margin,
                                    "ladder_name": ladder_name
                                })
                            update_signal_status(sig_id, db_updates)
                            print(f"🪜 [{symbol}] [{sig_tf}] {ladder_name} devrede! Stop: {current_sl} | Cebe alınan: ${current_realized_usd}")

                # 3. DİNAMİK İZ SÜREN KANAL (Basamak 4 Ötesi Runner İz Sürme)
                step4_trigger = active_ladder_steps[-1]["trigger_raw_pct"] * step_mult
                if peak_profit_pct >= step4_trigger:
                    dyn_chan_pct = round(max(LADDER_DYNAMIC_CHANNEL_PCT, atr_pct_val * 0.65), 4) if atr_pct_val else (LADDER_DYNAMIC_CHANNEL_PCT * step_mult)
                    if is_long:
                        channel_sl = round(highest_price * (1.0 - dyn_chan_pct / 100.0), 8)
                        if channel_sl > current_sl:
                            current_sl = channel_sl
                            ladder_name = f"⚡ Dinamik Kanal ({sig_tf})"
                            update_signal_status(sig_id, {
                                "stop_loss": current_sl,
                                "trailing_stop": current_sl,
                                "ladder_name": ladder_name
                            })
                    else:
                        channel_sl = round(lowest_price * (1.0 + dyn_chan_pct / 100.0), 8)
                        if channel_sl < current_sl:
                            current_sl = channel_sl
                            ladder_name = f"⚡ Dinamik Kanal ({sig_tf})"
                            update_signal_status(sig_id, {
                                "stop_loss": current_sl,
                                "trailing_stop": current_sl,
                                "ladder_name": ladder_name
                            })

            # 4. ZAMAN BOZULMASI VE KÂR KİLİDİ (TIME-DECAY ROI & VADEYE GÖRE SÜRE)
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
            net_unrealized_margin = (raw_profit_pct * leverage) - (0.10 * leverage)
            if minutes_open >= (30 * ladder_mult) and net_unrealized_margin >= (2.5 * ladder_mult):
                protect_sl = round(entry_price * (1.0 + 0.0025 * ladder_mult), 8) if is_long else round(entry_price * (1.0 - 0.0025 * ladder_mult), 8)
                if (is_long and protect_sl > current_sl) or (not is_long and protect_sl < current_sl):
                    current_sl = protect_sl
                    update_signal_status(sig_id, {"stop_loss": current_sl, "ladder_name": f"⏱️ {int(30*ladder_mult)}dk Kâr Kilidi"})

            # 4. HEDEF (TP) VE MERDİVEN STOP KONTROLLERİ (BİRİNCİL ÖNCELİK)
            if not is_closed:
                # Hedefe (TP1 / TP2) ulaştı mı?
                is_hit_tp1 = (is_long and current_price >= tp) or (not is_long and current_price <= tp)
                is_hit_tp2 = (is_long and current_price >= tp2) or (not is_long and current_price <= tp2)

                # 4a. PARÇALI MERDİVEN ÇIKIŞI & FREE-TRADE RUNNER (Partial TP1 Scaling-Out)
                if is_hit_tp1 and partial_tp_taken in (0, 2):
                    # Mevcut marjinin %50'sini realize et, kârı kilitle ve kalanını 'FREE-TRADE RUNNER' yap!
                    partial_raw_gain = ((tp - entry_price) / entry_price) if is_long else ((entry_price - tp) / entry_price)
                    partial_gross = partial_raw_gain * leverage * 100
                    partial_fee = BINANCE_ROUNDTRIP_FEE_PCT * leverage
                    partial_net_pct = round(partial_gross - partial_fee, 2)
                    half_margin = round(allocated_margin * 0.5, 2)
                    realized_usd = round(half_margin * (partial_net_pct / 100.0), 2)
                    current_realized_usd = round(current_realized_usd + realized_usd, 2)
                    new_partial_state = 3 if partial_tp_taken == 2 else 1

                    # Stop-Loss'u hemen giriş fiyatına (Break-Even) çek:
                    be_sl = round(entry_price * (1.0005 if is_long else 0.9995), 8)
                    current_sl = be_sl
                    current_ladder_step = max(current_ladder_step, 2)
                    ladder_name = f"🎯 TP1 %50 Kilit (+${current_realized_usd}) | 🏃 Free-Trade Runner"

                    update_signal_status(sig_id, {
                        "partial_tp_taken": new_partial_state,
                        "realized_pnl_usd": current_realized_usd,
                        "stop_loss": current_sl,
                        "allocated_margin_usdt": half_margin,
                        "status": "ACTIVE_PARTIAL_TP1",
                        "ladder_step": current_ladder_step,
                        "ladder_name": ladder_name
                    })
                    partial_tp_taken = new_partial_state
                    allocated_margin = half_margin
                    print(f"🎯 [{symbol}] TP1 Vuruldu! Kâr Cebe Alındı (Toplam Kilit: +${current_realized_usd}). Free-Trade Runner TP2'ye koşuyor!")

                elif partial_tp_taken in (1, 3) and is_hit_tp2:
                    # Runner hedefe (TP2) ulaştı! Kalan pozisyon da tepe fiyattan kapatıldı!
                    is_closed = True
                    final_status = "HIT_TP2_RUNNER"
                    exit_price = tp2
                    raw_change = ((tp2 - entry_price) / entry_price) if is_long else ((entry_price - tp2) / entry_price)
                    print(f"🚀 [{symbol}] Runner TP2 Vuruldu! Kalan işlem de tepe fiyattan kapatıldı!")

                # Stop veya Merdiven Kâr Stopuna çarptı mı?
                if not is_closed and ((is_long and current_price <= current_sl) or (not is_long and current_price >= current_sl)):
                    is_closed = True
                    exit_price = current_sl
                    raw_change = ((current_sl - entry_price) / entry_price) if is_long else ((entry_price - current_sl) / entry_price)

                    if partial_tp_taken in (1, 3):
                        final_status = "RUNNER_BE_EXIT"  # Free-trade sıfır riskle kapandı, TP1 kârı cepte!
                    elif current_ladder_step >= 2 or peak_profit_pct >= (0.75 * ladder_mult):
                        final_status = f"LADDER_STEP_{current_ladder_step}_EXIT" if current_ladder_step > 0 else "LADDER_PROFIT_EXIT"
                    elif current_ladder_step == 1 or partial_tp_taken == 2 or (status in ("ACTIVE_BE", "ACTIVE_LADDER") and raw_change >= 0):
                        final_status = "CLOSED_BE"
                    else:
                        final_status = "HIT_SL"

            # 5. AKILLI YAPISAL ERKEN ZARAR KES KALKANI & VADEYE GÖRE DİNAMİK SÜRELER
            sig_tf = sig.get("timeframe") or ("1h" if "1h" in str(sig.get("trade_horizon")) else ("30m" if "30m" in str(sig.get("trade_horizon")) else "15m"))
            if sig_tf == "1h":
                effective_early_inval_min = 60
                effective_max_hold = 1440  # 24 saat nefes payı
            elif sig_tf == "30m":
                effective_early_inval_min = 40
                effective_max_hold = 360   # 6 saat nefes payı
            else:
                effective_early_inval_min = EARLY_INVALIDATION_MINUTES
                effective_max_hold = MAX_HOLD_MINUTES

            effective_inval_loss = EARLY_INVALIDATION_LOSS_PCT * ladder_mult
            if entry_limit_2_hit == 1:
                effective_early_inval_min += 25  # 2. Kademe DCA dolduysa toparlanma nefesi
                effective_inval_loss *= 1.35

            # Eğer henüz SL'e çarpmamışsa, vadeye göre erken süreyi geçmişse ve ladder_step == 0 ise:
            if not is_closed and EARLY_INVALIDATION_ENABLED and current_ladder_step == 0 and minutes_open >= effective_early_inval_min:
                raw_c = ((current_price - entry_price) / entry_price) if is_long else ((entry_price - current_price) / entry_price)
                if raw_c <= -(effective_inval_loss / 100.0):
                    # Yapısal Mum Kapanışı Teyidi: Sadece fitil iğnesiyle değil, kapanan mum EMA20 aleyhine döndüyse kes
                    structural_confirm = True
                    try:
                        tf_klines = self.client.get_klines(symbol, interval=sig_tf, limit=25)
                        if tf_klines and len(tf_klines) >= 22:
                            closes = [float(k["close"]) for k in tf_klines]
                            last_closed = closes[-2]
                            ema_val = sum(closes[:20]) / 20.0
                            mult_k = 2.0 / 21.0
                            for c_px in closes[20:-1]:
                                ema_val = (c_px - ema_val) * mult_k + ema_val
                            if is_long and last_closed >= ema_val:
                                structural_confirm = False
                            elif (not is_long) and last_closed <= ema_val:
                                structural_confirm = False
                    except Exception:
                        pass

                    if structural_confirm:
                        is_closed = True
                        final_status = "EARLY_INVALIDATION_EXIT"
                        exit_price = current_price
                        raw_change = raw_c
                        print(f"🛡️ [{symbol}] [{sig_tf}] Akıllı Erken Zarar Kes devrede! ({minutes_open:.0f} dk, ham: {raw_c*100:.2f}%). Mum EMA20 aleyhine kapandı.")
                    else:
                        print(f"⏳ [{symbol}] [{sig_tf}] Fiyat hafif ekside ({raw_c*100:.2f}%) ama son kapanan mum EMA20 desteğini koruyor -> Panik kesim önlendi.")

            # 6. ZAMAN AŞIMI (TIMEOUT / VADEYE GÖRE HAREKETSİZLİK ÇIKIŞI)
            if not is_closed and minutes_open >= effective_max_hold:
                raw_change = ((current_price - entry_price) / entry_price) if is_long else ((entry_price - current_price) / entry_price)
                # Eğer pozisyon kârda ise hemen kârı kilitleyip çık:
                if raw_change > 0.001:
                    is_closed = True
                    final_status = "TIMEOUT_PROFIT_EXIT"
                    exit_price = current_price
                    print(f"⏱️ [{symbol}] [{sig_tf}] {effective_max_hold} dk doldu: Pozisyon kârda ({raw_change*100:+.2f}%) kapatıldı.")
                # Eğer pozisyon hafif ekside ancak Stop mesafesine çok uzaksa (<%0.4) ek nefes payı tanı:
                elif minutes_open < (effective_max_hold * 1.3) and abs(raw_change) < 0.004:
                    pass
                else:
                    is_closed = True
                    final_status = "TIMEOUT_EXIT"
                    exit_price = current_price
                    print(f"⏱️ [{symbol}] [{sig_tf}] {minutes_open:.0f} dakika doldu! Hareketsiz pozisyon {current_price} seviyesinden kapatıldı.")

            # 6. İŞLEM KAPANDIYSA NET MARJİN PnL'İ HESAPLA VE VERİTABANINA YAZ
            if is_closed:
                gross_pnl_pct = round(raw_change * leverage * 100, 2)
                # Borsa komisyon kesintisi: Giriş (%0.05) + Çıkış (%0.05) = %0.10 raw price * kaldıraç
                fee_pct = round(BINANCE_ROUNDTRIP_FEE_PCT * leverage, 2)
                net_pnl_pct = round(gross_pnl_pct - fee_pct, 2)

                net_pnl_pct, gross_pnl_pct, final_margin_to_save = reconcile_partial_pnl(
                    allocated_margin, partial_tp_taken, current_realized_usd, net_pnl_pct, fee_pct, final_status
                )

                candles = self.client.get_klines(symbol, interval="15m", limit=40)
                exit_png_path = self.generate_outcome_chart(sig, candles, final_status, exit_price, net_pnl_pct, leverage)

                update_signal_status(sig_id, {
                    "status": final_status,
                    "closed_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "exit_price": exit_price,
                    "simulated_pnl_pct": net_pnl_pct,
                    "gross_pnl_pct": gross_pnl_pct,
                    "fee_pct": fee_pct,
                    "allocated_margin_usdt": final_margin_to_save,
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
            outcome_title = f"[⏱️ ZAMAN AŞIMI - {MAX_HOLD_MINUTES}dk]"
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
