"""
Risk & Strategy Officer Agent (Dynamic 10x and 20x Specialist)
Enforces strict margin risk caps, validates BTC Market Shield, and assigns
Risk Profile Grades & Dynamic Position Sizing (Fixed 2% Risk Rule):
- Grade A+ : 20x Sniper (Ultra Dar Stop, Yüksek Kar Marjı)
- Grade A  : 10x Düşük Risk / İstikrarlı Kar Marjı
- Grade B  : 10x Orta Risk / Dengeli Fırsat
- Grade C  : 10x Spekülatif / Yüksek Volatilite
"""
from typing import Dict, Tuple, Optional, List
from datetime import datetime, timezone
from core.timeutil import wall_utc
from config import (
    MAX_SL_PCT_10X,
    MAX_SL_PCT_20X,
    PORTFOLIO_EQUITY_USDT,
    RISK_PER_TRADE_PCT,
    MAX_ALLOCATED_MARGIN_PER_TRADE,
    BINANCE_ROUNDTRIP_FEE_PCT,
    MIN_RR_RATIO,
    MAX_ORDERBOOK_SPREAD_PCT,
    MAX_ALLOWED_FUNDING_RATE,
    MAX_POSITIONS_PER_DIRECTION,
    SIDE_STOPLOSS_GUARD_ENABLED,
    SIDE_STOPLOSS_MAX_CONSECUTIVE_LOSSES,
    SIDE_STOPLOSS_COOLDOWN_MINUTES
)

