"""
Core Advanced Indicators & Quantitative Technical Analysis Engine
Provides institutional-grade technical analysis modules:
1. Linear Regression Trend Channel (Rolling OLS + 2 Std Dev Dynamic Bands)
2. Volume Profile (Point of Control - POC, Value Area High - VAH, Value Area Low - VAL)
3. Camarilla Pivot Points & Dynamic Intraday S/R (H3/H4 & L3/L4)
4. RSI Regular & Hidden Divergence Detection (Trend Reversal & Continuation)
5. Welles Wilder ADX (Trend Strength & False Breakout Filter)
"""
import math
import numpy as np
from typing import List, Dict, Optional, Tuple

def calculate_linear_regression_channel(candles: List[Dict], period: int = 40, num_std: float = 2.0) -> Dict:
    """
    Rolling Linear Regression Channel with OLS Baseline and +/- 2 Std Dev Volatility Bands.
    Determines channel direction, slope angle, and exact position within the channel.
    """
    if len(candles) < period:
        return {
            "slope": 0.0, "slope_pct": 0.0, "baseline": 0.0,
            "upper": 0.0, "lower": 0.0, "channel_width_pct": 0.0,
            "position_pct": 50.0, "trend": "FLAT",
            "is_support_test": False, "is_resistance_test": False,
            "is_upper_breakout": False, "is_lower_breakdown": False
        }
    
    recent = candles[-period:]
    closes = [float(c["close"]) for c in recent]
    n = len(closes)
    x = list(range(n))
    
    # OLS Formula: y = slope * x + intercept
    sum_x = sum(x)
    sum_y = sum(closes)
    sum_xx = sum(xi * xi for xi in x)
    sum_xy = sum(xi * yi for xi, yi in zip(x, closes))
    
    denom = (n * sum_xx - sum_x * sum_x)
    if denom == 0:
        return {
            "slope": 0.0, "slope_pct": 0.0, "baseline": closes[-1],
            "upper": closes[-1], "lower": closes[-1], "channel_width_pct": 0.0,
            "position_pct": 50.0, "trend": "FLAT",
            "is_support_test": False, "is_resistance_test": False,
            "is_upper_breakout": False, "is_lower_breakdown": False
        }
    
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    
    # Current bar regression baseline value (at x = n - 1)
    baseline = slope * (n - 1) + intercept
    
    # Standard Error of Residuals
    residuals = [(closes[i] - (slope * i + intercept)) for i in range(n)]
    variance = sum(r * r for r in residuals) / n
    std_dev = math.sqrt(variance)
    
    upper = baseline + (num_std * std_dev)
    lower = baseline - (num_std * std_dev)
    
    curr_price = closes[-1]
    channel_width = upper - lower
    pos_pct = ((curr_price - lower) / channel_width * 100.0) if channel_width > 0 else 50.0
    
    slope_pct = (slope * n / baseline) * 100.0 if baseline > 0 else 0.0
    
    if slope_pct > 1.2:
        trend = "BULLISH_CHANNEL"
    elif slope_pct < -1.2:
        trend = "BEARISH_CHANNEL"
    else:
        trend = "HORIZONTAL_CHANNEL"
        
    return {
        "slope": round(slope, 6),
        "slope_pct": round(slope_pct, 2),
        "baseline": round(baseline, 4),
        "upper": round(upper, 4),
        "lower": round(lower, 4),
        "channel_width_pct": round((channel_width / baseline * 100.0) if baseline > 0 else 0.0, 2),
        "position_pct": round(pos_pct, 1),
        "trend": trend,
        "is_support_test": pos_pct <= 18.0,
        "is_resistance_test": pos_pct >= 82.0,
        "is_upper_breakout": curr_price > upper,
        "is_lower_breakdown": curr_price < lower
    }

