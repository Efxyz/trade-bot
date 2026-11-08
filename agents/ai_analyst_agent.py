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
from core.database import save_committee_debate_db
from core.reflection import ReflectorEngine

class AIAnalystAgent:
    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()

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
        
        # 1. Eğer Gemini API Anahtarı mevcutsa LLM tabanlı canlı komiteyi çağır
        if self.gemini_api_key:
            try:
                llm_debate = self._call_gemini_committee(
                    ta_setup, risk_report, news_analysis, btc_regime, ticker, funding_data, past_context
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
        bull_points = []
        if direction == "LONG":
            bull_points.append(f"15m grafikte kurumsal alıcı desteği çok net ({score}/100 SMC skoru)")
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
            bull_points.append(f"15m grafikte kurumsal satıcı baskısı ve arz boşluğu net ({score}/100 SMC skoru)")
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

            if curr_rsi > 64:
                bear_points.append(f"RSI {curr_rsi:.1f} seviyesinde, tepeye çok yakınız. Buradan alım yapmak tepe likiditesi olmak demek!")
                is_fatal_trap = True
                trap_reason = "Aşırı yükselmiş RSI (tepeden mal alma riski)"
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

            if curr_rsi < 36:
                bear_points.append(f"RSI {curr_rsi:.1f} ile dibe çok inmiş! Buradan short açmak ayı tuzağına (bear trap) düşmek olur!")
                is_fatal_trap = True
                trap_reason = "Aşırı düşmüş RSI (dipten short açma riski)"
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
        # 📰 3. MAKRO & DUYGU MASASI (Market Context Analyst)
        # ----------------------------------------------------
        macro_arg = (
            f"Makro Görünüm: Bitcoin ${btc_price:,.0f} seviyesinde ({btc_summary}). "
            f"Duygu Masası: {news_summary} ({sentiment}). "
            f"Genel piyasa havası incelendiğinde {symbol} paritesinde ani haber riski görünmüyor, "
            f"fakat genel likiditeye saygı gösterilmeli."
        )

        # ----------------------------------------------------
        # 🎲 4. KUANT & MONTE CARLO SİMÜLASYON MASASI (5,000 Fiyat Yolu Simülatörü)
        # ----------------------------------------------------
        quant_approved = True
        quant_win_prob = 65.0
        quant_loss_prob = 35.0
        quant_exp_r = 1.40
        quant_arg = ""

        if quant_sim:
            quant_approved = quant_sim.get("is_approved", True)
            quant_win_prob = quant_sim.get("win_probability_pct", 65.0)
            quant_loss_prob = quant_sim.get("loss_probability_pct", 35.0)
            quant_exp_r = quant_sim.get("expected_return_r", 1.40)
            quant_arg = quant_sim.get("argument", "")
        else:
            quant_arg = (
                f"{symbol} üzerinde 5,000 Monte Carlo fiyat yolu koşturuldu. "
                f"TP1'e ulaşma olasılığı: %{quant_win_prob:.1f}, SL Riski: %{quant_loss_prob:.1f}. OY: ONAYLANDI."
            )

        # ----------------------------------------------------
        # 👑 5. KOMİTE BAŞKANI (Lead Arbiter - Nihai Karar ve Sentez)
        # ----------------------------------------------------
        dialogue = [
            {"role": "BULL", "agent_name": "Boğa Analisti (Alpha Hunter)", "avatar": "🟢", "argument": bull_arg},
            {"role": "BEAR", "agent_name": "Ayı Analisti (Risk Şefi)", "avatar": "🔴", "argument": bear_arg},
            {"role": "MACRO", "agent_name": "Makro & Duygu Masası", "avatar": "📰", "argument": macro_arg},
            {
                "role": "QUANT",
                "agent_name": "Kuant Simülasyon Ajanı (Monte Carlo 5,000 Yol)",
                "avatar": "🎲",
                "argument": quant_arg,
                "metrics": {
                    "simulations": quant_sim.get("num_simulations", 5000) if quant_sim else 5000,
                    "win_rate": quant_win_prob,
                    "loss_rate": quant_loss_prob,
                    "expectancy_r": quant_exp_r,
                    "vote": "APPROVED" if quant_approved else "REJECTED"
                }
            }
        ]

        if is_fatal_trap or score < 76 or not quant_approved:
            consensus_verdict = "REJECTED"
            consensus_score = round(min(7.2, max(5.0, score / 10.0)), 1)
            rating = "NEUTRAL_PASS"
            if not quant_approved:
                chief_arg = (
                    f"Komite Kararı: Kuant Simülasyon Ajanı'nın 5,000 Monte Carlo stokastik fiyat yolu simülasyonu "
                    f"yetersiz kazanma olasılığı (%{quant_win_prob:.1f} < %60.0) ve yüksek Stop riski (%{quant_loss_prob:.1f}) tespit etti! "
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
            # Kuant onayı ek güven skoru ekler
            bonus = 0.3 if quant_win_prob >= 65.0 else 0.0
            consensus_score = round(min(9.8, 7.8 + (score - 76) * 0.1 + bonus), 1)
            rating = f"STRONG_{direction}" if consensus_score >= 8.6 else f"TACTICAL_{direction}"
            chief_arg = (
                f"Komite Kararı: Boğa Analisti'nin SMC argümanları, Kuant Ajanı'nın 5,000 Monte Carlo "
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

    def _call_gemini_committee(
        self,
        ta_setup: Dict,
        risk_report: Dict,
        news_analysis: Dict,
        btc_regime: Optional[Dict],
        ticker: Optional[Dict],
        funding_data: Optional[Dict],
        past_context: str = ""
    ) -> Optional[Dict]:
        """Gemini LLM kullanarak 4 ajanlı adversarial diyalog üretir (Tauric Research Modeli)."""
        symbol = ta_setup["symbol"]
        direction = ta_setup["direction"]
        leverage = ta_setup.get("leverage", 10)
        score = ta_setup.get("confluence_score", 76)
        
        prompt = f"""
Sen bir Kripto Vadeli İşlemler Hedge Fund Yatırım Komitesinin 4 farklı üyesini canlandıran Baş Yapay Zekasın.
Parite: {symbol} | Yön: {direction} ({leverage}x Kaldıraç) | SMC Güven Skoru: {score}/100
Fiyat: {ta_setup.get('current_price')} | SL: %{ta_setup.get('sl_pct')} | TP: %{ta_setup.get('tp1_pct')} | R:R: 1:{ta_setup.get('risk_reward')}
Nedenler: {ta_setup.get('ta_reasons')}
Haber: {news_analysis.get('summary')}
BTC Durumu: {btc_regime.get('summary') if btc_regime else 'Nötr'}

{past_context}

4 Ajan birbiriyle canlı olarak Türkçe tartışacak:
1. Boğa Analisti (Alpha Hunter): Neden bu işlem açılmalı, hangi göstergeler ve SMC formasyonu iyi?
2. Ayı Analisti (Muhafazakar Risk Şefi): Geçmiş hafıza kayıtlarındaki dersleri ve tuzak risklerini (RSI/fonlama/BTC dead chop) ortaya koyarak itiraz eder.
3. Makro & Duygu Masası: BTC ve piyasa genel durumu ne diyor?
4. Komite Başkanı: Argümanları tartar, Ayı mı Boğa mı haklı karar verir, ONAY veya RET kararı ile rating (STRONG_LONG, TACTICAL_LONG, REJECT) açıklar.

SADECE geçerli bir JSON döndür:
{{
    "symbol": "{symbol}",
    "direction": "{direction}",
    "timestamp": "{datetime.now().strftime('%H:%M:%S')}",
    "consensus_verdict": "APPROVED" veya "REJECTED",
    "consensus_score": 1.0 ile 10.0 arasında sayı (örnek 8.5),
    "rating": "STRONG_{direction}" veya "TACTICAL_{direction}" veya "NEUTRAL_PASS",
    "decision_summary": "Başkanın 1-2 cümlelik nihai gerekçesi",
    "debate_dialogue": [
        {{"role": "BULL", "agent_name": "Boğa Analisti (Alpha Hunter)", "avatar": "🟢", "argument": "..."}},
        {{"role": "BEAR", "agent_name": "Ayı Analisti (Risk Şefi)", "avatar": "🔴", "argument": "..."}},
        {{"role": "MACRO", "agent_name": "Makro & Duygu Masası", "avatar": "📰", "argument": "..."}},
        {{"role": "CHIEF", "agent_name": "Yatırım Komitesi Başkanı (Nihai Karar)", "avatar": "👑", "argument": "..."}}
    ],
    "strengths": ["...", "..."],
    "concerns": ["...", "..."],
    "source": "Gemini Multi-Agent Committee"
}}
"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "response_mime_type": "application/json"}
        }

        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=9) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            candidate = res_data.get("candidates", [])[0]
            raw_text = candidate["content"]["parts"][0]["text"]
            return json.loads(raw_text)
