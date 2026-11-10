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

        # Kriter 1: Son tamamlanan mum hacimli mi kapattı?
        prev_vol = candles[-2]["volume"]
        if prev_vol >= (avg_vol * 1.05):
            return True

        # Kriter 2: Canlı mumun dakikalık projeksiyonu patlama gösteriyor mu?
        curr_c = candles[-1]
        curr_vol = curr_c["volume"]
        now_ms = time.time() * 1000
        candle_open_ms = curr_c.get("timestamp", now_ms)
        elapsed_sec = max(30.0, min(900.0, (now_ms - candle_open_ms) / 1000.0))
        projected_vol = curr_vol * (900.0 / elapsed_sec)

        if projected_vol >= (avg_vol * 1.15):
            return True

        # Kriter 3: Canlı mum henüz kapanmadan tek başına ortalamanın %75'ini aştıysa
        if curr_vol >= (avg_vol * 0.75):
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
        # 1. Fair Value Gap (FVG / İmbalance): Sadece aktif retest veya çok yakın (<%0.35) ise puan ver
        if fvg["current_in_fvg"] == "BULLISH_TEST":
            long_score += 15
            long_factors.append("Bullish FVG Test Desteği")
        elif fvg["bullish_fvg"] and abs(current_price - fvg["bullish_fvg"]["top"]) / current_price <= 0.0035:
            long_score += 8
            long_factors.append("Bullish FVG Yakınlığı")

        if fvg["current_in_fvg"] == "BEARISH_TEST":
            short_score += 15
            short_factors.append("Bearish FVG Test Direnci")
        elif fvg["bearish_fvg"] and abs(current_price - fvg["bearish_fvg"]["bottom"]) / current_price <= 0.0035:
            short_score += 8
            short_factors.append("Bearish FVG Yakınlığı")

        # 2. Kurumsal Order Block (OB): Sadece aktif retest veya çok yakın (<%0.35) ise puan ver
        if ob["current_at_ob"] == "BULLISH_OB_RETEST":
            long_score += 12
            long_factors.append("Kurumsal Order Block Retest (Alıcı)")
        elif ob["bullish_ob"] and abs(current_price - ob["bullish_ob"]["high"]) / current_price <= 0.0035:
            long_score += 6
            long_factors.append("Kurumsal Order Block Yakınlığı")

        if ob["current_at_ob"] == "BEARISH_OB_RETEST":
            short_score += 12
            short_factors.append("Kurumsal Order Block Retest (Satıcı)")
        elif ob["bearish_ob"] and abs(current_price - ob["bearish_ob"]["low"]) / current_price <= 0.0035:
            short_score += 6
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

        # Hacim patlama bonusu
        recent_vol = candles_15m[-1]["volume"]
        avg_v = sum(c["volume"] for c in candles_15m[-11:-1]) / 10
        if recent_vol > (avg_v * 1.3):
            long_score += 8
            short_score += 8
            long_factors.append("Hacim Patlaması (>1.3x)")
            short_factors.append("Hacim Patlaması (>1.3x)")

        # --- D. Trend & RSI Momentumu (20 Puan) ---
        # Long Trend
        if current_price > curr_ema20 and curr_ema20 >= curr_ema50:
            long_score += 10
            long_factors.append("EMA 20>50 Trend")
        # Short Trend
        if current_price < curr_ema20 and curr_ema20 <= curr_ema50:
            short_score += 10
            short_factors.append("EMA 20<50 Trend")

        # RSI Sweet Spot
        if 48 <= curr_rsi <= 68:
            long_score += 10
            long_factors.append(f"RSI İdeal İvme ({curr_rsi:.1f})")
        if 32 <= curr_rsi <= 52:
            short_score += 10
            short_factors.append(f"RSI İdeal Baskı ({curr_rsi:.1f})")

        # --- 0. 1 SAATLİK MAKRO TREND KALKANI (1h Macro Confluence Shield) ---
        # Üst zaman diliminin ana yönüne karşı ters işlem açılması kesinlikle yasaklanır
        if candles_1h and len(candles_1h) >= 20:
            closes_1h = [c["close"] for c in candles_1h]
            ema20_1h = self.calculate_ema(closes_1h, 20)[-1]
            last_1h = closes_1h[-1]
            if ema20_1h is not None:
                if long_score >= target_min_score and last_1h < ema20_1h:
                    return None, (
                        f"📌 <strong>Mevcut Durum:</strong> 1 Saatlik Makro Trend Satıcılı (Fiyat {last_1h} < 1h EMA20 {ema20_1h:.4f}).<br>"
                        f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Üst zaman diliminde (1h) düşüş trendi varken 15m'de LONG açmak testere tuzağına çeker.<br>"
                        f"🎯 <strong>Beklenen Şart:</strong> 1 Saatlik mumun EMA20 üzerine çıkarak makro boğa teyidi vermesi."
                    )
                if short_score >= target_min_score and last_1h > ema20_1h:
                    return None, (
                        f"📌 <strong>Mevcut Durum:</strong> 1 Saatlik Makro Trend Alıcılı (Fiyat {last_1h} > 1h EMA20 {ema20_1h:.4f}).<br>"
                        f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Üst zaman diliminde (1h) yükseliş trendi varken 15m'de SHORT açmak ralliye karşı durmaktır.<br>"
                        f"🎯 <strong>Beklenen Şart:</strong> 1 Saatlik mumun EMA20 altına inerek makro ayı teyidi vermesi."
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
            # 1. SMC Discount Kalkanı: Tepeden Alımı Kesinlikle Engelle
            # Fiyat dalganın üst %55'inde (Primli/Premium bölgede) ise ve aktif FVG/OB desteği test edilmiyorsa elenir!
            if SMC_PREMIUM_DISCOUNT_FILTER and zone_pct > 55.0 and fvg["current_in_fvg"] != "BULLISH_TEST" and ob["current_at_ob"] != "BULLISH_OB_RETEST":
                return None, (
                    f"📌 <strong>Mevcut Durum:</strong> Fiyat Primli / Premium Bölgede (%{zone_pct:.1f} / Denge: %50.0).<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Yükseliş dalgasının tepesinde alım (long) açmak kurumsal kar realizasyonu tuzağına çeker.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Fiyatın İndirimli (Discount < %50) bölgeye veya Bullish FVG/OB desteğine geri çekilmesi (pullback)."
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

            stop_loss = round(current_price - sl_dist, 6)
            tp = round(current_price + tp_dist, 6)

            factors_str = ", ".join(long_factors[:4])
            setup = {
                "symbol": symbol,
                "direction": "LONG",
                "leverage": leverage,
                "risk_grade": grade,
                "confluence_score": long_score,
                "setup_type": setup_type,
                "current_price": current_price,
                "entry_min": round(current_price * 0.9995, 6),
                "entry_max": round(current_price * 1.0005, 6),
                "actual_entry_price": current_price,
                "stop_loss": stop_loss,
                "take_profit_1": tp,
                "take_profit_2": tp,
                "risk_reward": actual_rr,
                "sl_pct": sl_pct,
                "tp1_pct": tp_pct,
                "tp2_pct": tp_pct,
                "ta_reasons": (
                    f"[{setup_type} | Skor: {long_score}/100] {factors_str}. "
                    f"RSI={curr_rsi:.1f}, VWAP={curr_vwap:.4f}, Bölge=%{zone_pct:.0f} (Discount/Destek). Hedef: +%{tp_pct} ({leverage}x ile +%{round(tp_pct*leverage, 1)} kar)."
                ),
                "indicators": {
                    "ema20": ema20,
                    "ema50": ema50,
                    "rsi": rsi,
                    "vwap": vwap
                },
                "smc_data": {
                    "fvg": fvg,
                    "ob": ob,
                    "sweeps": sweeps,
                    "squeeze": squeeze
                }
            }
            return setup, f"SMC LONG Onayı ({long_score}/100 Puan) | {factors_str}"

        # SHORT KONTROLÜ (Short Asimetrisi Kalkanı: Baraj 84)
        elif short_score >= short_min_score and short_score > long_score:
            # 1. SMC Premium Kalkanı: Dipten Satışı Kesinlikle Engelle
            # Fiyat dalganın alt %45'inde (İndirimli/Discount bölgede) ise ve aktif FVG/OB direnci test edilmiyorsa elenir!
            if SMC_PREMIUM_DISCOUNT_FILTER and zone_pct < 45.0 and fvg["current_in_fvg"] != "BEARISH_TEST" and ob["current_at_ob"] != "BEARISH_OB_RETEST":
                return None, (
                    f"📌 <strong>Mevcut Durum:</strong> Fiyat İndirimli / Discount Bölgede (%{zone_pct:.1f} / Denge: %50.0).<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Düşüş dalgasının dip seviyesinde satış (short) açmak kurumsal dip avı (V-dip) tuzağına çeker.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Fiyatın Primli (Premium > %50) bölgeye veya Bearish FVG/OB direncine retest yapması."
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

            stop_loss = round(current_price + sl_dist, 6)
            tp = round(current_price - tp_dist, 6)

            factors_str = ", ".join(short_factors[:4])
            setup = {
                "symbol": symbol,
                "direction": "SHORT",
                "leverage": leverage,
                "risk_grade": grade,
                "confluence_score": short_score,
                "setup_type": setup_type,
                "current_price": current_price,
                "entry_min": round(current_price * 0.9995, 6),
                "entry_max": round(current_price * 1.0005, 6),
                "actual_entry_price": current_price,
                "stop_loss": stop_loss,
                "take_profit_1": tp,
                "take_profit_2": tp,
                "risk_reward": actual_rr,
                "sl_pct": sl_pct,
                "tp1_pct": tp_pct,
                "tp2_pct": tp_pct,
                "ta_reasons": (
                    f"[{setup_type} | Skor: {short_score}/100] {factors_str}. "
                    f"RSI={curr_rsi:.1f}, VWAP={curr_vwap:.4f}, Bölge=%{zone_pct:.0f} (Premium/Direnç). Hedef: %{tp_pct} düşüş ({leverage}x ile +%{round(tp_pct*leverage, 1)} kar)."
                ),
                "indicators": {
                    "ema20": ema20,
                    "ema50": ema50,
                    "rsi": rsi,
                    "vwap": vwap
                },
                "smc_data": {
                    "fvg": fvg,
                    "ob": ob,
                    "sweeps": sweeps,
                    "squeeze": squeeze
                }
            }
            return setup, f"SMC SHORT Onayı ({short_score}/100 Puan) | {factors_str}"

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