def calculate_volume_profile(candles: List[Dict], lookback: int = 48, bins: int = 30, value_area_pct: float = 0.70) -> Dict:
    """
    Volume Profile Engine:
    Identifies POC (Point of Control - Peak Volume Price Node),
    VAH (Value Area High) and VAL (Value Area Low) enclosing 70% of transacted volume.
    """
    if len(candles) < 20:
        return {
            "poc": 0.0, "vah": 0.0, "val": 0.0, "dist_poc_pct": 0.0,
            "interaction": "NONE", "is_above_poc": False,
            "is_poc_retest": False, "is_vah_breakout": False, "is_val_support": False
        }
    
    recent = candles[-min(len(candles), lookback):]
    highs = [float(c["high"]) for c in recent]
    lows = [float(c["low"]) for c in recent]
    
    max_p = max(highs)
    min_p = min(lows)
    
    if max_p == min_p:
        return {
            "poc": max_p, "vah": max_p, "val": min_p, "dist_poc_pct": 0.0,
            "interaction": "NONE", "is_above_poc": False,
            "is_poc_retest": False, "is_vah_breakout": False, "is_val_support": False
        }
    
    bin_width = (max_p - min_p) / bins
    bin_centers = [min_p + (i + 0.5) * bin_width for i in range(bins)]
    bin_volumes = [0.0] * bins
    
    for c in recent:
        c_h = float(c["high"])
        c_l = float(c["low"])
        c_vol = float(c["volume"])
        if c_h == c_l or c_vol <= 0:
            continue
            
        overlap_indices = [i for i, center in enumerate(bin_centers) if (center >= c_l - bin_width * 0.5) and (center <= c_h + bin_width * 0.5)]
        if overlap_indices:
            vol_per_bin = c_vol / len(overlap_indices)
            for idx in overlap_indices:
                bin_volumes[idx] += vol_per_bin
        else:
            c_close = float(c["close"])
            closest_idx = min(range(bins), key=lambda i: abs(bin_centers[i] - c_close))
            bin_volumes[closest_idx] += c_vol
            
    # POC Index
    poc_idx = max(range(bins), key=lambda i: bin_volumes[i])
    poc_price = bin_centers[poc_idx]
    
    # Value Area Expansion (70% Volume)
    total_vol = sum(bin_volumes)
    target_vol = total_vol * value_area_pct
    
    accum_vol = bin_volumes[poc_idx]
    up_idx = poc_idx
    down_idx = poc_idx
    
    while accum_vol < target_vol:
        next_up_vol = bin_volumes[up_idx + 1] if up_idx + 1 < bins else -1.0
        next_down_vol = bin_volumes[down_idx - 1] if down_idx - 1 >= 0 else -1.0
        
        if next_up_vol < 0 and next_down_vol < 0:
            break
            
        if next_up_vol >= next_down_vol:
            up_idx += 1
            accum_vol += bin_volumes[up_idx]
        else:
            down_idx -= 1
            accum_vol += bin_volumes[down_idx]
            
    val_price = bin_centers[down_idx]
    vah_price = bin_centers[up_idx]
    
    curr_price = float(candles[-1]["close"])
    dist_poc_pct = abs(curr_price - poc_price) / curr_price * 100.0
    
    interaction = "INSIDE_VALUE_AREA"
    if curr_price > vah_price:
        interaction = "ABOVE_VAH_EXPANSION"
    elif curr_price < val_price:
        interaction = "BELOW_VAL_BREAKDOWN"
    elif dist_poc_pct <= 0.35:
        interaction = "AT_POC_LIQUIDITY_CORE"
        
    return {
        "poc": round(poc_price, 4),
        "vah": round(vah_price, 4),
        "val": round(val_price, 4),
        "dist_poc_pct": round(dist_poc_pct, 2),
        "interaction": interaction,
        "is_above_poc": curr_price > poc_price,
        "is_poc_retest": dist_poc_pct <= 0.40,
        "is_vah_breakout": curr_price >= vah_price * 0.998,
        "is_val_support": abs(curr_price - val_price) / curr_price * 100.0 <= 0.45
    }

