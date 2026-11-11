"""
SÜPER FAST Technical Analysis Agent - Saniyelik & Mikro-Tick Momentum Motoru
High-Frequency Trading (HFT) mikro dalgalanma, emir akışı ve saniyelik momentum avcısı.

Strateji Bileşenleri:
1. Saniyelik Mikro Trend & Tick Momentum (Hızlı İvme)
2. Sub-Minute EMA 3 / EMA 8 Dinamik Kesişimi
3. Hacim İvmesi & Emir Kitabı Dengesizliği (Order Flow Velocity)
4. Saniyelik Dar Spread & Likidite Doğrulaması
5. 60+ Confluence Skoru ile Bol ve Seri İşlem Üretimi
"""
from typing import Dict, List, Tuple, Optional
import numpy as np

from super_fast_config import (
    SUPER_FAST_TARGET_PROFIT_PCT,
    SUPER_FAST_STOP_LOSS_PCT,
    SUPER_FAST_LEVERAGE
)

class SuperFastTechnicalAnalysisAgent:
    def __init__(self):
        self.min_confluence_score = 60  # Bol ve seri işlem için dinamik eşik

    def analyze_super_fast_setup(
        self,
        symbol: str,
        recent_prices: List[float],
        candles_1m: List[Dict],
        book_ticker: Optional[Dict] = None
    ) -> Tuple[Optional[Dict], str]:
        """
        Saniyelik fiyat serisini ve mikro 1m teyidini analiz ederek anlık mikro scalp sinyali üretir.
        """
        if not candles_1m or len(candles_1m) < 10:
            return None, "Yetersiz 1m veri"

        # 1. Anlık Fiyat ve Spread Filtresi
        current_price = recent_prices[-1] if recent_prices else float(candles_1m[-1]["close"])
        if current_price <= 0:
            return None, "Geçersiz fiyat"

        # Book Ticker ile dar spread doğrulaması (Saniyelik işlemde geniş makas kabul edilmez)
        if book_ticker:
            spread = float(book_ticker.get("spread_pct", 0.0))
            if spread > 0.08:  # %0.08'den geniş makas varsa mikro-scalp için riskli
                return None, f"Geniş spread (%{spread:.3f})"

        # 2. Saniyelik Fiyat Serisi Analizi (Yoksa son 1m mum kapanışları ve tepe/dip noktaları)
        prices = recent_prices if len(recent_prices) >= 8 else [float(c["close"]) for c in candles_1m[-15:]]
        
        # Hızlı Mikro EMA 3 ve EMA 8
        weights_3 = np.exp(np.linspace(-1., 0., 3))
        weights_3 /= weights_3.sum()
        ema_3 = np.convolve(prices, weights_3, mode='valid')[-1]

        weights_8 = np.exp(np.linspace(-1., 0., 8))
        weights_8 /= weights_8.sum()
        ema_8 = np.convolve(prices, weights_8, mode='valid')[-1]

        # Son mum ve yön eğilimi
        last_candle = candles_1m[-1]
        c_open = float(last_candle["open"])
        c_close = float(last_candle["close"])
        c_volume = float(last_candle.get("volume", 0.0))
        prev_candle = candles_1m[-2]

        # 20 periyotluk ortalama hacim
        vols = [float(c.get("volume", 0.0)) for c in candles_1m[-10:]]
        avg_vol = np.mean(vols) if vols else 1.0
        vol_ratio = c_volume / avg_vol if avg_vol > 0 else 1.0

        # Mikro Momentum Skoru
        long_score = 0
        short_score = 0
        ta_reasons = []

        # Kural 1: Saniyelik EMA Kesişimi & Açısı
        if ema_3 > ema_8:
            long_score += 25
            if (ema_3 - ema_8) / ema_8 > 0.0005:
                long_score += 15
                ta_reasons.append("⚡⚡ EMA 3/8 Yukarı İvme")
        elif ema_3 < ema_8:
            short_score += 25
            if (ema_8 - ema_3) / ema_8 > 0.0005:
                short_score += 15
                ta_reasons.append("⚡⚡ EMA 3/8 Aşağı İvme")

        # Kural 2: Anlık Mum Gövdesi ve İtiş Gücü (Price Impulse)
        candle_pct = ((c_close - c_open) / c_open) * 100.0
        if candle_pct > 0.05:
            long_score += 20
            ta_reasons.append(f"🟢 Yeşil Mum İtişi (+%{candle_pct:.2f})")
        elif candle_pct < -0.05:
            short_score += 20
            ta_reasons.append(f"🔴 Kırmızı Mum Baskısı (%{candle_pct:.2f})")

        # Kural 3: Hacim Desteği (HFT Volume Velocity)
        if vol_ratio >= 1.15:
            if candle_pct > 0:
                long_score += 20
                ta_reasons.append(f"📊 Hacim İtişi ({vol_ratio:.1f}x)")
            else:
                short_score += 20
                ta_reasons.append(f"📊 Hacim Boşalması ({vol_ratio:.1f}x)")

        # Kural 4: Mikro Kırılım (Son 3 mum tepe veya dip ihlali)
        recent_highs = [float(c["high"]) for c in candles_1m[-4:-1]]
        recent_lows = [float(c["low"]) for c in candles_1m[-4:-1]]
        if recent_highs and c_close > max(recent_highs):
            long_score += 15
            ta_reasons.append("🚀 Mikro Tepe Kırılımı")
        elif recent_lows and c_close < min(recent_lows):
            short_score += 15
            ta_reasons.append("🩸 Mikro Dip Kırılımı")

        # Karar ve Kurulum Üretimi
        direction = None
        confluence_score = 0

        if long_score >= self.min_confluence_score and long_score > short_score:
            direction = "LONG"
            confluence_score = min(long_score, 100)
        elif short_score >= self.min_confluence_score and short_score > long_score:
            direction = "SHORT"
            confluence_score = min(short_score, 100)
        else:
            return None, f"Yetersiz Confluence (L:{long_score}, S:{short_score})"

        # Dar & Hızlı TP / SL Hesaplama
        tp_pct = SUPER_FAST_TARGET_PROFIT_PCT
        sl_pct = SUPER_FAST_STOP_LOSS_PCT

        if direction == "LONG":
            tp_price = round(current_price * (1.0 + tp_pct / 100.0), 6)
            sl_price = round(current_price * (1.0 - sl_pct / 100.0), 6)
        else:
            tp_price = round(current_price * (1.0 - tp_pct / 100.0), 6)
            sl_price = round(current_price * (1.0 + sl_pct / 100.0), 6)

        setup = {
            "symbol": symbol,
            "direction": direction,
            "current_price": current_price,
            "entry_min": current_price,
            "entry_max": current_price,
            "take_profit_1": tp_price,
            "take_profit_2": tp_price,
            "stop_loss": sl_price,
            "tp1_pct": tp_pct,
            "sl_pct": sl_pct,
            "risk_reward": round(tp_pct / sl_pct, 2),
            "confluence_score": confluence_score,
            "risk_grade": f"⚡⚡ SÜPER FAST ({confluence_score}/100)",
            "ta_reasons": " | ".join(ta_reasons)
        }

        return setup, f"Süper FAST {direction} Kurulumu Onaylandı (Skor: {confluence_score})"

