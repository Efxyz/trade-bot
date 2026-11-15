"""
Technical Analysis (TA) Agent - Institutional Smart Money Concepts (SMC) & Quant Confluence Engine
Features:
- Fair Value Gap (FVG / Imbalance) Detection & Retest Engine
- Order Block (OB / Kurumsal Balina Blokları) Identification
- Liquidity Sweep (Fitil / Stop Avı) Detection
- TTM Squeeze (Bollinger Bands vs Keltner Channels Volatility Compression)
- VWAP (Volume-Weighted Average Price) Institutional Bias
- Dynamic 0-100 Confluence Score (Grade A+ 20x / Grade A 10x)
"""
from typing import List, Dict, Optional, Tuple
import math
import time
from config import (
    TARGET_PROFIT_PCT,
    MAX_SCALP_SL_PCT,
    MIN_SCALP_SL_PCT,
    MAX_SL_PCT_20X,
    EXCLUDED_SYMBOLS_BLACKLIST,
    MIN_RR_RATIO,
    MAX_RSI_LONG,
    MIN_RSI_LONG,
    MIN_RSI_SHORT,
    MAX_RSI_SHORT,
    MIN_4BAR_RANGE_PCT,
    MIN_CONFLUENCE_SCORE,
    MIN_CONFLUENCE_SCORE_SHORT,
    MAX_VWAP_DISTANCE_PCT,
    SMC_PREMIUM_DISCOUNT_FILTER
)
from core.advanced_indicators import (
    calculate_linear_regression_channel,
    calculate_volume_profile,
    calculate_camarilla_pivots,
    detect_rsi_divergence as advanced_detect_rsi_divergence,
    calculate_adx,
    calculate_fibonacci_golden_pocket,
    detect_swing_failure_pattern,
    calculate_supertrend,
    calculate_vwap_bands
)