def calculate_camarilla_pivots(candles: List[Dict], lookback_bars: int = 24) -> Dict:
    """
    Camarilla Intraday Support & Resistance Pivot Formula.
    H4/L4 = Institutional Momentum Breakout / Breakdown boundaries
    H3/L3 = Institutional Mean-Reversion boundaries
    """
    if len(candles) < 10:
        return {}
    
    bars = candles[-min(len(candles), lookback_bars):]
    high = max(float(c["high"]) for c in bars[:-1]) if len(bars) > 1 else float(bars[0]["high"])
    low = min(float(c["low"]) for c in bars[:-1]) if len(bars) > 1 else float(bars[0]["low"])
    close = float(bars[-2]["close"]) if len(bars) > 1 else float(bars[-1]["close"])
    
    rng = high - low
    if rng <= 0:
        rng = close * 0.01
        
    pp = (high + low + close) / 3.0
    
    r4 = close + rng * (1.1 / 2.0)
    r3 = close + rng * (1.1 / 4.0)
    r2 = close + rng * (1.1 / 6.0)
    r1 = close + rng * (1.1 / 12.0)
    
    s1 = close - rng * (1.1 / 12.0)
    s2 = close - rng * (1.1 / 6.0)
    s3 = close - rng * (1.1 / 4.0)
    s4 = close - rng * (1.1 / 2.0)
    
    curr = float(candles[-1]["close"])
    
    return {
        "pp": round(pp, 4),
        "r4": round(r4, 4),
        "r3": round(r3, 4),
        "s3": round(s3, 4),
        "s4": round(s4, 4),
        "r4_breakout": round(r4, 4),
        "r3_reversal": round(r3, 4),
        "s3_reversal": round(s3, 4),
        "s4_breakdown": round(s4, 4),
        "is_above_h4": curr > r4,
        "is_near_h4_breakout": (curr >= r4 * 0.998) and (curr <= r4 * 1.01),
        "is_at_s3_support": abs(curr - s3) / curr * 100.0 <= 0.40,
        "is_below_s4": curr < s4,
        "is_near_s4_breakdown": (curr <= s4 * 1.002) and (curr >= s4 * 0.99)
    }

def detect_rsi_divergence(candles: List[Dict], rsi_series: List[float], lookback: int = 40, order: int = 3) -> Dict:
    """
    RSI Regular & Hidden Divergence Detection Engine:
    - Regular Bullish: Price LL, RSI HL -> Trend Reversal UP
    - Hidden Bullish: Price HL, RSI LL -> Trend Continuation UP
    - Regular Bearish: Price HH, RSI LH -> Trend Reversal DOWN
    - Hidden Bearish: Price LH, RSI HH -> Trend Continuation DOWN
    """
    if len(candles) < lookback or len(rsi_series) < lookback:
        return {"bullish_divergence": None, "bearish_divergence": None, "description": "Yetersiz Veri", "bonus_score": 0}
        
    recent = candles[-lookback:]
    recent_rsi = rsi_series[-lookback:]
    lows = [float(c["low"]) for c in recent]
    highs = [float(c["high"]) for c in recent]
    n = len(recent)
    
    swing_lows = []
    swing_highs = []
    
    for i in range(order, n - order):
        if all(lows[i] <= lows[i - k] for k in range(1, order + 1)) and all(lows[i] <= lows[i + k] for k in range(1, order + 1)):
            swing_lows.append(i)
        if all(highs[i] >= highs[i - k] for k in range(1, order + 1)) and all(highs[i] >= highs[i + k] for k in range(1, order + 1)):
            swing_highs.append(i)
            
    bullish_divergence = None
    bearish_divergence = None
    desc_list = []
    bonus_score_long = 0
    bonus_score_short = 0
    
    # 1. Boğa Diverjansları (Dip Analizi)
    if len(swing_lows) >= 1:
        prev_idx = swing_lows[-1]
        prev_p = lows[prev_idx]
        prev_r = recent_rsi[prev_idx]
        
        recent_p = min(lows[-3:])
        recent_p_idx = -3 + lows[-3:].index(recent_p) + n
        recent_r = recent_rsi[recent_p_idx]
        
        if (n - 1 - prev_idx) >= 4:
            if recent_p < prev_p and recent_r > prev_r + 1.2:
                bullish_divergence = "REGULAR_BULLISH"
                desc_list.append(f"Düzenli Boğa Diverjansı (Fiyat Dip: {recent_p:.2f} < {prev_p:.2f} | RSI: {recent_r:.1f} > {prev_r:.1f})")
                bonus_score_long = 15
            elif recent_p > prev_p and recent_r < prev_r - 1.2:
                bullish_divergence = "HIDDEN_BULLISH"
                desc_list.append(f"Gizli Boğa Diverjansı (Trend Devamı: Fiyat {recent_p:.2f} > {prev_p:.2f} | RSI: {recent_r:.1f} < {prev_r:.1f})")
                bonus_score_long = 12

    # 2. Ayı Diverjansları (Tepe Analizi)
    if len(swing_highs) >= 1:
        prev_idx = swing_highs[-1]
        prev_p = highs[prev_idx]
        prev_r = recent_rsi[prev_idx]
        
        recent_p = max(highs[-3:])
        recent_p_idx = -3 + highs[-3:].index(recent_p) + n
        recent_r = recent_rsi[recent_p_idx]
        
        if (n - 1 - prev_idx) >= 4:
            if recent_p > prev_p and recent_r < prev_r - 1.2:
                bearish_divergence = "REGULAR_BEARISH"
                desc_list.append(f"Düzenli Ayı Diverjansı (Fiyat Tepe: {recent_p:.2f} > {prev_p:.2f} | RSI: {recent_r:.1f} < {prev_r:.1f})")
                bonus_score_short = 15
            elif recent_p < prev_p and recent_r > prev_r + 1.2:
                bearish_divergence = "HIDDEN_BEARISH"
                desc_list.append(f"Gizli Ayı Diverjansı (Ayı Devamı: Fiyat {recent_p:.2f} < {prev_p:.2f} | RSI: {recent_r:.1f} > {prev_r:.1f})")
                bonus_score_short = 12

    return {
        "bullish_divergence": bullish_divergence,
        "bearish_divergence": bearish_divergence,
        "bonus_score_long": bonus_score_long,
        "bonus_score_short": bonus_score_short,
        "description": " | ".join(desc_list) if desc_list else "Diverjans Yok"
    }

