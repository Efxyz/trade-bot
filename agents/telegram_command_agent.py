"""
Telegram Interactive Command Agent
Listens for user commands from Telegram in the background:
- /tara veya /scan : Anında piyasa taraması başlatır.
- /durum veya /stats : Geçmiş sanal işlem başarı ve PnL istatistiklerini getirir.
- /aktif : Açıkta olan sanal pozisyonları listeler.
- /btc : Anlık BTC durumunu ve Piyasa Çöküş Kalkanı durumunu raporlar.
- /yardim : Komut listesini gösterir.
"""
import time
import threading
import requests
from typing import Optional
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from core.database import (
    get_performance_stats,
    get_active_and_pending_signals,
    close_single_signal_db,
    close_all_active_signals_db
)

class TelegramCommandAgent:
    def __init__(self, orchestrator, bot_token: str = TELEGRAM_BOT_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        self.orchestrator = orchestrator
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.is_running = False
        self.last_update_id = 0

    def start_in_background(self):
        """Arka planda dinleyici thread'i başlatır."""
        if not (self.bot_token and self.chat_id):
            return
        self.is_running = True
        thread = threading.Thread(target=self._poll_loop, daemon=True, name="TelegramListener")
        thread.start()
        print("📱 [Telegram Komut Dinleyici] Aktif! Telegram'dan /tara, /durum, /btc yazabilirsiniz.")

    def _poll_loop(self):
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        while self.is_running:
            try:
                params = {"offset": self.last_update_id + 1, "timeout": 10}
                resp = requests.get(url, params=params, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        self.last_update_id = update["update_id"]
                        msg = update.get("message", {})
                        text = (msg.get("text") or "").strip()
                        sender_id = str(msg.get("chat", {}).get("id", ""))

                        # Sadece yetkili kullanıcıdan gelen komutları işle
                        if sender_id == self.chat_id and text.startswith("/"):
                            self._handle_command(text.lower())
            except Exception:
                time.sleep(3)
            time.sleep(1)

    def _handle_command(self, cmd: str):
        print(f"[Telegram Komut Alındı]: {cmd}")
        parts = cmd.strip().split()
        if not parts:
            return
        base_cmd = parts[0]
        args = parts[1:]
        
        if base_cmd in ("/tara", "/scan"):
            self.orchestrator.notifier.send_text_message("🔍 *Piyasa Taraması Başlatıldı...*\nBinance Futures taranıyor, birazdan sonuç gelecek.")
            try:
                self.orchestrator.run_cycle()
            except Exception as e:
                self.orchestrator.notifier.send_text_message(f"⚠️ Tarama hatası: {e}")

        elif base_cmd in ("/durum", "/stats", "/performans"):
            stats = get_performance_stats()
            total = stats.get("total_trades", 0)
            wins = stats.get("win_count", 0)
            losses = stats.get("loss_count", 0)
            rate = stats.get("win_rate", 0.0)
            tot_pnl = round(stats.get("total_pnl_pct") or 0.0, 2)
            net_dollar = round(stats.get("net_dollar_gain") or 0.0, 2)
            equity = stats.get("portfolio_balance", 1000.0)

            # Günlük PnL (Türkiye Saati 00:00 - 23:59)
            today_trades = stats.get("today_trades", 0)
            today_wins = stats.get("today_wins", 0)
            today_losses = stats.get("today_losses", 0)
            today_dollar = stats.get("today_dollar_gain", 0.0)
            today_pct = stats.get("today_net_pnl_pct", 0.0)
            today_sign = "+" if today_dollar >= 0 else ""
            today_icon = "🟢" if today_dollar >= 0 else ("🔴" if today_dollar < 0 else "⚪")
            tot_sign = "+" if net_dollar >= 0 else ""
            tot_icon = "🟢" if net_dollar >= 0 else "🔴"

            msg = (
                f"📊 *FON KASASI VE PERFORMANS RAPORU*\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💼 *Güncel Fon Kasası:* `${equity:,.2f} USDT`\n\n"
                f"{tot_icon} *GENEL TOPLAM KÂR (Kümülatif):*\n"
                f"  ↳ Net Kâr: *{tot_sign}${net_dollar:.2f}* ({tot_sign}%{tot_pnl:.2f})\n"
                f"  ↳ İşlem Sayısı: `{total}` ({wins}W / {losses}L - %{rate} Win)\n\n"
                f"{today_icon} *BUGÜNKÜ NET PnL (TRT):*\n"
                f"  ↳ Günlük Net: *{today_sign}${today_dollar:.2f}* ({today_sign}%{today_pct:.2f})\n"
                f"  ↳ Bugünkü İşlemler: `{today_trades}` adet ({today_wins}W / {today_losses}L)\n"
                f"  ↳ Sıfırlanma: `23:59:59 TRT (Otomatik Arşivlenir)`\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 _Bileşik Kasa & Zirve Kâr Koruma Kalkanı aktiftir._"
            )
            self.orchestrator.notifier.send_text_message(msg)

        elif base_cmd in ("/btc", "/shield", "/kalkan"):
            regime = self.orchestrator.client.get_btc_regime()
            status_emoji = "🟢" if regime["status"] == "BULLISH" else ("🚨" if regime["status"] == "DUMP_ALERT" else "📉")
            msg = (
                f"{status_emoji} *BTC PİYASA ÇÖKÜŞ KALKANI*\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💵 *BTC Fiyatı:* ${regime.get('btc_price', 'N/A')}\n"
                f"📊 *Son 3 Saat Değişimi:* %{regime.get('change_3h_pct', 0.0)}\n"
                f"🛡️ *Durum:* `{regime['status']}`\n"
                f"💬 _{regime.get('summary', '')}_\n"
            )
            self.orchestrator.notifier.send_text_message(msg)

        elif base_cmd in ("/aktif", "/pozisyonlar"):
            signals = get_active_and_pending_signals()
            if not signals:
                self.orchestrator.notifier.send_text_message("💤 Şu anda aktif veya giriş bekleyen sanal işlem bulunmuyor.")
                return

            text_lines = ["📌 *AÇIKTAKİ SANAL İŞLEMLER:*\n"]
            for s in signals:
                text_lines.append(
                    f"🪙 *{s['symbol']}* ({s['direction']} {s.get('leverage', 10)}x)\n"
                    f"  Durum: `{s['status']}` | Giriş: `{s.get('actual_entry_price') or s['entry_min']}`\n"
                    f"  SL: `{s['stop_loss']}` | TP2: `{s['take_profit_2']}`\n"
                )
            self.orchestrator.notifier.send_text_message("\n".join(text_lines))

        elif base_cmd in ("/kapat", "/close"):
            if not args:
                self.orchestrator.notifier.send_text_message(
                    "⚠️ *Kapatılacak pariteyi belirtiniz!*\n"
                    "Örnek: `/kapat BTC` veya `/kapat SOLUSDT`\n"
                    "Tüm pozisyonları kapatmak için: `/hepsini_kapat`"
                )
                return
            target_symbol = args[0]
            closed_trade = close_single_signal_db(target_symbol, self.orchestrator.client)
            if closed_trade:
                pnl = closed_trade.get("simulated_pnl_pct", 0.0)
                pnl_icon = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")
                pnl_sign = "+" if pnl > 0 else ""
                self.orchestrator.notifier.send_text_message(
                    f"🛑 *MANUEL POZİSYON KAPATILDI*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"🪙 *Parite:* `{closed_trade['symbol']}` ({closed_trade['direction']} {closed_trade.get('leverage', 10)}x)\n"
                    f"🚪 *Kapanış Fiyatı:* `{closed_trade['exit_price']}`\n"
                    f"{pnl_icon} *Net PnL:* *{pnl_sign}%{pnl:.2f}*\n"
                    f"🧾 _İşlem kâr/zarar defterine ve hafızaya işlendi._"
                )
            else:
                self.orchestrator.notifier.send_text_message(f"⚠️ `{target_symbol.upper()}` için aktif açık bir pozisyon bulunamadı.")

        elif base_cmd in ("/hepsini_kapat", "/close_all", "/kapat_hepsi", "/acil_durdur"):
            count = close_all_active_signals_db(self.orchestrator.client)
            if count > 0:
                self.orchestrator.notifier.send_text_message(
                    f"🚨 *ACİL DURUM KAPANIŞI TAMAMLANDI!*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"⚡ Toplam *{count}* adet aktif pozisyon piyasa fiyatıyla derhal kapatıldı.\n"
                    f"🛡️ Sermaye koruma altına alındı."
                )
            else:
                self.orchestrator.notifier.send_text_message("💤 Kapatılacak aktif açık pozisyon bulunmuyor.")

        elif base_cmd in ("/rapor", "/gunsonu", "/daily", "/24s"):
            self.orchestrator.notifier.send_text_message("⏳ *Son 24 Saatlik Gün Sonu Raporu Derleniyor...*")
            try:
                self.orchestrator.notifier.send_daily_summary_report()
            except Exception as e:
                self.orchestrator.notifier.send_text_message(f"⚠️ Rapor oluşturma hatası: {e}")

        elif base_cmd in ("/yardim", "/help", "/start"):
            msg = (
                "🤖 *TRADE BOT KOMUT REHBERİ*\n\n"
                "🔹 `/rapor` : Son 24 saatlik gün sonu kâr/zarar ve işlem özetini atar.\n"
                "🔹 `/tara` : Binance vadeli piyasayı anında tarar.\n"
                "🔹 `/durum` : 'Girseydim ne olurdu?' PnL raporunu getirir.\n"
                "🔹 `/aktif` : Açıkta bekleyen sanal pozisyonları listeler.\n"
                "🔹 `/kapat [COIN]` : Belirtilen coini anlık piyasa fiyatıyla kapatır (Örn: `/kapat BTC`).\n"
                "🔹 `/hepsini_kapat` : Açık tüm pozisyonları acil durum kalkanıyla tek tuşla kapatır.\n"
                "🔹 `/btc` : Bitcoin çöküş kalkanı ve piyasa yönünü gösterir.\n"
            )
            self.orchestrator.notifier.send_text_message(msg)

