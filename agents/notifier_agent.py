"""
Notifier & Presentation Agent
Formats and delivers executive trade briefs with PNG charts to Telegram & Console.
Supports dynamic leverage (10x vs 20x Sniper) and Break-Even protection alerts.
"""
import os
import requests
from typing import Dict
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

class NotifierAgent:
    def __init__(self, bot_token: str = TELEGRAM_BOT_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.has_telegram = bool(bot_token and chat_id)

    def send_trade_presentation(self, signal_data: Dict, risk_report: Dict, news_data: Dict, chart_png_path: str):
        """
        Kullanıcıya eksiksiz bir yatırım/işlem sunumu gönderir (Telegram + Konsol).
        """
        symbol = signal_data["symbol"]
        direction = signal_data["direction"]
        leverage = signal_data.get("leverage", 10)
        risk_grade = risk_report["risk_grade"]
        
        lev_tag = f"⚡ {leverage}x SNIPER" if leverage == 20 else f"{leverage}x Trend"

        # Konsol Sunumu
        border = "=" * 65
        print("\n" + border)
        print(f"🚀 YENİ FIRSAT ANALİZİ: {symbol} ({direction} {lev_tag})")
        print(border)
        print(f"📊 Risk Profili     : {risk_grade}")
        print(f"💰 Giriş Aralığı    : {signal_data['entry_min']} - {signal_data['entry_max']}")
        print(f"🛑 Stop Loss (SL)   : {signal_data['stop_loss']} (-%{signal_data['sl_pct']} | Marjin: -%{risk_report['margin_risk_pct']}%)")
        print(f"🎯 Hedef 1 (TP1)    : {signal_data['take_profit_1']} (+%{signal_data.get('tp1_pct', round(signal_data['sl_pct']*1.5, 2))}% | Marjin: +%{risk_report['margin_tp1_pct']}%)")
        print(f"🎯 Hedef 2 (TP2)    : {signal_data['take_profit_2']} (+%{signal_data['tp2_pct']}% | Marjin: +%{risk_report['margin_tp2_pct']}%)")
        print(f"⚖️ Risk/Ödül (R:R)  : 1 : {signal_data['risk_reward']}")
        print("-" * 65)
        print(f"📰 Temel & Haber    : {news_data['verdict']}")
        print(f"💡 Haber Özeti      : {news_data['summary']}")
        print(f"📉 Fonlama Oranı    : %{news_data['funding_rate_pct']}")
        print(f"📈 Teknik Gerekçe   : {signal_data.get('ta_reasons', '')}")
        print(f"🖼️ PNG Grafik       : {chart_png_path}")
        print(border + "\n")

        ai_verdict = signal_data.get("ai_verdict", {})
        ai_line = ""
        if ai_verdict:
            ai_line = f"🧠 *AI Analist Konsensüsü:* {ai_verdict.get('ai_confidence', 0)}/10 ({ai_verdict.get('verdict', '')})\n💬 _{ai_verdict.get('ai_critique', '')}_\n\n"

        debate_data = signal_data.get("debate_json") or {}
        debate_text = ""
        if debate_data and "debate_dialogue" in debate_data:
            debate_text = "🏛️ *Yatırım Komitesi Tartışması:*\n"
            for d in debate_data["debate_dialogue"]:
                role_icon = d.get("avatar", "💬")
                name = d.get("agent_name", "")
                arg = d.get("argument", "")
                short_arg = arg[:130] + "..." if len(arg) > 130 else arg
                debate_text += f"{role_icon} *{name}:* _{short_arg}_\n"
            debate_text += "\n"

        # Telegram Gönderimi
        if self.has_telegram:
            msg_text = (
                f"🎯 *YENİ İŞLEM FIRSATI (Binance Futures)*\n\n"
                f"🪙 *Parite:* `{symbol}` (*{direction} {lev_tag}*)\n"
                f"🏷️ *Risk Grubu:* {risk_grade}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💵 *Giriş Aralığı:* `{signal_data['entry_min']} - {signal_data['entry_max']}`\n"
                f"🛑 *Stop Loss:* `{signal_data['stop_loss']}` (Marjin Riski: -%{risk_report['margin_risk_pct']})\n"
                f"🎯 *Hedef 1 (TP1):* `{signal_data['take_profit_1']}` (Marjin: +%{risk_report['margin_tp1_pct']})\n"
                f"🎯 *Hedef 2 (TP2):* `{signal_data['take_profit_2']}` (Marjin: *+%{risk_report['margin_tp2_pct']}*)\n"
                f"⚖️ *R:R Oranı:* 1:{signal_data['risk_reward']}\n\n"
                f"{debate_text}"
                f"{ai_line}"
                f"📰 *Haber / Katalizör:* {news_data['verdict']}\n"
                f"💬 _{news_data['summary']}_\n\n"
                f"📈 *Teknik:* {signal_data.get('ta_reasons', '')}\n\n"
                f"⚠️ *Not:* TP1'e ulaşıldığında Stop Loss otomatik giriş seviyesine (Break-Even) çekilerek pozisyon risksiz hale getirilir."
            )
            self._send_telegram_photo(chart_png_path, msg_text)

    def send_be_update(self, symbol: str, direction: str, leverage: int, tp1: float, entry_price: float):
        """TP1'e ulaşıldığında Stop'un başabaşa çekildiği bildirimini gönderir."""
        if not self.has_telegram:
            return
        text = (
            f"🛡️ *BREAK-EVEN KORUMASI AKTİF (Sıfır Risk!)*\n\n"
            f"🪙 *Parite:* `{symbol}` ({direction} {leverage}x)\n"
            f"🎯 *TP1 Seviyesi ({tp1}) başarıyla vuruldu!*\n"
            f"🔒 Stop Loss seviyesi otomatik olarak giriş fiyatına (`{entry_price}`) taşındı.\n\n"
            f"✨ *Bu işlem artık tamamen risksizdir.* Fiyat geri dönse bile zarar edilmeyecektir."
        )
        self.send_text_message(text)

    def send_outcome_report(self, trade_info: Dict):
        """
        'Girseydim Ne Olurdu?' sonuç bildirimini gönderir.
        """
        symbol = trade_info["symbol"]
        status = trade_info["status"]
        leverage = trade_info.get("leverage", 10)
        pnl = trade_info["pnl_pct"]
        is_win = pnl > 0
        icon = "🎉" if is_win else ("🛡️" if status == "CLOSED_BE" else "🛑")
        sign = "+" if pnl > 0 else ""

        if status in ("HIT_TP", "HIT_TP1", "HIT_TP2"):
            status_text = "🎯 Hedef Vuruldu (Vur-Kaç Kar Alındı!)"
        elif status == "TIMEOUT_EXIT":
            status_text = "⏱️ 45dk Zaman Aşımı (Hareketsizlikten Çıkıldı)"
        elif status == "CLOSED_BE":
            status_text = "🛡️ Başabaş Kapandı (Break-Even)"
        elif status == "HIT_SL":
            status_text = "🛑 Stop Loss Oldu"
        else:
            status_text = status

        print("\n" + "=" * 65)
        print(f"{icon} SANAL İŞLEM SONUÇLANDI: {symbol} -> {status_text}")
        print(f"💰 Gerçekleşen PnL ({leverage}x Kaldıraç): {sign}{pnl}%")
        print(f"🖼️ Sonuç Grafiği: {trade_info['chart_exit_png']}")
        print("=" * 65 + "\n")

        if self.has_telegram:
            caption = (
                f"{icon} *SANAL İŞLEM SONUCU (Girseydim Ne Olurdu?)*\n\n"
                f"🪙 *Parite:* `{symbol}` ({trade_info['direction']} {leverage}x)\n"
                f"📌 *Durum:* `{status_text}`\n"
                f"💵 *Giriş:* `{trade_info['entry_price']}` -> *Çıkış:* `{trade_info['exit_price']}`\n"
                f"📊 *Simüle Edilen Net PnL:* *{sign}{pnl}%* ({leverage}x Kaldıraç)\n"
            )
            self._send_telegram_photo(trade_info["chart_exit_png"], caption)

    def send_text_message(self, text: str):
        """Düz metin mesajı gönderir."""
        if not self.has_telegram:
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            requests.post(url, data={"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
        except Exception as e:
            print(f"[Notifier] Telegram mesaj hatası: {e}")

    def send_daily_summary_report(self) -> Dict:
        """Gün sonu 24 saatlik işlem ve kâr/zarar raporunu derler ve Telegram'a iletir."""
        from core.database import generate_daily_summary_report, format_daily_telegram_message
        report = generate_daily_summary_report()
        msg_text = format_daily_telegram_message(report)
        self.send_text_message(msg_text)
        print("🏆 [Gün Sonu Raporu] 24 saatlik işlem ve kâr/zarar raporu Telegram'a iletildi.")
        return report

    def _send_telegram_photo(self, photo_path: str, caption: str):
        """Telegram bot API'sine fotoğraf ve metin yükler."""
        if not os.path.exists(photo_path):
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        try:
            with open(photo_path, "rb") as f:
                payload = {
                    "chat_id": self.chat_id,
                    "caption": caption,
                    "parse_mode": "Markdown"
                }
                files = {"photo": f}
                requests.post(url, data=payload, files=files, timeout=15)
        except Exception as e:
            print(f"[Notifier] Telegram gönderme hatası: {e}")
