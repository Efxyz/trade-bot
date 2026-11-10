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

    @staticmethod
    def run_empirical_replay(
        candles_15m: List[Dict],
        direction: str,
        tp_pct: float,
        sl_pct: float,
        horizon_bars: int = 24
    ) -> Dict:
        """
        trader-timemachine'den uyarlanan Ampirik Geçmiş Rezonans Algoritması:
        Teorik matematiksel formüller yerine, paritenin son dönem gerçek 15m mumları taranır.
        Benzer yönlü momentum / kırılım şartının oluştuğu her geçmiş mumda:
        Sonraki horizon_bars (24 bar = 6 saat) içinde fiyatın önce TP'ye mi yoksa SL'e mi vurduğu test edilir.
        """
        n = len(candles_15m)
        if n < 30:
            return {
                "samples": 0,
                "tp_count": 0,
                "sl_count": 0,
                "neither_green": 0,
                "neither_red": 0,
                "side_win_rate": 50.0,
                "green_rate": 50.0,
                "is_approved": True,
                "verdict": "INSUFFICIENT_SAMPLES",
                "summary": "Ampirik örneklem sınırlı (yetersiz mum)"
            }

        avg_vol = sum(float(c.get("volume", 0.0)) for c in candles_15m) / max(n, 1)
        tp_count = 0
        sl_count = 0
        neither_green = 0
        neither_red = 0
        samples = 0

        # Son 8 mum henüz olgunlaşamayacağı için geçmişi tararız
        for i in range(15, n - 8):
            c = candles_15m[i]
            prev = candles_15m[i - 1]

            c_open = float(c.get("open", 0.0))
            c_close = float(c.get("close", 0.0))
            c_vol = float(c.get("volume", 0.0))
            prev_high = float(prev.get("high", 0.0))
            prev_low = float(prev.get("low", 0.0))

            is_candidate = False
            if direction == "LONG":
                if c_close > c_open and c_close >= prev_high and c_vol >= avg_vol * 0.85:
                    is_candidate = True
            else:  # SHORT
                if c_close < c_open and c_close <= prev_low and c_vol >= avg_vol * 0.85:
                    is_candidate = True

            if not is_candidate:
                continue

            samples += 1
            entry = c_close
            tp_price = entry * (1.0 + tp_pct / 100.0) if direction == "LONG" else entry * (1.0 - tp_pct / 100.0)
            sl_price = entry * (1.0 - sl_pct / 100.0) if direction == "LONG" else entry * (1.0 + sl_pct / 100.0)

            resolved = False
            max_look = min(i + horizon_bars + 1, n)
            for k in range(i + 1, max_look):
                ck = candles_15m[k]
                h = float(ck.get("high", 0.0))
                l = float(ck.get("low", 0.0))

                if direction == "LONG":
                    # Hem SL hem TP aynı mumda geldiyse muhafazakar olarak SL kabul et (timemachine kuralı)
                    if l <= sl_price:
                        sl_count += 1
                        resolved = True
                        break
                    elif h >= tp_price:
                        tp_count += 1
                        resolved = True
                        break
                else:  # SHORT
                    if h >= sl_price:
                        sl_count += 1
                        resolved = True
                        break
                    elif l <= tp_price:
                        tp_count += 1
                        resolved = True
                        break

            if not resolved and max_look > i + 1:
                last_c = float(candles_15m[max_look - 1].get("close", entry))
                pnl = ((last_c - entry) / entry) if direction == "LONG" else ((entry - last_c) / entry)
                if pnl > 0:
                    neither_green += 1
                else:
                    neither_red += 1

        total_side = tp_count + sl_count
        side_win_rate = round((tp_count / total_side * 100.0), 1) if total_side > 0 else 50.0
        overall_green = tp_count + neither_green
        green_rate = round((overall_green / samples * 100.0), 1) if samples > 0 else 50.0

        # Karar Kuralı:
        # Eğer yeterli örneklem varsa (>= 5) ve bu coinde benzer kırılımlar kronik zarar üretiyorsa (< %35 green_rate veya TP/SL < %35):
        if samples >= 5 and (green_rate < 35.0 or (total_side >= 5 and side_win_rate < 35.0)):
            verdict = "POOR_CHOP_TRAP"
            is_approved = False
            summary = f"Kronik Tuzak Parite (Son {samples} kırılımda başarı: %{green_rate:.1f} < %35.0)"
        elif samples >= 5 and green_rate >= 55.0:
            verdict = "STRONG_MATCH"
            is_approved = True
            summary = f"Güçlü Tarihsel Rezonans ({samples} örnekte başarı: %{green_rate:.1f}, TP/SL: %{side_win_rate:.1f})"
        else:
            verdict = "FAIR_MATCH"
            is_approved = True
            summary = f"Tarihsel Uyum Kabul Edilebilir ({samples} örnekte başarı: %{green_rate:.1f})"

        return {
            "samples": samples,
            "tp_count": tp_count,
            "sl_count": sl_count,
            "neither_green": neither_green,
            "neither_red": neither_red,
            "side_win_rate": side_win_rate,
            "green_rate": green_rate,
            "is_approved": is_approved,
            "verdict": verdict,
            "summary": summary
        }

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

        # 3b. Ampirik Geçmiş Rezonans Testi (trader-timemachine Algoritması)
        empirical_data = self.run_empirical_replay(candles_15m, direction, tp1_pct, sl_pct, horizon_bars=steps)
        empirical_approved = empirical_data.get("is_approved", True)

        # 4. Karar Kuralı (Ortak Oya Sunulma ve Onay Kriteri)
        # Hem 10,000 Stokastik Monte Carlo yolu (win_prob >= %70)
        # HEM DE paritenin gerçek geçmiş ampirik rezonansı onay vermelidir!
        mc_approved = (win_prob >= self.win_threshold_pct) and (expected_r > 0.05)
        is_approved = mc_approved and empirical_approved
        vote = "APPROVED" if is_approved else "REJECTED"

        # Temsili Fan Grafiği Örneklemeleri (10., 50. medyan ve 90. persentil yolları)
        sample_median_path = [round(float(p), 4) for p in np.median(paths, axis=0)[::4]]
        sample_p90_path = [round(float(p), 4) for p in np.percentile(paths, 90, axis=0)[::4]]
        sample_p10_path = [round(float(p), 4) for p in np.percentile(paths, 10, axis=0)[::4]]

        # Argüman Metni (Komite Tartışması İçin)
        if is_approved:
            arg = (
                f"{symbol} paritesi üzerinde {n_sims:,} bağımsız Monte Carlo stokastik fiyat yolu simüle ettim "
                f"(TP1 İhtimali: %{win_prob:.1f}, SL Riski: %{loss_prob:.1f}, Beklenti: +{expected_r:.2f}R). "
                f"Ayrıca Time Machine ampirik geçmiş testinde ({empirical_data['samples']} gerçek kırılım) "
                f"%{empirical_data['green_rate']:.1f} kârlılık rezonansı teyit edildi ({empirical_data['summary']}). "
                f"OYUM: ONAYLANDI (POZİSYONA UYGUN)!"
            )
        elif not empirical_approved:
            arg = (
                f"{symbol} paritesi üzerinde 10,000 Monte Carlo simülasyonu olumlu görünse bile, "
                f"Time Machine ampirik geçmiş testi VETO ETTİ! "
                f"Bu paritenin son dönem gerçek 15m verisinde oluşan {empirical_data['samples']} benzer kırılımın "
                f"yalnızca %{empirical_data['green_rate']:.1f}'i kazandırdı (Kronik Testere / Stop-Hunt Tuzağı)! "
                f"Sermayeyi korumak için OYUM: VETO / RED (İŞLEMDEN UZAK DURULMALI)!"
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
            "empirical_match": empirical_data,
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
            "empirical_match": {},
            "sample_paths": {}
        }

