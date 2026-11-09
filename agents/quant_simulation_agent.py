"""
Monte Carlo Kuant Fiyat Yolu Simülasyon Ajanı (Stochastic Path Simulator)
Tauric Research / Hedge Fund Quantitative Decision Engine

Görevi:
Teknik analizin uygun bulduğu coin üzerinde anlık fiyattan başlayarak
hedef yöne doğru 10.000 bağımsız stokastik fiyat yolu (Geometric Brownian Motion + Jump Diffusion)
koşturur. 

Kazanma İhtimali (Win Probability): Fiyatın Stop-Loss'a çarpmadan önce Take-Profit'e ulaşma yüzdesi.
Matematiksel Beklenti (R-Multiple): İşlemin beklenen getiri değeri.

Karar Kuralı:
- Simülasyon Win Probability >= %70.0 ve Matematiksel Beklenti > 0 ise -> OY: ONAYLANDI (APPROVED)
- Simülasyon Win Probability < %70.0 ise -> OY: VETO / RED (REJECTED)
"""

import numpy as np
from typing import Dict, List, Optional


class QuantSimulationAgent:
    def __init__(self, default_simulations: int = 10000, horizon_steps: int = 48, win_threshold_pct: float = 70.0):
        """
        :param default_simulations: Koşturulacak stokastik fiyat yolu sayısı (Varsayılan: 10.000 yol)
        :param horizon_steps: 15 dakikalık periyot adımı (48 adım = 12 saatlik projeksiyon)
        :param win_threshold_pct: Ortak oya sunulması ve onay için gereken asgari kazanma ihtimali (%70.0)
        """
        self.default_simulations = default_simulations
        self.horizon_steps = horizon_steps
        self.win_threshold_pct = win_threshold_pct

    def simulate_setup(
        self,
        symbol: str,
        ta_setup: Dict,
        candles_15m: List[Dict],
        num_simulations: Optional[int] = None
    ) -> Dict:
        """
        Aday parite üzerinde 10.000 Monte Carlo stokastik fiyat simülasyonu çalıştırır.
        """
        n_sims = num_simulations or self.default_simulations
        steps = self.horizon_steps

        current_price = float(ta_setup.get("current_price", 0.0))
        direction = ta_setup.get("direction", "LONG").upper()
        tp1 = float(ta_setup.get("take_profit_1", 0.0))
        sl = float(ta_setup.get("stop_loss", 0.0))
        sl_pct = float(ta_setup.get("sl_pct", 1.5))
        tp1_pct = float(ta_setup.get("tp1_pct", 3.0))

        if current_price <= 0 or tp1 <= 0 or sl <= 0 or len(candles_15m) < 15:
            return self._fallback_result(symbol, direction, n_sims)

        # 1. 15m Mumlarından Tarihsel Volatilite ve Drift Hesapla
        closes = [float(c["close"]) for c in candles_15m if "close" in c]
        if len(closes) < 15:
            return self._fallback_result(symbol, direction, n_sims)

        closes = np.array(closes)
        log_returns = np.diff(np.log(closes))
        hist_vol = float(np.std(log_returns)) if len(log_returns) > 1 else 0.008

        # Taban volatilite koruması (ölü piyasada sıfır bölmeyi engeller)
        sigma = max(hist_vol, 0.0035)

        # Yöne göre momentum drift desteği
        base_drift = float(np.mean(log_returns)) if len(log_returns) > 1 else 0.0
        confluence_score = float(ta_setup.get("confluence_score", 75))
        # Skora göre hafif pozitif drift katkısı
        drift_bias = ((confluence_score - 50.0) / 100.0) * (sigma * 0.15)
        drift = (base_drift + drift_bias) if direction == "LONG" else (base_drift - drift_bias)

        # 2. Vektörize Monte Carlo Simülasyonu (NumPy Matrisi: 10000 x 48)
        # Z: Standart normal dağılım şokları
        Z = np.random.standard_normal((n_sims, steps))
        # Kripto piyasasına özgü mikro sıçramalar (Jump-diffusion: %4 ihtimalle ani fitil)
        jumps = (np.random.rand(n_sims, steps) < 0.04) * np.random.laplace(0, 1.4 * sigma, (n_sims, steps))

        # Adım getirileri: Geometric Brownian Motion
        dt = 1.0
        step_returns = (drift - 0.5 * (sigma ** 2)) * dt + (sigma * np.sqrt(dt) * Z) + jumps
        cum_returns = np.cumsum(step_returns, axis=1)

        # 10.000 simüle edilmiş fiyat patikası
        sim_paths = current_price * np.exp(cum_returns)
        # t=0 başlangıç fiyatını ekle (10000 x 49)
        paths = np.hstack([np.full((n_sims, 1), current_price), sim_paths])

        # 3. First-Hit (İlk Çarpan Kazanır) Mantığı ile TP ve SL Analizi
        if direction == "LONG":
            tp_hits = paths >= tp1
            sl_hits = paths <= sl
        else:
            tp_hits = paths <= tp1
            sl_hits = paths >= sl

        tp_any = np.any(tp_hits, axis=1)
        sl_any = np.any(sl_hits, axis=1)

        # İlk TP ve ilk SL vuruş indeksleri
        first_tp_idx = np.where(tp_any, np.argmax(tp_hits, axis=1), 99999)
        first_sl_idx = np.where(sl_any, np.argmax(sl_hits, axis=1), 99999)

        # Kazanma: TP'ye SL'den ÖNCE ulaşılan yollar
        wins = (first_tp_idx < first_sl_idx) & tp_any
        # Kaybetme: SL'ye TP'den ÖNCE ulaşılan yollar
        losses = (first_sl_idx < first_tp_idx) & sl_any
        # İkisine de çarpmadan 48 adım (12 saat) süren yollar
        neither = ~wins & ~losses

        win_count = int(np.sum(wins))
        loss_count = int(np.sum(losses))
        neither_count = int(np.sum(neither))

        win_prob = (win_count / n_sims) * 100.0
        loss_prob = (loss_count / n_sims) * 100.0
        neither_prob = (neither_count / n_sims) * 100.0

        # Matematiksel Beklenti (R-Multiple)
        # 1R = SL mesafesi, Kazanç = (TP / SL mesafesi) * 1R
        reward_r = (tp1_pct / max(sl_pct, 0.1))
        expected_r = ((win_prob / 100.0) * reward_r) - ((loss_prob / 100.0) * 1.0)

        # 4. Karar Kuralı (Ortak Oya Sunulma ve Onay Kriteri)
        is_approved = (win_prob >= self.win_threshold_pct) and (expected_r > 0.05)
        vote = "APPROVED" if is_approved else "REJECTED"

        # Temsili Fan Grafiği Örneklemeleri (10., 50. medyan ve 90. persentil yolları)
        sample_median_path = [round(float(p), 4) for p in np.median(paths, axis=0)[::4]]
        sample_p90_path = [round(float(p), 4) for p in np.percentile(paths, 90, axis=0)[::4]]
        sample_p10_path = [round(float(p), 4) for p in np.percentile(paths, 10, axis=0)[::4]]

        # Argüman Metni (Komite Tartışması İçin)
        if is_approved:
            arg = (
                f"{symbol} paritesi üzerinde {n_sims:,} bağımsız Monte Carlo stokastik fiyat yolu simüle ettim. "
                f"Fiyatın ${current_price:,.4f} seviyesinden TP1 hedefimize (${tp1:,.4f}) Stop'tan önce ulaşma ihtimali %{win_prob:.1f}! "
                f"Stop Loss riski: %{loss_prob:.1f}. Matematiksel beklenti: +{expected_r:.2f}R. "
                f"Stokastik dağılım ve volatilite rejimi pozisyonu kuvvetle destekliyor. OYUM: ONAYLANDI (POZİSYONA UYGUN)!"
            )
        else:
            arg = (
                f"{symbol} paritesi üzerinde {n_sims:,} Monte Carlo fiyat yolu koşturdum. "
                f"TP1'e ulaşma ihtimali yalnızca %{win_prob:.1f} (Asgari eşiğimiz %{self.win_threshold_pct:.1f}). "
                f"Stop Loss olma riski ise %{loss_prob:.1f} ile kabul edilemez seviyede! "
                f"Matematiksel beklenti: {expected_r:+.2f}R. Bu fiyat yolunda sermayeyi riske atmak matematiksel hata olur. "
                f"OYUM: VETO / RED (İŞLEMDEN UZAK DURULMALI)!"
            )

        return {
            "symbol": symbol,
            "direction": direction,
            "num_simulations": n_sims,
            "horizon_hours": steps * 15 // 60,
            "win_probability_pct": round(win_prob, 1),
            "loss_probability_pct": round(loss_prob, 1),
            "neither_probability_pct": round(neither_prob, 1),
            "expected_return_r": round(expected_r, 2),
            "historical_volatility": round(sigma * 100, 3),
            "vote": vote,
            "is_approved": is_approved,
            "argument": arg,
            "sample_paths": {
                "p10": sample_p10_path,
                "median": sample_median_path,
                "p90": sample_p90_path
            }
        }

    def _fallback_result(self, symbol: str, direction: str, n_sims: int) -> Dict:
        """Yetersiz veri durumunda güvenli yedek çıktı."""
        return {
            "symbol": symbol,
            "direction": direction,
            "num_simulations": n_sims,
            "horizon_hours": 12,
            "win_probability_pct": 50.0,
            "loss_probability_pct": 50.0,
            "neither_probability_pct": 0.0,
            "expected_return_r": 0.0,
            "historical_volatility": 1.0,
            "vote": "REJECTED",
            "is_approved": False,
            "argument": f"{symbol} için yetersiz mum verisi nedeniyle 10,000 simülasyon güven aralığına ulaşamadı. Sermaye koruma kuralı gereği VETO verildi.",
            "sample_paths": {}
        }

