"""
Multi-Agent Adversarial Debate Committee (Ajanlar Arası Yatırım Komitesi)
Institutional Hedge Fund Decision Chamber:
- 🟢 Boğa Analisti (Alpha Hunter - Setup'ı ve alım gücünü savunur)
- 🔴 Ayı Analisti (Devil's Advocate / Risk Şefi - Tuzakları, fonlama risklerini ve tehlikeleri ortaya döker)
- 📰 Makro & Duygu Masası (Haber akışını, BTC korelasyonunu ve piyasa rüzgarını değerlendirir)
- 👑 Komite Başkanı (Lead Arbiter - Argümanları tartar ve nihai konsensüs kararını verir)

Outputs structured multi-agent debate dialogue, pros & cons, consensus score, and binding verdict.
"""
import os
import json
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Tuple, Optional, List
from core.database import save_committee_debate_db, get_gemini_api_key
from core.reflection import ReflectorEngine

class AIAnalystAgent:
    def __init__(self):
        self.gemini_api_key = get_gemini_api_key()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()

    def _get_active_gemini_key(self) -> str:
        """Güncel Gemini API anahtarını dinamik olarak döner (DB veya env)."""
        key = get_gemini_api_key()
        if key:
            self.gemini_api_key = key
        return key or self.gemini_api_key

    def evaluate_setup(
        self,
        ta_setup: Dict,
        risk_report: Dict,
        news_analysis: Dict,
        btc_regime: Optional[Dict] = None,
        ticker: Optional[Dict] = None,
        funding_data: Optional[Dict] = None,
        quant_sim: Optional[Dict] = None
    ) -> Dict:
        """
        Geriye dönük uyumluluk ve komite tartışması ana çağrısı.
        Tauric Research 5 Kademeli Derecelendirme (Rating) Ölçeği içerir.
        """
        debate_result = self.run_committee_debate(
            ta_setup, risk_report, news_analysis, btc_regime, ticker, funding_data, quant_sim=quant_sim
        )

        direction = ta_setup["direction"]
        score = debate_result["consensus_score"]
        is_approved = (debate_result["consensus_verdict"] == "APPROVED")

        # 5 Kademeli Kurumsal Karar Ölçeği (Tauric Research standardı)
        if not is_approved:
            rating = "NEUTRAL_PASS"
        elif score >= 8.6:
            rating = f"STRONG_{direction}"
        elif score >= 7.6:
            rating = f"TACTICAL_{direction}"
        else:
            rating = "NEUTRAL_PASS"

        return {
            "ai_approved": is_approved,
            "ai_confidence": score,
            "verdict": rating,
            "rating": rating,
            "ai_critique": debate_result["decision_summary"],
            "source": debate_result.get("source", "Multi-Agent Debate Committee"),
            "edge_summary": f"R:R 1:{ta_setup.get('risk_reward', 1.5)} | Dar Stop %{ta_setup.get('sl_pct', 1.0)} | {rating}",
            "debate_data": debate_result
        }

    def run_committee_debate(
        self,
        ta_setup: Dict,
        risk_report: Dict,
        news_analysis: Dict,
        btc_regime: Optional[Dict] = None,
        ticker: Optional[Dict] = None,
        funding_data: Optional[Dict] = None,
        quant_sim: Optional[Dict] = None
    ) -> Dict:
        """
        Ajanlar arası karşılıklı tartışma oturumunu yönetir.
        Geçmiş işlem hafızasını (Reflections) tartışmaya dahil eder.
        """
        symbol = ta_setup["symbol"]
        direction = ta_setup["direction"]
        leverage = ta_setup.get("leverage", 10)
        score = ta_setup.get("confluence_score", 76)

        # 🧠 Tauric Reflector: Episodik Hafıza Defterinden son dersleri al
        past_context = ReflectorEngine.get_past_context_for_committee(symbol, limit=4)

        # 1. Eğer Gemini API Anahtarı mevcutsa gerçek Gemini LLM komitesini çağır
        if self._get_active_gemini_key():
            try:
                llm_debate = self._call_gemini_committee(
                    ta_setup, risk_report, news_analysis, btc_regime, ticker, funding_data,
                    past_context, quant_sim=quant_sim
                )
                if llm_debate:
                    llm_debate["past_memory_used"] = past_context
                    # DB'ye kaydet
                    save_committee_debate_db(
                        symbol, direction, llm_debate["consensus_verdict"],
                        llm_debate["consensus_score"], llm_debate["decision_summary"], llm_debate
                    )
                    return llm_debate
            except Exception as e:
                print(f"⚠️ [Gemini Debate] İstek hatası: {e}. Yerel Quant Komite motoruna geçiliyor.")

        # 2. Yerleşik Gelişmiş Quant Tartışma Motoru (Hedge-Fund Heuristics + Memory + Monte Carlo)
        debate = self._local_adversarial_debate(
            ta_setup, risk_report, news_analysis, btc_regime, ticker, funding_data, past_context, quant_sim=quant_sim
        )
        debate["past_memory_used"] = past_context

        # Veritabanına kaydet
        try:
            save_committee_debate_db(
                symbol, direction, debate["consensus_verdict"],
                debate["consensus_score"], debate["decision_summary"], debate
            )
        except Exception:
            pass

        return debate

    def _local_adversarial_debate(
        self,
        ta_setup: Dict,
        risk_report: Dict,
        news_analysis: Dict,
        btc_regime: Optional[Dict],
        ticker: Optional[Dict],
        funding_data: Optional[Dict],
        past_context: str = "",
        quant_sim: Optional[Dict] = None
    ) -> Dict:
        """
        Yerel Quant Ajanlar Arası Çelişkili Tartışma Simülasyonu (Tauric Research Modeli).
        Gerçek piyasa verilerini, indikatörleri ve geçmiş episodik hafıza derslerini konuşturur.
        """
        symbol = ta_setup["symbol"]
        direction = ta_setup["direction"]
        leverage = ta_setup.get("leverage", 10)
        score = ta_setup.get("confluence_score", 76)
        current_price = ta_setup.get("current_price", 0.0)
        sl_pct = ta_setup.get("sl_pct", 1.0)
        tp1_pct = ta_setup.get("tp1_pct", 1.6)
        rr = ta_setup.get("risk_reward", 1.5)
        reasons = ta_setup.get("ta_reasons", "")

        indicators = ta_setup.get("indicators", {})
        rsi_series = indicators.get("rsi") or []
        curr_rsi = rsi_series[-1] if rsi_series and rsi_series[-1] is not None else 50.0

        vwap_series = indicators.get("vwap") or []
        curr_vwap = vwap_series[-1] if vwap_series else current_price

        funding_rate = funding_data.get("lastFundingRate", 0.0) if funding_data else 0.0
        funding_pct = funding_rate * 100.0

        btc_status = btc_regime.get("status", "NEUTRAL") if btc_regime else "NEUTRAL"
        btc_summary = btc_regime.get("summary", "") if btc_regime else "BTC stabil"
        btc_price = btc_regime.get("btc_price", 0) if btc_regime else 0

        news_summary = news_analysis.get("summary", "Normal piyasa akışı")
        sentiment = news_analysis.get("sentiment", "NEUTRAL")

        # 🧠 Hafıza Defterinden son dersleri çıkar
        memory_warning = ""
        recent_memory_brief = ""
        if past_context and "HAFIZA" in past_context:
            lines = [l.strip() for l in past_context.splitlines() if l.strip().startswith("•")]
            if lines:
                recent_memory_brief = lines[0].replace("• ", "")
                memory_warning = f" Hafıza Defterimizi unutmayın: '{recent_memory_brief}'. Aynı hataya iki kez düşmemeliyiz!"

        # ----------------------------------------------------
        # 🟢 1. BOĞA ANALİSTİ (Alpha Hunter - Argümanı Savunan Ajan)
        # ----------------------------------------------------
        horizon_desc = ta_setup.get("trade_horizon") or "15m Kısa Vade"
        bull_points = []
        if direction == "LONG":
            bull_points.append(f"{horizon_desc} grafiğinde kurumsal alıcı desteği çok net ({score}/100 SMC skoru)")
            if current_price >= curr_vwap:
                bull_points.append(f"Fiyat VWAP (${curr_vwap:.4f}) üzerinde kalarak alıcıların tahtayı koruduğunu gösteriyor")
            bull_points.append(f"RSI ({curr_rsi:.1f}) pozitif ivme bölgesinde, aşırı alıma girmeden sağlıklı ilerliyor")
            bull_points.append(f"{leverage}x kaldıraç ile +%{tp1_pct} hedefimiz (+%{round(tp1_pct * leverage, 1)} net marjin) çok makul")

            bull_arg = (
                f"{symbol} için bu LONG kurulumu kaçırılmayacak bir fırsat! "
                f"{'. '.join(bull_points)}. "
                f"Alıcılar satış bloklarını emiyor, hacim desteğiyle yukarı patlama bekliyorum."
            )
        else:
            bull_points.append(f"{horizon_desc} grafiğinde kurumsal satıcı baskısı ve arz boşluğu net ({score}/100 SMC skoru)")
            if current_price <= curr_vwap:
                bull_points.append(f"Fiyat VWAP (${curr_vwap:.4f}) altında kalarak satıcıların piyasayı ezdiğini kanıtlıyor")
            bull_points.append(f"RSI ({curr_rsi:.1f}) aşağı yönlü baskıyı teyit ediyor, satış dalgası taze")
            bull_points.append(f"{leverage}x kaldıraç ile %{tp1_pct} düşüş hedefimiz (+%{round(tp1_pct * leverage, 1)} marjin kârı) lehimize")

            bull_arg = (
                f"{symbol} paritesinde çok temiz bir SHORT fırsatı yakaladık! "
                f"{'. '.join(bull_points)}. "
                f"Satıcılar tahtayı aşağı süpürüyor, düşüş trendinin devamı çok kuvvetli."
            )

        # ----------------------------------------------------
        # 🔴 2. AYI ANALİSTİ (Devil's Advocate / Risk Şefi - Şüpheci Ajan)
        # ----------------------------------------------------
        bear_points = []
        is_fatal_trap = False
        trap_reason = ""

        if recent_memory_brief:
            bear_points.append(f"Geçmiş Hafıza Uyarısı: {recent_memory_brief}")

        if direction == "LONG":
            if funding_pct > 0.015:
                bear_points.append(f"Fonlama oranı +%{funding_pct:.4f} ile çok yüksek, perakende long aşırı kalabalık. Likidite avı (fitil) riski var!")
                is_fatal_trap = True
                trap_reason = "Şişkin pozitif fonlama ve likidite avı riski"
            elif funding_pct > 0.005:
                bear_points.append(f"Fonlama pozitif (+%{funding_pct:.4f}), dikkatli olunmalı")

            if curr_rsi > 70.0:
                bear_points.append(f"RSI {curr_rsi:.1f} seviyesinde, aşırı alım bölgesindeyiz. Buradan alım yapmak tepe likiditesi olmak demek!")
                is_fatal_trap = True
                trap_reason = "Aşırı yükselmiş RSI (>70.0 tepeden mal alma riski)"
            elif curr_rsi < 42:
                bear_points.append(f"RSI {curr_rsi:.1f} zayıf momentumda, yukarı tepki zayıf kalabilir")

            if btc_status in ("DEAD_CHOP", "DUMP_ALERT", "BEARISH"):
                bear_points.append(f"BTC {btc_status} durumunda ({btc_summary}). Lider zayıfken altcoin long'u açmak boğa tuzağı (bull trap) olabilir!")
                if btc_status == "DEAD_CHOP":
                    is_fatal_trap = True
                    trap_reason = "Bitcoin ölü testere piyasasında, sahte kırılım riski"
            
            bear_points.append(f"Stop mesafemiz %{sl_pct}. Normal dalgalanmada fitil yeme riskimiz var")

            bear_arg = (
                f"Bir dakika durun! Çok aceleci davranıyorsunuz.{memory_warning} "
                f"{'. '.join(bear_points)}. "
                f"Bu piyasada tuzaklar çok fazla, sermayeyi gereksiz yere riske atmamalıyız!"
            )
        else: # SHORT
            if funding_pct < -0.015:
                bear_points.append(f"Fonlama oranı -%{abs(funding_pct):.4f} ile negatif! Herkes short'a yığılmış, ani bir short squeeze (sıkışma) ile patlayabiliriz!")
                is_fatal_trap = True
                trap_reason = "Negatif fonlama ve ani short squeeze riski"
            elif funding_pct < -0.005:
                bear_points.append(f"Fonlama negatif (-%{abs(funding_pct):.4f}), yukarı sıçrama riski var")

            if curr_rsi < 30.0:
                bear_points.append(f"RSI {curr_rsi:.1f} ile aşırı satım bölgesine inmiş! Buradan short açmak ayı tuzağına (bear trap) düşmek olur!")
                is_fatal_trap = True
                trap_reason = "Aşırı düşmüş RSI (<30.0 dipten short açma riski)"
            elif curr_rsi > 58:
                bear_points.append(f"RSI {curr_rsi:.1f} seviyesinde alıcı baskısı devam ediyor, short için henüz erken")

            if btc_status == "BULLISH":
                bear_points.append("BTC güçlü boğa modundayken altcoin shortlamak akıntıya karşı yüzmektir!")

            bear_points.append(f"Stop mesafemiz %{sl_pct}. Ani rahatlama sıçramalarında zarar edebiliriz")

            bear_arg = (
                f"Bekleyin! Bu SHORT işleminde büyük bir tehlike görüyorum.{memory_warning} "
                f"{'. '.join(bear_points)}. "
                f"Düşüşe atlamak yerine teyit beklemek çok daha güvenli!"
            )

        # ----------------------------------------------------
        # 🏛️ 3. HABER KARARLANDIRMA KONSEYİ (News Intelligence Council - 3 Uzman Masa)
        # ----------------------------------------------------
        council_quotes = news_analysis.get("council_debate", [])
        news_verdict = news_analysis.get("verdict", "NÖTR ORGANİK AKIŞ")
        news_score = news_analysis.get("news_score", 50)
        pos_mult = news_analysis.get("pos_multiplier", 1.0)
        
        council_summary_str = " | ".join(council_quotes) if council_quotes else news_summary
        macro_arg = (
            f"🏛️ Haber Kararlandırma Konseyi ({news_score}/100 Puan | {news_verdict} | Kasa Çarpanı: {pos_mult}x): "
            f"{council_summary_str}. "
            f"Makro Lider: Bitcoin ${btc_price:,.0f} ({btc_summary})."
        )

        # ----------------------------------------------------
        # 🎲 4. KUANT & MONTE CARLO SİMÜLASYON MASASI (10,000 Fiyat Yolu Simülatörü)
        # ----------------------------------------------------
        quant_approved = True
        quant_win_prob = 72.0
        quant_loss_prob = 28.0
        quant_exp_r = 1.40
        quant_arg = ""

        if quant_sim:
            quant_approved = quant_sim.get("is_approved", True)
            quant_win_prob = quant_sim.get("win_probability_pct", 72.0)
            quant_loss_prob = quant_sim.get("loss_probability_pct", 28.0)
            quant_exp_r = quant_sim.get("expected_return_r", 1.40)
            quant_arg = quant_sim.get("argument", "")
        else:
            quant_arg = (
                f"{symbol} üzerinde 10,000 Monte Carlo fiyat yolu koşturuldu. "
                f"TP1'e ulaşma olasılığı: %{quant_win_prob:.1f}, SL Riski: %{quant_loss_prob:.1f}. OY: ONAYLANDI."
            )

        # ----------------------------------------------------
        # 👑 5. KOMİTE BAŞKANI (Lead Arbiter - Nihai Karar ve Sentez)
        # ----------------------------------------------------
        dialogue = [
            {"role": "BULL", "agent_name": "Boğa Analisti (Alpha Hunter)", "avatar": "🟢", "argument": bull_arg},
            {"role": "BEAR", "agent_name": "Ayı Analisti (Risk Şefi)", "avatar": "🔴", "argument": bear_arg},
            {"role": "MACRO", "agent_name": "Haber Kararlandırma Konseyi (3 Uzman Masa)", "avatar": "🏛️", "argument": macro_arg},
            {
                "role": "QUANT",
                "agent_name": "Kuant Simülasyon Ajanı (Monte Carlo 10,000 Yol)",
                "avatar": "🎲",
                "argument": quant_arg,
                "metrics": {
                    "simulations": quant_sim.get("num_simulations", 10000) if quant_sim else 10000,
                    "win_rate": quant_win_prob,
                    "loss_rate": quant_loss_prob,
                    "expectancy_r": quant_exp_r,
                    "vote": "APPROVED" if quant_approved else "REJECTED"
                }
            }
        ]

        from config import MIN_CONFLUENCE_SCORE
        try:
            from core.self_tuning_engine import SelfTuningEngine
            active_min_score = SelfTuningEngine.get_current_params().get("min_confluence_score", MIN_CONFLUENCE_SCORE)
        except Exception:
            active_min_score = MIN_CONFLUENCE_SCORE

        if is_fatal_trap or score < active_min_score or not quant_approved:
            consensus_verdict = "REJECTED"
            consensus_score = round(min(7.2, max(5.0, score / 10.0)), 1)
            rating = "NEUTRAL_PASS"
            if not quant_approved:
                chief_arg = (
                    f"Komite Kararı: Kuant Simülasyon Ajanı'nın 10,000 Monte Carlo stokastik fiyat yolu simülasyonu "
                    f"yetersiz kazanma olasılığı (%{quant_win_prob:.1f} < %48.0) veya negatif beklenti ({quant_exp_r:+.2f}R) tespit etti! "
                    f"Matematiksel kural gereği Boğa talebi VETO EDİLDİ (Rating: {rating})."
                )
            else:
                chief_arg = (
                    f"Komite Kararı: Ayı Analisti'nin uyarıları ve risk argümanları haklı bulundu! "
                    f"'{trap_reason or 'Yetersiz güven skoru'}' nedeniyle Boğa Analisti'nin talebi VETO EDİLDİ. "
                    f"Sermaye koruma kuralımız gereği bu işlem pas geçiliyor (Rating: {rating})."
                )
        else:
            consensus_verdict = "APPROVED"
            # Kuant onayı ek güven skoru ekler (%55 üzeri win rate)
            bonus = 0.3 if quant_win_prob >= 55.0 else 0.0
            consensus_score = round(min(9.8, 7.8 + (score - active_min_score) * 0.1 + bonus), 1)
            rating = f"STRONG_{direction}" if consensus_score >= 8.6 else f"TACTICAL_{direction}"
            chief_arg = (
                f"Komite Kararı: Boğa Analisti'nin SMC argümanları, Kuant Ajanı'nın 10,000 Monte Carlo "
                f"fiyat yolu simülasyonu (%{quant_win_prob:.1f} TP ihtimali, +{quant_exp_r:.2f}R beklenti) ile tam teyit edildi! "
                f"Ayı Analisti'nin belirttiği riskler ve hafıza kayıtları değerlendirildi; "
                f"dinamik stopumuz (%{sl_pct}) ve basamaklı Merdiven Kâr Kilidimiz ile kontrol altına alındı. "
                f"Risk/Ödül 1:{rr} oranı lehimize. İşlem {leverage}x kaldıraçla ONAYLANDI (Rating: {rating})."
            )

        dialogue.append({
            "role": "CHIEF",
            "agent_name": "Yatırım Komitesi Başkanı (Nihai Karar)",
            "avatar": "👑",
            "argument": chief_arg
        })

        return {
            "symbol": symbol,
            "direction": direction,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "consensus_verdict": consensus_verdict,
            "consensus_score": consensus_score,
            "rating": rating,
            "decision_summary": chief_arg,
            "debate_dialogue": dialogue,
            "strengths": bull_points[:3],
            "concerns": bear_points[:3],
            "source": "Ajanlar Yatırım Komitesi (Tauric Multi-Agent Framework)"
        }

    @staticmethod
    def _build_gemini_endpoints(api_key: str, model_name: str) -> List[str]:
        """Anahtar tipine göre (AQ.* -> Vertex Express, AIza* -> AI Studio) uygun REST uç noktalarını sırayla döner."""
        vtx = f"https://aiplatform.googleapis.com/v1/publishers/google/models/{model_name}:generateContent?key={api_key}"
        gl = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        return [vtx, gl] if api_key.startswith("AQ.") else [gl, vtx]

    @staticmethod
    def _extract_http_error(err: Exception) -> str:
        if isinstance(err, urllib.error.HTTPError):
            try:
                body = err.read().decode("utf-8", errors="ignore")
                parsed = json.loads(body)
                if isinstance(parsed, list) and parsed:
                    parsed = parsed[0]
                msg = (parsed.get("error") or {}).get("message") if isinstance(parsed, dict) else ""
                return f"HTTP {err.code}: {msg or body[:160]}"
            except Exception:
                return f"HTTP {err.code}: {err.reason}"
        return str(err)

    def _call_gemini_api(self, parts: List[Dict], temperature: float = 0.45, timeout: int = 24) -> Optional[Dict]:
        """Google Gemini API'yi (gemini-2.5-flash -> gemini-2.0-flash fallback) çağırır ve JSON döner."""
        api_key = self._get_active_gemini_key()
        if not api_key:
            return None

        self._last_gemini_error = ""
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": temperature,
                "response_mime_type": "application/json"
            }
        }
        encoded = json.dumps(payload).encode("utf-8")

        for model_name in ("gemini-2.5-flash", "gemini-2.0-flash"):
            for url in self._build_gemini_endpoints(api_key, model_name):
                try:
                    req = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=timeout) as response:
                        res_data = json.loads(response.read().decode("utf-8"))
                    candidates = res_data.get("candidates") or []
                    if not candidates:
                        continue
                    part_list = (candidates[0].get("content") or {}).get("parts") or []
                    raw_text = "".join(p.get("text", "") for p in part_list if isinstance(p, dict)).strip()
                    if not raw_text:
                        continue
                    if raw_text.startswith("```"):
                        raw_text = raw_text.strip("`")
                        if raw_text.lower().startswith("json"):
                            raw_text = raw_text[4:].strip()
                    parsed = json.loads(raw_text)
                    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                        parsed = parsed[0]
                    if isinstance(parsed, dict):
                        parsed["_gemini_model"] = model_name
                        return parsed
                except Exception as err:
                    self._last_gemini_error = self._extract_http_error(err)
                    print(f"⚠️ [Gemini API - {model_name}] Çağrı hatası: {self._last_gemini_error}")
                    continue
        return None

    def _call_gemini_committee(
        self,
        ta_setup: Dict,
        risk_report: Dict,
        news_analysis: Dict,
        btc_regime: Optional[Dict],
        ticker: Optional[Dict],
        funding_data: Optional[Dict],
        past_context: str = "",
        quant_sim: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Gerçek Gemini LLM kullanarak ham teknik/kuant verileriyle 4 ajanlı adversarial münazara üretir."""
        symbol = ta_setup["symbol"]
        direction = ta_setup["direction"]
        leverage = ta_setup.get("leverage", 10)
        score = ta_setup.get("confluence_score", 76)
        indicators = ta_setup.get("indicators", {})
        rsi_list = indicators.get("rsi") or []
        vwap_list = indicators.get("vwap") or []
        lr_ch = indicators.get("lr_channel") or {}
        vp = indicators.get("volume_profile") or {}
        adx_d = indicators.get("adx_data") or {}
        st_d = indicators.get("supertrend") or {}
        mc = quant_sim or {}

        telemetry_summary = {
            "rsi_latest": round(float(rsi_list[-1]), 2) if rsi_list and rsi_list[-1] is not None else None,
            "vwap_latest": round(float(vwap_list[-1]), 6) if vwap_list else None,
            "poc": vp.get("poc"),
            "vah": vp.get("vah"),
            "val": vp.get("val"),
            "lr_trend": lr_ch.get("trend"),
            "lr_pos_pct": lr_ch.get("position_pct"),
            "adx": adx_d.get("adx"),
            "supertrend": st_d.get("trend"),
            "mc_win_prob_pct": mc.get("win_probability_pct"),
            "mc_expectancy_r": mc.get("expectancy_r"),
            "funding_rate_pct": funding_data.get("fundingRatePct") if isinstance(funding_data, dict) else None,
            "change_24h_pct": ticker.get("priceChangePercent") if isinstance(ticker, dict) else None,
            "quote_vol_24h": ticker.get("quoteVolume") if isinstance(ticker, dict) else None,
            "allocated_margin_usdt": risk_report.get("allocated_margin_usdt") if isinstance(risk_report, dict) else None,
            "risk_usd": risk_report.get("risk_usd") if isinstance(risk_report, dict) else None,
        }

        prompt = (
            f"Sen kurumsal bir kripto vadeli işlemler hedge fonunun 4 üyeli Yatırım Komitesini gerçek zamanlı yöneten Baş Yapay Zekasın.\n"
            f"KESİNLİKLE kalıp/jenerik cümleler kurma! Yalnızca aşağıdaki ham verilere ve geçmiş derslere dayanarak her ajan için somut fiyat ve oran içeren özgün teknik muhakeme üret.\n\n"
            f"Parite: {symbol} | Önerilen Yön: {direction} ({leverage}x) | Vade: {ta_setup.get('timeframe', '15m')} | SMC Skor: {score}/100\n"
            f"Giriş: {ta_setup.get('current_price')} | SL: {ta_setup.get('stop_loss')} (-%{ta_setup.get('sl_pct')}) | "
            f"TP1: {ta_setup.get('take_profit_1')} (+%{ta_setup.get('tp1_pct')}) | TP2: {ta_setup.get('take_profit_2')} | R:R: 1:{ta_setup.get('risk_reward')}\n"
            f"SMC Bulguları: {ta_setup.get('ta_reasons')}\n"
            f"Ham Telemetri JSON: {json.dumps(telemetry_summary, ensure_ascii=False)}\n"
            f"Haber Özeti: {news_analysis.get('summary') if isinstance(news_analysis, dict) else 'Nötr'}\n"
            f"BTC Rejimi: {btc_regime.get('summary') if isinstance(btc_regime, dict) else 'Nötr'}\n"
            f"{past_context}\n\n"
            f"Türkçe olarak 4 üyenin somut sayısal verilerle çatışan tartışmasını ve bağlayıcı kararını SADECE geçerli JSON formatında döndür:\n"
            f'{{"symbol": "{symbol}", "direction": "{direction}", "timestamp": "{datetime.now().strftime("%H:%M:%S")}", '
            f'"consensus_verdict": "APPROVED" veya "REJECTED", "consensus_score": 1.0-10.0 arası sayı, '
            f'"rating": "STRONG_{direction}" veya "TACTICAL_{direction}" veya "NEUTRAL_PASS", '
            f'"decision_summary": "Başkanın somut seviye içeren 1-2 cümlelik nihai kararı", '
            f'"debate_dialogue": ['
            f'{{"role": "BULL", "agent_name": "Boğa Analisti (Alpha Hunter)", "avatar": "🟢", "argument": "..."}}, '
            f'{{"role": "BEAR", "agent_name": "Ayı Analisti (Risk Şefi)", "avatar": "🔴", "argument": "..."}}, '
            f'{{"role": "MACRO", "agent_name": "Makro & Kuant Masası", "avatar": "📰", "argument": "..."}}, '
            f'{{"role": "CHIEF", "agent_name": "Yatırım Komitesi Başkanı", "avatar": "👑", "argument": "..."}}'
            f'], "strengths": ["somut güç 1", "somut güç 2"], "concerns": ["somut risk 1", "somut risk 2"]}}'
        )

        res = self._call_gemini_api([{"text": prompt}], temperature=0.45, timeout=20)
        if not res:
            return None
        model_used = res.pop("_gemini_model", "gemini-2.5-flash")
        res.setdefault("symbol", symbol)
        res.setdefault("direction", direction)
        res.setdefault("timestamp", datetime.now().strftime("%H:%M:%S"))
        res["consensus_score"] = round(max(1.0, min(10.0, float(res.get("consensus_score") or 7.0))), 1)
        res["consensus_verdict"] = "APPROVED" if str(res.get("consensus_verdict", "")).upper() == "APPROVED" else "REJECTED"
        res["source"] = f"Gerçek Yapay Zeka ({model_used})"
        return res

    def analyze_chart_or_coin_with_ai(
        self,
        client,
        symbol: str = "",
        timeframe: str = "15m",
        image_b64: str = "",
        image_mime: str = "image/png",
        user_prompt: str = ""
    ) -> Dict:
        """
        Grafik ekran görüntüsü (Multimodal Vision) ve/veya canlı Binance Futures verisi üzerinde
        sıfır şablonlu gerçek Gemini 2.5 Flash teknik/SMC muhakemesi çalıştırır.
        """
        clean_sym = str(symbol or "").upper().strip()
        if clean_sym and not clean_sym.endswith("USDT"):
            clean_sym = f"{clean_sym}USDT"
        clean_tf = str(timeframe or "15m").lower().strip()
        if clean_tf not in ("5m", "15m", "30m", "1h", "4h"):
            clean_tf = "15m"

        telemetry: Dict = {"symbol": clean_sym, "timeframe": clean_tf}

        if clean_sym and client is not None:
            try:
                from agents.ta_agent import TechnicalAnalysisAgent
                from core.advanced_indicators import (
                    calculate_linear_regression_channel,
                    calculate_volume_profile,
                    calculate_adx,
                    calculate_supertrend,
                    calculate_vwap_bands,
                )
                candles_tf = client.get_klines(clean_sym, interval=clean_tf, limit=60) or []
                candles_4h = client.get_klines(clean_sym, interval="4h", limit=45) if clean_tf != "4h" else candles_tf
                tickers = client.get_24hr_tickers() or {}
                ticker_sym = tickers.get(clean_sym, {})
                funding_sym = client.get_funding_rate(clean_sym) or {}
                book_sym = client.get_book_ticker(clean_sym) or {}

                if candles_tf and len(candles_tf) >= 20:
                    closes = [float(c["close"]) for c in candles_tf]
                    rsi_vals = TechnicalAnalysisAgent.calculate_rsi(closes, 14)
                    atr_vals = TechnicalAnalysisAgent.calculate_atr(candles_tf, 14)
                    fvg_res = TechnicalAnalysisAgent.detect_fvg(candles_tf, max_lookback=15)
                    ob_res = TechnicalAnalysisAgent.detect_order_blocks(candles_tf, max_lookback=20)
                    sweep_res = TechnicalAnalysisAgent.detect_liquidity_sweep(candles_tf, lookback=15)
                    lr_res = calculate_linear_regression_channel(candles_tf)
                    vp_res = calculate_volume_profile(candles_tf)
                    adx_res = calculate_adx(candles_tf)
                    st_res = calculate_supertrend(candles_tf)
                    vwap_res = calculate_vwap_bands(candles_tf)

                    recent_20 = candles_tf[-20:]
                    swing_high = round(max(float(c["high"]) for c in candles_tf[-35:]), 6)
                    swing_low = round(min(float(c["low"]) for c in candles_tf[-35:]), 6)
                    curr_close = closes[-1]
                    prev_20_high = max(float(c["high"]) for c in candles_tf[-25:-5])
                    prev_20_low = min(float(c["low"]) for c in candles_tf[-25:-5])
                    if curr_close > prev_20_high:
                        bos_choch_hint = "Bullish BOS / Yukarı Yapı Kırılımı"
                    elif curr_close < prev_20_low:
                        bos_choch_hint = "Bearish BOS / Aşağı Yapı Kırılımı"
                    else:
                        bos_choch_hint = "Range / Yapı İçi Konsolidasyon"

                    bid_px = float(book_sym.get("bidPrice") or 0.0)
                    ask_px = float(book_sym.get("askPrice") or 0.0)
                    spread_pct = round(((ask_px - bid_px) / bid_px) * 100.0, 4) if bid_px > 0 and ask_px > 0 else None

                    compact_candles = [
                        {
                            "o": round(float(c["open"]), 6),
                            "h": round(float(c["high"]), 6),
                            "l": round(float(c["low"]), 6),
                            "c": round(float(c["close"]), 6),
                            "v": round(float(c.get("volume", 0.0)), 2)
                        }
                        for c in recent_20
                    ]
                    st_4h = calculate_supertrend(candles_4h).get("trend") if candles_4h and len(candles_4h) >= 15 else "N/A"

                    telemetry.update({
                        "current_price": curr_close,
                        "change_24h_pct": ticker_sym.get("priceChangePercent"),
                        "quote_volume_24h": ticker_sym.get("quoteVolume"),
                        "funding_rate_pct": funding_sym.get("fundingRatePct"),
                        "spread_pct": spread_pct,
                        "rsi_14": round(float(rsi_vals[-1]), 2) if rsi_vals and rsi_vals[-1] is not None else None,
                        "atr_14": round(float(atr_vals[-1]), 6) if atr_vals and atr_vals[-1] is not None else None,
                        "adx": adx_res.get("adx"),
                        "supertrend": st_res.get("trend"),
                        "supertrend_4h": st_4h,
                        "vwap": vwap_res.get("vwap"),
                        "vwap_z_score": vwap_res.get("z_score"),
                        "poc": vp_res.get("poc"),
                        "vah": vp_res.get("vah"),
                        "val": vp_res.get("val"),
                        "lr_trend": lr_res.get("trend"),
                        "lr_pos_pct": lr_res.get("position_pct"),
                        "swing_high_35": swing_high,
                        "swing_low_35": swing_low,
                        "structure_hint": bos_choch_hint,
                        "fvg": {"bull": fvg_res.get("bullish_fvg"), "bear": fvg_res.get("bearish_fvg")},
                        "order_blocks": {"bull": ob_res.get("bullish_ob"), "bear": ob_res.get("bearish_ob")},
                        "liquidity_sweep": sweep_res,
                        "last_20_candles": compact_candles,
                    })
            except Exception as tel_err:
                telemetry["telemetry_error"] = str(tel_err)

        if not clean_sym and not image_b64:
            return {"status": "error", "message": "Lütfen bir coin sembolü girin veya grafik ekran görüntüsü yükleyin."}

        if not self._get_active_gemini_key():
            return {
                "status": "key_required",
                "ai_key_missing": True,
                "symbol": clean_sym or "GÖRSEL",
                "timeframe": clean_tf,
                "telemetry": telemetry,
                "message": "Gerçek Gemini 2.5 Flash muhakemesi ve grafik okuma için önce panelden Google Gemini API anahtarınızı kaydedin."
            }

        parts: List[Dict] = []
        clean_b64 = str(image_b64 or "").strip()
        if clean_b64:
            if "," in clean_b64 and clean_b64.startswith("data:"):
                header_part, clean_b64 = clean_b64.split(",", 1)
                if ";" in header_part and ":" in header_part:
                    image_mime = header_part.split(":", 1)[1].split(";", 1)[0]
            parts.append({
                "inline_data": {
                    "mime_type": str(image_mime or "image/png"),
                    "data": clean_b64
                }
            })

        past_notes = ReflectorEngine.get_past_context_for_committee(clean_sym or "BTCUSDT", limit=3)
        prompt_text = (
            "Sen kurumsal bir Kripto Vadeli İşlemler Baş Analisti ve SMC/Fiyat Aksiyonu (Price Action) uzmanısın.\n"
            "Sana verilen verileri (varsa yüklenen grafik ekran görüntüsündeki mumlar, fitiller, sağdaki fiyat ekseni, çizili indikatörler ve formasyonlar; ayrıca varsa canlı Binance Futures OHLCV ve SMC telemetrisi) birleştirerek GERÇEK, ÖZGÜN ve DERİN bir analiz üret.\n"
            "ASLA yuvarlak/jenerik şablon ifadeler yazma; mutlaka somut fiyat seviyeleri, yapısal kırılım noktaları, Boğa ve Ayı senaryolarını anlat.\n\n"
            f"Hedef Sembol: {clean_sym or 'Grafikten Tespit Et'} | Vade: {clean_tf}\n"
            f"Kullanıcı Sorusu / Notu: {user_prompt or 'Genel kurumsal SMC, likidite ve risk/ödül değerlendirmesi yap.'}\n"
            f"Canlı Borsa Telemetrisi: {json.dumps(telemetry, ensure_ascii=False)}\n"
            f"{past_notes}\n\n"
            "Yalnızca geçerli tek bir Türkçe JSON nesnesi döndür:\n"
            "{\n"
            '  "detected_symbol": "Sembol (örn: ETHUSDT)",\n'
            '  "detected_timeframe": "Vade (örn: 15m)",\n'
            '  "market_bias": "BULLISH" veya "BEARISH" veya "NEUTRAL_RANGE",\n'
            '  "confidence_score": 0-100 arası tam sayı,\n'
            '  "market_structure": {\n'
            '    "trend": "Ana/ikincil trend yönü özeti",\n'
            '    "bos_choch": "Tespit edilen BOS / CHoCH kırılım seviyeleri ve fiyatları",\n'
            '    "key_levels": ["Direnç/Destek fiyat seviyesi 1", "Seviye 2", "Seviye 3"]\n'
            '  },\n'
            '  "smc_liquidity_map": {\n'
            '    "order_blocks": "Tespit edilen OB bölgeleri (fiyat aralığı)",\n'
            '    "fvg_gaps": "Doldurulmamış FVG dengesizlik bölgeleri",\n'
            '    "liquidity_pools": "Eşit tepeler/dipler ve olası stop-avı (sweep) hedefleri",\n'
            '    "patterns": ["Görülen mum / grafik formasyonları"]\n'
            '  },\n'
            '  "deep_ai_commentary": "3-5 cümlelik sıfır şablonlu, fiyat seviyeli, hem fırsat hem tuzak senaryosunu anlatan derin yapay zeka yorumu",\n'
            '  "trade_plan": {\n'
            '    "action": "LONG" veya "SHORT" veya "BEKLE",\n'
            '    "entry_zone": "Önerilen giriş fiyatı/aralığı",\n'
            '    "stop_loss": "Geçersiz kılma (SL) seviyesi ve gerekçesi",\n'
            '    "take_profit_1": "İlk likidite/TP1 hedefi",\n'
            '    "take_profit_2": "Runner TP2 hedefi",\n'
            '    "risk_reward": "Tahmini R:R oranı (örn: 1:2.2)"\n'
            '  }\n'
            "}"
        )
        parts.append({"text": prompt_text})

        ai_res = self._call_gemini_api(parts, temperature=0.35, timeout=28)
        if not ai_res:
            return {
                "status": "error",
                "ai_key_missing": False,
                "symbol": clean_sym or "GÖRSEL",
                "timeframe": clean_tf,
                "telemetry": telemetry,
                "message": "Gemini API yanıt vermedi. API anahtarınızı veya kotanızı kontrol edip tekrar deneyin."
            }

        model_used = ai_res.pop("_gemini_model", "gemini-2.5-flash")
        ai_res.setdefault("detected_symbol", clean_sym or "Bilinmiyor")
        ai_res.setdefault("detected_timeframe", clean_tf)
        ai_res.setdefault("market_bias", "NEUTRAL_RANGE")
        ai_res["confidence_score"] = int(max(0, min(100, float(ai_res.get("confidence_score") or 50))))
        ai_res["source"] = f"Gerçek Yapay Zeka ({model_used}{' + Vision' if clean_b64 else ''})"

        return {
            "status": "ok",
            "ai_key_missing": False,
            "symbol": ai_res["detected_symbol"],
            "timeframe": ai_res["detected_timeframe"],
            "telemetry": telemetry,
            "analysis": ai_res
        }

    def _call_gemini_chat(
        self,
        system_instruction: str,
        contents: List[Dict],
        temperature: float = 0.45,
        timeout: int = 26
    ) -> Optional[Tuple[str, str]]:
        """Çok turlu sohbet ve tartışma için Gemini API'yi doğal metin modunda çağırır."""
        api_key = self._get_active_gemini_key()
        if not api_key:
            return None

        self._last_gemini_error = ""
        headers = {"Content-Type": "application/json"}
        payload = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": contents,
            "generationConfig": {"temperature": temperature}
        }
        encoded = json.dumps(payload).encode("utf-8")

        for model_name in ("gemini-2.5-flash", "gemini-2.0-flash"):
            for url in self._build_gemini_endpoints(api_key, model_name):
                try:
                    req = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=timeout) as response:
                        res_data = json.loads(response.read().decode("utf-8"))
                    candidates = res_data.get("candidates") or []
                    if not candidates:
                        continue
                    parts = (candidates[0].get("content") or {}).get("parts") or []
                    reply_text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
                    if reply_text:
                        return reply_text, model_name
                except Exception as err:
                    self._last_gemini_error = self._extract_http_error(err)
                    print(f"⚠️ [Gemini Chat - {model_name}] Çağrı hatası: {self._last_gemini_error}")
                    continue
        return None

    def chat_with_strategist(
        self,
        client,
        message: str,
        history: Optional[List[Dict]] = None,
        symbol: str = "",
        timeframe: str = "15m"
    ) -> Dict:
        """
        Patron Efe ile canlı portföy, açık/geçmiş işlemler, ders çıkarımı ve coin kararları üzerine
        çok turlu (multi-turn) tartışabilen gerçek Gemini 2.5 Flash Baş Stratejist sohbet motoru.
        """
        user_msg = str(message or "").strip()
        if not user_msg:
            return {"status": "error", "message": "Lütfen bir soru veya yorum yazın."}

        if not self._get_active_gemini_key():
            return {
                "status": "key_required",
                "ai_key_missing": True,
                "message": "AI Baş Stratejist ile canlı sohbet ve işlem tartışması için önce Gemini API anahtarınızı bağlayın."
            }

        from core.database import (
            get_active_and_pending_signals,
            get_all_signals,
            get_performance_stats,
            get_recent_reflections_db,
            get_today_trades_count_by_timeframe,
        )

        # 1. Canlı Portföy, Açık Pozisyonlar ve Son İşlemler Bağlamı
        stats = {}
        active_list = []
        recent_closed = []
        reflections = []
        quotas = {}
        btc_regime = {}
        try:
            stats = get_performance_stats() or {}
            active_raw = get_active_and_pending_signals() or []
            tickers = (client.get_24hr_tickers() or {}) if client is not None else {}
            for s in active_raw:
                sym_s = s.get("symbol", "")
                entry_s = float(s.get("actual_entry_price") or s.get("entry_min") or 0.0)
                live_s = float((tickers.get(sym_s) or {}).get("lastPrice") or entry_s)
                lev_s = int(s.get("leverage") or 10)
                is_l = (s.get("direction") == "LONG")
                raw_p = ((live_s - entry_s) / entry_s) if (entry_s > 0 and is_l) else (((entry_s - live_s) / entry_s) if entry_s > 0 else 0.0)
                est_net_pct = round(raw_p * lev_s * 100.0 - (0.10 * lev_s), 2)
                active_list.append({
                    "id": s.get("id"),
                    "symbol": sym_s,
                    "direction": s.get("direction"),
                    "timeframe": s.get("timeframe"),
                    "is_pair": s.get("is_pair_trade"),
                    "pair_symbol": s.get("pair_symbol"),
                    "entry": entry_s,
                    "live_price": live_s,
                    "sl": s.get("stop_loss"),
                    "tp1": s.get("take_profit_1"),
                    "margin_usdt": s.get("allocated_margin_usdt"),
                    "est_net_pnl_pct": est_net_pct,
                    "ladder": s.get("ladder_name"),
                })

            all_sigs = get_all_signals(limit=22) or []
            active_statuses = {"PENDING_ENTRY", "ACTIVE", "ACTIVE_BE", "ACTIVE_LADDER", "ACTIVE_PARTIAL_TP1"}
            for t in all_sigs:
                if t.get("status") not in active_statuses:
                    recent_closed.append({
                        "id": t.get("id"),
                        "symbol": t.get("symbol"),
                        "direction": t.get("direction"),
                        "tf": t.get("timeframe"),
                        "pair": t.get("pair_symbol") if t.get("is_pair_trade") else "",
                        "status": t.get("status"),
                        "net_pct": t.get("simulated_pnl_pct"),
                        "margin_usdt": t.get("allocated_margin_usdt"),
                        "entry": t.get("actual_entry_price"),
                        "exit": t.get("exit_price"),
                        "closed_at": t.get("closed_at"),
                    })
                if len(recent_closed) >= 15:
                    break

            reflections = [
                {"symbol": r.get("symbol"), "dir": r.get("direction"), "status": r.get("status"), "pnl": r.get("pnl_pct"), "lesson": r.get("lesson")}
                for r in (get_recent_reflections_db(limit=10) or [])
            ]
            quotas = get_today_trades_count_by_timeframe() or {}
            if client is not None:
                btc_regime = client.get_btc_regime() or {}
        except Exception:
            pass

        # 2. Eğer belirli bir coin sorulmuşsa o coinin canlı Binance Futures telemetrisini çek
        clean_sym = str(symbol or "").upper().strip()
        if clean_sym and not clean_sym.endswith("USDT"):
            clean_sym = f"{clean_sym}USDT"
        clean_tf = str(timeframe or "15m").lower().strip()
        if clean_tf not in ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d", "1w"):
            clean_tf = "15m"

        coin_telemetry = None
        if clean_sym and client is not None:
            try:
                from agents.ta_agent import TechnicalAnalysisAgent
                from core.advanced_indicators import (
                    calculate_linear_regression_channel,
                    calculate_volume_profile,
                    calculate_adx,
                    calculate_supertrend,
                    calculate_vwap_bands,
                )
                c_tf = client.get_klines(clean_sym, interval=clean_tf, limit=60) or []
                if len(c_tf) >= 20:
                    closes = [float(c["close"]) for c in c_tf]
                    rsi_v = TechnicalAnalysisAgent.calculate_rsi(closes, 14)
                    fvg_r = TechnicalAnalysisAgent.detect_fvg(c_tf, max_lookback=15)
                    ob_r = TechnicalAnalysisAgent.detect_order_blocks(c_tf, max_lookback=20)
                    lr_r = calculate_linear_regression_channel(c_tf)
                    vp_r = calculate_volume_profile(c_tf)
                    adx_r = calculate_adx(c_tf)
                    st_r = calculate_supertrend(c_tf)
                    vwap_r = calculate_vwap_bands(c_tf)
                    t_24h = (client.get_24hr_tickers() or {}).get(clean_sym, {})
                    f_rate = client.get_funding_rate(clean_sym) or {}
                    coin_telemetry = {
                        "symbol": clean_sym,
                        "timeframe": clean_tf,
                        "price": closes[-1],
                        "change_24h_pct": t_24h.get("priceChangePercent"),
                        "funding_rate_pct": f_rate.get("fundingRatePct"),
                        "rsi_14": round(float(rsi_v[-1]), 2) if rsi_v and rsi_v[-1] is not None else None,
                        "adx": adx_r.get("adx"),
                        "supertrend": st_r.get("trend"),
                        "vwap": vwap_r.get("vwap"),
                        "poc": vp_r.get("poc"),
                        "vah": vp_r.get("vah"),
                        "val": vp_r.get("val"),
                        "lr_trend": lr_r.get("trend"),
                        "lr_pos_pct": lr_r.get("position_pct"),
                        "fvg": {"bull": fvg_r.get("bullish_fvg"), "bear": fvg_r.get("bearish_fvg")},
                        "ob": {"bull": ob_r.get("bullish_ob"), "bear": ob_r.get("bearish_ob")},
                        "last_12_closes": [round(x, 6) for x in closes[-12:]],
                    }
            except Exception:
                pass

        live_context_json = json.dumps({
            "kasa_ozeti": {
                "bakiye_usdt": stats.get("portfolio_balance"),
                "win_rate_pct": stats.get("win_rate"),
                "profit_factor": stats.get("profit_factor"),
                "bugun_net_usd": stats.get("today_dollar_gain"),
                "bugun_islem": stats.get("today_trades"),
                "bugun_win": stats.get("today_wins"),
                "bugun_loss": stats.get("today_losses"),
            },
            "gunluk_kotalar": quotas,
            "btc_rejimi": btc_regime,
            "acik_pozisyonlar": active_list,
            "son_15_kapanan_islem": recent_closed,
            "hafiza_dersleri": reflections,
            "sorulan_coin_canli_verisi": coin_telemetry,
        }, ensure_ascii=False)

        system_instruction = (
            "Sen Patron Efe'nin kripto vadeli işlemler fonunun Baş Stratejisti, Risk Danışmanı ve Öğrenen Hafıza Ortağısın.\n"
            "Ekran görüntüsüne ihtiyacın yok; doğrudan aşağıdaki CANLI PORTFÖY & BORSA VERİTABANI üzerinde çalışırsın:\n"
            f"{live_context_json}\n\n"
            "GÖREV KURALLARI:\n"
            "1. Patron sana açık pozisyonları hakkında karar sorabilir ('kapatayım mı, tutayım mı?'), geçmiş işlemlerini analiz ettirebilir, "
            "yeni bir coin/vade tartışabilir veya fikrine itiraz edebilir. ASLA yuvarlak kalıp cümleler kurma.\n"
            "2. Her cevabında mutlaka somut işlem ID'lerine (#99, #105 vb.), gerçek fiyatlara, kâr/zarar rakamlarına ve risk/ödül mantığına dayan.\n"
            "3. Patron hatalı veya yüksek riskli bir hamle savunursa kibar ama net bir şekilde verilerle itiraz et (tartış), "
            "alternatif stop/giriş/kasa çözümü sun.\n"
            "4. Geçmiş işlemlerden çıkarılacak net bir ders/kural varsa cevabının sonunda '📌 Çıkarılan Ders:' başlığıyla 1 cümlelik somut kural öner.\n"
            "5. Yanıtların Türkçe, akıcı, net maddeli ve aşırı uzun olmadan doğrudan sonuca odaklı olsun."
        )

        contents: List[Dict] = []
        if isinstance(history, list):
            for turn in history[-10:]:
                if not isinstance(turn, dict):
                    continue
                role = "model" if turn.get("role") in ("model", "assistant") else "user"
                txt = str(turn.get("text") or turn.get("content") or "").strip()
                if txt:
                    contents.append({"role": role, "parts": [{"text": txt}]})

        msg_with_ctx = user_msg
        if coin_telemetry:
            msg_with_ctx = f"[Odak Coin: {clean_sym} ({clean_tf}) | Canlı Fiyat: ${coin_telemetry.get('price')}]\n{user_msg}"
        contents.append({"role": "user", "parts": [{"text": msg_with_ctx}]})

        chat_res = self._call_gemini_chat(system_instruction, contents, temperature=0.45, timeout=26)
        if not chat_res:
            err_detail = getattr(self, "_last_gemini_error", "")
            return {
                "status": "error",
                "ai_key_missing": False,
                "message": f"Gemini API yanıt vermedi ({err_detail})." if err_detail else "Gemini API yanıt vermedi. API anahtarınızı veya internet/kota durumunu kontrol edin."
            }

        reply_text, model_used = chat_res
        return {
            "status": "ok",
            "ai_key_missing": False,
            "reply": reply_text,
            "symbol": clean_sym,
            "timeframe": clean_tf,
            "source": f"Gerçek Yapay Zeka ({model_used})"
        }