class TechnicalAnalysisAgent:
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
        tr = [candles[0]["high"] - candles[0]["low"]]
        for i in range(1, len(candles)):
            tr.append(max(
                candles[i]["high"] - candles[i]["low"],
                abs(candles[i]["high"] - candles[i - 1]["close"]),
                abs(candles[i]["low"] - candles[i - 1]["close"])
            ))
        first_atr = sum(tr[:period]) / period
        atr = [None] * (period - 1)
        atr.append(first_atr)
        current_atr = first_atr
        for i in range(period, len(tr)):
            current_atr = (current_atr * (period - 1) + tr[i]) / period
            atr.append(current_atr)
        return atr

    @staticmethod
    def calculate_vwap(candles: List[Dict]) -> List[float]:
        """Hacim Ağırlıklı Ortalama Fiyat (VWAP) serisini hesaplar."""
        cum_tp_vol = 0.0
        cum_vol = 0.0
        vwap_series = []
        for c in candles:
            tp = (c["high"] + c["low"] + c["close"]) / 3.0
            vol = c["volume"] if c["volume"] > 0 else 1.0
            cum_tp_vol += tp * vol
            cum_vol += vol
            vwap_series.append(cum_tp_vol / cum_vol)
        return vwap_series

    @staticmethod
    def calculate_ttm_squeeze(candles: List[Dict], period: int = 20, bb_mult: float = 2.0, kc_mult: float = 1.5) -> Dict:
        """
        TTM Squeeze: Bollinger Bantları Keltner Kanalı'nın içine girince enerji depolar (Sıkışma).
        Dışına çıktığı an patlama yönüne doğru momentum başlar.
        """
        if len(candles) < period + 5:
            return {"in_squeeze": False, "squeeze_fired": False, "momentum": 0.0}

        closes = [c["close"] for c in candles]
        
        # 1. Bollinger Bantları
        recent_closes = closes[-period:]
        sma = sum(recent_closes) / period
        variance = sum((x - sma) ** 2 for x in recent_closes) / period
        std_dev = math.sqrt(variance)
        bb_upper = sma + (bb_mult * std_dev)
        bb_lower = sma - (bb_mult * std_dev)

        # 2. Keltner Kanalı (ATR tabanlı)
        tr_list = []
        for i in range(-period, 0):
            prev_close = candles[i - 1]["close"]
            h = candles[i]["high"]
            l = candles[i]["low"]
            tr_list.append(max(h - l, abs(h - prev_close), abs(l - prev_close)))
        atr = sum(tr_list) / period
        kc_upper = sma + (kc_mult * atr)
        kc_lower = sma - (kc_mult * atr)

        # Sıkışma durumu
        in_squeeze = (bb_upper <= kc_upper) and (bb_lower >= kc_lower)

        # Önceki mumlarda sıkışma olup olmadığını kontrol et (Squeeze Fired tespiti)
        prev_closes = closes[-(period + 2):-2]
        prev_sma = sum(prev_closes) / len(prev_closes)
        prev_std = math.sqrt(sum((x - prev_sma) ** 2 for x in prev_closes) / len(prev_closes))
        prev_bb_up = prev_sma + (bb_mult * prev_std)
        prev_bb_dn = prev_sma - (bb_mult * prev_std)
        was_in_squeeze = (prev_bb_up <= kc_upper) and (prev_bb_dn >= kc_lower)

        squeeze_fired = was_in_squeeze and not in_squeeze
        momentum = (closes[-1] - sma) / (atr if atr > 0 else 1.0)

        return {
            "in_squeeze": in_squeeze,
            "squeeze_fired": squeeze_fired,
            "momentum": momentum,
            "bb_width_pct": ((bb_upper - bb_lower) / sma) * 100 if sma > 0 else 0.0
        }

    @staticmethod
    def detect_fvg(candles: List[Dict], max_lookback: int = 15) -> Dict:
        """
        Fair Value Gap (FVG / Kurumsal Dengesizlik) Tespiti:
        Bullish FVG: 1. mumun tepesi < 3. mumun dibi (fiyat yükselirken arkada bıraktığı mıknatıs boşluk).
        Bearish FVG: 1. mumun dibi > 3. mumun tepesi (fiyat düşerken bıraktığı arz boşluğu).
        """
        n = len(candles)
        if n < 5:
            return {"bullish_fvg": None, "bearish_fvg": None, "current_in_fvg": None}

        current_price = candles[-1]["close"]
        bullish_fvg = None
        bearish_fvg = None
        start_idx = max(2, n - max_lookback)

        for i in range(start_idx, n - 1):
            c1 = candles[i - 2]
            c2 = candles[i - 1]
            c3 = candles[i]

            # Bullish FVG
            if c1["high"] < c3["low"]:
                gap_top = c3["low"]
                gap_bottom = c1["high"]
                # FVG henüz doldurulmadıysa (unmitigated)
                if current_price >= gap_bottom * 0.998:
                    bullish_fvg = {
                        "top": gap_top,
                        "bottom": gap_bottom,
                        "mid": (gap_top + gap_bottom) / 2.0,
                        "age_candles": (n - 1) - i
                    }

            # Bearish FVG
            if c1["low"] > c3["high"]:
                gap_top = c1["low"]
                gap_bottom = c3["high"]
                if current_price <= gap_top * 1.002:
                    bearish_fvg = {
                        "top": gap_top,
                        "bottom": gap_bottom,
                        "mid": (gap_top + gap_bottom) / 2.0,
                        "age_candles": (n - 1) - i
                    }

        # Anlık fiyat FVG içinde mi test ediyor?
        current_in_fvg = None
        if bullish_fvg and (bullish_fvg["bottom"] <= current_price <= bullish_fvg["top"] * 1.002):
            current_in_fvg = "BULLISH_TEST"
        elif bearish_fvg and (bearish_fvg["bottom"] * 0.998 <= current_price <= bearish_fvg["top"]):
            current_in_fvg = "BEARISH_TEST"

        return {
            "bullish_fvg": bullish_fvg,
            "bearish_fvg": bearish_fvg,
            "current_in_fvg": current_in_fvg
        }

    @staticmethod
    def detect_order_blocks(candles: List[Dict], max_lookback: int = 20) -> Dict:
        """
        Order Block (Kurumsal Balina Blokları) Tespiti:
        Güçlü bir kırılım (displacement) öncesindeki son zıt yönlü kurumsal mum.
        """
        n = len(candles)
        if n < 8:
            return {"bullish_ob": None, "bearish_ob": None, "current_at_ob": None}

        current_price = candles[-1]["close"]
        bullish_ob = None
        bearish_ob = None
        start_idx = max(3, n - max_lookback)

        for i in range(start_idx, n - 2):
            curr_c = candles[i]
            next_c = candles[i + 1]
            next_c2 = candles[i + 2]

            body_size = abs(curr_c["close"] - curr_c["open"])
            disp_body = abs(next_c["close"] - next_c["open"]) + abs(next_c2["close"] - next_c2["open"])

            # Bullish OB: Kırmızı mum ardından 2 mumda güçlü yukarı patlama
            if curr_c["close"] < curr_c["open"] and next_c["close"] > next_c["open"] and disp_body > body_size * 1.8:
                bullish_ob = {
                    "high": max(curr_c["open"], curr_c["close"]),
                    "low": curr_c["low"],
                    "age": (n - 1) - i
                }

            # Bearish OB: Yeşil mum ardından 2 mumda güçlü aşağı patlama
            if curr_c["close"] > curr_c["open"] and next_c["close"] < next_c["open"] and disp_body > body_size * 1.8:
                bearish_ob = {
                    "high": curr_c["high"],
                    "low": min(curr_c["open"], curr_c["close"]),
                    "age": (n - 1) - i
                }

        current_at_ob = None
        if bullish_ob and (bullish_ob["low"] * 0.998 <= current_price <= bullish_ob["high"] * 1.002):
            current_at_ob = "BULLISH_OB_RETEST"
        elif bearish_ob and (bearish_ob["low"] * 0.998 <= current_price <= bearish_ob["high"] * 1.002):
            current_at_ob = "BEARISH_OB_RETEST"

        return {
            "bullish_ob": bullish_ob,
            "bearish_ob": bearish_ob,
            "current_at_ob": current_at_ob
        }

    @staticmethod
    def detect_liquidity_sweep(candles: List[Dict], lookback: int = 15) -> Dict:
        """
        Liquidity Sweep (Fitil / Stop Avı) Tespiti:
        Fiyat önceki tepeyi/dibi fitille delip (stopları avlayıp) seviyenin içinde kapattıysa sahte kırılım avıdır.
        """
        n = len(candles)
        if n < lookback + 2:
            return {"bullish_sweep": False, "bearish_sweep": False}

        last_c = candles[-1]
        prior_candles = candles[-(lookback + 1):-1]
        highest_high = max(c["high"] for c in prior_candles)
        lowest_low = min(c["low"] for c in prior_candles)

        # Bullish Sweep: Dibi delip (fitil atıp) gövdesi dibin üzerinde kapattı (Alıcı tepkisi)
        bullish_sweep = (last_c["low"] < lowest_low) and (last_c["close"] > lowest_low)

        # Bearish Sweep: Tepeyi delip fitil attı ve tepenin altında kapattı (Satıcı baskısı)
        bearish_sweep = (last_c["high"] > highest_high) and (last_c["close"] < highest_high)

        return {
            "bullish_sweep": bullish_sweep,
            "bearish_sweep": bearish_sweep
        }

    @staticmethod
    def detect_rsi_divergence(candles_15m: List[Dict], rsi_values: List[Optional[float]], direction: str) -> Tuple[bool, str]:
        """
        15m mumlarında ve RSI değerlerinde uyumsuzluk (Divergence) tespiti yapar.
        - SHORT için: Fiyat Lower Low yaparken RSI Higher Low yapıyorsa (Bullish Div -> SHORT VETO)
        - LONG için: Fiyat Higher High yaparken RSI Lower High yapıyorsa (Bearish Div -> LONG VETO)
        """
        if len(candles_15m) < 15 or len(rsi_values) < 15:
            return False, ""

        curr_candles = candles_15m[-4:]
        prev_candles = candles_15m[-12:-4]

        valid_rsi_curr = [r for r in rsi_values[-4:] if r is not None]
        valid_rsi_prev = [r for r in rsi_values[-12:-4] if r is not None]

        if not valid_rsi_curr or not valid_rsi_prev:
            return False, ""

        if direction == "SHORT":
            curr_low = min(c["low"] for c in curr_candles)
            prev_low = min(c["low"] for c in prev_candles)
            curr_rsi_min = min(valid_rsi_curr)
            prev_rsi_min = min(valid_rsi_prev)

            # Fiyat daha düşük dip yaptı ama RSI 3+ puan daha yüksekte kaldıysa (Pozitif Uyumsuzluk / V-dip tuzağı)
            if curr_low < prev_low and curr_rsi_min > (prev_rsi_min + 3.0):
                return True, f"Pozitif RSI Uyumsuzluğu (Fiyat Dip: {curr_low:.4f} < {prev_low:.4f}, RSI Dip: {curr_rsi_min:.1f} > {prev_rsi_min:.1f})"

        elif direction == "LONG":
            curr_high = max(c["high"] for c in curr_candles)
            prev_high = max(c["high"] for c in prev_candles)
            curr_rsi_max = max(valid_rsi_curr)
            prev_rsi_max = max(valid_rsi_prev)

            # Fiyat daha yüksek tepe yaptı ama RSI 3+ puan daha aşağıda kaldıysa (Negatif Uyumsuzluk / Tepe alımı)
            if curr_high > prev_high and curr_rsi_max < (prev_rsi_max - 3.0):
                return True, f"Negatif RSI Uyumsuzluğu (Fiyat Tepe: {curr_high:.4f} > {prev_high:.4f}, RSI Tepe: {curr_rsi_max:.1f} < {prev_rsi_max:.1f})"

        return False, ""

    @staticmethod
    def check_volume_burst(candles: List[Dict]) -> bool:
        """
        Hareketsiz coinleri eler:
        1. Son kapanan mumun hacmi (candles[-2]) ortalamanın üzerindeyse VEYA
        2. Canlı mumun (candles[-1]) projeksiyon hacmi ortalamayı aşıyorsa VEYA
        3. Canlı mum henüz bitmeden ortalama hacmin %75'ine ulaştıysa (Ani balina hacmi).
        """
        if len(candles) < 15:
            return False

        # Son kapanan 10 mumun ortalama hacmi
        prior_vols = [c["volume"] for c in candles[-12:-2]]
        avg_vol = sum(prior_vols) / len(prior_vols) if prior_vols else 1.0

        # Kriter 1: Son tamamlanan mum sağlıklı hacimli mi kapattı? (Dengeli Eşik: %55+)
        prev_vol = candles[-2]["volume"]
        if prev_vol >= (avg_vol * 0.55):
            return True

        # Kriter 2: Canlı mumun dakikalık projeksiyonu hacimli mi? (Dengeli Eşik: %70+)
        curr_c = candles[-1]
        curr_vol = curr_c["volume"]
        now_ms = time.time() * 1000
        candle_open_ms = curr_c.get("timestamp", now_ms)
        elapsed_sec = max(30.0, min(900.0, (now_ms - candle_open_ms) / 1000.0))
        projected_vol = curr_vol * (900.0 / elapsed_sec)

        if projected_vol >= (avg_vol * 0.70):
            return True

        # Kriter 3: Canlı mum henüz kapanmadan tek başına ortalamanın %35'ine ulaştıysa
        if curr_vol >= (avg_vol * 0.35):
            return True

        return False

    def analyze(self, symbol: str, candles_15m: List[Dict], candles_1h: Optional[List[Dict]] = None) -> Optional[Dict]:
        setup, _ = self.analyze_setup(symbol, candles_15m)
        return setup

    def analyze_setup(self, symbol: str, candles_15m: List[Dict], candles_1h: Optional[List[Dict]] = None) -> Tuple[Optional[Dict], str]:
        """
        Kurumsal SMC + Quant Confluence Scalp Analizi (15m):
        FVG, Order Block, Liquidity Sweep, TTM Squeeze, VWAP ve EMA/RSI birleşimiyle
        0-100 arası Güven Skoru üretir.
        """
        if symbol in EXCLUDED_SYMBOLS_BLACKLIST:
            return None, f"📌 {symbol} Zehirli Parite Kara Listesinde (Kronik testere/zarar geçmişi nedeniyle elendi)."

        if len(candles_15m) < 35:
            return None, "Yetersiz 15m mum verisi (en az 35 mum gerekli)"

        # 1. Hacim Patlaması & Hareket Kontrolü
        if not self.check_volume_burst(candles_15m):
            return None, "15m Hacim patlaması yetersiz (Hareketsiz / Yatay Tahta)"

        closes = [c["close"] for c in candles_15m]
        current_price = closes[-1]

        # 1b. Chop / Ölü Piyasa Filtresi (Son 4 mumun dalgalanması < MIN_4BAR_RANGE_PCT ise yatay testere)
        if len(candles_15m) >= 4:
            recent_4 = candles_15m[-4:]
            max_h = max(c["high"] for c in recent_4)
            min_l = min(c["low"] for c in recent_4)
            range_pct = ((max_h - min_l) / current_price) * 100.0 if current_price > 0 else 0.0
            if range_pct < MIN_4BAR_RANGE_PCT:
                return None, f"Yatay / Testere Piyasa (Son 1 saat dalgalanma %{range_pct:.2f} < %{MIN_4BAR_RANGE_PCT} eşiği)"

        # Temel İndikatörler
        ema20 = self.calculate_ema(closes, 20)
        ema50 = self.calculate_ema(closes, 50)
        rsi = self.calculate_rsi(closes, 14)
        atr = self.calculate_atr(candles_15m, 14)
        vwap = self.calculate_vwap(candles_15m)
        squeeze = self.calculate_ttm_squeeze(candles_15m)

        # SMC Analizleri
        fvg = self.detect_fvg(candles_15m)
        ob = self.detect_order_blocks(candles_15m)
        sweeps = self.detect_liquidity_sweep(candles_15m)

        # 🚀 KURUMSAL GELİŞMİŞ GRAFİK & TREND ANALİZLERİ (ADVANCED QUANT ENGINE)
        lr_channel = calculate_linear_regression_channel(candles_15m, period=40, num_std=2.0)
        vol_profile = calculate_volume_profile(candles_15m, lookback=48, bins=30)
        camarilla = calculate_camarilla_pivots(candles_15m, lookback_bars=24)
        rsi_clean = [r if r is not None else 50.0 for r in rsi]
        rsi_div = advanced_detect_rsi_divergence(candles_15m, rsi_clean, lookback=40, order=3)
        adx_data = calculate_adx(candles_15m, period=14)
        fib_gp = calculate_fibonacci_golden_pocket(candles_15m, lookback=45)
        sfp = detect_swing_failure_pattern(candles_15m, lookback=25)
        supertrend = calculate_supertrend(candles_15m, period=10, multiplier=3.0)
        vwap_bands = calculate_vwap_bands(candles_15m, lookback=40)

        curr_ema20 = ema20[-1]
        curr_ema50 = ema50[-1]
        curr_rsi = rsi[-1]
        curr_atr = atr[-1]
        curr_vwap = vwap[-1] if vwap else current_price

        if not (curr_ema20 and curr_ema50 and curr_rsi and curr_atr):
            return None, "15m İndikatör verisi eksik"

        # Dinamik ATR Tabanlı Stop & Hedef Hesabı (Fitil ve gürültüye ezilmeme garantisi & Otonom Kalibrasyon)
        try:
            from core.self_tuning_engine import SelfTuningEngine
            adaptive_params = SelfTuningEngine.get_current_params()
            active_min_sl = adaptive_params.get("min_scalp_sl_pct", MIN_SCALP_SL_PCT)
            active_max_sl = adaptive_params.get("max_scalp_sl_pct", MAX_SCALP_SL_PCT)
            target_min_score = adaptive_params.get("min_confluence_score", MIN_CONFLUENCE_SCORE)
        except Exception:
            active_min_sl = MIN_SCALP_SL_PCT
            active_max_sl = MAX_SCALP_SL_PCT
            target_min_score = MIN_CONFLUENCE_SCORE

        # 15m ATR x 1.3 stop mesafesi, adaptif kalibre edilmiş sınırlar arasına korunur
        min_sl_dist = current_price * (active_min_sl / 100.0)
        max_sl_dist = current_price * (active_max_sl / 100.0)
        sl_dist = max(min_sl_dist, min(max_sl_dist, curr_atr * 1.3))
        sl_pct = round((sl_dist / current_price) * 100, 2)

        # Dinamik TP: En az MIN_RR_RATIO (1:1.8) Risk/Ödül ve en az TARGET_PROFIT_PCT (%2.00)
        min_tp_dist = current_price * (TARGET_PROFIT_PCT / 100.0)
        tp_dist = max(sl_dist * MIN_RR_RATIO, min_tp_dist)
        tp_pct = round((tp_dist / current_price) * 100, 2)
        actual_rr = round(tp_pct / sl_pct, 2) if sl_pct > 0 else MIN_RR_RATIO

        # ==========================================
        # 🎯 SMC & QUANT CONFLUENCE SKORLAMA (0-100)
        # ==========================================
        long_score = 0
        short_score = 0
        long_factors = []
        short_factors = []

        # --- A. SMC Kriterleri (35 Puan) ---
        # 1. Fair Value Gap (FVG / İmbalance)
        if fvg["current_in_fvg"] == "BULLISH_TEST":
            long_score += 15
            long_factors.append("Bullish FVG Test Desteği")
        elif fvg.get("bullish_fvg"):
            age = fvg["bullish_fvg"].get("age_candles", 10)
            dist_pct = abs(current_price - fvg["bullish_fvg"]["top"]) / current_price * 100.0
            if age <= 3:
                long_score += 15
                long_factors.append(f"Taze Bullish FVG Oluşumu ({age}. mum)")
            elif dist_pct <= 1.20:
                long_score += 10
                long_factors.append("Bullish FVG Yakınlığı")

        if fvg["current_in_fvg"] == "BEARISH_TEST":
            short_score += 15
            short_factors.append("Bearish FVG Test Direnci")
        elif fvg.get("bearish_fvg"):
            age = fvg["bearish_fvg"].get("age_candles", 10)
            dist_pct = abs(current_price - fvg["bearish_fvg"]["bottom"]) / current_price * 100.0
            if age <= 3:
                short_score += 15
                short_factors.append(f"Taze Bearish FVG Oluşumu ({age}. mum)")
            elif dist_pct <= 1.20:
                short_score += 10
                short_factors.append("Bearish FVG Yakınlığı")

        # 2. Kurumsal Order Block (OB)
        if ob["current_at_ob"] == "BULLISH_OB_RETEST":
            long_score += 12
            long_factors.append("Kurumsal Order Block Retest (Alıcı)")
        elif ob.get("bullish_ob"):
            dist_ob = abs(current_price - ob["bullish_ob"]["high"]) / current_price * 100.0
            if dist_ob <= 1.50:
                long_score += 8
                long_factors.append("Kurumsal Order Block Yakınlığı")

        if ob["current_at_ob"] == "BEARISH_OB_RETEST":
            short_score += 12
            short_factors.append("Kurumsal Order Block Retest (Satıcı)")
        elif ob.get("bearish_ob"):
            dist_ob = abs(current_price - ob["bearish_ob"]["low"]) / current_price * 100.0
            if dist_ob <= 1.50:
                short_score += 8
                short_factors.append("Kurumsal Order Block Yakınlığı")

        if sweeps["bullish_sweep"]:
            long_score += 8
            long_factors.append("Dip Likidite Avı (Stop Sweep)")
        if sweeps["bearish_sweep"]:
            short_score += 8
            short_factors.append("Tepe Likidite Avı (Stop Sweep)")

        # --- B. TTM Squeeze & Kırılım (25 Puan) ---
        if squeeze["squeeze_fired"] and squeeze["momentum"] > 0:
            long_score += 25
            long_factors.append("TTM Squeeze Patlaması (Boğa)")
        elif squeeze["squeeze_fired"] and squeeze["momentum"] < 0:
            short_score += 25
            short_factors.append("TTM Squeeze Patlaması (Ayı)")
        elif squeeze["momentum"] > 0.5:
            long_score += 15
            long_factors.append("Volatilite İvmesi")
        elif squeeze["momentum"] < -0.5:
            short_score += 15
            short_factors.append("Volatilite Baskısı")

        # --- C. Hacim & VWAP Uyumu (20 Puan) ---
        if current_price > curr_vwap:
            long_score += 12
            long_factors.append("VWAP Üzeri (Kurumsal Alıcı)")
        else:
            short_score += 12
            short_factors.append("VWAP Altı (Kurumsal Satıcı)")

        # Hacim patlama bonusu (Son tamamlanan muma göre gürültüsüz ölçüm)
        prior_vols = [c["volume"] for c in candles_15m[-12:-2]]
        avg_v = sum(prior_vols) / len(prior_vols) if prior_vols else 1.0
        if len(candles_15m) >= 2 and (candles_15m[-2]["volume"] >= (avg_v * 0.85) or candles_15m[-1]["volume"] >= (avg_v * 1.10)):
            long_score += 8
            short_score += 8
            long_factors.append("Sağlıklı Hacim İvmesi")
            short_factors.append("Sağlıklı Hacim İvmesi")

        # --- C2. VWAP Standart Sapma Bantları & Kurumsal Mean-Reversion (15 Puan) ---
        if vwap_bands.get("is_mean_reversion_long"):
            long_score += 15
            long_factors.append(f"🌊 VWAP Mean-Reversion Taban Sekmesi (Z: {vwap_bands['z_score']})")
        elif vwap_bands.get("is_mean_reversion_short"):
            short_score += 15
            short_factors.append(f"🌊 VWAP Mean-Reversion Tavan Reddi (Z: {vwap_bands['z_score']})")

        # --- D. Trend & RSI Momentumu (20 Puan) ---
        # Trend & EMA Momentumu (15m)
        if current_price > curr_ema20:
            if curr_ema20 >= curr_ema50:
                long_score += 10
                long_factors.append("EMA 20>50 Trend")
            else:
                long_score += 7
                long_factors.append("EMA 20 Üzeri İvme (Erken Trend)")
        if current_price < curr_ema20:
            if curr_ema20 <= curr_ema50:
                short_score += 10
                short_factors.append("EMA 20<50 Trend")
            else:
                short_score += 7
                short_factors.append("EMA 20 Altı Baskı (Erken Trend)")

        # RSI Sweet Spot
        if 48 <= curr_rsi <= 68:
            long_score += 10
            long_factors.append(f"RSI İdeal İvme ({curr_rsi:.1f})")
        if 32 <= curr_rsi <= 52:
            short_score += 10
            short_factors.append(f"RSI İdeal Baskı ({curr_rsi:.1f})")

        # --- E. Trend Kanalları (Linear Regression Channels - 15 Puan) ---
        if lr_channel["is_support_test"]:
            long_score += 12
            long_factors.append(f"LR Kanal Desteği Sekmesi (%{lr_channel['position_pct']})")
        elif lr_channel["is_upper_breakout"]:
            long_score += 14
            long_factors.append("LR Kanal Üstü Güçlü Kırılım")
        elif lr_channel["trend"] == "BULLISH_CHANNEL" and lr_channel["position_pct"] < 65:
            long_score += 6
            long_factors.append("Yükselen Trend Kanalı İvmesi")

        if lr_channel["is_resistance_test"]:
            short_score += 12
            short_factors.append(f"LR Kanal Tavanı Direnci (%{lr_channel['position_pct']})")
        elif lr_channel["is_lower_breakdown"]:
            short_score += 14
            short_factors.append("LR Kanal Altı Çöküş Kırılımı")
        elif lr_channel["trend"] == "BEARISH_CHANNEL" and lr_channel["position_pct"] > 35:
            short_score += 6
            short_factors.append("Düşen Trend Kanalı Baskısı")

        # --- F. Volume Profile: POC & Value Area (15 Puan) ---
        if vol_profile.get("is_vah_breakout"):
            long_score += 12
            long_factors.append(f"Değer Alanı (VAH ${vol_profile['vah']}) Kırılımı")
        elif vol_profile.get("is_poc_retest") and current_price >= vol_profile["poc"]:
            long_score += 10
            long_factors.append(f"Volume Profile POC Desteği (${vol_profile['poc']})")
        elif vol_profile.get("is_val_support"):
            long_score += 8
            long_factors.append(f"Değer Alanı Dibi (VAL ${vol_profile['val']}) Desteği")

        if vol_profile.get("interaction") == "BELOW_VAL_BREAKDOWN":
            short_score += 12
            short_factors.append(f"Değer Alanı (VAL ${vol_profile['val']}) Altı Çöküş")
        elif vol_profile.get("is_poc_retest") and current_price <= vol_profile["poc"]:
            short_score += 10
            short_factors.append(f"Volume Profile POC Direnci (${vol_profile['poc']})")

        # --- G. Camarilla İntraday Destek & Direnç Pivotları (12 Puan) ---
        if camarilla.get("is_near_h4_breakout") or camarilla.get("is_above_h4"):
            long_score += 12
            long_factors.append(f"Camarilla H4 Boğa Kırılımı (${camarilla.get('r4_breakout', 0)})")
        elif camarilla.get("is_at_s3_support"):
            long_score += 8
            long_factors.append(f"Camarilla L3 Taban Desteği (${camarilla.get('s3_reversal', 0)})")

        if camarilla.get("is_near_s4_breakdown") or camarilla.get("is_below_s4"):
            short_score += 12
            short_factors.append(f"Camarilla L4 Ayı Kırılımı (${camarilla.get('s4_breakdown', 0)})")
        elif camarilla.get("r3_reversal") and abs(current_price - camarilla["r3_reversal"]) / current_price * 100.0 <= 0.40:
            short_score += 8
            short_factors.append(f"Camarilla H3 Tepe Direnci (${camarilla['r3_reversal']})")

        # --- H. RSI Uyumsuzluk & Diverjans (15 Puan) ---
        if rsi_div.get("bullish_divergence") == "REGULAR_BULLISH":
            long_score += 15
            long_factors.append("🚀 Düzenli Boğa Diverjansı (Dip Dönüşü)")
        elif rsi_div.get("bullish_divergence") == "HIDDEN_BULLISH":
            long_score += 12
            long_factors.append("⚡ Gizli Boğa Diverjansı (Trend Devamı)")

        if rsi_div.get("bearish_divergence") == "REGULAR_BEARISH":
            short_score += 15
            short_factors.append("🩸 Düzenli Ayı Diverjansı (Tepe Dönüşü)")
        elif rsi_div.get("bearish_divergence") == "HIDDEN_BEARISH":
            short_score += 12
            short_factors.append("⚡ Gizli Ayı Diverjansı (Ayı Devamı)")

        # --- I. Welles Wilder ADX Trend Gücü & Kararlılık (10 Puan) ---
        if adx_data.get("is_strong_trend"):
            if adx_data.get("is_bullish_dominance"):
                long_score += 10
                long_factors.append(f"ADX Güçlü Trend Onayı ({adx_data['adx']})")
            elif adx_data.get("is_bearish_dominance"):
                short_score += 10
                short_factors.append(f"ADX Güçlü Düşüş Trendi ({adx_data['adx']})")

        # --- J. Fibonacci Altın Cep (Golden Pocket 0.618-0.665) & OTE (12 Puan) ---
        if fib_gp.get("is_in_golden_pocket"):
            if fib_gp.get("impulse") == "BULLISH_IMPULSE":
                long_score += 12
                long_factors.append(f"🎯 Fibonacci Altın Cep (0.618-0.665) Alım Bölgesi (${fib_gp['fib_618']})")
            elif fib_gp.get("impulse") == "BEARISH_IMPULSE":
                short_score += 12
                short_factors.append(f"🎯 Fibonacci Altın Cep (0.618-0.665) Satış Bölgesi (${fib_gp['fib_618']})")
        elif fib_gp.get("is_in_ote"):
            if fib_gp.get("impulse") == "BULLISH_IMPULSE":
                long_score += 8
                long_factors.append("📐 Fibonacci OTE (Optimal Trade Entry) Destek Bölgesi")
            elif fib_gp.get("impulse") == "BEARISH_IMPULSE":
                short_score += 8
                short_factors.append("📐 Fibonacci OTE Ayı Tepki Direnç Bölgesi")

        # --- K. Swing Failure Pattern (SFP) & SuperTrend Doğrulaması (15 Puan) ---
        if sfp.get("bullish_sfp"):
            long_score += 15
            long_factors.append(f"🔥 Boğa Likidite Süpürme (SFP Dip Avı: ${sfp.get('sweep_level')})")
        if sfp.get("bearish_sfp"):
            short_score += 15
            short_factors.append(f"🔥 Ayı Likidite Süpürme (SFP Tepe Avı: ${sfp.get('sweep_level')})")

        if supertrend.get("is_bullish"):
            long_score += 8
            long_factors.append(f"🛡️ SuperTrend Boğa Rejimi (${supertrend.get('supertrend')})")
        elif supertrend.get("is_bearish"):
            short_score += 8
            short_factors.append(f"🛡️ SuperTrend Ayı Rejimi (${supertrend.get('supertrend')})")

        # --- 0. 1 SAATLİK MAKRO TREND KALKANI (1h Macro Confluence Shield) ---
        # 1 saatlik grafikte derin çöküş (%2.5'ten fazla fark) varsa LONG engellenir;
        # normal toparlanma ve konsolidasyon aşamasında ise kaliteli kurulumlar onaylanır
        if candles_1h and len(candles_1h) >= 20:
            closes_1h = [c["close"] for c in candles_1h]
            ema20_1h = self.calculate_ema(closes_1h, 20)[-1]
            last_1h = closes_1h[-1]
            if ema20_1h is not None and ema20_1h > 0:
                macro_diff_pct = ((last_1h - ema20_1h) / ema20_1h) * 100.0
                if long_score >= target_min_score and macro_diff_pct < -2.5:
                    return None, (
                        f"📌 <strong>Mevcut Durum:</strong> 1 Saatlik Makro Çöküş Trendi (Fiyat %{abs(macro_diff_pct):.1f} EMA20 altında).<br>"
                        f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Üst zaman diliminde derin düşüş varken LONG açmak testere tuzağına çeker.<br>"
                        f"🎯 <strong>Beklenen Şart:</strong> Fiyatın toparlanarak 1h EMA20 (%{abs(macro_diff_pct):.1f}) yaklaşması."
                    )
                if short_score >= target_min_score and macro_diff_pct > 2.5:
                    return None, (
                        f"📌 <strong>Mevcut Durum:</strong> 1 Saatlik Makro Ralli Trendi (Fiyat %{macro_diff_pct:.1f} EMA20 üzerinde).<br>"
                        f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Üst zaman diliminde güçlü ralli varken SHORT açmak ralliye karşı durmaktır.<br>"
                        f"🎯 <strong>Beklenen Şart:</strong> Rallinin soğuması."
                    )

        # --- SMC PREMIUM / DISCOUNT & DALGA ANALİZİ (Son 20 Mum) ---
        lookback_candles = candles_15m[-20:] if len(candles_15m) >= 20 else candles_15m
        swing_high = max(c["high"] for c in lookback_candles)
        swing_low = min(c["low"] for c in lookback_candles)
        swing_range = swing_high - swing_low
        zone_pct = round(((current_price - swing_low) / swing_range * 100.0), 1) if swing_range > 0 else 50.0

        # VWAP Aşırı Uzaklaşma Oranı
        vwap_dist_pct = round(((current_price - curr_vwap) / curr_vwap * 100.0), 2) if curr_vwap > 0 else 0.0

        # Short Asimetrisi Kalkanı: Tarihsel kayıpların %100'ü short kaynaklı olduğundan SHORT için baraj 84'tür
        short_min_score = max(target_min_score, MIN_CONFLUENCE_SCORE_SHORT)

        # --- EŞİK DEĞERLERİ & İŞLEM KARARI (Otonom Kalibre Edilmiş Baraj: target_min_score) ---
        # LONG KONTROLÜ
        if long_score >= target_min_score and long_score > short_score:
            # 0. KURUMSAL SMC YAPISAL TEYİT KONTROLÜ (Mandatory SMC Confirmation Gate)
            # Yalnızca indikatör toplamı yetmez; fiyatta somut kurumsal Smart Money yapısı şarttır:
            has_smc_confirmation_long = (
                fvg.get("current_in_fvg") == "BULLISH_TEST" or
                (fvg.get("bullish_fvg") and fvg["bullish_fvg"].get("age_candles", 10) <= 3) or
                ob.get("current_at_ob") == "BULLISH_OB_RETEST" or
                (ob.get("bullish_ob") and abs(current_price - ob["bullish_ob"]["high"]) / current_price * 100.0 <= 1.50) or
                sweeps.get("bullish_sweep") or
                sfp.get("bullish_sfp") or
                (fib_gp.get("is_in_golden_pocket") and fib_gp.get("impulse") == "BULLISH_IMPULSE")
            )
            if not has_smc_confirmation_long:
                return None, (
                    f"📌 <strong>Mevcut Durum:</strong> İndikatör Skoru {long_score}/100 ancak SMC Yapısal Teyidi Yok.<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Kurumsal Bullish FVG testi, Order Block retesti, Likidite Avı (Sweep/SFP) veya Altın Cep bulunmuyor.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Fiyatın kurumsal destek veya FVG/OB bölgesini test etmesi."
                )

            # 1. SMC Discount Kalkanı: Aşırı Şişkinlik / Tepe Alımını Engelle
            # Sadece aşırı tepe bölgesinde (%88 üzeri) ve taze FVG/OB desteği veya Squeeze kırılımı YOKSA engellenir!
            has_fresh_support = (
                fvg.get("current_in_fvg") == "BULLISH_TEST" or
                ob.get("current_at_ob") == "BULLISH_OB_RETEST" or
                (fvg.get("bullish_fvg") and fvg["bullish_fvg"].get("age_candles", 10) <= 3) or
                (squeeze.get("squeeze_fired") and squeeze.get("momentum") > 0)
            )
            if SMC_PREMIUM_DISCOUNT_FILTER and zone_pct > 88.0 and not has_fresh_support:
                return None, (
                    f"📌 <strong>Mevcut Durum:</strong> Fiyat Aşırı Primli Bölgede (%{zone_pct:.1f} / Denge: %50.0).<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Yükseliş dalgasının aşırı tepesinde alım (long) açmak kurumsal kar realizasyonu tuzağına çeker.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Fiyatın konsolide olup desteğe gevşemesi."
                )

            # 2. VWAP Aşırı Uzaklaşma (Lastik Bandı Kalkanı)
            if curr_vwap > 0 and vwap_dist_pct > MAX_VWAP_DISTANCE_PCT:
                return None, (
                    f"📌 <strong>Mevcut Durum:</strong> Fiyat VWAP'ın +%{vwap_dist_pct:.2f} Üzerinde Aşırı Uzamış.<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Ortalamadan aşırı sapan fiyatlarda elastik kar satışı (mean-reversion) riski çok yüksektir.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Fiyatın VWAP/EMA20 desteğine geri çekilip güç toplaması."
                )

            # 3. RSI Uyumsuzluk Kalkanı (Bearish Divergence / Tepe Alımı Koruması)
            has_bear_div, div_desc = self.detect_rsi_divergence(candles_15m, rsi, "LONG")
            if has_bear_div:
                return None, (
                    f"📌 <strong>Mevcut Durum:</strong> {div_desc}.<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Fiyat yeni tepe yaparken RSI'ın zayıflaması tepe alımı ve kâr satışı düzeltmesi riskini gösterir.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Negatif uyumsuzluğun kâr satışı ile dengelenip desteğin test edilmesi."
                )

            # RSI Sınır Kontrolü (Tepeden Alımı Kesinlikle Engelle)
            if curr_rsi > MAX_RSI_LONG:
                return None, (
                    f"📌 <strong>Mevcut Durum:</strong> RSI={curr_rsi:.1f} (Aşırı Alım Şişkinliği).<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> RSI {MAX_RSI_LONG} tavanını aştığı için tepeden alım riski oluştu. Ani geri çekilme stop patlatabilir.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> RSI seviyesinin 48 - 65 aralığına soğuması."
                )
            if curr_rsi < MIN_RSI_LONG:
                return None, (
                    f"📌 <strong>Mevcut Durum:</strong> RSI={curr_rsi:.1f} (Zayıf Boğa Momentumu).<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Alım baskısı yetersiz kaldığı için 10x/20x kaldıraçta sahte kırılım riski mevcut.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> RSI'ın {MIN_RSI_LONG}+ üzerine çıkıp alıcıların güçlenmesi."
                )

            # 20x Sniper Tetikleyici: Skor 85+ (Kusursuz SMC Onayı) ve Dar Stop (%1.20 altı)
            is_sniper_20x = (long_score >= 85 and sl_pct <= MAX_SL_PCT_20X)
            leverage = 20 if is_sniper_20x else 10
            grade = "Grade A+ (20x Sniper)" if is_sniper_20x else "Grade A"
            setup_type = f"15m {leverage}x SMC SNIPER" if is_sniper_20x else f"15m {leverage}x SMC SCALP"

            # 🛡️ Yapısal Destek Tabanlı Akıllı Stop İyileştirmesi (Fitil Avı Koruması)
            structural_supports = []
            if sfp.get("bullish_sfp") and sfp.get("invalidation_level"):
                structural_supports.append(sfp["invalidation_level"] * 0.999)
            if fib_gp.get("fib_786", 0) > 0:
                structural_supports.append(fib_gp["fib_786"] * 0.998)
            if supertrend.get("is_bullish") and supertrend.get("supertrend", 0) > 0:
                structural_supports.append(supertrend["supertrend"] * 0.998)
            if lr_channel.get("lower", 0) > 0:
                structural_supports.append(lr_channel["lower"] * 0.998)
            if vol_profile.get("val", 0) > 0:
                structural_supports.append(vol_profile["val"] * 0.998)
            if camarilla.get("s3_reversal", 0) > 0:
                structural_supports.append(camarilla["s3_reversal"] * 0.998)
                
            valid_supports = [s for s in structural_supports if (min_sl_dist <= (current_price - s) <= max_sl_dist)]
            if valid_supports:
                best_support = max(valid_supports) # En yakın korunaklı kurumsal destek
                sl_dist = current_price - best_support
                sl_pct = round((sl_dist / current_price) * 100, 2)

            stop_loss = round(current_price - sl_dist, 6)
            tp1 = round(current_price + tp_dist, 6)
            tp2 = round(current_price + (tp_dist * 1.6), 6)

            # 🪜 2 Kademeli Giriş Merdiveni (FVG/OB Equilibrium DCA)
            entry_limit_2 = 0.0
            if fvg.get("bullish_fvg"):
                f_eq = (fvg["bullish_fvg"]["top"] + fvg["bullish_fvg"]["bottom"]) / 2.0
                if stop_loss < f_eq < current_price:
                    entry_limit_2 = round(f_eq, 6)
            elif ob.get("bullish_ob"):
                o_eq = (ob["bullish_ob"]["high"] + ob["bullish_ob"]["low"]) / 2.0
                if stop_loss < o_eq < current_price:
                    entry_limit_2 = round(o_eq, 6)
            if entry_limit_2 <= 0:
                entry_limit_2 = round(current_price - (sl_dist * 0.35), 6)

            factors_str = ", ".join(long_factors[:5])
            setup = {
                "symbol": symbol,
                "direction": "LONG",
                "leverage": leverage,
                "risk_grade": grade,
                "confluence_score": min(long_score, 100),
                "setup_type": setup_type,
                "current_price": current_price,
                "entry_min": round(current_price * 0.9995, 6),
                "entry_max": round(current_price * 1.0005, 6),
                "actual_entry_price": current_price,
                "entry_limit_2": entry_limit_2,
                "stop_loss": stop_loss,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "risk_reward": actual_rr,
                "sl_pct": sl_pct,
                "tp1_pct": tp_pct,
                "tp2_pct": round(tp_pct * 1.6, 2),
                "ta_reasons": (
                    f"[{setup_type} | Skor: {min(long_score, 100)}/100] {factors_str}. "
                    f"RSI={curr_rsi:.1f}, VWAP={curr_vwap:.4f}, LR-Kanal={lr_channel.get('trend', 'FLAT')} (%{lr_channel.get('position_pct', 50)}), POC=${vol_profile.get('poc', 0)}. Hedef1: +%{tp_pct}, Runner TP2: +%{round(tp_pct*1.6, 2)} ({leverage}x)."
                ),
                "indicators": {
                    "ema20": ema20,
                    "ema50": ema50,
                    "rsi": rsi,
                    "vwap": vwap,
                    "lr_channel": lr_channel,
                    "volume_profile": vol_profile,
                    "camarilla": camarilla,
                    "rsi_divergence": rsi_div,
                    "adx_data": adx_data,
                    "fib_golden_pocket": fib_gp,
                    "sfp": sfp,
                    "supertrend": supertrend
                },
                "smc_data": {
                    "fvg": fvg,
                    "ob": ob,
                    "sweeps": sweeps,
                    "squeeze": squeeze
                }
            }
            return setup, f"SMC LONG Onayı ({min(long_score, 100)}/100 Puan) | {factors_str}"

        # SHORT KONTROLÜ (Short Asimetrisi Kalkanı: Baraj 84)
        elif short_score >= short_min_score and short_score > long_score:
            # 0. KURUMSAL SMC YAPISAL TEYİT KONTROLÜ (Mandatory SMC Confirmation Gate)
            has_smc_confirmation_short = (
                fvg.get("current_in_fvg") == "BEARISH_TEST" or
                (fvg.get("bearish_fvg") and fvg["bearish_fvg"].get("age_candles", 10) <= 3) or
                ob.get("current_at_ob") == "BEARISH_OB_RETEST" or
                (ob.get("bearish_ob") and abs(current_price - ob["bearish_ob"]["low"]) / current_price * 100.0 <= 1.50) or
                sweeps.get("bearish_sweep") or
                sfp.get("bearish_sfp") or
                (fib_gp.get("is_in_golden_pocket") and fib_gp.get("impulse") == "BEARISH_IMPULSE")
            )
            if not has_smc_confirmation_short:
                return None, (
                    f"📌 <strong>Mevcut Durum:</strong> İndikatör Skoru {short_score}/100 ancak SMC Yapısal Teyidi Yok.<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Kurumsal Bearish FVG testi, Order Block retesti, Likidite Avı (Sweep/SFP) veya Altın Cep bulunmuyor.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Fiyatın kurumsal direnç veya Bearish FVG/OB bölgesini test etmesi."
                )

            # 0b. FREQTRADE SIDE-SPECIFIC STOPLOSS GUARD (SHORT KİLİDİ)
            try:
                from core.database import check_side_stoploss_guard
                from config import SIDE_STOPLOSS_GUARD_ENABLED, SIDE_STOPLOSS_MAX_CONSECUTIVE_LOSSES, SIDE_STOPLOSS_COOLDOWN_MINUTES
                if SIDE_STOPLOSS_GUARD_ENABLED:
                    is_locked, lock_desc = check_side_stoploss_guard("SHORT", SIDE_STOPLOSS_MAX_CONSECUTIVE_LOSSES, SIDE_STOPLOSS_COOLDOWN_MINUTES)
                    if is_locked:
                        return None, f"📌 {lock_desc}"
            except Exception:
                pass

            # 1. SMC Premium Kalkanı: Aşırı Dipte Satışı Engelle
            has_fresh_resistance = (
                fvg.get("current_in_fvg") == "BEARISH_TEST" or
                ob.get("current_at_ob") == "BEARISH_OB_RETEST" or
                (fvg.get("bearish_fvg") and fvg["bearish_fvg"].get("age_candles", 10) <= 3) or
                (squeeze.get("squeeze_fired") and squeeze.get("momentum") < 0)
            )
            if SMC_PREMIUM_DISCOUNT_FILTER and zone_pct < 12.0 and not has_fresh_resistance:
                return None, (
                    f"📌 <strong>Mevcut Durum:</strong> Fiyat Aşırı Dip Bölgede (%{zone_pct:.1f} / Denge: %50.0).<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Düşüş dalgasının aşırı dibinde satış (short) açmak kurumsal dip alımı tuzağına çeker.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Fiyatın tepki verip dirence yükselmesi."
                )

            # 2. VWAP Aşırı Uzaklaşma (Lastik Bandı Kalkanı)
            if curr_vwap > 0 and vwap_dist_pct < -MAX_VWAP_DISTANCE_PCT:
                return None, (
                    f"📌 <strong>Mevcut Durum:</strong> Fiyat VWAP'ın %{abs(vwap_dist_pct):.2f} Altında Aşırı Uzamış.<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Ortalamadan aşırı sapan fiyatta elastik tepki sıçraması (V-dip) riski %75+ üzerindedir.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Fiyatın yukarı tepki verip VWAP veya direnç seviyesinden dönüş teyidi vermesi."
                )

            # 3. RSI Uyumsuzluk Kalkanı (Bullish Divergence / V-Dip Koruması)
            has_bull_div, div_desc = self.detect_rsi_divergence(candles_15m, rsi, "SHORT")
            if has_bull_div:
                return None, (
                    f"📌 <strong>Mevcut Durum:</strong> {div_desc}.<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Fiyat yeni dip yaparken RSI'ın güçlenmesi akıllı para birikimini ve V-dip tepki sıçramasını işaret eder.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Pozitif uyumsuzluğun sonlanıp satış baskısının RSI ile teyit edilmesi."
                )

            # RSI Sınır Kontrolü (Dipten Satışı Kesinlikle Engelle)
            if curr_rsi < MIN_RSI_SHORT:
                return None, (
                    f"📌 <strong>Mevcut Durum:</strong> RSI={curr_rsi:.1f} (Aşırı Satış Dibi).<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> RSI {MIN_RSI_SHORT} tabanına indiği için dipten satış riski var. Ani tepki sıçraması stop patlatabilir.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Fiyatın yukarı tepki verip dirençten dönüş göstermesi."
                )
            if curr_rsi > MAX_RSI_SHORT:
                return None, (
                    f"📌 <strong>Mevcut Durum:</strong> RSI={curr_rsi:.1f} (Güçlü Boğa Baskısı).<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Piyasa yukarı yönlü güçlü olduğu için trende karşı SHORT açmak yüksek risklidir.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Boğa momentumunun zayıflayıp 55 altına inmesi."
                )

            # 20x Sniper Tetikleyici: Skor 85+ (Kusursuz SMC Onayı) ve Dar Stop (%1.20 altı)
            is_sniper_20x = (short_score >= 85 and sl_pct <= MAX_SL_PCT_20X)
            leverage = 20 if is_sniper_20x else 10
            grade = "Grade A+ (20x Sniper)" if is_sniper_20x else "Grade A"
            setup_type = f"15m {leverage}x SMC SNIPER" if is_sniper_20x else f"15m {leverage}x SMC SCALP"

            # 🛡️ Yapısal Direnç Tabanlı Akıllı Stop İyileştirmesi (Fitil Avı Koruması)
            structural_resistances = []
            if sfp.get("bearish_sfp") and sfp.get("invalidation_level"):
                structural_resistances.append(sfp["invalidation_level"] * 1.001)
            if fib_gp.get("fib_786", 0) > 0:
                structural_resistances.append(fib_gp["fib_786"] * 1.002)
            if supertrend.get("is_bearish") and supertrend.get("supertrend", 0) > 0:
                structural_resistances.append(supertrend["supertrend"] * 1.002)
            if lr_channel.get("upper", 0) > 0:
                structural_resistances.append(lr_channel["upper"] * 1.002)
            if vol_profile.get("vah", 0) > 0:
                structural_resistances.append(vol_profile["vah"] * 1.002)
            if camarilla.get("r3_reversal", 0) > 0:
                structural_resistances.append(camarilla["r3_reversal"] * 1.002)
                
            valid_res = [r for r in structural_resistances if (min_sl_dist <= (r - current_price) <= max_sl_dist)]
            if valid_res:
                best_res = min(valid_res) # En yakın korunaklı kurumsal direnç
                sl_dist = best_res - current_price
                sl_pct = round((sl_dist / current_price) * 100, 2)

            stop_loss = round(current_price + sl_dist, 6)
            tp1 = round(current_price - tp_dist, 6)
            tp2 = round(current_price - (tp_dist * 1.6), 6)

            # 🪜 2 Kademeli Giriş Merdiveni (FVG/OB Equilibrium DCA)
            entry_limit_2 = 0.0
            if fvg.get("bearish_fvg"):
                f_eq = (fvg["bearish_fvg"]["top"] + fvg["bearish_fvg"]["bottom"]) / 2.0
                if current_price < f_eq < stop_loss:
                    entry_limit_2 = round(f_eq, 6)
            elif ob.get("bearish_ob"):
                o_eq = (ob["bearish_ob"]["high"] + ob["bearish_ob"]["low"]) / 2.0
                if current_price < o_eq < stop_loss:
                    entry_limit_2 = round(o_eq, 6)
            if entry_limit_2 <= 0:
                entry_limit_2 = round(current_price + (sl_dist * 0.35), 6)

            factors_str = ", ".join(short_factors[:5])
            setup = {
                "symbol": symbol,
                "direction": "SHORT",
                "leverage": leverage,
                "risk_grade": grade,
                "confluence_score": min(short_score, 100),
                "setup_type": setup_type,
                "current_price": current_price,
                "entry_min": round(current_price * 0.9995, 6),
                "entry_max": round(current_price * 1.0005, 6),
                "actual_entry_price": current_price,
                "entry_limit_2": entry_limit_2,
                "stop_loss": stop_loss,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "risk_reward": actual_rr,
                "sl_pct": sl_pct,
                "tp1_pct": tp_pct,
                "tp2_pct": round(tp_pct * 1.6, 2),
                "ta_reasons": (
                    f"[{setup_type} | Skor: {min(short_score, 100)}/100] {factors_str}. "
                    f"RSI={curr_rsi:.1f}, VWAP={curr_vwap:.4f}, LR-Kanal={lr_channel.get('trend', 'FLAT')} (%{lr_channel.get('position_pct', 50)}), POC=${vol_profile.get('poc', 0)}. Hedef1: %{tp_pct}, Runner TP2: %{round(tp_pct*1.6, 2)} ({leverage}x)."
                ),
                "indicators": {
                    "ema20": ema20,
                    "ema50": ema50,
                    "rsi": rsi,
                    "vwap": vwap,
                    "lr_channel": lr_channel,
                    "volume_profile": vol_profile,
                    "camarilla": camarilla,
                    "rsi_divergence": rsi_div,
                    "adx_data": adx_data,
                    "fib_golden_pocket": fib_gp,
                    "sfp": sfp,
                    "supertrend": supertrend
                },
                "smc_data": {
                    "fvg": fvg,
                    "ob": ob,
                    "sweeps": sweeps,
                    "squeeze": squeeze
                }
            }
            return setup, f"SMC SHORT Onayı ({min(short_score, 100)}/100 Puan) | {factors_str}"

        # REDDEDİLME GEREKÇESİ (Detaylı Kurumsal Açıklama)
        if short_score > long_score and short_score >= target_min_score and short_score < short_min_score:
            return None, (
                f"📌 <strong>Mevcut Durum:</strong> SHORT SMC skoru {short_score}/100 (Genel Baraj: {target_min_score}, Short Barajı: {short_min_score}).<br>"
                f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Short Asimetrisi Kalkanı: Tarihsel kayıpların %100'ü short kaynaklı olduğundan SHORT için en az {short_min_score} puan aranır.<br>"
                f"🎯 <strong>Beklenen Şart:</strong> Ek FVG kırılımı veya Order Block teyidi ile skorun {short_min_score}+ üzerine çıkması."
            )

        max_score = max(long_score, short_score)
        direction_hint = "LONG" if long_score >= short_score else "SHORT"
        dominant_factors = long_factors if long_score >= short_score else short_factors
        factor_desc = ", ".join(dominant_factors[:2]) if dominant_factors else "Formasyon / FVG onayı yok"
        
        return None, (
            f"📌 <strong>Mevcut Durum:</strong> {direction_hint} eğilimli SMC skoru {max_score}/100 seviyesinde kaldı (Güvenli Baraj: {target_min_score}).<br>"
            f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> {factor_desc}; 10x/20x kaldıraçta sahte fitil ve stop olma riski yüksek.<br>"
            f"🎯 <strong>Beklenen Şart:</strong> Net Likidite Temizliği (Sweep) veya FVG Kırılımı ile skorun {target_min_score}+ üzerine çıkması."
        )
