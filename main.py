"""
Trading Bot Orchestrator - Binance Futures (USDT.P) Multi-Agent System
Supports Dynamic Leverage (10x vs 20x Sniper), BTC Market Shield,
Multi-Timeframe Confluence (4h + 1h), Break-Even Protection,
and Background Telegram Command Listening.
"""
import sys
import time
import argparse
from datetime import datetime, timezone, timedelta

TURKEY_TZ = timezone(timedelta(hours=3))

from config import (
    SCAN_INTERVAL_SECONDS,
    PRIMARY_TIMEFRAME,
    MACRO_TIMEFRAME,
    ENABLE_TELEGRAM_COMMANDS,
    MAX_CONCURRENT_TRADES
)
from core.binance_client import BinanceFuturesClient
from core.database import (
    init_db,
    save_signal,
    get_performance_stats,
    get_active_positions_count
)
from agents.scanner_agent import MarketScannerAgent, add_scanner_log
from agents.ta_agent import TechnicalAnalysisAgent
from agents.news_agent import NewsAgent, get_live_news_feed
from agents.risk_agent import RiskOfficerAgent
from agents.chart_agent import ChartAgent
from agents.notifier_agent import NotifierAgent
from agents.tracker_agent import CounterfactualTrackerAgent
from agents.telegram_command_agent import TelegramCommandAgent
from agents.ai_analyst_agent import AIAnalystAgent
from agents.quant_simulation_agent import QuantSimulationAgent
from core.binance_streamer import start_streamer, pop_hot_symbols, add_stream_symbol, is_streamer_connected
from dashboard import start_dashboard