class RiskOfficerAgent:
    def __init__(self):
        pass

    @staticmethod
    def _calc_return_correlation(candles_a: List[Dict], candles_b: List[Dict], lookback: int = 24) -> float:
        """İki paritenin son kapanmış mum getirileri arasındaki Pearson korelasyonunu döner [-1, 1]."""
        import math
        if not candles_a or not candles_b or len(candles_a) < lookback + 2 or len(candles_b) < lookback + 2:
            return 0.0
        closed_a = candles_a[:-1]
        closed_b = candles_b[:-1]
        map_a = {c["timestamp"]: float(c["close"]) for c in closed_a if c.get("timestamp") is not None}
        map_b = {c["timestamp"]: float(c["close"]) for c in closed_b if c.get("timestamp") is not None}
        common_ts = sorted(set(map_a.keys()) & set(map_b.keys()))
        if len(common_ts) >= lookback + 1:
            used_ts = common_ts[-(lookback + 1):]
            ca = [map_a[t] for t in used_ts]
            cb = [map_b[t] for t in used_ts]
        else:
            ca = [float(c["close"]) for c in closed_a[-lookback - 1:]]
            cb = [float(c["close"]) for c in closed_b[-lookback - 1:]]
        n = min(len(ca), len(cb))
        if n < 10:
            return 0.0
        ra = [(ca[i] - ca[i - 1]) / ca[i - 1] for i in range(1, n) if ca[i - 1] > 0]
        rb = [(cb[i] - cb[i - 1]) / cb[i - 1] for i in range(1, n) if cb[i - 1] > 0]
        m = min(len(ra), len(rb))
        if m < 8:
            return 0.0
        ra, rb = ra[-m:], rb[-m:]
        ma = sum(ra) / m
        mb = sum(rb) / m
        cov = sum((ra[i] - ma) * (rb[i] - mb) for i in range(m))
        va = sum((ra[i] - ma) ** 2 for i in range(m))
        vb = sum((rb[i] - mb) ** 2 for i in range(m))
        denom = math.sqrt(va * vb)
        return round(cov / denom, 3) if denom > 0 else 0.0

    def evaluate(
        self,
        ta_setup: Dict,
        news_analysis: Dict,
        ticker: Dict,
        btc_regime: Optional[Dict] = None,
        funding_data: Optional[Dict] = None,
        book_ticker: Optional[Dict] = None,
        active_signals: Optional[List[Dict]] = None,
        current_equity: Optional[float] = None,
        client=None
    ) -> Tuple[bool, Dict]:
        """
        Setup'ı dinamik kaldıraç (10x veya 20x), komisyon hesabı, slippage (spread),
        fonlama oranı, dinamik bileşik kasa (exponential compounding) ve sabit %2 risk kurallarına göre denetler.
        """
        leverage = ta_setup.get("leverage", 10)
        direction = ta_setup["direction"]
        symbol = ta_setup["symbol"]
        sl_pct = ta_setup["sl_pct"]
        tp1_pct = ta_setup.get("tp1_pct", sl_pct * 1.5)
        tp2_pct = ta_setup.get("tp2_pct", tp1_pct * 1.5)
        rr = ta_setup.get("risk_reward", round(tp1_pct / sl_pct, 2) if sl_pct > 0 else 1.8)
        is_empty_move = news_analysis.get("is_empty_move", False) if news_analysis else False

        # 1. KRİTİK FİLTRE: BTC PİYASA ÇÖKÜŞ VE RALLİ KALKANI (BTC Market Shield)
        if btc_regime and btc_regime.get("block_longs", False) and direction == "LONG":
            return False, {
                "decision": "REJECT",
                "reason": (
                    f"📌 <strong>Mevcut Durum:</strong> BTC Rejimi: {btc_regime.get('status', 'RISK')} ({btc_regime.get('summary', '')}).<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Bitcoin düşüş veya ölü testere eğilimindeyken altcoinlerde LONG açmak sermayeyi yüksek riske atar.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Bitcoin'in yeniden Boğa (BULLISH) trendine dönmesi."
                )
            }
        if btc_regime and btc_regime.get("block_shorts", False) and direction == "SHORT":
            return False, {
                "decision": "REJECT",
                "reason": (
                    f"📌 <strong>Mevcut Durum:</strong> BTC Güçlü Yükseliş Rallisinde (+%{btc_regime.get('change_3h_pct', 0.0)}).<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Bitcoin sert ralli yaparken altcoinlerde SHORT açmak tasfiye (likidasyon) riski taşır.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Rallinin durulması veya sağlıklı düzeltme vermesi."
                )
            }

        # 1.1. HABER KARARLANDIRMA KONSEYİ VETO KALKANI (News Intelligence Veto)
        if news_analysis and news_analysis.get("is_vetoed"):
            return False, {
                "decision": "REJECT",
                "reason": news_analysis.get("veto_reason", "Haber Kararlandırma Konseyi Veto Etti")
            }

        # 1.1 FREQTRADE YÖN BAZLI STOPLOSS GUARD (SIDE-SPECIFIC SERİ ZARAR KALKANI)
        if SIDE_STOPLOSS_GUARD_ENABLED:
            try:
                from core.database import check_side_stoploss_guard
                is_side_locked, lock_reason = check_side_stoploss_guard(
                    direction=direction,
                    max_consecutive_losses=SIDE_STOPLOSS_MAX_CONSECUTIVE_LOSSES,
                    cooldown_minutes=SIDE_STOPLOSS_COOLDOWN_MINUTES
                )
                if is_side_locked:
                    opp_side = "LONG" if direction == "SHORT" else "SHORT"
                    return False, {
                        "decision": "REJECT",
                        "reason": (
                            f"📌 <strong>Mevcut Durum:</strong> {direction} Yönünde Seri Kayıp Koruması Devrede.<br>"
                            f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> {lock_reason}<br>"
                            f"🎯 <strong>Beklenen Şart:</strong> Soğuma süresinin tamamlanması veya kârlı yönde ({opp_side}) işlem aranması."
                        )
                    }
            except Exception as e:
                pass

        # 1.5 LİKİDİTE & SLIPPAGE (ORDER BOOK SPREAD) KALKANI
        if book_ticker:
            spread_pct = book_ticker.get("spread_pct", 0.0)
            if spread_pct > MAX_ORDERBOOK_SPREAD_PCT:
                return False, {
                    "decision": "REJECT",
                    "reason": (
                        f"📌 <strong>Mevcut Durum:</strong> Tahtada Alış-Satış Makası: %{spread_pct:.3f} (Maksimum İzin: %{MAX_ORDERBOOK_SPREAD_PCT}).<br>"
                        f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Slippage (Fiyat Kayması) Tuzağı! Makas açık olduğu için emir girildiği an pozisyon doğrudan zararla başlar.<br>"
                        f"🎯 <strong>Beklenen Şart:</strong> Tahtaya likidite girip makasın %{MAX_ORDERBOOK_SPREAD_PCT} altına daralması."
                    )
                }

        # 1.6 8 SAATLİK FONLAMA ORANI & PENCERE KAÇIŞ KALKANI
        if funding_data:
            fr = funding_data.get("lastFundingRate", 0.0)
            now_utc = wall_utc()
            # 8 saatlik döngü pencereleri: 00:00, 08:00, 16:00 UTC
            hour_mod = now_utc.hour % 8
            minutes_to_settlement = (8 - hour_mod) * 60 - now_utc.minute
            if minutes_to_settlement >= 480:
                minutes_to_settlement = 0

            # Kural A: Genel Zehirli Fonlama Oranı Tavanı
            if direction == "LONG" and fr > MAX_ALLOWED_FUNDING_RATE:
                return False, {
                    "decision": "REJECT",
                    "reason": (
                        f"📌 <strong>Mevcut Durum:</strong> LONG Fonlama Oranı: %{fr*100:.3f} (Tavan: %{MAX_ALLOWED_FUNDING_RATE*100:.2f}).<br>"
                        f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Aşırı fonlama maliyeti! Borsa her 8 saatte bir yüksek komisyon keserek kârınızı eritir.<br>"
                        f"🎯 <strong>Beklenen Şart:</strong> Fonlama oranının %{MAX_ALLOWED_FUNDING_RATE*100:.2f} altına çekilmesi."
                    )
                }
            elif direction == "SHORT" and fr < -MAX_ALLOWED_FUNDING_RATE:
                return False, {
                    "decision": "REJECT",
                    "reason": (
                        f"📌 <strong>Mevcut Durum:</strong> SHORT Fonlama Oranı: %{fr*100:.3f} (Taban: -%{MAX_ALLOWED_FUNDING_RATE*100:.2f}).<br>"
                        f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Aşırı negatif fonlama maliyeti! Borsa SHORT pozisyondan yüksek prim keser.<br>"
                        f"🎯 <strong>Beklenen Şart:</strong> Fonlama oranının normale dönmesi."
                    )
                }

            # Kural B: 8 Saatlik Fonlama Penceresi Kaçış Kalkanı (Settlement'a 30 dk kala fonlama aleyhte ise engelle)
            if minutes_to_settlement <= 30:
                if direction == "LONG" and fr > 0.00015:
                    return False, {
                        "decision": "REJECT",
                        "reason": (
                            f"📌 <strong>Mevcut Durum:</strong> Fonlama Kesintisine {minutes_to_settlement} dk kaldı (Aleyhte: +%{fr*100:.3f}).<br>"
                            f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> 8 saatlik pencere kapanışında ters fonlama ödememek için işlem donduruldu.<br>"
                            f"🎯 <strong>Beklenen Şart:</strong> Fonlama saatinin geçmesi."
                        )
                    }
                elif direction == "SHORT" and fr < -0.00015:
                    return False, {
                        "decision": "REJECT",
                        "reason": (
                            f"📌 <strong>Mevcut Durum:</strong> Fonlama Kesintisine {minutes_to_settlement} dk kaldı (Aleyhte: %{fr*100:.3f}).<br>"
                            f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> 8 saatlik pencere kapanışında ters fonlama ödememek için işlem donduruldu.<br>"
                            f"🎯 <strong>Beklenen Şart:</strong> Fonlama saatinin geçmesi."
                        )
                    }

        # 1.7 SEKTÖR VE AYNI COİN TEKRAR KORUMASI (DIVERSIFICATION GUARD)
        if active_signals:
            for act in active_signals:
                if act.get("symbol") == symbol:
                    return False, {
                        "decision": "REJECT",
                        "reason": f"📌 <strong>Mevcut Durum:</strong> {symbol} paritesinde zaten açık bir işlem var.<br>⛔ <strong>Giriş Yapılmama Nedeni:</strong> Çift risk almayı engelleme kuralı.<br>🎯 <strong>Beklenen Şart:</strong> Mevcut pozisyonun kâr veya stopla kapanması."
                    }

            # 1.8 TEK YÖNE YIĞILMA KALKANI (KORELASYON VE HEDGE KORUMASI - MAKS 4)
            same_dir_syms = [s.get("symbol") for s in active_signals if s.get("direction") == direction and s.get("symbol")]
            same_dir_count = len(same_dir_syms)
            if same_dir_count >= MAX_POSITIONS_PER_DIRECTION:
                opp_dir = "SHORT" if direction == "LONG" else "LONG"
                return False, {
                    "decision": "REJECT",
                    "reason": (
                        f"📌 <strong>Mevcut Durum:</strong> Radarda halihazırda {same_dir_count} adet {direction} pozisyonu açık.<br>"
                        f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Tek Yöne Yığılma Kalkanı (Maksimum {MAX_POSITIONS_PER_DIRECTION} {direction} kotası dolu).<br>"
                        f"🎯 <strong>Beklenen Şart:</strong> Portföy dengesi için zıt yönde ({opp_dir}) işlem bulunması veya bir {direction} pozisyonunun kapanması."
                    )
                }

            # 1.9 PORTFÖY KORELASYON KALKANI (Vibe-Trading İlkesi: Aynı yönde yüksek korelasyonlu toplu stop riskini önle)
            corr_multiplier = 1.0
            if client is not None and same_dir_count >= 1:
                try:
                    cand_kl_1h = client.get_klines(symbol, interval="1h", limit=30)
                    high_corr_syms = []
                    for act_sym in same_dir_syms:
                        act_kl_1h = client.get_klines(act_sym, interval="1h", limit=30)
                        rho = self._calc_return_correlation(cand_kl_1h, act_kl_1h, lookback=24)
                        if rho >= 0.78:
                            high_corr_syms.append((act_sym, rho))
                    if len(high_corr_syms) >= 2:
                        pairs_txt = ", ".join([f"{s} (r={r})" for s, r in high_corr_syms[:2]])
                        return False, {
                            "decision": "REJECT",
                            "reason": (
                                f"📌 <strong>Mevcut Durum:</strong> Portföy Korelasyon Kalkanı ({direction}: {pairs_txt}).<br>"
                                f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Aynı yönde zaten 2 yüksek korelasyonlu (r >= 0.78) pozisyon açık; toplu stop riski engellendi.<br>"
                                f"🎯 <strong>Beklenen Şart:</strong> Farklı/düşük korelasyonlu parite veya mevcut pozisyonun BE+ olması."
                            )
                        }
                    elif len(high_corr_syms) == 1:
                        corr_multiplier = 0.75
                except Exception:
                    corr_multiplier = 1.0
        else:
            corr_multiplier = 1.0

        # Vadeye Göre Dinamik Stop-Loss Tavanı (15m Kısa / 30m Orta / 1h Uzun)
        timeframe = ta_setup.get("timeframe") or ("1h" if "1h" in str(ta_setup.get("trade_horizon")) else ("30m" if "30m" in str(ta_setup.get("trade_horizon")) else "15m"))
        if timeframe == "1h":
            effective_max_sl_10x = 2.90
            effective_max_sl_20x = 1.80
        elif timeframe == "30m":
            effective_max_sl_10x = 1.85
            effective_max_sl_20x = 1.40
        else:
            adaptive_max_sl = MAX_SL_PCT_10X
            try:
                from core.self_tuning_engine import SelfTuningEngine
                adaptive_max_sl = float(SelfTuningEngine.get_current_params().get("max_scalp_sl_pct", MAX_SL_PCT_10X))
            except Exception:
                pass
            effective_max_sl_10x = round(max(MAX_SL_PCT_10X, adaptive_max_sl) + 0.03, 2)
            effective_max_sl_20x = MAX_SL_PCT_20X

        # 2. KALDIRAÇ VE SL UYGUNLUK DENETİMİ (Tüm işlemler 10x kaldıraçta sabitlenir)
        if leverage != 10:
            leverage = 10
            ta_setup["leverage"] = 10
            ta_setup["setup_type"] = "10x STANDART TREND"

        if leverage == 10:
            if sl_pct > effective_max_sl_10x:
                return False, {
                    "decision": "REJECT",
                    "reason": (
                        f"📌 <strong>Mevcut Durum:</strong> Stop Mesafesi: %{sl_pct:.2f} ({timeframe} 10x Sınırı: %{effective_max_sl_10x:.2f}).<br>"
                        f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Stop mesafesi {timeframe} 10x için fazla geniş.<br>"
                        f"🎯 <strong>Beklenen Şart:</strong> Daha dar stoplu (%{effective_max_sl_10x:.2f} altı) güvenli bir formasyon oluşması."
                    )
                }

        # 3. RİSK / ÖDÜL DENETİMİ (En az MIN_RR_RATIO = 1.4)
        # Rejim politikası etkinse kurulumun rejimine ait min R:R kullanılır (TRENDING 1.65 / CHOPPY 2.10)
        from config import USE_REGIME_MIN_RR, REGIME_POLICY
        min_rr_required = MIN_RR_RATIO
        if USE_REGIME_MIN_RR and ta_setup.get("regime") in REGIME_POLICY:
            min_rr_required = REGIME_POLICY[ta_setup["regime"]].get("min_rr", MIN_RR_RATIO)
        if rr < min_rr_required - 1e-9:
            return False, {
                "decision": "REJECT",
                "reason": (
                    f"📌 <strong>Mevcut Durum:</strong> Risk/Ödül Oranı 1:{rr:.2f} (Minimum Baraj: 1:{MIN_RR_RATIO}).<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Olası kâr, göze alınan riski karşılamıyor.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> En az 1:{MIN_RR_RATIO} getiri vadeden bir kurulum bulunması."
                )
            }

        # 4. GERÇEKÇİ BORSA KOMİSYONU & MARJİN NET HESAPLAMALARI
        # Binance Futures Taker: Giriş %0.05 + Çıkış %0.05 = %0.10 raw price
        fee_drag_pct = round(BINANCE_ROUNDTRIP_FEE_PCT * leverage, 2)  # 10x'te %1.0, 20x'te %2.0 marjin komisyonu
        
        gross_margin_risk_pct = round(sl_pct * leverage, 1)
        net_margin_risk_pct = round(gross_margin_risk_pct + fee_drag_pct, 1)

        gross_tp1_margin_pct = round(tp1_pct * leverage, 1)
        net_tp1_margin_pct = round(gross_tp1_margin_pct - fee_drag_pct, 1)

        gross_tp2_margin_pct = round(tp2_pct * leverage, 1)
        net_tp2_margin_pct = round(gross_tp2_margin_pct - fee_drag_pct, 1)

        # 5. DİNAMİK BİLEŞİK KASA VE POZİSYON BOYUTLANDIRMA (EXPONENTIAL COMPOUNDING & %2 RİSK KURALI)
        # Kasa arttıkça pozisyon büyüklüğü eşzamanlı katlanır (bileşik faiz); düşüşte ise kayıp frenlenir.
        active_equity = float(current_equity) if current_equity and current_equity > 50.0 else PORTFOLIO_EQUITY_USDT
        target_risk_usd = round(active_equity * (RISK_PER_TRADE_PCT / 100.0), 2)
        total_sl_loss_fraction = (sl_pct * leverage + fee_drag_pct) / 100.0
        
        calculated_margin = target_risk_usd / total_sl_loss_fraction if total_sl_loss_fraction > 0 else (active_equity * 0.15)
        
        # Dinamik marjin tavanı: 5 pozisyon için kasanın en fazla %20'si tek bir işleme ayrılabilir
        dynamic_max_margin = round(active_equity * 0.20, 1)
        allocated_margin = round(max(30.0, min(dynamic_max_margin, calculated_margin)), 1)

        # 5.1. Haber Kararlandırma Konseyi & Korelasyon Çarpanı
        news_multiplier = float(news_analysis.get("pos_multiplier", 1.0)) if news_analysis else 1.0
        if news_multiplier > 0 and news_multiplier != 1.0:
            allocated_margin = round(max(25.0, min(dynamic_max_margin * 1.25, allocated_margin * news_multiplier)), 1)
        if corr_multiplier < 1.0:
            allocated_margin = round(max(25.0, allocated_margin * corr_multiplier), 1)

        # Komisyon dahil sert risk tavanı: 20x veya geniş SL'de dahi tek işlem kaybı target_risk_usd'yi aşamaz
        if total_sl_loss_fraction > 0:
            hard_risk_cap_margin = round(max(25.0, target_risk_usd / total_sl_loss_fraction), 1)
            if allocated_margin > hard_risk_cap_margin:
                allocated_margin = hard_risk_cap_margin

        actual_risk_usd = round(allocated_margin * total_sl_loss_fraction, 2)

        # 6. RİSK SINIFLANDIRMASI (GRADE A+, A, B, C)
        if leverage == 20 and sl_pct <= MAX_SL_PCT_20X and not is_empty_move:
            risk_grade = "Grade A+ (20x Sniper / Ultra Dar Stop)"
            risk_desc = (
                f"Süper dar stop (%{sl_pct}), net SMC kırılımı. "
                f"20x kaldıraç ile TP'de net +%{net_tp1_margin_pct} kâr."
            )
        elif leverage == 10 and sl_pct <= MAX_SL_PCT_10X and not is_empty_move:
            risk_grade = "Grade A (10x Düşük Risk / İstikrarlı Scalp)"
            risk_desc = f"Sağlam trend desteği, düşük marjin riski (net -%{net_margin_risk_pct}) ve güvenli haber akışı."
        elif is_empty_move and direction == "LONG":
            risk_grade = "Grade C (10x Yüksek Risk / Spekülatif Şişme)"
            risk_desc = "Haber akışı zayıf veya likidite avı şüphesi var. Sermaye düşük tutulmalı."
            allocated_margin = max(30.0, round(allocated_margin * 0.6, 1))
        else:
            risk_grade = "Grade B (10x Orta Risk / Standart Fırsat)"
            risk_desc = "Trend yönünde dengeli kurulum. Standart volatilite."

        risk_report = {
            "decision": "APPROVED",
            "leverage": leverage,
            "risk_grade": risk_grade,
            "risk_desc": risk_desc,
            "portfolio_equity_usdt": active_equity,
            "allocated_margin_usdt": allocated_margin,
            "risk_usd": actual_risk_usd,
            "fee_drag_pct": fee_drag_pct,
            "margin_risk_pct": net_margin_risk_pct,
            "margin_tp1_pct": net_tp1_margin_pct,
            "margin_tp2_pct": net_tp2_margin_pct,
            "recommendation": (
                f"{leverage}x Kaldıraç | Tahsis Marjin: ${allocated_margin} (Risk: ${actual_risk_usd} / %{RISK_PER_TRADE_PCT} Kasa). "
                f"Net SL: -%{net_margin_risk_pct} (Komisyon dahil), Net TP: +%{net_tp1_margin_pct}."
            )
        }
        return True, risk_report