def calculate_adx(candles: List[Dict], period: int = 14) -> Dict:
    """
    Welles Wilder ADX Trend Strength Engine:
    Identifies strong institutional trending markets vs low-liquidity chop whipsaws.
    """
    if len(candles) < period * 2:
        return {
            "adx": 20.0, "pdi": 20.0, "mdi": 20.0,
            "trend_strength": "NEUTRAL", "is_strong_trend": False,
            "is_bullish_dominance": False, "is_bearish_dominance": False
        }
        
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    closes = [float(c["close"]) for c in candles]
    n = len(candles)
    
    tr_list = []
    pdm_list = []
    mdm_list = []
    
    for i in range(1, n):
        h = highs[i]
        l = lows[i]
        prev_h = highs[i - 1]
        prev_l = lows[i - 1]
        prev_c = closes[i - 1]
        
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)
        
        up_move = h - prev_h
        down_move = prev_l - l
        
        pdm_list.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        mdm_list.append(down_move if (down_move > up_move and down_move > 0) else 0.0)
            
    tr_smooth = sum(tr_list[:period])
    pdm_smooth = sum(pdm_list[:period])
    mdm_smooth = sum(mdm_list[:period])
    
    dx_list = []
    
    for i in range(period, len(tr_list)):
        tr_smooth = tr_smooth - (tr_smooth / period) + tr_list[i]
        pdm_smooth = pdm_smooth - (pdm_smooth / period) + pdm_list[i]
        mdm_smooth = mdm_smooth - (mdm_smooth / period) + mdm_list[i]
        
        pdi = (100.0 * pdm_smooth / tr_smooth) if tr_smooth > 0 else 0.0
        mdi = (100.0 * mdm_smooth / tr_smooth) if tr_smooth > 0 else 0.0
        
        di_sum = pdi + mdi
        dx = (100.0 * abs(pdi - mdi) / di_sum) if di_sum > 0 else 0.0
        dx_list.append((dx, pdi, mdi))
        
    if len(dx_list) < period:
        return {
            "adx": 20.0, "pdi": 20.0, "mdi": 20.0,
            "trend_strength": "NEUTRAL", "is_strong_trend": False,
            "is_bullish_dominance": False, "is_bearish_dominance": False
        }
        
    adx = sum(d[0] for d in dx_list[:period]) / period
    for d in dx_list[period:]:
        adx = (adx * (period - 1) + d[0]) / period
        
    last_pdi = dx_list[-1][1]
    last_mdi = dx_list[-1][2]
    
    if adx >= 28.0:
        strength = "VERY_STRONG_TREND"
    elif adx >= 22.0:
        strength = "STRONG_TREND"
    elif adx >= 17.0:
        strength = "MODERATE_TREND"
    else:
        strength = "WEAK_CHOP"
        
    return {
        "adx": round(adx, 1),
        "pdi": round(last_pdi, 1),
        "mdi": round(last_mdi, 1),
        "trend_strength": strength,
        "is_bullish_dominance": last_pdi > last_mdi,
        "is_bearish_dominance": last_mdi > last_pdi,
        "is_strong_trend": adx >= 22.0
    }

