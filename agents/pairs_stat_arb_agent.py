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
        for ca, cb in zip(sub_a, sub_b):
            c_a = float(ca["close"])
            c_b = float(cb["close"])
            if c_b > 0:
                ratios.append(c_a / c_b)

        if len(ratios) < 15:
            return {"is_signal": False, "z_score": 0.0, "action": "NONE"}

        mean_ratio = sum(ratios) / len(ratios)
        variance = sum((r - mean_ratio) ** 2 for r in ratios) / len(ratios)
        std_ratio = math.sqrt(variance) if variance > 0 else 0.0001

        current_ratio = ratios[-1]
        z_score = (current_ratio - mean_ratio) / std_ratio

        is_signal = False
        action = "NONE"
        leg_a_direction = None
        leg_b_direction = None
        reason = ""

        # Z >= +2.0: Varlık A, B'ye göre aşırı değerlendi (Pahalı) -> Short A / Long B
        if z_score >= self.entry_threshold:
            is_signal = True
            action = "SHORT_A_LONG_B"
            leg_a_direction = "SHORT"
            leg_b_direction = "LONG"
            reason = f"🎯 Pair Z-Score Tavanı (+{z_score:.2f} > +{self.entry_threshold}). A aşırı primli: A SHORT / B LONG (Piyasa Nötr)."

        # Z <= -2.0: Varlık A, B'ye göre aşırı ucuzladı (İskontolu) -> Long A / Short B
        elif z_score <= -self.entry_threshold:
            is_signal = True
            action = "LONG_A_SHORT_B"
            leg_a_direction = "LONG"
            leg_b_direction = "SHORT"
            reason = f"🎯 Pair Z-Score Tabanı ({z_score:.2f} < -{self.entry_threshold}). A aşırı iskontolu: A LONG / B SHORT (Piyasa Nötr)."

        return {
            "is_signal": is_signal,
            "action": action,
            "z_score": round(z_score, 2),
            "current_ratio": round(current_ratio, 6),
            "mean_ratio": round(mean_ratio, 6),
            "std_ratio": round(std_ratio, 6),
            "leg_a_direction": leg_a_direction,
            "leg_b_direction": leg_b_direction,
            "reason": reason
        }

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