class TradingBotOrchestrator:
    def __init__(self):
        print("🤖 [Sistem Başlatılıyor] Binance Futures Çoklu Ajanlı Trade Bot (10x / 20x Destekli)...")
        init_db()
        
        self.client = BinanceFuturesClient()
        self.scanner = MarketScannerAgent(self.client)
        self.ta_agent = TechnicalAnalysisAgent()
        self.news_agent = NewsAgent()
        self.risk_officer = RiskOfficerAgent()
        self.chart_agent = ChartAgent()
        self.notifier = NotifierAgent()
        self.tracker = CounterfactualTrackerAgent(self.client)
        self.cmd_agent = TelegramCommandAgent(self)
        self.ai_analyst = AIAnalystAgent()
        self.quant_sim = QuantSimulationAgent(default_simulations=10000, win_threshold_pct=48.0)
        self.last_daily_report_date = None

        # Canlı WebSocket Veri Boru Hattını Başlat
        try:
            start_streamer()
            print("⚡ [WebSocket Streamer] Canlı emir akışı ve fiyat soketi bağlandı.")
        except Exception as ws_err:
            print(f"⚠️ WebSocket başlatılamadı: {ws_err}")

        # Başlangıçta aktif bot verileriyle Otonom Kalibrasyon yenilemesi (Eski kirli cache varsa temizler)
        try:
            from core.self_tuning_engine import SelfTuningEngine
            SelfTuningEngine.get_current_params()
            SelfTuningEngine.run_autonomous_training_cycle(min_trades_required=5, auto_commit=True)
        except Exception as tune_err:
            print(f"⚠️ Otonom kalibrasyon başlangıç hatası: {tune_err}")

        print("✅ Tüm Ajanlar, BTC Kalkanı ve Binance Futures (USDT.P) hazır.\n")

    def _record_shadow_rejection(self, symbol: str, ta_setup: dict, filter_stage: str, reject_reason: str):
        """Reddedilen adayı filtre ablasyonu (Shadow Mode) için pasif olarak DB'ye kaydeder."""
        try:
            from core.database import save_shadow_rejection
            save_shadow_rejection({
                "symbol": symbol,
                "direction": ta_setup.get("direction", "LONG"),
                "timeframe": ta_setup.get("timeframe", "15m"),
                "filter_stage": filter_stage,
                "reject_reason": reject_reason,
                "confluence_score": ta_setup.get("confluence_score", 0),
                "entry_price": ta_setup.get("current_price") or ((float(ta_setup.get("entry_min", 0)) + float(ta_setup.get("entry_max", 0))) / 2.0),
                "stop_loss": ta_setup.get("stop_loss", 0),
                "take_profit_1": ta_setup.get("take_profit_1", 0),
            })
        except Exception:
            pass

    def _try_open_stat_arb_pair(self, slots_left: int, allowed_timeframes) -> bool:
        """Yönlü işlem bulunamadığında veya BTC yatay testere (DEAD_CHOP) modundayken piyasa-nötr ikili arbitraj açar."""
        if slots_left < 2 or "15m" not in allowed_timeframes:
            return False
        try:
            from agents.pairs_stat_arb_agent import StatisticalArbitrageAgent
            from core.database import get_active_and_pending_signals, get_current_equity
            active_pair_sigs = get_active_and_pending_signals() or []
            if any(int(s.get("is_pair_trade") or 0) == 1 for s in active_pair_sigs):
                return False
            active_syms_now = {s.get("symbol") for s in active_pair_sigs}
            eq_now = get_current_equity()
            pair_leg_margin = round(max(40.0, eq_now * 0.065), 1)
            pair_leg_risk = round(pair_leg_margin * 0.13, 2)
            pair_opps = StatisticalArbitrageAgent(z_score_entry_threshold=2.35).evaluate_all_pairs(self.client)
            for popp in pair_opps:
                sa, sb = popp["sym_a"], popp["sym_b"]
                if sa in active_syms_now or sb in active_syms_now:
                    continue
                pa, pb = popp["price_a"], popp["price_b"]
                la, lb = popp["leg_a_direction"], popp["leg_b_direction"]
                sl_pct_p, tp1_pct_p, tp2_pct_p = 1.20, 2.20, 3.50
                for leg_sym, leg_px, leg_dir, peer_sym in [(sa, pa, la, sb), (sb, pb, lb, sa)]:
                    sl_px = round(leg_px * (1 - sl_pct_p / 100) if leg_dir == "LONG" else leg_px * (1 + sl_pct_p / 100), 6)
                    tp1_px = round(leg_px * (1 + tp1_pct_p / 100) if leg_dir == "LONG" else leg_px * (1 - tp1_pct_p / 100), 6)
                    tp2_px = round(leg_px * (1 + tp2_pct_p / 100) if leg_dir == "LONG" else leg_px * (1 - tp2_pct_p / 100), 6)
                    sig_pair = {
                        "symbol": leg_sym,
                        "direction": leg_dir,
                        "leverage": 10,
                        "entry_min": round(leg_px * 0.9995, 6),
                        "entry_max": round(leg_px * 1.0005, 6),
                        "actual_entry_price": leg_px,
                        "stop_loss": sl_px,
                        "take_profit_1": tp1_px,
                        "take_profit_2": tp2_px,
                        "risk_reward": 1.83,
                        "risk_grade": "Grade A (Piyasa-Nötr Pair)",
                        "allocated_margin_usdt": pair_leg_margin,
                        "risk_usd": pair_leg_risk,
                        "news_summary": f"Piyasa-Nötr Stat-Arb ({popp['pair_name']})",
                        "ta_reasons": popp["reason"],
                        "chart_entry_png": "",
                        "is_pair_trade": 1,
                        "pair_symbol": peer_sym,
                        "timeframe": "15m",
                        "trade_horizon": "Kısa Vade (15m Pair)"
                    }
                    save_signal(sig_pair)
                add_scanner_log(f"{sa}/{sb}", "APPROVED", popp["reason"], f"Pair Z={popp['z_score']}")
                print(f"⚖️ [Piyasa-Nötr Pair] {sa} ({la}) + {sb} ({lb}) | Z={popp['z_score']}")
                return True
        except Exception as pair_err:
            print(f"⚠️ Pair Arbitraj kontrol hatası: {pair_err}")
        return False

    def run_cycle(self):
        """Tek bir tam analiz ve takip döngüsü yürütür."""
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Döngü Başladı...")

        # 0.5 GÜN SONU OTOMATİK TELEGRAM RAPORU (Kalıcı DB Loglu + Ertesi Gün Telafi Korumalı)
        # Bulut sunucuları (Railway Linux) UTC saat diliminde çalıştığından, TSİ (UTC+3) baz alınır.
        from core.database import is_daily_report_sent_db, mark_daily_report_sent_db
        now_utc = datetime.now(timezone.utc)
        now_tr = now_utc.astimezone(TURKEY_TZ)
        today_str = now_tr.strftime("%Y-%m-%d")
        yesterday_str = (now_tr - timedelta(days=1)).strftime("%Y-%m-%d")

        # Gece yarısı atlandıysa veya restart olduysa bir önceki günün raporunu otomatik telafi et
        if not is_daily_report_sent_db(yesterday_str):
            try:
                print(f"📅 [Gün Sonu Telafi Raporu] {yesterday_str} kapanış raporu Telegram'a gönderiliyor...")
                rep_y = self.notifier.send_daily_summary_report(target_date_str=yesterday_str)
                if rep_y.get("sent", True):
                    mark_daily_report_sent_db(yesterday_str)
            except Exception as rep_err:
                print(f"⚠️ Telafi gün sonu raporu gönderme hatası: {rep_err}")

        # Günün kapanış penceresi: TSİ 23:50 - 23:59 arası o günün raporunu + Shadow raporunu kalıcı mühürle gönder
        if now_tr.hour == 23 and now_tr.minute >= 50 and not is_daily_report_sent_db(today_str):
            try:
                print(f"📅 [Gün Sonu Raporu] {today_str} gün sonu raporu Telegram'a otomatik gönderiliyor... (TSİ {now_tr.strftime('%H:%M')})")
                rep_t = self.notifier.send_daily_summary_report(target_date_str=today_str)
                if rep_t.get("sent", True):
                    mark_daily_report_sent_db(today_str)
                    self.last_daily_report_date = today_str
            except Exception as rep_err:
                print(f"⚠️ Gün sonu raporu gönderme hatası: {rep_err}")

        # 1. Açık sanal işlemleri kontrol et (Break-Even & TP/SL takibi)
        print("📊 [Tracker Ajanı] Aktif sanal işlemler kontrol ediliyor...")
        resolved = self.tracker.update_tracked_trades(self.notifier)
        if resolved:
            print(f"🎯 {len(resolved)} adet sanal işlem sonuçlandı!")

        # 1.5 KASA KALKANI KONTROLÜ (Maksimum Eşzamanlı Açık İşlem Limiti)
        active_count = get_active_positions_count()
        if active_count >= MAX_CONCURRENT_TRADES:
            msg = f"Maksimum {MAX_CONCURRENT_TRADES} açık pozisyon kotası dolu ({active_count}/{MAX_CONCURRENT_TRADES}). Sermaye koruma kalkanı aktif."
            print(f"🛡️ [Kasa Kalkanı] {msg} Yeni pozisyon aranmayacak.")
            add_scanner_log("KASA KALKANI", "PROTECTED", msg, "Yeni Fırsat Arama Kilitlendi")
            return

        # 1.6 GÜNLÜK AZAMİ KAYIP SİGORTASI (Daily Drawdown Circuit Breaker)
        from config import (
            ENABLE_CIRCUIT_BREAKER,
            DAILY_BASE_MAX_TRADES,
            PROFIT_STEP_FOR_BONUS_TRADES,
            BONUS_TRADES_PER_STEP,
            DAILY_MAX_DRAWDOWN_USDT,
            DAILY_TRAILING_PROFIT_LOCK_ENABLED
        )
        from core.database import (
            get_today_trades_count,
            get_today_trades_count_by_timeframe,
            get_today_net_dollar_loss,
            get_today_net_dollar_pnl,
            get_and_update_today_peak_profit,
            get_open_unprotected_risk_usdt,
            get_current_equity
        )

        if ENABLE_CIRCUIT_BREAKER:
            today_loss = get_today_net_dollar_loss()
            open_risk = get_open_unprotected_risk_usdt()
            effective_max_dd = max(DAILY_MAX_DRAWDOWN_USDT, round(get_current_equity() * 0.035, 2))
            if today_loss >= effective_max_dd:
                msg = (
                    f"Günlük azami kayıp limiti (${effective_max_dd:.2f}) aşıldı! "
                    f"Bugünkü net zarar: -${today_loss:.2f}. Acil durum sigortası devreye girdi, "
                    f"tüm yeni girişler gün sonuna kadar donduruldu."
                )
                print(f"🛑 [Acil Durum Sigortası / Circuit Breaker] {msg}")
                add_scanner_log("CIRCUIT BREAKER", "PROTECTED", msg, "Acil Durum Sermaye Sigortası")
                return
            if today_loss > 0 and (today_loss + open_risk) >= (effective_max_dd * 1.15):
                msg = (
                    f"Birleşik Risk Kalkanı devrede! Gerçekleşmiş zarar (-${today_loss:.2f}) + BE+ olmamış açık risk "
                    f"(${open_risk:.2f}) günlük sigortaya (${effective_max_dd:.2f}) dayandı. Mevcut pozisyonlar korunana kadar yeni giriş durduruldu."
                )
                print(f"🛡️ [Birleşik Risk Kalkanı] {msg}")
                add_scanner_log("RİSK KALKANI", "PROTECTED", msg, "Açık+Kapanmış Risk Koruması")
                return

        today_pnl = get_today_net_dollar_pnl()

        # 1.7 GÜNLÜK ZİRVE KÂR KİLİDİ (Trailing Daily High-Water Mark Shield)
        if DAILY_TRAILING_PROFIT_LOCK_ENABLED:
            peak_profit, profit_floor, is_locked = get_and_update_today_peak_profit(today_pnl)
            if is_locked:
                msg = (
                    f"🏆 Günlük Zirve Kâr Kilidi Aktif! Bugün en yüksek +${peak_profit:.2f} kâr görüldü. "
                    f"Piyasa geri çekilmesinde günün taban kârı (+${profit_floor:.2f}) korumaya alındı "
                    f"(Anlık Net Kâr: +${today_pnl:.2f}). Kârın geri verilmemesi için tarama gün sonuna kadar kilitlendi."
                )
                print(f"🔒 [Zirve Kâr Kilidi / Trailing Profit Shield] {msg}")
                add_scanner_log("KÂR KİLİDİ", "PROFIT_LOCKED", msg, "Gün Sonu Kâr Sigortası")
                return

        # 1.8 VADEYE / ZAMAN DİLİMİNE ÖZEL BAĞIMSIZ GÜNLÜK İŞLEM KOTALARI
        from config import (
            DAILY_MAX_TRADES_15M, DAILY_MAX_TRADES_30M, DAILY_MAX_TRADES_1H,
            PROFIT_STEP_FOR_BONUS_TRADES, BONUS_TRADES_PER_STEP
        )
        bonus_slots = 0
        if today_pnl > 0 and PROFIT_STEP_FOR_BONUS_TRADES > 0:
            bonus_slots = int(today_pnl // PROFIT_STEP_FOR_BONUS_TRADES) * BONUS_TRADES_PER_STEP

        max_15m = DAILY_MAX_TRADES_15M + bonus_slots
        max_30m = DAILY_MAX_TRADES_30M + bonus_slots
        max_1h = DAILY_MAX_TRADES_1H + bonus_slots

        today_counts = get_today_trades_count_by_timeframe()
        c_15m = today_counts.get("15m", 0)
        c_30m = today_counts.get("30m", 0)
        c_1h = today_counts.get("1h", 0)

        allowed_timeframes = []
        quota_parts = []

        if c_15m < max_15m:
            allowed_timeframes.append("15m")
            quota_parts.append(f"⚡ 15m: {c_15m}/{max_15m}")
        else:
            quota_parts.append(f"⚡ 15m: DOLU ({c_15m}/{max_15m})")

        if c_30m < max_30m:
            allowed_timeframes.append("30m")
            quota_parts.append(f"🎯 30m: {c_30m}/{max_30m}")
        else:
            quota_parts.append(f"🎯 30m: DOLU ({c_30m}/{max_30m})")

        if c_1h < max_1h:
            allowed_timeframes.append("1h")
            quota_parts.append(f"👑 1h: {c_1h}/{max_1h}")
        else:
            quota_parts.append(f"👑 1h: DOLU ({c_1h}/{max_1h})")

        quota_summary = " | ".join(quota_parts)
        print(f"🛡️ [Vade Kotaları] {quota_summary} (Kâr Bonusu: +{bonus_slots} slot)")

        if not allowed_timeframes:
            msg = (
                f"Tüm vadelerin günlük işlem kotaları doldu! ({quota_summary}). "
                f"Bugünkü Net Kâr: ${today_pnl:+.2f}. Komisyon ve sermaye koruma kalkanı devrede."
            )
            print(f"🛑 [Keskin Nişancı Kotası] {msg} Bugün yeni işlem aranmayacak.")
            add_scanner_log("GÜNLÜK KOTA", "PROTECTED", msg, "Tüm Zaman Dilimleri Dolu")
            return

        slots_left = MAX_CONCURRENT_TRADES - active_count
        print(f"🛡️ [Kasa Kalkanı] Aktif Pozisyon: {active_count}/{MAX_CONCURRENT_TRADES} | Kalan İşlem Kotası: {slots_left}")

        # 1.9 KÜRESEL İŞLEM TEMPOSU KORUMASI (Son işlemden bu yana min 12 dk bekleme -> kota erimesini önler)
        try:
            from core.database import get_last_signal_created_at
            last_created = str(get_last_signal_created_at() or "")[:19]
            if last_created:
                last_dt = datetime.strptime(last_created, "%Y-%m-%d %H:%M:%S")
                mins_since = (datetime.now() - last_dt).total_seconds() / 60.0
                if 0 <= mins_since < 12.0:
                    wait_min = int(12.0 - mins_since) + 1
                    msg_pace = f"Son işlemden bu yana 12 dk soğuma/tempo koruması aktif ({wait_min} dk kaldı)."
                    print(f"⏱️ [Tempo Koruması] {msg_pace}")
                    add_scanner_log("TEMPO KALKANI", "PROTECTED", msg_pace, "Peş Peşe İşlem Engellendi")
                    return
        except Exception:
            pass

        # 2. BTC Piyasa Çöküş ve Ölü Piyasa Kalkanı Kontrolü
        btc_regime = self.client.get_btc_regime()
        print(f"🛡️ [BTC Kalkanı] Durum: {btc_regime['status']} | {btc_regime.get('summary', '')}")
        if btc_regime.get("block_all_entries", False):
            summary_msg = btc_regime.get("summary", "BTC ölü testere piyasada, tarama donduruldu.")
            detailed_msg = btc_regime.get("detailed_reason") or summary_msg
            print(f"🛑 [BTC Ölü Piyasa Freni] {summary_msg}")
            add_scanner_log("BTC KALKANI", "PROTECTED", detailed_msg, "Sermaye Koruma Modu (0 Risk)")
            if "CRASH" not in str(btc_regime.get("status", "")).upper():
                self._try_open_stat_arb_pair(slots_left, allowed_timeframes)
            return

        # 2.5 SEMBOL + YÖN BAZLI SOĞUMA MOLASI: Aday döngüsünde TA kurulumu sonrası kontrol edilir (Global dondurma kaldırıldı)

        # 3. Binance Futures USDT.P çiftlerini tara (Akıllı 200+ Parite Rotasyonu & Cooldown Koruması)
        print("📡 [Scanner Ajanı] Binance Futures USDT.P çiftleri taranıyor...")
        from core.database import get_recently_traded_symbols
        # Açık olan veya son 45 dk içinde açılıp kapanmış coinleri al (aynı coinleri tekrar denememek için)
        excluded_symbols = get_recently_traded_symbols(within_minutes=45)

        candidates = self.scanner.scan_opportunities(limit=18, exclude_symbols=excluded_symbols)

        # Canlı WebSocket Balina & Sıcak Parite Akışı Kontrolü
        hot_items = pop_hot_symbols()
        if hot_items:
            hot_syms = [h["symbol"] for h in hot_items if h["symbol"] not in excluded_symbols]
            if hot_syms:
                print(f"🔥 [WebSocket Canlı Balina Akışı] {len(hot_syms)} sıcak parite analiz sırasına eklendi: {', '.join(hot_syms[:4])}")
                hot_tickers = [{"symbol": s} for s in hot_syms]
                candidates = hot_tickers + [c for c in candidates if c["symbol"] not in hot_syms]

        print(f"⚡ 200+ likit parite arasından seçilen {len(candidates)} farklı parite analiz havuzuna alındı.")

        found_setups_count = 0
        shortlist_candidates = []

        # 4. Haber masasını güncelle (Sağ Alttaki Haber Masası için)
        try:
            self.news_agent.fetch_latest_market_news()
        except Exception:
            pass

        # 5. BİRİNCİ AŞAMA: Tüm pariteleri baştan sona tara, önüne gelen ilk pariteye atlama, kaliteli olanları Aday Havuzunda topla
        for ticker in candidates:
            symbol = ticker["symbol"]
            if symbol in excluded_symbols:
                continue  # Zaten açık veya yakın zamanda denenmişse tekrar girme

            try:
                # Kotası dolmamış vadeleri tara (Kotası biten vade için boşuna REST API ve tarama yapma)
                candles_15m = []
                candles_30m = []
                candles_1h = []

                if "15m" in allowed_timeframes:
                    candles_15m = self.client.get_klines(symbol, interval="15m", limit=100)
                    if len(candles_15m) < 35:
                        add_scanner_log(symbol, "REJECTED", "Yetersiz 15m mum verisi")
                        continue

                if "30m" in allowed_timeframes:
                    candles_30m = self.client.get_klines(symbol, interval="30m", limit=80)
                    if len(candles_30m) < 35 and "15m" not in allowed_timeframes and "1h" not in allowed_timeframes:
                        add_scanner_log(symbol, "REJECTED", "Yetersiz 30m mum verisi")
                        continue

                # 1h mumları: 1h kotası açıksa veya 15m/30m için makro trend teyidi gerekiyorsa çek
                if "1h" in allowed_timeframes or ("15m" in allowed_timeframes) or ("30m" in allowed_timeframes):
                    candles_1h = self.client.get_klines(symbol, interval="1h", limit=80)
                    if "1h" in allowed_timeframes and "15m" not in allowed_timeframes and "30m" not in allowed_timeframes:
                        if len(candles_1h) < 20:
                            add_scanner_log(symbol, "REJECTED", "Yetersiz 1h mum verisi")
                            continue

                if not candles_15m and not candles_30m and not candles_1h:
                    add_scanner_log(symbol, "REJECTED", "Kotası açık vadeye ait veri yok")
                    continue

                # Ajan 1: 3-Zaman Dilimli Çoklu-Vade SMC İncelemesi (15m Kısa • 30m Orta • 1h Uzun Vade)
                ta_setup, ta_reason = self.ta_agent.analyze_multi_horizon(
                    symbol, candles_15m, candles_30m, candles_1h, allowed_timeframes=allowed_timeframes
                )
                if not ta_setup:
                    add_scanner_log(symbol, "REJECTED", ta_reason)
                    continue

                # 4h Makro Pusula & Yapısal Duvar Kalkanı (Sadece TA'yı geçen adaylar için 4h kontrolü)
                try:
                    candles_4h = self.client.get_klines(symbol, interval="4h", limit=60)
                    is_macro_ok, macro_reason, _ = self.ta_agent.check_4h_macro_compass(ta_setup, candles_4h)
                    if not is_macro_ok:
                        self._record_shadow_rejection(symbol, ta_setup, "4H_MACRO", macro_reason)
                        add_scanner_log(symbol, "REJECTED", macro_reason)
                        continue
                except Exception:
                    pass

                # Open Interest (OI) + Likidasyon Şelalesi + Basis + Emir Defteri (OBI) Mikroyapı Kalkanı
                try:
                    oi_data = self.client.get_open_interest_delta(symbol, period="15m")
                    if oi_data and len(candles_15m) >= 6:
                        closed_15 = candles_15m[:-1]
                        p_ref = float(closed_15[-4]["open"])
                        p_end = float(closed_15[-1]["close"])
                        p_chg = ((p_end - p_ref) / p_ref) * 100.0 if p_ref > 0 else 0.0
                        oi_chg = float(oi_data.get("oi_change_pct", 0.0))
                        c_dir = ta_setup.get("direction", "LONG")
                        c_score = int(ta_setup.get("confluence_score", 0))

                        # Son kapanan mum fitil analizi (Likidasyon Şelalesi Dönüşü tespiti)
                        lc = closed_15[-1]
                        lc_body = max(1e-9, abs(float(lc["close"]) - float(lc["open"])))
                        lower_wick = min(float(lc["open"]), float(lc["close"])) - float(lc["low"])
                        upper_wick = float(lc["high"]) - max(float(lc["open"]), float(lc["close"]))
                        is_cascade_rev = (
                            oi_chg <= -3.0 and (
                                (c_dir == "LONG" and lower_wick >= lc_body * 1.5) or
                                (c_dir == "SHORT" and upper_wick >= lc_body * 1.5)
                            )
                        )

                        if is_cascade_rev:
                            ta_setup["confluence_score"] = min(100, c_score + 6)
                            ta_setup["ta_reasons"] = f"{ta_setup.get('ta_reasons', '')} | 💥 Likidasyon Şelalesi Dönüşü (OI %{oi_chg:.1f}, +6)".strip(" |")
                        elif c_dir == "LONG" and p_chg >= 0.50 and oi_chg <= -1.20 and c_score < 84:
                            self._record_shadow_rejection(symbol, ta_setup, "OI_DELTA", "Sahte Kirilim / Short Squeeze")
                            add_scanner_log(symbol, "REJECTED", f"📌 <strong>Mevcut Durum:</strong> Sahte Kırılım / Short Squeeze (Fiyat +%{p_chg:.2f}, OI -%{abs(oi_chg):.2f}).<br>⛔ <strong>Giriş Yapılmama Nedeni:</strong> Yeni alım gelmeden yalnızca short stopları patladığı için geri dönüş riski yüksek.")
                            continue
                        elif c_dir == "SHORT" and p_chg <= -0.50 and oi_chg <= -1.20 and c_score < 84:
                            self._record_shadow_rejection(symbol, ta_setup, "OI_DELTA", "Tukenmis Long Tasfiyesi")
                            add_scanner_log(symbol, "REJECTED", f"📌 <strong>Mevcut Durum:</strong> Tükenmiş Long Tasfiyesi (Fiyat %{p_chg:.2f}, OI -%{abs(oi_chg):.2f}).<br>⛔ <strong>Giriş Yapılmama Nedeni:</strong> Tasfiye tamamlanırken dipten tepki sıçraması riski yüksek.")
                            continue
                        elif oi_chg >= 0.80:
                            ta_setup["confluence_score"] = min(100, c_score + 4)
                            ta_setup["ta_reasons"] = f"{ta_setup.get('ta_reasons', '')} | 📈 Organik OI (+%{oi_chg:.1f}, +4)".strip(" |")

                    # Spot-Vadeli Basis & Kalabalık Pozisyon Karşıtı Filtre
                    basis_info = (self.client.get_all_premium_basis() or {}).get(symbol)
                    if basis_info:
                        b_pct = float(basis_info.get("basis_pct", 0.0))
                        fr_pct = float(basis_info.get("funding_rate_pct", 0.0))
                        c_dir = ta_setup.get("direction", "LONG")
                        c_score = int(ta_setup.get("confluence_score", 0))
                        if b_pct >= 0.25 and fr_pct >= 0.05:
                            if c_dir == "LONG" and c_score < 84:
                                add_scanner_log(symbol, "REJECTED", f"📌 <strong>Mevcut Durum:</strong> Aşırı Pozitif Basis (+%{b_pct:.2f}, Fonlama +%{fr_pct:.3f}).<br>⛔ <strong>Giriş Yapılmama Nedeni:</strong> Kalabalık LONG coşkusu spottan koptu; tepe yakalanma riski yüksek.")
                                continue
                            elif c_dir == "SHORT":
                                ta_setup["confluence_score"] = min(100, c_score + 5)
                                ta_setup["ta_reasons"] = f"{ta_setup.get('ta_reasons', '')} | 📉 Pozitif Basis Karşıtı (+5)".strip(" |")
                        elif b_pct <= -0.25 and fr_pct <= -0.05:
                            if c_dir == "SHORT" and c_score < 84:
                                add_scanner_log(symbol, "REJECTED", f"📌 <strong>Mevcut Durum:</strong> Aşırı Negatif Basis (%{b_pct:.2f}, Fonlama %{fr_pct:.3f}).<br>⛔ <strong>Giriş Yapılmama Nedeni:</strong> Kalabalık SHORT paniğinde short squeeze riski yüksek.")
                                continue
                            elif c_dir == "LONG":
                                ta_setup["confluence_score"] = min(100, c_score + 5)
                                ta_setup["ta_reasons"] = f"{ta_setup.get('ta_reasons', '')} | 📈 Negatif Basis Squeeze (+5)".strip(" |")

                    obi_data = self.client.get_order_book_imbalance(symbol, limit=20)
                    if obi_data:
                        ratio = float(obi_data.get("imbalance_ratio", 1.0))
                        c_dir = ta_setup.get("direction", "LONG")
                        c_score = int(ta_setup.get("confluence_score", 0))
                        if c_dir == "LONG" and ratio <= 0.28 and c_score < 84:
                            self._record_shadow_rejection(symbol, ta_setup, "OBI", f"Satis Duvari OBI={ratio:.2f}")
                            add_scanner_log(symbol, "REJECTED", f"📌 <strong>Mevcut Durum:</strong> Tahtada Ağır Satış Duvarı (OBI: {ratio:.2f}).<br>⛔ <strong>Giriş Yapılmama Nedeni:</strong> Emir defterinde satış baskısı alışların 3.5x üzerinde; tepe duvarı riski.")
                            continue
                        if c_dir == "SHORT" and ratio >= 3.50 and c_score < 84:
                            self._record_shadow_rejection(symbol, ta_setup, "OBI", f"Alis Duvari OBI={ratio:.2f}")
                            add_scanner_log(symbol, "REJECTED", f"📌 <strong>Mevcut Durum:</strong> Tahtada Ağır Alış Duvarı (OBI: {ratio:.2f}).<br>⛔ <strong>Giriş Yapılmama Nedeni:</strong> Emir defterinde alış desteği satışların 3.5x üzerinde; dip duvarı riski.")
                            continue
                except Exception:
                    pass

                # Sembol + Yön Bazlı Soğuma Molası (Aynı paritede aynı yönde intikam işlemini önle, diğer pariteleri kilitleme)
                try:
                    from core.database import get_last_loss_for
                    from config import POST_LOSS_COOLDOWN_MINUTES
                    last_loss_sym_dir = get_last_loss_for(symbol, ta_setup["direction"])
                    if last_loss_sym_dir:
                        last_loss_dt = datetime.strptime(last_loss_sym_dir[:19], "%Y-%m-%d %H:%M:%S")
                        elapsed_min = (datetime.now() - last_loss_dt).total_seconds() / 60.0
                        if elapsed_min < POST_LOSS_COOLDOWN_MINUTES:
                            rem_min = int(POST_LOSS_COOLDOWN_MINUTES - elapsed_min) + 1
                            msg = f"{symbol} {ta_setup['direction']} son zarar sonrası soğuma molasında ({rem_min} dk kaldı)."
                            add_scanner_log(symbol, "PROTECTED", msg, "Sembol+Yön Soğuma Molası")
                            continue
                except Exception:
                    pass

                # Ajan 2: Fonlama Oranı, Derinlik (Spread) ve Haber Analizi (Haber Kararlandırma Konseyi)
                funding_data = self.client.get_funding_rate(symbol)
                book_ticker = self.client.get_book_ticker(symbol)
                news_analysis = self.news_agent.analyze_catalyst(symbol, ta_setup["direction"], funding_data)

                # Haber Kararlandırma Konseyi Veto Kalkanı (Kara Kuğu, Hack, SEC vb.)
                if news_analysis and news_analysis.get("is_vetoed"):
                    add_scanner_log(
                        symbol,
                        "REJECTED",
                        news_analysis.get("veto_reason", "Haber Konseyi Veto Etti"),
                        news_analysis.get("summary", "")[:75]
                    )
                    continue

                # Ajan 3: Risk Şefi (Dinamik Bileşik Kasa, 10x/20x, BTC Kalkanı, Slippage ve Fonlama denetimi)
                from core.database import get_active_and_pending_signals, get_current_equity
                active_sigs = get_active_and_pending_signals() or []
                current_equity = get_current_equity()
                is_approved, risk_report = self.risk_officer.evaluate(
                    ta_setup, news_analysis, ticker, btc_regime,
                    funding_data=funding_data,
                    book_ticker=book_ticker,
                    active_signals=active_sigs,
                    current_equity=current_equity,
                    client=self.client
                )
                if not is_approved:
                    self._record_shadow_rejection(symbol, ta_setup, "RISK_CHIEF", risk_report.get("reason", "Risk"))
                    add_scanner_log(symbol, "REJECTED", risk_report.get("reason", "Risk kurallarına uymadı"))
                    continue

                # Ajan 3.2: Kuant & Monte Carlo Fiyat Yolu Simülasyon Ajanı (10,000 Bağımsız Yol)
                chosen_tf = ta_setup.get("timeframe", "15m")
                if chosen_tf == "1h" and candles_1h and len(candles_1h) >= 15:
                    sim_candles = candles_1h
                    sim_horizon = 48  # 48 saatlik projeksiyon
                elif chosen_tf == "30m" and candles_30m and len(candles_30m) >= 15:
                    sim_candles = candles_30m
                    sim_horizon = 36  # 18 saatlik projeksiyon
                else:
                    sim_candles = candles_15m
                    sim_horizon = 24  # 6 saatlik projeksiyon

                quant_sim = self.quant_sim.simulate_setup(
                    symbol, ta_setup, sim_candles, num_simulations=10000, horizon_bars=sim_horizon
                )
                win_pct = quant_sim.get("win_probability_pct", 0.0)

                if not quant_sim.get("is_approved", False):
                    self._record_shadow_rejection(symbol, ta_setup, "MONTE_CARLO", f"Win %{win_pct:.1f}")
                    add_scanner_log(
                        symbol,
                        "REJECTED",
                        f"Kuant Simülasyon Veto Etti (10,000 Yol: TP İhtimali %{win_pct:.1f} < %{self.quant_sim.win_threshold_pct:.1f})",
                        f"Stop Loss Riski: %{quant_sim.get('loss_probability_pct', 0.0):.1f}"
                    )
                    continue

                # Ajan 3.5: AI Baş Analisti & Yatırım Komitesi Tartışması (Adversarial Multi-Agent Chamber)
                ai_verdict = self.ai_analyst.evaluate_setup(
                    ta_setup, risk_report, news_analysis, btc_regime, ticker, funding_data, quant_sim=quant_sim
                )
                debate_data = ai_verdict.get("debate_data", {})

                if not ai_verdict.get("ai_approved", True):
                    critique = ai_verdict.get('ai_critique', '')
                    self._record_shadow_rejection(symbol, ta_setup, "AI_COMMITTEE", critique[:120])
                    add_scanner_log(symbol, "REJECTED", f"Yatırım Komitesi Veto Etti ({ai_verdict.get('ai_confidence', 0)}/10)", critique[:60])
                    continue

                # Onaylanan parametreleri hazırla
                leverage = risk_report["leverage"]
                ta_setup["leverage"] = leverage
                ta_setup["risk_grade"] = risk_report["risk_grade"]

                # FIRSAT KALİTE SKORU HESAPLA (0 - 100 Puan Ağırlıklı Sistem)
                mc_win_pct = float(quant_sim.get("win_probability_pct", 50.0))
                mc_score = (mc_win_pct / 100.0) * 35.0  # %35 Kuant Monte Carlo Gücü

                ai_conf = float(ai_verdict.get("ai_confidence", 5))
                ai_score = (ai_conf / 10.0) * 25.0      # %25 Komite Konsensüsü

                rr = float(ta_setup.get("risk_reward", 2.0))
                rr_capped = max(1.5, min(rr, 4.0))
                rr_score = ((rr_capped - 1.5) / 2.5) * 20.0  # %20 Risk/Ödül Oranı

                grade = risk_report.get("risk_grade", "A")
                grade_score = 20.0 if grade == "A+" else (16.0 if grade == "A" else 10.0)  # %20 Risk Notu

                total_quality_score = round(mc_score + ai_score + rr_score + grade_score, 1)
                horizon_badge = ta_setup.get("trade_horizon", "Kısa Vade (15m)")
                cand_tf = ta_setup.get("timeframe", "15m").lower()

                # Aday Havuzuna Ekle (Hemen işleme girme, diğer tüm coinler bitene kadar aklında tut!)
                shortlist_candidates.append({
                    "symbol": symbol,
                    "quality_score": total_quality_score,
                    "ta_setup": ta_setup,
                    "risk_report": risk_report,
                    "news_analysis": news_analysis,
                    "quant_sim": quant_sim,
                    "ai_verdict": ai_verdict,
                    "debate_data": debate_data,
                    "candles_15m": candles_15m,
                    "candles": candles_1h if cand_tf == '1h' else (candles_30m if cand_tf == '30m' else candles_15m),
                    "ticker": ticker,
                    "timeframe": cand_tf,
                    "horizon_badge": horizon_badge,
                    "leverage": leverage
                })

                add_scanner_log(
                    symbol,
                    "PENDING_ENTRY",
                    f"🎯 Aday Havuzuna Alındı (Kalite: {total_quality_score}/100 | Komite: {ai_conf:.0f}/10 | Win: %{mc_win_pct:.1f})",
                    f"Tüm pariteler tarandıktan sonra nihai eleme turnuvasında yarışacak"
                )
                print(f"🎯 [{symbol}] Aday Havuzuna Alındı! Kalite Skoru: {total_quality_score}/100 (Komite: {ai_conf:.0f}/10, Win: %{mc_win_pct:.1f}, RR: {rr:.1f})")

            except Exception as e:
                print(f"⚠️ [{symbol}] Analiz hatası: {e}")
                continue
            finally:
                time.sleep(0.08)

        # =========================================================================
        # 🏆 İKİNCİ AŞAMA: TÜM TARAMA BİTTİKTEN SONRA TURNUVA SIRALAMASI & İKİNCİ TEYİT TARAMASI
        # =========================================================================
        if not shortlist_candidates:
            print("💤 Bu döngüde kurallara tam uyan yönlü A+ kurulum bulunamadı (Piyasa-Nötr İkili Arbitraj kontrol ediliyor)...")
            self._try_open_stat_arb_pair(slots_left, allowed_timeframes)
        else:
            # 1. Adayları Kalite Skoruna Göre En İyiden En Düşüğe Sırala (Tournament Leaderboard)
            shortlist_candidates.sort(key=lambda x: x["quality_score"], reverse=True)

            print(f"\n🏆 [Turnuva Masası] Tüm paritelerin 1. taraması tamamlandı! {len(shortlist_candidates)} aday fırsat yarışıyor:")
            for rank, cand in enumerate(shortlist_candidates, 1):
                tf = cand["timeframe"].upper()
                dir_ = cand["ta_setup"]["direction"]
                score = cand["quality_score"]
                conf = cand["ai_verdict"].get("ai_confidence", 0)
                win_p = cand["quant_sim"].get("win_probability_pct", 0.0)
                rr_val = cand["ta_setup"].get("risk_reward", 0.0)
                print(f"   #{rank} {cand['symbol']} -> Kalite: {score}/100 | {tf} {dir_} | RR: {rr_val:.1f} | Komite: {conf}/10 | MC Win: %{win_p:.1f}")

            # 2. İkinci Teyit Taraması ve Seçim Döngüsü (Fresh Re-Validation Scan)
            from core.binance_streamer import get_live_price
            for cand in shortlist_candidates:
                if found_setups_count >= min(1, slots_left):
                    print(f"🛡️ [Kasa & Seçicilik Kalkanı] Bu döngü için en iyi şampiyon açıldı (1 işlem/döngü sınırı). Turnuva tamamlandı.")
                    break

                if float(cand.get("quality_score") or 0.0) < 68.0:
                    add_scanner_log(
                        cand["symbol"],
                        "REJECTED",
                        f"Turnuva Kalite Barajı Altında ({cand['quality_score']}/100 < 68.0)",
                        "Yüksek Seçicilik Kalkanı"
                    )
                    continue

                cand_tf = cand["timeframe"]
                if cand_tf not in allowed_timeframes:
                    add_scanner_log(
                        cand["symbol"],
                        "REJECTED",
                        f"Vade Kotası Doldu ({cand_tf.upper()} kotası dolu olduğu için turnuvada elendi)",
                        f"Turnuva Skoru: {cand['quality_score']}/100"
                    )
                    continue

                symbol = cand["symbol"]
                ta_setup = cand["ta_setup"]
                risk_report = cand["risk_report"]
                news_analysis = cand["news_analysis"]
                quant_sim = cand["quant_sim"]
                ai_verdict = cand["ai_verdict"]
                debate_data = cand["debate_data"]
                candles_15m = cand["candles_15m"]
                horizon_badge = cand["horizon_badge"]
                leverage = cand["leverage"]

                # --- İKİNCİ TEYİT TARAMASI (Canlı Fiyat, Slippage ve Tahta Denetimi) ---
                print(f"🔬 [İkinci Teyit Taraması] Turnuva Lideri: {symbol} canlı piyasada teyit ediliyor...")
                fresh_ws_price = get_live_price(symbol)
                fresh_book = None
                try:
                    fresh_book = self.client.get_book_ticker(symbol)
                except Exception:
                    pass

                fresh_price = fresh_ws_price
                if not fresh_price and fresh_book:
                    fresh_price = float(fresh_book.get("askPrice" if ta_setup["direction"] == "LONG" else "bidPrice") or 0.0)
                if not fresh_price or fresh_price <= 0:
                    fresh_price = float(ta_setup["current_price"])

                # Teyit 1: Fiyat Giriş Bölgesini Aştı mı & Canlı Dolum Fiyatıyla Net R:R Korunuyor mu?
                entry_min = float(ta_setup["entry_min"])
                entry_max = float(ta_setup["entry_max"])
                sl_px = float(ta_setup["stop_loss"])
                tp1_px = float(ta_setup["take_profit_1"])
                orig_entry = float(ta_setup.get("current_price") or ((entry_min + entry_max) / 2.0))
                orig_sl_dist = abs(orig_entry - sl_px)
                chase_tol = min(orig_entry * 0.0035, orig_sl_dist * 0.15) if orig_sl_dist > 0 else orig_entry * 0.0020
                is_chasing = False
                chase_reason = ""

                if ta_setup["direction"] == "LONG":
                    if fresh_price > entry_max + chase_tol:
                        is_chasing = True
                        chase_reason = f"Fiyat SL-oranlı kovalama sınırını aştı (Canlı: ${fresh_price}, Tavan: ${entry_max + chase_tol:.6f})"
                    elif fresh_price <= sl_px:
                        is_chasing = True
                        chase_reason = f"Fiyat stop seviyesinin altına indi (Canlı: ${fresh_price}, SL: ${sl_px})"
                else:  # SHORT
                    if fresh_price < entry_min - chase_tol:
                        is_chasing = True
                        chase_reason = f"Fiyat SL-oranlı kovalama sınırını aştı (Canlı: ${fresh_price}, Taban: ${entry_min - chase_tol:.6f})"
                    elif fresh_price >= sl_px:
                        is_chasing = True
                        chase_reason = f"Fiyat stop seviyesinin üzerine çıktı (Canlı: ${fresh_price}, SL: ${sl_px})"

                if not is_chasing:
                    live_sl_dist = abs(fresh_price - sl_px)
                    live_tp1_dist = (tp1_px - fresh_price) if ta_setup["direction"] == "LONG" else (fresh_price - tp1_px)
                    live_rr = (live_tp1_dist / live_sl_dist) if live_sl_dist > 0 else 0.0
                    if live_rr < 1.65:
                        is_chasing = True
                        chase_reason = f"Canlı dolum fiyatında R:R bozuldu ({live_rr:.2f} < 1.65)"
                    else:
                        ta_setup["risk_reward"] = round(live_rr, 2)

                if is_chasing:
                    self._record_shadow_rejection(symbol, ta_setup, "LIVE_RR", chase_reason)
                    print(f"⚠️ [{symbol}] İkinci Teyit Başarısız: {chase_reason}. Fırsat elendi, sıradaki adaya geçiliyor.")
                    add_scanner_log(
                        symbol,
                        "TIMEOUT",
                        f"2. Teyitte Elendi: {chase_reason}",
                        "Kovalama ve R:R Bozulması Engellendi"
                    )
                    continue

                # Teyit 2: Tahta Spread Denetimi (SL Mesafesine Oranlı Sıkı Spread Koruması)
                if fresh_book and fresh_book.get("bidPrice") and fresh_book.get("askPrice"):
                    bid = float(fresh_book["bidPrice"])
                    ask = float(fresh_book["askPrice"])
                    if bid > 0 and ask > 0:
                        spread_pct = ((ask - bid) / bid) * 100.0
                        sl_pct_dist = (abs(fresh_price - sl_px) / fresh_price) * 100.0 if fresh_price > 0 else 1.0
                        max_spread_pct = min(0.08, max(0.03, round(sl_pct_dist * 0.08, 4)))
                        if spread_pct > max_spread_pct:
                            self._record_shadow_rejection(symbol, ta_setup, "SPREAD", f"Spread %{spread_pct:.3f} > %{max_spread_pct:.3f}")
                            print(f"⚠️ [{symbol}] Geniş Spread (%{spread_pct:.3f} > %{max_spread_pct:.3f}). İkinci taramada elendi.")
                            add_scanner_log(symbol, "REJECTED", f"2. Teyit: Geniş Spread (%{spread_pct:.3f} > %{max_spread_pct:.3f})", "SL-Oranlı Kayma Riski")
                            continue

                # Teyit 3: Güncel BTC Ani Çöküş & Yönlü Ralli/Squeeze Denetimi
                fresh_btc = self.client.get_btc_regime()
                if fresh_btc.get("block_all_entries", False):
                    print(f"🛑 [BTC Acil Fren] İkinci teyit anında BTC çöküş alarmı verdi: {fresh_btc.get('summary')}")
                    add_scanner_log(symbol, "PROTECTED", "İkinci teyitte BTC Çöküş Alarmı", "Sermaye Koruma Devrede")
                    break
                if ta_setup["direction"] == "LONG" and fresh_btc.get("block_longs", False):
                    print(f"🛑 [{symbol}] 2. teyitte BTC düşüş trendi nedeniyle LONG engellendi.")
                    add_scanner_log(symbol, "REJECTED", "2. Teyit: BTC Düşüş Rejimi (LONG Engelli)", "Yönlü BTC Koruması")
                    continue
                if ta_setup["direction"] == "SHORT" and fresh_btc.get("block_shorts", False):
                    print(f"🛑 [{symbol}] 2. teyitte BTC yükseliş rallisi (Squeeze) nedeniyle SHORT engellendi.")
                    add_scanner_log(symbol, "REJECTED", "2. Teyit: BTC Ralli Rejimi (SHORT Engelli)", "Yönlü BTC Koruması")
                    continue

                # =========================================================================
                # 🎉 İKİNCİ TEYİT BAŞARILI: İŞLEMİ AÇ VE SİSTEME KAYDET (EXECUTION)
                # =========================================================================
                ta_setup["leverage"] = leverage
                ta_setup["risk_grade"] = risk_report["risk_grade"]

                # Canlı dolum fiyatına göre sert risk tavanı (komisyon dahil risk_usd'yi asla aşma)
                if fresh_price > 0 and sl_px > 0:
                    live_sl_pct = (abs(fresh_price - sl_px) / fresh_price) * 100.0
                    total_loss_frac = (live_sl_pct * leverage + 0.10 * leverage) / 100.0
                    if total_loss_frac > 0:
                        risk_report["allocated_margin_usdt"] = round(
                            min(float(risk_report["allocated_margin_usdt"]), float(risk_report["risk_usd"]) / total_loss_frac),
                            1
                        )

                signal_data = {
                    "symbol": symbol,
                    "direction": ta_setup["direction"],
                    "timeframe": cand_tf,
                    "trade_horizon": horizon_badge,
                    "leverage": leverage,
                    "entry_min": ta_setup["entry_min"],
                    "entry_max": ta_setup["entry_max"],
                    "actual_entry_price": fresh_price,
                    "entry_limit_2": ta_setup.get("entry_limit_2", 0.0),
                    "stop_loss": ta_setup["stop_loss"],
                    "take_profit_1": ta_setup["take_profit_1"],
                    "take_profit_2": ta_setup["take_profit_2"],
                    "risk_reward": ta_setup["risk_reward"],
                    "risk_grade": risk_report["risk_grade"],
                    "sl_pct": ta_setup["sl_pct"],
                    "tp1_pct": ta_setup["tp1_pct"],
                    "tp2_pct": ta_setup["tp2_pct"],
                    "allocated_margin_usdt": risk_report["allocated_margin_usdt"],
                    "risk_usd": risk_report["risk_usd"],
                    "news_summary": f"[{horizon_badge}] {news_analysis.get('summary', '')} | 🏆 Turnuva: {cand['quality_score']}/100",
                    "ta_reasons": ta_setup["ta_reasons"],
                    "ai_verdict": ai_verdict,
                    "quant_sim": quant_sim,
                    "debate_json": debate_data,
                    "chart_entry_png": ""
                }

                sig_id = save_signal(signal_data)
                add_stream_symbol(symbol)
                excluded_symbols.add(symbol)
                found_setups_count += 1

                add_scanner_log(
                    symbol,
                    "APPROVED",
                    f"🏆 Turnuva 1.'si Seçildi (Kalite: {cand['quality_score']}/100) | [{horizon_badge}] {leverage}x {ta_setup['direction']} (Giriş: ${fresh_price})",
                    f"2. Teyit Başarılı! Net SL: -%{risk_report['margin_risk_pct']}, Net TP: +%{risk_report['margin_tp1_pct']}"
                )
                print(f"🚀 [İşlem Açıldı] {symbol} 2. teyitten başarıyla geçti ve portföye eklendi! (Giriş: ${fresh_price})")

                # Vade kotasını dinamik güncelle
                if cand_tf == "15m":
                    c_15m += 1
                    if c_15m >= max_15m and "15m" in allowed_timeframes:
                        allowed_timeframes.remove("15m")
                elif cand_tf == "30m":
                    c_30m += 1
                    if c_30m >= max_30m and "30m" in allowed_timeframes:
                        allowed_timeframes.remove("30m")
                elif cand_tf == "1h":
                    c_1h += 1
                    if c_1h >= max_1h and "1h" in allowed_timeframes:
                        allowed_timeframes.remove("1h")

                # Grafik Çizim Ajanı
                chart_path = ""
                try:
                    target_candles = cand.get("candles") or candles_15m or candles_30m or candles_1h
                    chart_path = self.chart_agent.generate_chart(ta_setup, target_candles, suffix="setup")
                    if chart_path and sig_id:
                        from core.database import update_signal_status
                        update_signal_status(sig_id, {"chart_entry_png": chart_path})
                except Exception as chart_err:
                    print(f"⚠️ [{symbol}] Grafik çizim hatası: {chart_err}")

                # Bildirim Ajanı (Telegram + Konsol)
                try:
                    self.notifier.send_trade_presentation(signal_data, risk_report, news_analysis, chart_path)
                except Exception as notify_err:
                    print(f"⚠️ [{symbol}] Bildirim hatası: {notify_err}")

                time.sleep(0.15)

            # Kotaya takılan diğer iyi fırsatları logda belirt
            for unselected in shortlist_candidates:
                if unselected["symbol"] not in excluded_symbols:
                    add_scanner_log(
                        unselected["symbol"],
                        "REJECTED",
                        f"Turnuva Kotası Doldu (Kalite Skoru: {unselected['quality_score']}/100)",
                        f"Daha yüksek kaliteli fırsatlar ({found_setups_count} adet) önceliklendirildi"
                    )

        if found_setups_count == 0:
            print("💤 Bu döngüde kurallara tam uyan A+ kurulum bulunamadı veya 2. teyitte elendi.")
        else:
            print(f"🎉 Bu döngüde turnuva elemeleri ve 2. teyit sonrasında toplam {found_setups_count} adet şampiyon fırsat işleme alındı!")

    def show_stats(self):
        """'Girseydim Ne Olurdu?' performans istatistiklerini görüntüler."""
        stats = get_performance_stats()
        print("\n" + "=" * 55)
        print("📊 'GİRSEYDİM NE OLURDU?' SANAL İŞLEM PERFORMANS RAPORU")
        print("=" * 55)
        print(f"Toplam Tamamlanan İşlem : {stats.get('total_trades', 0)}")
        print(f"Kazanan İşlemler (Win)   : {stats.get('win_count', 0)}")
        print(f"Kaybeden İşlemler (Loss) : {stats.get('loss_count', 0)}")
        print(f"Başabaş Kapanan (BE)     : {stats.get('be_count', 0)}")
        print(f"Kazanma Oranı (Win Rate) : %{stats.get('win_rate', 0.0)}")
        print(f"Ortalama İşlem PnL       : %{round(stats.get('avg_pnl_pct') or 0.0, 2)}")
        print(f"Kümülatif Toplam PnL     : %{round(stats.get('total_pnl_pct') or 0.0, 2)}")
        print("=" * 55 + "\n")

    def run_forever(self, skip_dashboard: bool = False):
        """7/24 kesintisiz arka plan modu."""
        # Windows'un uyku moduna geçmesini engelleyen sistem bayrağı
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
            print("⚡ [Windows Güç Yönetimi] Bilgisayarın uyku moduna geçmesi engellendi (Sürekli aktif).")
        except Exception:
            pass

        # Telegram Komut Dinleyicisini Başlat
        if ENABLE_TELEGRAM_COMMANDS:
            self.cmd_agent.start_in_background()

        # Canlı Web Dashboard'u Başlat (http://127.0.0.1:5000)
        if not skip_dashboard:
            try:
                start_dashboard(orchestrator=self, port=5000, auto_open=True)
            except Exception as dash_err:
                print(f"⚠️ Dashboard başlatılamadı: {dash_err}")

        print(f"🔄 7/24 Kesintisiz Tarama Modu Aktif (Her {SCAN_INTERVAL_SECONDS} saniyede bir tarama yapılacak).")
        print("Durdurmak için Ctrl+C tuşlarına basabilirsiniz.\n")

        # Telegram'a başlatıldı bildirimi
        if self.notifier.has_telegram:
            startup_msg = (
                "🟢 *Trade Bot 7/24 Aktif Edildi!*\n\n"
                "📡 *Piyasa:* Binance Futures (USDT.P)\n"
                "⚡ *Kaldıraç:* Dinamik 10x ve 20x (Sniper)\n"
                "🛡️ *Korumalar:* BTC Çöküş Kalkanı + Break-Even (Sıfır Risk)\n\n"
                "💬 *Telegram Komutları:*\n"
                "• `/rapor` : Son 24 saatlik gün sonu kâr/zarar ve işlem raporu\n"
                "• `/tara` : Anında tarama yap\n"
                "• `/durum` : 'Girseydim ne olurdu?' PnL raporu\n"
                "• `/aktif` : Açık sanal işlemleri listele\n"
                "• `/btc` : BTC piyasa durumu ve kalkanı gör"
            )
            self.notifier.send_text_message(startup_msg)

        try:
            while True:
                try:
                    self.run_cycle()
                except Exception as cycle_err:
                    print(f"⚠️ [Döngü Hatası]: {cycle_err}. 30 saniye sonra tekrar denenecek...")
                    time.sleep(30)
                    continue

                time.sleep(SCAN_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\n🛑 Bot kullanıcı tarafından durduruldu.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Binance Futures 10x/20x Trade Bot")
    parser.add_argument("--scan", action="store_true", help="Hemen tek bir tarama döngüsü çalıştır")
    parser.add_argument("--stats", action="store_true", help="Geçmiş sanal işlem performans raporunu göster")
    args = parser.parse_args()

    orchestrator = TradingBotOrchestrator()

    if args.stats:
        orchestrator.show_stats()
    elif args.scan:
        orchestrator.run_cycle()
    else:
        orchestrator.run_forever()