def calculate_fibonacci_golden_pocket(candles: List[Dict], lookback: int = 40) -> Dict:
    """
    Kurumsal Fibonacci & Optimal Trade Entry (OTE) Analiz Motoru:
    - 0.618 - 0.665: Altın Cep (Golden Pocket) - Kripto vadeli piyasasının en yüksek kazanma oranlı dönüş alanı.
    - 0.500: Denge / Equilibrium.
    - 0.786: Son Kurumsal Likidite Savunma Hattı.
    """
    if len(candles) < lookback:
        return {}
        
    recent = candles[-lookback:]
    highs = [float(c["high"]) for c in recent]
    lows = [float(c["low"]) for c in recent]
    
    max_idx = int(np.argmax(highs))
    min_idx = int(np.argmin(lows))
    swing_high = highs[max_idx]
    swing_low = lows[min_idx]
    
    rng = swing_high - swing_low
    if rng <= 0:
        return {}
        
    curr = float(candles[-1]["close"])
    
    # Eğer en dip, en tepeden önce gerçekleşmişse: Yükseliş İmpulsu -> Düzeltme / Pullback Analizi
    if min_idx < max_idx:
        impulse = "BULLISH_IMPULSE"
        fib_382 = swing_high - rng * 0.382
        fib_500 = swing_high - rng * 0.500
        fib_618 = swing_high - rng * 0.618
        fib_665 = swing_high - rng * 0.665
        fib_786 = swing_high - rng * 0.786
        
        gp_top = fib_618
        gp_bottom = fib_665
        is_in_golden_pocket = (curr <= gp_top * 1.002) and (curr >= gp_bottom * 0.998)
        is_in_ote = (curr <= fib_618 * 1.002) and (curr >= fib_786 * 0.998)
    else:
        # En tepe, en dipten önce gerçekleşmişse: Düşüş İmpulsu -> Yukarı Tepki / Retracement Analizi
        impulse = "BEARISH_IMPULSE"
        fib_382 = swing_low + rng * 0.382
        fib_500 = swing_low + rng * 0.500
        fib_618 = swing_low + rng * 0.618
        fib_665 = swing_low + rng * 0.665
        fib_786 = swing_low + rng * 0.786
        
        gp_bottom = fib_618
        gp_top = fib_665
        is_in_golden_pocket = (curr >= gp_bottom * 0.998) and (curr <= gp_top * 1.002)
        is_in_ote = (curr >= fib_618 * 0.998) and (curr <= fib_786 * 1.002)
        
    return {
        "impulse": impulse,
        "swing_high": round(swing_high, 4),
        "swing_low": round(swing_low, 4),
        "fib_382": round(fib_382, 4),
        "fib_500": round(fib_500, 4),
        "fib_618": round(fib_618, 4),
        "fib_665": round(fib_665, 4),
        "fib_786": round(fib_786, 4),
        "is_in_golden_pocket": is_in_golden_pocket,
        "is_in_ote": is_in_ote
    }

