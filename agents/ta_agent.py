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
    MIN_RR_RATIO,
    MAX_RSI_LONG,
    MIN_RSI_LONG,
    MIN_RSI_SHORT,
    MAX_RSI_SHORT,
    MIN_4BAR_RANGE_PCT,
    MIN_CONFLUENCE_SCORE
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

        # Dinamik TP: En az 1:1.4 Risk/Ödül ve en az TARGET_PROFIT_PCT (%1.60)
        min_tp_dist = current_price * (TARGET_PROFIT_PCT / 100.0)
        tp_dist = max(sl_dist * MIN_RR_RATIO, min_tp_dist)
        tp_pct = round((tp_dist / current_price) * 100, 2)
        actual_rr = round(tp_pct / sl_pct, 2) if sl_pct > 0 else 1.4

        # ==========================================
        # 🎯 SMC & QUANT CONFLUENCE SKORLAMA (0-100)
        # ==========================================
        long_score = 0
        short_score = 0
        long_factors = []
        short_factors = []

        # --- A. SMC Kriterleri (35 Puan) ---
        if fvg["current_in_fvg"] == "BULLISH_TEST" or (fvg["bullish_fvg"] and current_price >= fvg["bullish_fvg"]["bottom"]):
            long_score += 15
            long_factors.append("Bullish FVG Desteği")
        if fvg["current_in_fvg"] == "BEARISH_TEST" or (fvg["bearish_fvg"] and current_price <= fvg["bearish_fvg"]["top"]):
            short_score += 15
            short_factors.append("Bearish FVG Direnci")

        if ob["current_at_ob"] == "BULLISH_OB_RETEST" or ob["bullish_ob"]:
            long_score += 12
            long_factors.append("Kurumsal Order Block (Alıcı)")
        if ob["current_at_ob"] == "BEARISH_OB_RETEST" or ob["bearish_ob"]:
            short_score += 12
            short_factors.append("Kurumsal Order Block (Satıcı)")

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

        # --- EŞİK DEĞERLERİ & İŞLEM KARARI (Otonom Kalibre Edilmiş Baraj: target_min_score) ---
        # LONG KONTROLÜ
        if long_score >= target_min_score and long_score > short_score:
            # RSI Sınır Kontrolü (Tepeden Alımı Kesinlikle Engelle)
            if curr_rsi > MAX_RSI_LONG:
                return None, f"LONG Reddi: RSI aşırı şişkin ({curr_rsi:.1f} > {MAX_RSI_LONG}). Tepeden mal alma riski!"
            if curr_rsi < MIN_RSI_LONG:
                return None, f"LONG Reddi: RSI çok zayıf ({curr_rsi:.1f} < {MIN_RSI_LONG}). Yetersiz boğa momentumu!"

            leverage = 20 if (long_score >= 82 and sl_pct <= 0.85) else 10
            grade = "Grade A+" if leverage == 20 else "Grade A"
            setup_type = f"15m {leverage}x SMC SNIPER" if leverage == 20 else f"15m {leverage}x SMC SCALP"

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
                    f"RSI={curr_rsi:.1f}, VWAP={curr_vwap:.4f}. Hedef: +%{tp_pct} ({leverage}x ile +%{round(tp_pct*leverage, 1)} kar)."
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

        # SHORT KONTROLÜ
        elif short_score >= target_min_score and short_score > long_score:
            # RSI Sınır Kontrolü (Dipten Satışı Kesinlikle Engelle)
            if curr_rsi < MIN_RSI_SHORT:
                return None, f"SHORT Reddi: RSI dip seviyede ({curr_rsi:.1f} < {MIN_RSI_SHORT}). Tepki yükselişi riski!"
            if curr_rsi > MAX_RSI_SHORT:
                return None, f"SHORT Reddi: RSI çok güçlü ({curr_rsi:.1f} > {MAX_RSI_SHORT}). Boğa trendine karşı short açılmaz!"

            leverage = 20 if (short_score >= 82 and sl_pct <= 0.85) else 10
            grade = "Grade A+" if leverage == 20 else "Grade A"
            setup_type = f"15m {leverage}x SMC SNIPER" if leverage == 20 else f"15m {leverage}x SMC SCALP"

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
                    f"RSI={curr_rsi:.1f}, VWAP={curr_vwap:.4f}. Hedef: %{tp_pct} düşüş ({leverage}x ile +%{round(tp_pct*leverage, 1)} kar)."
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
        max_score = max(long_score, short_score)
        direction_hint = "LONG" if long_score >= short_score else "SHORT"
        dominant_factors = long_factors if long_score >= short_score else short_factors
        factor_desc = ", ".join(dominant_factors[:2]) if dominant_factors else "Formasyon / FVG onayı yok"
        
        return None, f"SMC Skoru Yetersiz ({max_score}/100 - Hedef: {target_min_score}) [{direction_hint} Eğilimli: {factor_desc}]"
