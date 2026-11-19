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
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from core.database import (
    save_trade_reflection_db,
    get_recent_reflections_db,
    get_pinned_patron_lessons_db,
    get_gemini_api_key,
)

class ReflectorEngine:
    """İşlem sonuçlarını kurumsal derslere dönüştüren hafıza motoru."""

    @staticmethod
    def _generate_llm_reflection(trade_data: Dict, outcome_type: str) -> Optional[Tuple[str, str]]:
        """Gemini API aktifse kapanan işlem için şablonsuz gerçek AI otopsi ve ders üretir."""
        api_key = get_gemini_api_key()
        if not api_key:
            return None

        payload_info = {
            "symbol": trade_data.get("symbol"),
            "direction": trade_data.get("direction"),
            "status": trade_data.get("status"),
            "outcome_type": outcome_type,
            "net_pnl_pct": trade_data.get("pnl_pct"),
            "gross_pnl_pct": trade_data.get("gross_pnl_pct"),
            "fee_pct": trade_data.get("fee_pct"),
            "leverage": trade_data.get("leverage"),
            "minutes_open": round(float(trade_data.get("minutes_open") or 0), 1),
            "ladder_step": trade_data.get("ladder_step"),
            "ladder_name": trade_data.get("ladder_name"),
            "entry_price": trade_data.get("entry_price"),
            "exit_price": trade_data.get("exit_price"),
        }
        prompt = (
            "Sen kurumsal bir kripto vadeli işlemler hedge fonunun Baş Risk & Refleksiyon Analistisin.\n"
            "Aşağıdaki kapanan işleme özel GERÇEK, kalıpsız ve sonraki komite toplantılarında doğrudan referans verilebilecek somut bir işlem sonrası otopsi (post-mortem) ve aksiyon dersi yaz.\n"
            "Veri: " + json.dumps(payload_info, ensure_ascii=False) + "\n"
            "SADECE geçerli Türkçe JSON döndür: "
            '{"thesis_evaluation": "Tez ve piyasa davranışının 1-2 cümlelik somut değerlendirmesi", '
            '"lesson": "Sonraki işlemler için somut sayısal referanslı 1-2 cümlelik net kural/ders"}'
        )
        req_body = json.dumps({
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.35, "response_mime_type": "application/json"}
        }).encode("utf-8")

        for model_name in ("gemini-3-flash-preview", "gemini-3.8-flash", "gemini-flash-latest"):
            gl = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            vtx = f"https://aiplatform.googleapis.com/v1/publishers/google/models/{model_name}:generateContent?key={api_key}"
            urls = [gl, vtx]
            for url in urls:
                try:
                    req = urllib.request.Request(url, data=req_body, headers={"Content-Type": "application/json"}, method="POST")
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                    cands = res_data.get("candidates") or []
                    if not cands:
                        continue
                    raw_txt = "".join(
                        p.get("text", "") for p in ((cands[0].get("content") or {}).get("parts") or []) if isinstance(p, dict)
                    ).strip()
                    if raw_txt.startswith("```"):
                        raw_txt = raw_txt.strip("`")
                        if raw_txt.lower().startswith("json"):
                            raw_txt = raw_txt[4:].strip()
                    parsed = json.loads(raw_txt)
                    th = str(parsed.get("thesis_evaluation") or "").strip()
                    ls = str(parsed.get("lesson") or "").strip()
                    if th and ls:
                        return th, ls
                except Exception:
                    continue
        return None

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
        if status in ("HIT_TP", "HIT_TP1", "HIT_TP2", "HIT_TP2_RUNNER", "TIMEOUT_PROFIT_EXIT"):
            thesis_evaluation = "Kurumsal tez ve SMC likidite hedefi tam başarıyla gerçekleşti."
            lesson = (
                f"{symbol} {direction} işleminde ({status}) +%{pnl_pct} net kâr elde edildi. "
                f"SMC konsepti ve hacim desteği mükemmel çalıştı. "
                f"Ders: Yüksek güven skorlu kurulumlarda TP hedefine sadık kalmak yüksek alfa üretiyor."
            )
            outcome_type = "WIN"

        elif "LADDER" in status or status == "TRAILING_STOP_EXIT":
            thesis_evaluation = f"Fiyat kâra geçtikten sonra trend yoruldu, Merdiven Kâr Sistemi devreye girdi ({ladder_name})."
            lesson = (
                f"{symbol} {direction} işleminde Merdiven Kâr Kilidi ile +%{pnl_pct} net kâr kasaya alındı. "
                f"Ders: Fiyat geri dönse bile stopu kademeli kâra taşımak, kazancı kayba dönüştürmeyi %100 engelledi."
            )
            outcome_type = "WIN_LADDER"

        elif status in ("CLOSED_BE", "RUNNER_BE_EXIT"):
            thesis_evaluation = "İşlem komisyon kurtaran başabaş veya kısmi TP korumalı Runner BE seviyesinde güvenle kapatıldı."
            lesson = (
                f"{symbol} {direction} işleminde momentum zayıflayınca {status} devreye girdi (Net: {'+' if pnl_pct >= 0 else ''}%{pnl_pct}). "
                f"Ders: İnatlaşmayıp kârı ve komisyonu güvenceye almak gereksiz sermaye erimesini önledi."
            )
            outcome_type = "BE"

        elif status in ("TIMEOUT_EXIT", "MOMENTUM_STAGNATION_EXIT"):
            thesis_evaluation = f"Pozisyon {int(minutes_open)} dakika boyunca hedefe gitmedi, testere piyasasında yataya bağladı."
            lesson = (
                f"{symbol} {direction} işlemi {status} nedeniyle kapatıldı (Net: {'+' if pnl_pct >= 0 else ''}%{pnl_pct}). "
                f"Ders: Mikro-scalpingte hareketsiz pozisyonda beklemek fırsat maliyetidir; sermaye hemen likit edildi."
            )
            outcome_type = "TIMEOUT"

        elif status in ("HIT_SL", "EARLY_INVALIDATION_EXIT"):
            thesis_evaluation = "Stop-loss veya yapısal erken zarar kes seviyesine vuruldu, kurumsal tez geçersiz kaldı."
            # Neden stop oldu analizi
            if status == "EARLY_INVALIDATION_EXIT":
                failure_reason = "İlk mumlarda momentum teyidi alınamadı ve EMA20 aleyhine kapandı."
                action_rule = "Erken yapısal geçersiz kılma kalkanı büyük stop kaybını önledi."
            elif minutes_open < 10:
                failure_reason = "Girişten hemen sonra likidite avı fitili geldi (ani ters volatilite)."
                action_rule = "Aşırı oynak anlarda breakout yerine pullback teyidi beklenmeli."
            elif pnl_pct <= -15.0:
                failure_reason = "Sert piyasa yön değişimi yaşandı, stop korunmasa zarar büyüyecekti."
                action_rule = "Dar stop kuralı ve sabit $20 risk tavanı sermayeyi tam korudu."
            else:
                failure_reason = "Momentum kırılımı sahte çıktı veya BTC karşı yönde baskı kurdu."
                action_rule = "BTC Dead Chop veya zıt trend halindeyken bu yönde işleme girilmemeli."

            lesson = (
                f"{symbol} {direction} işleminde {status} gerçekleşti (Net: {'+' if pnl_pct >= 0 else ''}%{pnl_pct}). "
                f"{failure_reason} Ders: {action_rule}"
            )
            outcome_type = "LOSS"

        elif status in ("PAIR_MEAN_REVERSION_EXIT", "PAIR_PARTNER_CLOSED_EXIT"):
            thesis_evaluation = "Piyasa-nötr istatistiksel arbitraj çifti çıkışı gerçekleştirildi."
            lesson = f"{symbol} {direction} pair bacağı {status} ile Net {'+' if pnl_pct >= 0 else ''}%{pnl_pct} ile kapatıldı."
            outcome_type = "PAIR_EXIT"

        else:
            thesis_evaluation = "Manuel veya harici kapanış gerçekleştirildi."
            lesson = f"{symbol} {direction} işleminden Net %{pnl_pct} ile çıkıldı. Ders: Sistem kurallarına sadık kal."
            outcome_type = "MANUAL"

        llm_pair = ReflectorEngine._generate_llm_reflection(trade_data, outcome_type)
        if llm_pair:
            thesis_evaluation, lesson = llm_pair

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

        # Otonom Kendi Kendini Eğitme Döngüsünü Tetikle (Sürekli Öğrenen Ajan Politikası)
        try:
            from core.self_tuning_engine import SelfTuningEngine
            SelfTuningEngine.run_autonomous_training_cycle(auto_commit=True)
        except Exception as e:
            print(f"⚠️ [Reflector] Otonom eğitim döngüsü tetikleme hatası: {e}")

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

            pinned_rules = get_pinned_patron_lessons_db(limit=6)
            if not combined and not pinned_rules:
                return "Hafıza Defteri: Henüz kayıtlı geçmiş işlem dersi yok (Sistem ilk döngülerinde)."

            lines = []
            if pinned_rules:
                lines.append("📌 SABİT PATRON & EĞİTİM KURALLARI (Her Kararda Bağlayıcı):")
                for pr in pinned_rules:
                    lines.append(f"• [{pr.get('symbol', 'GENERAL')} | {pr.get('status')}]: {pr.get('lesson')}")

            if combined:
                lines.append("🧠 HAFIZA DEFTERİNDEN ÇIKARILAN SON DERSLER (Tauric Reflection Log):")
                for r in combined:
                    pnl = r.get("pnl_pct", 0.0)
                    sign = "+" if pnl >= 0 else ""
                    lines.append(f"• [{r.get('symbol')} {r.get('direction')} | {r.get('status')} | {sign}{pnl}%]: {r.get('lesson')}")

            return "\n".join(lines)
        except Exception as e:
            return f"Hafıza okuma hatası: {e}"

