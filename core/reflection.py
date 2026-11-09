"""
Episodic Trade Memory & Post-Trade Reflection Engine
Inspired by Tauric Research - TradingAgents (121k ⭐)

Her kapanan işlemden sonra (kâr, zarar, merdiven stop, zaman aşımı)
otomatik olarak objektif ve somut dersler çıkarır.
Bu dersler kalıcı hafızaya kaydedilir ve bir sonraki Ajan Komitesi
tartışmasında (özellikle Ayı Analisti / Risk Şefi tarafından)
aynı hataların tekrarlanmaması için karar sürecine enjekte edilir.
"""
import os
import json
from datetime import datetime
from typing import Dict, List, Optional
from core.database import save_trade_reflection_db, get_recent_reflections_db

class ReflectorEngine:
    """İşlem sonuçlarını kurumsal derslere dönüştüren hafıza motoru."""

    @staticmethod
    def reflect_on_trade(trade_data: Dict) -> Dict:
        """
        Kapanan bir işlem için refleksif analiz yapar ve DB'ye kaydeder.
        """
        signal_id = trade_data.get("signal_id") or trade_data.get("id")
        symbol = trade_data.get("symbol", "UNKNOWN")
        direction = trade_data.get("direction", "LONG")
        status = trade_data.get("status", "CLOSED")
        pnl_pct = trade_data.get("pnl_pct", 0.0)
        gross_pnl_pct = trade_data.get("gross_pnl_pct", pnl_pct)
        fee_pct = trade_data.get("fee_pct", 1.0)
        leverage = trade_data.get("leverage", 10)
        ladder_step = trade_data.get("ladder_step", 0)
        ladder_name = trade_data.get("ladder_name", "")
        minutes_open = trade_data.get("minutes_open", 0)

        # 1. KÂR / ZARAR TÜRÜNE GÖRE STRATEJİK DERS ÇIKARIMI
        if status == "HIT_TP":
            thesis_evaluation = "Kurumsal tez ve SMC likidite hedefi tam başarıyla gerçekleşti."
            lesson = (
                f"{symbol} {direction} işleminde +%{pnl_pct} net kâr elde edildi. "
                f"SMC konsepti ve hacim desteği mükemmel çalıştı. "
                f"Ders: Yüksek güven skorlu kurulumlarda TP hedefine sadık kalmak yüksek alfa üretiyor."
            )
            outcome_type = "WIN"

        elif "LADDER" in status:
            thesis_evaluation = f"Fiyat kâra geçtikten sonra trend yoruldu, Merdiven Kâr Sistemi devreye girdi ({ladder_name})."
            lesson = (
                f"{symbol} {direction} işleminde Merdiven Kâr Kilidi ile +%{pnl_pct} net kâr kasaya alındı. "
                f"Ders: Fiyat geri dönse bile stopu kademeli kâra taşımak, kazancı kayba dönüştürmeyi %100 engelledi."
            )
            outcome_type = "WIN_LADDER"

        elif status == "CLOSED_BE":
            thesis_evaluation = "İşlem komisyon kurtaran başabaş seviyesinde güvenle kapatıldı."
            lesson = (
                f"{symbol} {direction} işleminde momentum zayıflayınca Başa-Baş Stop devreye girdi (Net: {'+' if pnl_pct >= 0 else ''}%{pnl_pct}). "
                f"Ders: İnatlaşmayıp komisyonu güvenceye almak gereksiz sermaye erimesini önledi."
            )
            outcome_type = "BE"

        elif status == "TIMEOUT_EXIT":
            thesis_evaluation = f"Pozisyon {int(minutes_open)} dakika boyunca hedefe gitmedi, testere piyasasında yataya bağladı."
            lesson = (
                f"{symbol} {direction} işlemi 90 dakika zaman aşımı nedeniyle kapatıldı (Net: {'+' if pnl_pct >= 0 else ''}%{pnl_pct}). "
                f"Ders: Mikro-scalpingte hareketsiz pozisyonda beklemek fırsat maliyetidir; sermaye hemen likit edildi."
            )
            outcome_type = "TIMEOUT"

        elif status == "HIT_SL":
            thesis_evaluation = "Stop-loss seviyesine vuruldu, kurumsal tez geçersiz kaldı."
            # Neden stop oldu analizi
            if minutes_open < 10:
                failure_reason = "Girişten hemen sonra likidite avı fitili geldi (ani ters volatilite)."
                action_rule = "Aşırı oynak anlarda breakout yerine pullback teyidi beklenmeli."
            elif pnl_pct <= -15.0:
                failure_reason = "Sert piyasa yön değişimi yaşandı, stop korunmasa zarar büyüyecekti."
                action_rule = "Dar stop kuralı ve sabit $20 risk tavanı sermayeyi tam korudu."
            else:
                failure_reason = "Momentum kırılımı sahte çıktı veya BTC karşı yönde baskı kurdu."
                action_rule = "BTC Dead Chop veya zıt trend halindeyken bu yönde işleme girilmemeli."

            lesson = (
                f"{symbol} {direction} işleminde stop olundu (-%{abs(pnl_pct)} marjin kaybı). "
                f"{failure_reason} Ders: {action_rule}"
            )
            outcome_type = "LOSS"

        else:
            thesis_evaluation = "Manuel veya harici kapanış gerçekleştirildi."
            lesson = f"{symbol} {direction} işleminden Net %{pnl_pct} ile çıkıldı. Ders: Sistem kurallarına sadık kal."
            outcome_type = "MANUAL"

        reflection_dict = {
            "symbol": symbol,
            "direction": direction,
            "status": status,
            "outcome_type": outcome_type,
            "pnl_pct": pnl_pct,
            "gross_pnl_pct": gross_pnl_pct,
            "fee_pct": fee_pct,
            "thesis_evaluation": thesis_evaluation,
            "lesson": lesson,
            "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Veritabanına kaydet
        try:
            save_trade_reflection_db(
                signal_id=signal_id,
                symbol=symbol,
                direction=direction,
                status=status,
                pnl_pct=pnl_pct,
                lesson=lesson,
                reflection_dict=reflection_dict
            )
        except Exception as e:
            print(f"⚠️ [Reflector] DB kayıt hatası: {e}")

        return reflection_dict

    @staticmethod
    def get_past_context_for_committee(symbol: str, limit: int = 4) -> str:
        """
        Yatırım komitesi tartışmasına enjekte edilmek üzere hafızadaki
        en kritik son dersleri formatlar.
        """
        try:
            # 1. Önce bu pariteye ait geçmiş dersler
            same_symbol_reflections = get_recent_reflections_db(limit=2, symbol=symbol)
            # 2. Son genel dersler (tüm piyasa)
            general_reflections = get_recent_reflections_db(limit=limit)

            combined = []
            seen_ids = set()

            for r in same_symbol_reflections:
                if r["id"] not in seen_ids:
                    combined.append(r)
                    seen_ids.add(r["id"])

            for r in general_reflections:
                if r["id"] not in seen_ids and len(combined) < limit:
                    combined.append(r)
                    seen_ids.add(r["id"])

            if not combined:
                return "Hafıza Defteri: Henüz kayıtlı geçmiş işlem dersi yok (Sistem ilk döngülerinde)."

            lines = ["🧠 HAFIZA DEFTERİNDEN ÇIKARILAN DERSLER (Tauric Reflection Log):"]
            for r in combined:
                pnl = r.get("pnl_pct", 0.0)
                sign = "+" if pnl >= 0 else ""
                lines.append(f"• [{r.get('symbol')} {r.get('direction')} | {r.get('status')} | {sign}{pnl}%]: {r.get('lesson')}")

            return "\n".join(lines)
        except Exception as e:
            return f"Hafıza okuma hatası: {e}"

