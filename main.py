"""
Trading Bot Orchestrator - Binance Futures (USDT.P) Multi-Agent System
Supports Dynamic Leverage (10x vs 20x Sniper), BTC Market Shield,
Multi-Timeframe Confluence (4h + 1h), Break-Even Protection,
and Background Telegram Command Listening.
"""
import sys
import time
import argparse
from datetime import datetime

from config import (
    SCAN_INTERVAL_SECONDS,
    PRIMARY_TIMEFRAME,
    MACRO_TIMEFRAME,
    ENABLE_TELEGRAM_COMMANDS,
    MAX_CONCURRENT_TRADES
)
from core.binance_client import BinanceFuturesClient
from core.database import init_db, save_signal, get_performance_stats, get_active_positions_count
from agents.scanner_agent import MarketScannerAgent, add_scanner_log
from agents.ta_agent import TechnicalAnalysisAgent
from agents.news_agent import NewsAgent, get_live_news_feed
from agents.risk_agent import RiskOfficerAgent
from agents.chart_agent import ChartAgent
from agents.notifier_agent import NotifierAgent
from agents.tracker_agent import CounterfactualTrackerAgent
from agents.telegram_command_agent import TelegramCommandAgent
from agents.ai_analyst_agent import AIAnalystAgent
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

        # Canlı WebSocket Veri Boru Hattını Başlat
        try:
            start_streamer()
            print("⚡ [WebSocket Streamer] Canlı emir akışı ve fiyat soketi bağlandı.")
        except Exception as ws_err:
            print(f"⚠️ WebSocket başlatılamadı: {ws_err}")
        
        print("✅ Tüm Ajanlar, BTC Kalkanı ve Binance Futures (USDT.P) hazır.\n")

    def run_cycle(self):
        """Tek bir tam analiz ve takip döngüsü yürütür."""
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Döngü Başladı...")

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

        slots_left = MAX_CONCURRENT_TRADES - active_count
        print(f"🛡️ [Kasa Kalkanı] Aktif Pozisyon: {active_count}/{MAX_CONCURRENT_TRADES} | Kalan İşlem Kotası: {slots_left}")

        # 2. BTC Piyasa Çöküş ve Ölü Piyasa Kalkanı Kontrolü
        btc_regime = self.client.get_btc_regime()
        print(f"🛡️ [BTC Kalkanı] Durum: {btc_regime['status']} | {btc_regime.get('summary', '')}")
        if btc_regime.get("block_all_entries", False):
            summary_msg = btc_regime.get("summary", "BTC ölü testere piyasada, tarama donduruldu.")
            detailed_msg = btc_regime.get("detailed_reason") or summary_msg
            print(f"🛑 [BTC Ölü Piyasa Freni] {summary_msg}")
            add_scanner_log("BTC KALKANI", "PROTECTED", detailed_msg, "Sermaye Koruma Modu (0 Risk)")
            return

        # 2.5 ZARARLI İŞLEM SONRASI SOĞUMA MOLASI (Anti-Overtrading Cooldown)
        from core.database import get_last_loss_closed_time
        from config import POST_LOSS_COOLDOWN_MINUTES
        last_loss_time_str = get_last_loss_closed_time()
        if last_loss_time_str:
            try:
                last_loss_dt = datetime.strptime(last_loss_time_str[:19], "%Y-%m-%d %H:%M:%S")
                elapsed_min = (datetime.now() - last_loss_dt).total_seconds() / 60.0
                if elapsed_min < POST_LOSS_COOLDOWN_MINUTES:
                    rem_min = int(POST_LOSS_COOLDOWN_MINUTES - elapsed_min) + 1
                    msg = f"Son zararlı işlem sonrası soğuma molasında ({rem_min} dk kaldı). Testere piyasa tuzağı engellendi."
                    print(f"⏳ [Soğuma Molası] {msg}")
                    add_scanner_log("SOĞUMA MOLASI", "PROTECTED", msg, "Aşırı İşlem Freni")
                    return
            except Exception:
                pass

        # 3. Binance Futures USDT.P çiftlerini tara (Akıllı 200+ Parite Rotasyonu & Cooldown Koruması)
        print("📡 [Scanner Ajanı] Binance Futures USDT.P çiftleri taranıyor...")
        from core.database import get_recently_traded_symbols
        # Açık olan veya son 45 dk içinde açılıp kapanmış coinleri al (aynı coinleri tekrar denememek için)
        excluded_symbols = get_recently_traded_symbols(within_minutes=45)

        candidates = self.scanner.scan_opportunities(limit=16, exclude_symbols=excluded_symbols)

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

        # 4. Haber masasını güncelle (Sağ Alttaki Haber Masası için)
        try:
            self.news_agent.fetch_latest_market_news()
        except Exception:
            pass

        # 5. Her aday pariteyi uzman ajanlar ekibine gönder (15m Hızlı Day Trade & 1h Makro Teyit)
        for ticker in candidates:
            symbol = ticker["symbol"]
            if symbol in excluded_symbols:
                continue  # Zaten açık veya yakın zamanda denenmişse tekrar girme

            try:
                # Sadece 15 dakikalık (15m) scalping mumlarını çek (1 saatlik grafik filtresi kaldırıldı)
                candles_15m = self.client.get_klines(symbol, interval=PRIMARY_TIMEFRAME, limit=60)
                if len(candles_15m) < 40:
                    add_scanner_log(symbol, "REJECTED", "Yetersiz 15m mum verisi")
                    continue

                # Ajan 1: Teknik Analist incelemesi (Tamamen 15m Hızlı Scalp & Anlık Momentum)
                ta_setup, ta_reason = self.ta_agent.analyze_setup(symbol, candles_15m)
                if not ta_setup:
                    add_scanner_log(symbol, "REJECTED", ta_reason)
                    continue

                # Ajan 2: Fonlama Oranı, Derinlik (Spread) ve Haber Analizi
                funding_data = self.client.get_funding_rate(symbol)
                book_ticker = self.client.get_book_ticker(symbol)
                news_analysis = self.news_agent.analyze_catalyst(symbol, ta_setup["direction"], funding_data)

                # Ajan 3: Risk Şefi (Dinamik 10x/20x, BTC Kalkanı, Slippage ve Fonlama denetimi)
                from core.database import get_active_and_pending_signals
                active_sigs = get_active_and_pending_signals() or []
                is_approved, risk_report = self.risk_officer.evaluate(
                    ta_setup, news_analysis, ticker, btc_regime,
                    funding_data=funding_data,
                    book_ticker=book_ticker,
                    active_signals=active_sigs
                )
                if not is_approved:
                    add_scanner_log(symbol, "REJECTED", risk_report.get("reason", "Risk kurallarına uymadı"))
                    continue

                # Ajan 3.5: AI Baş Analisti & Yatırım Komitesi Tartışması (Adversarial Multi-Agent Chamber)
                ai_verdict = self.ai_analyst.evaluate_setup(ta_setup, risk_report, news_analysis, btc_regime, ticker, funding_data)
                debate_data = ai_verdict.get("debate_data", {})

                if not ai_verdict.get("ai_approved", True):
                    critique = ai_verdict.get('ai_critique', '')
                    add_scanner_log(symbol, "REJECTED", f"Yatırım Komitesi Veto Etti ({ai_verdict.get('ai_confidence', 0)}/10)", critique[:60])
                    continue

                # Onaylanan kaldıraç ve risk grubunu ata
                leverage = risk_report["leverage"]
                ta_setup["leverage"] = leverage
                ta_setup["risk_grade"] = risk_report["risk_grade"]

                # Veritabanına Sanal İşlem Olarak Kaydet (ÖNCELİKLE POZİSYONU AÇ VE DB'YE YAZ!)
                signal_data = {
                    "symbol": symbol,
                    "direction": ta_setup["direction"],
                    "leverage": leverage,
                    "entry_min": ta_setup["entry_min"],
                    "entry_max": ta_setup["entry_max"],
                    "actual_entry_price": ta_setup["current_price"],
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
                    "news_summary": f"🏛️ Komite Puanı: {ai_verdict.get('ai_confidence', 0)}/10 | {ai_verdict.get('ai_critique', '')}",
                    "ta_reasons": ta_setup["ta_reasons"],
                    "ai_verdict": ai_verdict,
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
                    f"{leverage}x {ta_setup['direction']} SMC Scalp Açıldı! (Marjin: ${risk_report['allocated_margin_usdt']}, Risk: ${risk_report['risk_usd']})",
                    f"Net SL: -%{risk_report['margin_risk_pct']}, Net TP: +%{risk_report['margin_tp1_pct']}"
                )

                if found_setups_count >= slots_left:
                    print(f"🛡️ [Kasa Kalkanı] İzin verilen kota ({slots_left}) doldu. Yeni fırsat taraması kilitlendi.")
                    break

                # Ajan 4: Grafik Çizim Ajanı (Çizgi Grafiği PNG Üretimi)
                chart_path = ""
                try:
                    chart_path = self.chart_agent.generate_chart(ta_setup, candles_15m, suffix="setup")
                    if chart_path and sig_id:
                        from core.database import update_signal_status
                        update_signal_status(sig_id, {"chart_entry_png": chart_path})
                except Exception as chart_err:
                    print(f"⚠️ [{symbol}] Grafik çizim hatası: {chart_err}")

                # Ajan 5: Sunum ve Bildirim Ajanı (Telegram + Konsol)
                try:
                    self.notifier.send_trade_presentation(signal_data, risk_report, news_analysis, chart_path)
                except Exception as notify_err:
                    print(f"⚠️ [{symbol}] Bildirim hatası: {notify_err}")

            except Exception as e:
                print(f"⚠️ [{symbol}] Analiz hatası: {e}")
                continue

        if found_setups_count == 0:
            print("💤 Bu döngüde kurallara tam uyan A+ kurulum bulunamadı (Filtreler sermayeyi koruyor).")
        else:
            print(f"🎉 Bu döngüde toplam {found_setups_count} adet yüksek kaliteli fırsat tespit edildi ve sunuldu!")

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