def detect_swing_failure_pattern(candles: List[Dict], lookback: int = 25, swing_window: int = 3) -> Dict:
    """
    Swing Failure Pattern (SFP) & Kurumsal Likidite Süpürme (Liquidity Sweep) Algoritması:
    Perakende stop-loss emirlerinin tetiklenip fiyatın derhal seviyenin içine geri çekildiği
    (sahte kırılım / fitil avı) anları matematiksel olarak yakalar.
    """
    if len(candles) < lookback:
        return {"bullish_sfp": False, "bearish_sfp": False}
        
    bars = candles[-lookback:]
    curr_c = float(bars[-1]["close"])
    curr_h = float(bars[-1]["high"])
    curr_l = float(bars[-1]["low"])
    curr_o = float(bars[-1]["open"])
    
    # Geçmiş mumlardaki belirgin Swing High ve Swing Low noktalarını tespit et
    swing_highs = []
    swing_lows = []
    
    for i in range(swing_window, len(bars) - swing_window - 1):
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        
        is_high = all(h >= float(bars[i - j]["high"]) for j in range(1, swing_window + 1)) and \
                  all(h >= float(bars[i + j]["high"]) for j in range(1, swing_window + 1))
        if is_high:
            swing_highs.append(h)
            
        is_low = all(l <= float(bars[i - j]["low"]) for j in range(1, swing_window + 1)) and \
                 all(l <= float(bars[i + j]["low"]) for j in range(1, swing_window + 1))
        if is_low:
            swing_lows.append(l)
            
    bullish_sfp = False
    bearish_sfp = False
    sweep_level = None
    invalidation_level = None
    
    # 1. Boğa SFP: Fiyat geçmiş bir swing low'u aşağı fitilleyip içine kapattı mı?
    if swing_lows:
        recent_low = min(swing_lows[-3:])
        if curr_l < recent_low and curr_c > recent_low and min(curr_o, curr_c) > recent_low:
            bullish_sfp = True
            sweep_level = recent_low
            invalidation_level = curr_l
            
    # 2. Ayı SFP: Fiyat geçmiş bir swing high'ı yukarı fitilleyip altına kapattı mı?
    if swing_highs:
        recent_high = max(swing_highs[-3:])
        if curr_h > recent_high and curr_c < recent_high and max(curr_o, curr_c) < recent_high:
            bearish_sfp = True
            sweep_level = recent_high
            invalidation_level = curr_h
            
    return {
        "bullish_sfp": bullish_sfp,
        "bearish_sfp": bearish_sfp,
        "sweep_level": round(sweep_level, 4) if sweep_level else None,
        "invalidation_level": round(invalidation_level, 4) if invalidation_level else None
    }

def calculate_supertrend(candles: List[Dict], period: int = 10, multiplier: float = 3.0) -> Dict:
    """
    Wilder ATR Tabanlı SuperTrend Algoritması.
    Kurumsal algoritmik fonların volatiliteye duyarlı trend takibinde kullandığı temel motor.
    """
    if len(candles) < period + 2:
        return {"trend": "NEUTRAL", "supertrend": 0.0, "is_bullish": False, "is_bearish": False}
        
    tr_list = []
    for i in range(1, len(candles)):
        h = float(candles[i]["high"])
        l = float(candles[i]["low"])
        prev_c = float(candles[i - 1]["close"])
        tr_list.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
        
    atr = [sum(tr_list[:period]) / period]
    for tr in tr_list[period:]:
        atr.append((atr[-1] * (period - 1) + tr) / period)
        
    n = len(atr)
    sub_candles = candles[-n:]
    
    upper_band = []
    lower_band = []
    
    for i in range(n):
        hl2 = (float(sub_candles[i]["high"]) + float(sub_candles[i]["low"])) / 2.0
        cur_atr = atr[i]
        upper_band.append(hl2 + multiplier * cur_atr)
        lower_band.append(hl2 - multiplier * cur_atr)
        
    trend = 1  # 1: Bullish, -1: Bearish
    supertrend = [lower_band[0]]
    
    for i in range(1, n):
        close_curr = float(sub_candles[i]["close"])
        close_prev = float(sub_candles[i - 1]["close"])
        
        # Lower band trailing
        if lower_band[i] > lower_band[i - 1] or close_prev < lower_band[i - 1]:
            cur_lower = lower_band[i]
        else:
            cur_lower = lower_band[i - 1]
            
        # Upper band trailing
        if upper_band[i] < upper_band[i - 1] or close_prev > upper_band[i - 1]:
            cur_upper = upper_band[i]
        else:
            cur_upper = upper_band[i - 1]
            
        if trend == 1:
            if close_curr < cur_lower:
                trend = -1
                supertrend.append(cur_upper)
            else:
                supertrend.append(cur_lower)
        else:
            if close_curr > cur_upper:
                trend = 1
                supertrend.append(cur_lower)
            else:
                supertrend.append(cur_upper)
                
    curr_trend = "BULLISH" if trend == 1 else "BEARISH"
    curr_st = supertrend[-1]
    curr_price = float(candles[-1]["close"])
    
    return {
        "trend": curr_trend,
        "supertrend": round(curr_st, 4),
        "is_bullish": trend == 1,
        "is_bearish": trend == -1,
        "dist_to_supertrend_pct": round(abs(curr_price - curr_st) / curr_price * 100.0, 2)
    }


