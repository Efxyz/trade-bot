"""
Statistical Arbitrage & Pairs Trading Agent (Market-Neutral Quantitative Engine)
Monitors co-integrated / highly correlated cryptocurrency pairs (e.g., SOL/ETH, AVAX/SOL, BTC/ETH).
Generates market-neutral spread mean-reversion signals based on rolling Z-Score deviations.
"""
import math
from typing import List, Dict, Optional, Tuple

PAIRS_UNIVERSE = [
    ("SOLUSDT", "ETHUSDT"),
    ("AVAXUSDT", "SOLUSDT"),
    ("BTCUSDT", "ETHUSDT"),
    ("DOGEUSDT", "XRPUSDT"),
    ("BNBUSDT", "ETHUSDT")
]

class StatisticalArbitrageAgent:
    def __init__(self, z_score_entry_threshold: float = 2.1, z_score_exit_threshold: float = 0.4):
        self.entry_threshold = z_score_entry_threshold
        self.exit_threshold = z_score_exit_threshold

    def calculate_pair_spread(
        self,
        candles_a: List[Dict],
        candles_b: List[Dict],
        lookback: int = 35
    ) -> Dict:
        """
        İki varlık arasındaki fiyat oranının (Price Ratio) yuvarlanan ortalamasını,
        standart sapmasını ve anlık Z-Score sapmasını hesaplar.
        """
        min_len = min(len(candles_a), len(candles_b))
        if min_len < 15:
            return {
                "is_signal": False,
                "z_score": 0.0,
                "action": "NONE",
                "ratio": 0.0,
                "mean_ratio": 0.0,
                "std_ratio": 0.0,
                "reason": "Yetersiz mum verisi"
            }

        n = min(min_len, lookback)
        sub_a = candles_a[-n:]
        sub_b = candles_b[-n:]

        ratios = []
        rets_a, rets_b = [], []
        prev_a, prev_b = None, None
        for ca, cb in zip(sub_a, sub_b):
            c_a = float(ca["close"])
            c_b = float(cb["close"])
            if c_b > 0 and c_a > 0:
                ratios.append(c_a / c_b)
                if prev_a is not None and prev_b is not None:
                    rets_a.append((c_a - prev_a) / prev_a)
                    rets_b.append((c_b - prev_b) / prev_b)
                prev_a, prev_b = c_a, c_b

        if len(ratios) < 15:
            return {"is_signal": False, "z_score": 0.0, "action": "NONE"}

        # 1. Pearson getiri korelasyonu (aynı yönde hareket etmeyen çiftlerde sahte Z-skoru engelle)
        corr = 0.0
        if len(rets_a) >= 10:
            ma = sum(rets_a) / len(rets_a)
            mb = sum(rets_b) / len(rets_b)
            cov = sum((a - ma) * (b - mb) for a, b in zip(rets_a, rets_b))
            va = math.sqrt(sum((a - ma) ** 2 for a in rets_a))
            vb = math.sqrt(sum((b - mb) ** 2 for b in rets_b))
            corr = (cov / (va * vb)) if (va > 0 and vb > 0) else 0.0

        mean_ratio = sum(ratios) / len(ratios)
        variance = sum((r - mean_ratio) ** 2 for r in ratios) / len(ratios)
        std_ratio = math.sqrt(variance) if variance > 0 else 0.0001

        # 2. AR(1) ortalamaya dönüş hızı (phi < 0.96 -> durağanlık / mean-reversion teyidi)
        devs = [r - mean_ratio for r in ratios]
        denom_ar = sum(d * d for d in devs[:-1])
        ar1_phi = (sum(devs[i] * devs[i + 1] for i in range(len(devs) - 1)) / denom_ar) if denom_ar > 0 else 1.0

        current_ratio = ratios[-1]
        z_score = (current_ratio - mean_ratio) / std_ratio

        is_signal = False
        action = "NONE"
        leg_a_direction = None
        leg_b_direction = None
        reason = ""

        # Z >= +2.1: Varlık A, B'ye göre aşırı değerlendi -> Short A / Long B (korelasyon ve durağanlık şartlı)
        if z_score >= self.entry_threshold and corr >= 0.65 and ar1_phi < 0.96:
            is_signal = True
            action = "SHORT_A_LONG_B"
            leg_a_direction = "SHORT"
            leg_b_direction = "LONG"
            reason = f"🎯 Pair Z-Score Tavanı (+{z_score:.2f} > +{self.entry_threshold} | r={corr:.2f}, φ={ar1_phi:.2f}). A SHORT / B LONG (Piyasa Nötr)."

        # Z <= -2.1: Varlık A, B'ye göre aşırı ucuzladı -> Long A / Short B
        elif z_score <= -self.entry_threshold and corr >= 0.65 and ar1_phi < 0.96:
            is_signal = True
            action = "LONG_A_SHORT_B"
            leg_a_direction = "LONG"
            leg_b_direction = "SHORT"
            reason = f"🎯 Pair Z-Score Tabanı ({z_score:.2f} < -{self.entry_threshold} | r={corr:.2f}, φ={ar1_phi:.2f}). A LONG / B SHORT (Piyasa Nötr)."

        return {
            "is_signal": is_signal,
            "action": action,
            "z_score": round(z_score, 2),
            "correlation": round(corr, 3),
            "ar1_phi": round(ar1_phi, 3),
            "current_ratio": round(current_ratio, 6),
            "mean_ratio": round(mean_ratio, 6),
            "std_ratio": round(std_ratio, 6),
            "leg_a_direction": leg_a_direction,
            "leg_b_direction": leg_b_direction,
            "reason": reason
        }

    def get_pair_live_zscore(self, client, sym_a: str, sym_b: str) -> Optional[float]:
        """Açık bir pair pozisyonunun güncel 15m spread Z-skorunu döndürür (eşzamanlı çıkış için)."""
        try:
            candles_a = client.get_klines(sym_a, interval="15m", limit=40)
            candles_b = client.get_klines(sym_b, interval="15m", limit=40)
            if not candles_a or not candles_b or len(candles_a) < 20 or len(candles_b) < 20:
                return None
            res = self.calculate_pair_spread(candles_a[:-1], candles_b[:-1])
            return float(res.get("z_score", 0.0))
        except Exception:
            return None

    def evaluate_all_pairs(self, client) -> List[Dict]:
        """Tüm korele çiftler arasında 15m kapanmış mumlarla piyasa-nötr istatistiksel arbitraj tarar."""
        opportunities = []
        for sym_a, sym_b in PAIRS_UNIVERSE:
            try:
                candles_a = client.get_klines(sym_a, interval="15m", limit=40)
                candles_b = client.get_klines(sym_b, interval="15m", limit=40)
                if not candles_a or not candles_b or len(candles_a) < 20 or len(candles_b) < 20:
                    continue

                res = self.calculate_pair_spread(candles_a[:-1], candles_b[:-1])
                if res.get("is_signal"):
                    price_a = float(candles_a[-1]["close"])
                    price_b = float(candles_b[-1]["close"])
                    opportunities.append({
                        "pair_name": f"{sym_a} / {sym_b}",
                        "sym_a": sym_a,
                        "sym_b": sym_b,
                        "price_a": price_a,
                        "price_b": price_b,
                        "action": res["action"],
                        "leg_a_direction": res["leg_a_direction"],
                        "leg_b_direction": res["leg_b_direction"],
                        "z_score": res["z_score"],
                        "reason": res["reason"]
                    })
            except Exception:
                continue
        return opportunities
