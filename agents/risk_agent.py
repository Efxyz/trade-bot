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
from config import (
    MAX_SL_PCT_10X,
    MAX_SL_PCT_20X,
    PORTFOLIO_EQUITY_USDT,
    RISK_PER_TRADE_PCT,
    MAX_ALLOCATED_MARGIN_PER_TRADE,
    BINANCE_ROUNDTRIP_FEE_PCT,
    MIN_RR_RATIO,
    MAX_ORDERBOOK_SPREAD_PCT,
    MAX_ALLOWED_FUNDING_RATE
)

class RiskOfficerAgent:
    def __init__(self):
        pass

    def evaluate(
        self,
        ta_setup: Dict,
        news_analysis: Dict,
        ticker: Dict,
        btc_regime: Optional[Dict] = None,
        funding_data: Optional[Dict] = None,
        book_ticker: Optional[Dict] = None,
        active_signals: Optional[List[Dict]] = None
    ) -> Tuple[bool, Dict]:
        """
        Setup'ı dinamik kaldıraç (10x veya 20x), komisyon hesabı, slippage (spread),
        fonlama oranı ve sabit risk kurallarına göre denetler.
        """
        leverage = ta_setup.get("leverage", 10)
        direction = ta_setup["direction"]
        symbol = ta_setup["symbol"]
        sl_pct = ta_setup["sl_pct"]
        tp1_pct = ta_setup.get("tp1_pct", sl_pct * 1.5)
        tp2_pct = ta_setup["tp2_pct"]
        rr = ta_setup["risk_reward"]
        is_empty_move = news_analysis.get("is_empty_move", False)

        # 1. KRİTİK FİLTRE: BTC PİYASA ÇÖKÜŞ KALKANI (BTC Market Shield)
        if btc_regime and btc_regime.get("block_longs", False) and direction == "LONG":
            return False, {
                "decision": "REJECT",
                "reason": f"BTC Çöküş Kalkanı Devrede: {btc_regime.get('summary', 'BTC riskli')}. Altcoin LONG engellendi."
            }

        # 1.5 LİKİDİTE & SLIPPAGE (ORDER BOOK SPREAD) KALKANI
        # Alış-Satış makası geniş olan paritelerde piyasa emri anında büyük zararla başlar
        if book_ticker:
            spread_pct = book_ticker.get("spread_pct", 0.0)
            if spread_pct > MAX_ORDERBOOK_SPREAD_PCT:
                return False, {
                    "decision": "REJECT",
                    "reason": f"Slippage Tuzağı: Alış/Satış makası çok geniş (%{spread_pct:.3f} > %{MAX_ORDERBOOK_SPREAD_PCT}). Likidite yetersiz."
                }

        # 1.6 ZEHİRLİ FONLAMA ORANI (TOXIC FUNDING RATE) KALKANI
        # Eğer fonlama aşırı yüksekse, pozisyonda kalmak her 8 saatte bir yüksek komisyon kesintisine yol açar
        if funding_data:
            fr = funding_data.get("lastFundingRate", 0.0)
            if direction == "LONG" and fr > MAX_ALLOWED_FUNDING_RATE:
                return False, {
                    "decision": "REJECT",
                    "reason": f"Fonlama Tuzağı: LONG fonlama oranı aşırı yüksek (%{fr*100:.3f} > %{MAX_ALLOWED_FUNDING_RATE*100:.2f}). Borsa kesintisi kârı yiyecektir."
                }
            elif direction == "SHORT" and fr < -MAX_ALLOWED_FUNDING_RATE:
                return False, {
                    "decision": "REJECT",
                    "reason": f"Fonlama Tuzağı: SHORT fonlama oranı aşırı negatif (%{fr*100:.3f} < -%{MAX_ALLOWED_FUNDING_RATE*100:.2f}). Borsa kesintisi kârı yiyecektir."
                }

        # 1.7 SEKTÖR VE AYNI COİN TEKRAR KORUMASI (DIVERSIFICATION GUARD)
        if active_signals:
            for act in active_signals:
                if act.get("symbol") == symbol:
                    return False, {
                        "decision": "REJECT",
                        "reason": f"Çift Pozisyon Engeli: {symbol} için zaten aktif bir pozisyon mevcut."
                    }

        # 2. KALDIRAÇ VE SL UYGUNLUK DENETİMİ
        if leverage == 20:
            if sl_pct > MAX_SL_PCT_20X:
                leverage = 10
                ta_setup["leverage"] = 10
                ta_setup["setup_type"] = "10x STANDART TREND"

        if leverage == 10:
            if sl_pct > MAX_SL_PCT_10X:
                return False, {
                    "decision": "REJECT",
                    "reason": f"SL mesafesi (%{sl_pct}) 10x kaldıraç için çok geniş (Marjin riski > %15). İptal edildi."
                }

        # 3. RİSK / ÖDÜL DENETİMİ (En az MIN_RR_RATIO = 1.4)
        if rr < MIN_RR_RATIO:
            return False, {
                "decision": "REJECT",
                "reason": f"Risk/Ödül oranı (1:{rr}) yetersiz. Minimum 1:{MIN_RR_RATIO} aranıyor."
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

        # 5. DİNAMİK POZİSYON BOYUTLANDIRMA (SABİT %2 KASA RİSK KURALI)
        # Portföy $1,000 ise, %2 risk = $20.0 maksimum kayıp
        target_risk_usd = round(PORTFOLIO_EQUITY_USDT * (RISK_PER_TRADE_PCT / 100.0), 2)
        total_sl_loss_fraction = (sl_pct * leverage + fee_drag_pct) / 100.0
        
        calculated_margin = target_risk_usd / total_sl_loss_fraction if total_sl_loss_fraction > 0 else 100.0
        # Sermaye sınırları: Minimum $30 USDT, Maksimum $250 USDT ($1000 / 4)
        allocated_margin = round(max(30.0, min(MAX_ALLOCATED_MARGIN_PER_TRADE, calculated_margin)), 1)
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