def calculate_vwap_bands(
    candles: List[Dict],
    lookback: int = 40,
    stdev_mult1: float = 1.5,
    stdev_mult2: float = 2.0
) -> Dict:
    """
    VWAP Standart Sapma Bantları ve Kurumsal Mean-Reversion Katmanı.
    Fiyatın hacim ağırlıklı ortalamadan (VWAP) ne kadar saptığını (Z-Score)
    ve kurumsal ortalamaya dönüş (Mean-Reversion) sinyalini hesaplar.
    """
    if len(candles) < 15:
        return {
            "vwap": 0.0,
            "stdev": 0.0,
            "z_score": 0.0,
            "upper_band_1": 0.0,
            "lower_band_1": 0.0,
            "upper_band_2": 0.0,
            "lower_band_2": 0.0,
            "is_mean_reversion_long": False,
            "is_mean_reversion_short": False,
            "reversion_target": 0.0
        }

    sub = candles[-lookback:] if len(candles) >= lookback else candles
    cum_tp_vol = 0.0
    cum_vol = 0.0
    tp_list = []
    vol_list = []

    for c in sub:
        high = float(c["high"])
        low = float(c["low"])
        close = float(c["close"])
        vol = float(c.get("volume", 1.0)) or 1.0
        tp = (high + low + close) / 3.0
        tp_list.append(tp)
        vol_list.append(vol)
        cum_tp_vol += tp * vol
        cum_vol += vol

    vwap = cum_tp_vol / cum_vol if cum_vol > 0 else float(candles[-1]["close"])

    # Hacim Ağırlıklı Standart Sapma (Volume-Weighted Variance)
    variance_sum = 0.0
    for tp, vol in zip(tp_list, vol_list):
        variance_sum += vol * ((tp - vwap) ** 2)

    stdev = math.sqrt(variance_sum / cum_vol) if cum_vol > 0 else 0.0

    upper_band_1 = vwap + (stdev * stdev_mult1)
    lower_band_1 = vwap - (stdev * stdev_mult1)
    upper_band_2 = vwap + (stdev * stdev_mult2)
    lower_band_2 = vwap - (stdev * stdev_mult2)

    curr_close = float(candles[-1]["close"])
    curr_open = float(candles[-1]["open"])
    prev_close = float(candles[-2]["close"]) if len(candles) >= 2 else curr_close
    prev_low = float(candles[-2]["low"]) if len(candles) >= 2 else curr_close
    prev_high = float(candles[-2]["high"]) if len(candles) >= 2 else curr_close

    z_score = (curr_close - vwap) / stdev if stdev > 0 else 0.0

    # Mean Reversion Long Koşulu:
    # Fiyat alt bant 2.0'ı test edip yeşil mumla içeri toparlanmış (Z-Score <= -1.4)
    is_mr_long = (
        (prev_low <= lower_band_2 or curr_close <= lower_band_1)
        and curr_close > curr_open
        and curr_close > prev_close
        and z_score <= -1.4
    )

    # Mean Reversion Short Koşulu:
    # Fiyat üst bant 2.0'ı test edip kırmızı mumla red yemiş (Z-Score >= +1.4)
    is_mr_short = (
        (prev_high >= upper_band_2 or curr_close >= upper_band_1)
        and curr_close < curr_open
        and curr_close < prev_close
        and z_score >= 1.4
    )

    return {
        "vwap": round(vwap, 6),
        "stdev": round(stdev, 6),
        "z_score": round(z_score, 2),
        "upper_band_1": round(upper_band_1, 6),
        "lower_band_1": round(lower_band_1, 6),
        "upper_band_2": round(upper_band_2, 6),
        "lower_band_2": round(lower_band_2, 6),
        "is_mean_reversion_long": is_mr_long,
        "is_mean_reversion_short": is_mr_short,
        "reversion_target": round(vwap, 6)
    }
