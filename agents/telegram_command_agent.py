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
from core.database import get_performance_stats, get_active_and_pending_signals

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
        
        if cmd in ("/tara", "/scan"):
            self.orchestrator.notifier.send_text_message("🔍 *Piyasa Taraması Başlatıldı...*\nBinance Futures taranıyor, birazdan sonuç gelecek.")
            try:
                self.orchestrator.run_cycle()
            except Exception as e:
                self.orchestrator.notifier.send_text_message(f"⚠️ Tarama hatası: {e}")

        elif cmd in ("/durum", "/stats", "/performans"):
            stats = get_performance_stats()
            total = stats.get("total_trades", 0)
            wins = stats.get("win_count", 0)
            losses = stats.get("loss_count", 0)
            rate = stats.get("win_rate", 0.0)
            tot_pnl = round(stats.get("total_pnl_pct") or 0.0, 2)
            avg_pnl = round(stats.get("avg_pnl_pct") or 0.0, 2)

            msg = (
                f"📊 *'GİRSEYDİM NE OLURDU?' PERFORMANS RAPORU*\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 *Toplam İşlem:* {total}\n"
                f"✅ *Kazanan (Win):* {wins}\n"
                f"🛑 *Kaybeden (Loss):* {losses}\n"
                f"📈 *Kazanma Oranı (Win Rate):* %{rate}\n"
                f"💰 *Kümülatif Toplam PnL:* *%{tot_pnl}*\n"
                f"⚖️ *Ortalama İşlem Getirisi:* %{avg_pnl}\n"
            )
            self.orchestrator.notifier.send_text_message(msg)

        elif cmd in ("/btc", "/shield", "/kalkan"):
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

        elif cmd in ("/aktif", "/pozisyonlar"):
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

        elif cmd in ("/yardim", "/help", "/start"):
            msg = (
                "🤖 *TRADE BOT KOMUT REHBERİ*\n\n"
                "🔹 `/tara` : Binance vadeli piyasayı anında tarar.\n"
                "🔹 `/durum` : 'Girseydim ne olurdu?' PnL raporunu getirir.\n"
                "🔹 `/aktif` : Açıkta bekleyen sanal pozisyonları listeler.\n"
                "🔹 `/btc` : Bitcoin çöküş kalkanı ve piyasa yönünü gösterir.\n"
            )
            self.orchestrator.notifier.send_text_message(msg)

