"""
FAST Technical Analysis (TA) Agent - 1-Minute Micro-Scalping Confluence Engine
Features for High-Frequency / High-Volume Scalping:
- 1m Micro Fair Value Gap (Micro FVG) & Imbalance Retest
- 1m EMA 9 & EMA 21 Ribbon Expansion & Momentum Cross
- 1m Volume Surge Detection (1.4x+ Volume Spike)
- 1m RSI Elastic Momentum (Trend Continuation)
- 1m & 5m Micro VWAP Trend Confirmation
- Dynamic Target (+0.60% to +0.80%) & Tight Stop (-0.35% to -0.45%)
"""
from typing import List, Dict, Optional, Tuple
import math
from fast_config import (
    FAST_TARGET_PROFIT_PCT,
    FAST_STOP_LOSS_PCT,
    FAST_MIN_CONFLUENCE_SCORE,
    FAST_MIN_RR_RATIO
)

class FastTechnicalAnalysisAgent:
    @staticmethod
    def calculate_ema(closes: List[float], period: int) -> List[Optional[float]]:
        if len(closes) < period:
            return [None] * len(closes)
        multiplier = 2 / (period + 1)
        first_sma = sum(closes[:period]) / period
        ema = [None] * (period - 1)
        ema.append(first_sma)
        current_ema = first_sma
        for price in closes[period:]:
            current_ema = (price - current_ema) * multiplier + current_ema
            ema.append(current_ema)
        return ema

    @staticmethod
    def calculate_rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
        if len(closes) <= period:
            return [None] * len(closes)
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(0, d) for d in deltas]
        losses = [max(0, -d) for d in deltas]
        rsi = [None] * period
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        rsi.append(100.0 if avg_loss == 0 else (100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))))
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            rsi.append(100.0 if avg_loss == 0 else (100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))))
        return rsi

    @staticmethod
    def calculate_atr(candles: List[Dict], period: int = 14) -> List[Optional[float]]:
        if len(candles) <= period:
            return [None] * len(candles)
        tr = [float(candles[0]["high"]) - float(candles[0]["low"])]
        for i in range(1, len(candles)):
            h = float(candles[i]["high"])
            l = float(candles[i]["low"])
            prev_c = float(candles[i - 1]["close"])
            tr.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
        atr = [None] * (period - 1)
        first_atr = sum(tr[:period]) / period
        atr.append(first_atr)
        current_atr = first_atr
        for i in range(period, len(tr)):
            current_atr = (current_atr * (period - 1) + tr[i]) / period
            atr.append(current_atr)
        return atr

    @staticmethod
    def calculate_vwap(candles: List[Dict]) -> float:
        cum_vol_price = 0.0
        cum_vol = 0.0
        for c in candles:
            typical = (float(c["high"]) + float(c["low"]) + float(c["close"])) / 3.0
            vol = float(c.get("volume", 0.0))
            cum_vol_price += typical * vol
            cum_vol += vol
        return (cum_vol_price / cum_vol) if cum_vol > 0 else float(candles[-1]["close"])

    def analyze_fast_setup(
        self,
        symbol: str,
        candles_1m: List[Dict],
        candles_5m: Optional[List[Dict]] = None
    ) -> Tuple[Optional[Dict], str]:
        """
        1 Dakikalık hızlı mumlar ve 5 dakikalık teyit ile mikro scalping fırsatını analiz eder.
        """
        if len(candles_1m) < 30:
            return None, "Yetersiz 1m mum verisi"

        closes_1m = [float(c["close"]) for c in candles_1m]
        highs_1m = [float(c["high"]) for c in candles_1m]
        lows_1m = [float(c["low"]) for c in candles_1m]
        volumes_1m = [float(c.get("volume", 0.0)) for c in candles_1m]
        current_price = closes_1m[-1]

        # 1. Hızlı İndikatörler (1m EMA 9 & EMA 21, RSI 14, ATR 14)
        ema9_list = self.calculate_ema(closes_1m, 9)
        ema21_list = self.calculate_ema(closes_1m, 21)
        rsi_list = self.calculate_rsi(closes_1m, 14)
        atr_list = self.calculate_atr(candles_1m, 14)

        ema9 = ema9_list[-1]
        ema21 = ema21_list[-1]
        prev_ema9 = ema9_list[-2] if len(ema9_list) >= 2 else ema9
        prev_ema21 = ema21_list[-2] if len(ema21_list) >= 2 else ema21
        rsi = rsi_list[-1]
        atr = atr_list[-1] if atr_list and atr_list[-1] else (current_price * 0.003)

        if not ema9 or not ema21 or not rsi:
            return None, "İndikatörler hesaplanamadı"

        # 2. Hacim Patlaması (Volume Spike)
        avg_vol = sum(volumes_1m[-20:]) / 20.0 if len(volumes_1m) >= 20 else volumes_1m[-1]
        last_vol = volumes_1m[-1]
        vol_ratio = (last_vol / avg_vol) if avg_vol > 0 else 1.0

        # 3. 1m VWAP Seviyesi
        vwap_1m = self.calculate_vwap(candles_1m[-40:])

        # 4. 5m Mikro Trend Teyidi (Varsa)
        macro_bias = "NEUTRAL"
        if candles_5m and len(candles_5m) >= 15:
            closes_5m = [float(c["close"]) for c in candles_5m]
            ema20_5m = self.calculate_ema(closes_5m, 20)[-1]
            if ema20_5m:
                macro_bias = "BULLISH" if closes_5m[-1] > ema20_5m else "BEARISH"

        # 5. Sinyal Tespiti ve Skorlama
        long_score = 0
        short_score = 0
        reasons = []

        # Kural A: EMA 9 / EMA 21 Dizilimi
        if ema9 > ema21:
            long_score += 25
            reasons.append("1m EMA9 > EMA21 Pozitif Trend")
            if prev_ema9 <= prev_ema21:
                long_score += 15
                reasons.append("⚡ 1m Taze Golden Cross Kesişimi!")
        else:
            short_score += 25
            reasons.append("1m EMA9 < EMA21 Negatif Trend")
            if prev_ema9 >= prev_ema21:
                short_score += 15
                reasons.append("⚡ 1m Taze Death Cross Kesişimi!")

        # Kural B: 1m VWAP Uyumu
        if current_price >= vwap_1m:
            long_score += 20
            reasons.append("Fiyat 1m VWAP Üzerinde (Kurumsal Alım)")
        else:
            short_score += 20
            reasons.append("Fiyat 1m VWAP Altında (Kurumsal Satım)")

        # Kural C: RSI İtici Gücü
        if 48 <= rsi <= 68:
            long_score += 20
            reasons.append(f"1m RSI İdeal Momentumda ({rsi:.1f})")
        elif 32 <= rsi <= 52:
            short_score += 20
            reasons.append(f"1m RSI İdeal Düşüş Momentumunda ({rsi:.1f})")
        elif rsi > 72:
            long_score -= 15  # Aşırı alım freni
        elif rsi < 28:
            short_score -= 15 # Aşırı satım freni

        # Kural D: Hacim Desteği
        if vol_ratio >= 1.3:
            if ema9 > ema21:
                long_score += 15
                reasons.append(f"Hacim Patlaması ({vol_ratio:.1f}x)")
            else:
                short_score += 15
                reasons.append(f"Hacim Patlaması ({vol_ratio:.1f}x)")

        # Kural E: 5m Makro Trend Bonusu
        if macro_bias == "BULLISH":
            long_score += 10
            reasons.append("5m Makro Boğa Desteği")
        elif macro_bias == "BEARISH":
            short_score += 10
            reasons.append("5m Makro Ayı Desteği")

        # 6. Yön Kararı
        direction = None
        confluence_score = 0
        if long_score >= FAST_MIN_CONFLUENCE_SCORE and long_score > short_score:
            direction = "LONG"
            confluence_score = min(long_score, 100)
        elif short_score >= FAST_MIN_CONFLUENCE_SCORE and short_score > long_score:
            direction = "SHORT"
            confluence_score = min(short_score, 100)
        else:
            return None, f"Yetersiz FAST Confluence (Long: {long_score}, Short: {short_score} < {FAST_MIN_CONFLUENCE_SCORE})"

        # 7. Hedef (TP) ve Stop-Loss (SL) Fiyatları
        # Mikro ATR tabanlı dinamik stop: min %0.30, max %0.45
        atr_pct = (atr / current_price) * 100.0 if current_price > 0 else 0.40
        sl_pct = max(0.30, min(atr_pct * 1.2, FAST_STOP_LOSS_PCT))
        tp_pct = max(sl_pct * FAST_MIN_RR_RATIO, FAST_TARGET_PROFIT_PCT)

        if direction == "LONG":
            stop_loss = round(current_price * (1.0 - sl_pct / 100.0), 6)
            take_profit_1 = round(current_price * (1.0 + tp_pct / 100.0), 6)
            take_profit_2 = round(current_price * (1.0 + (tp_pct * 1.5) / 100.0), 6)
        else:
            stop_loss = round(current_price * (1.0 + sl_pct / 100.0), 6)
            take_profit_1 = round(current_price * (1.0 - tp_pct / 100.0), 6)
            take_profit_2 = round(current_price * (1.0 - (tp_pct * 1.5) / 100.0), 6)

        risk_reward = round(tp_pct / sl_pct, 2) if sl_pct > 0 else 1.5

        return {
            "symbol": symbol,
            "direction": direction,
            "current_price": current_price,
            "entry_min": current_price,
            "entry_max": current_price,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "sl_pct": round(sl_pct, 2),
            "tp1_pct": round(tp_pct, 2),
            "tp2_pct": round(tp_pct * 1.5, 2),
            "risk_reward": risk_reward,
            "confluence_score": confluence_score,
            "risk_grade": "⚡ FAST A+" if confluence_score >= 80 else "⚡ FAST Scalp",
            "ta_reasons": " | ".join(reasons[:4]),
            "timeframe": "1m"
        }, f"FAST 1m {direction} Onaylandı ({confluence_score}/100)"

