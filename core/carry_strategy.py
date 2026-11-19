"""
Fonlama faktörü (kesitsel funding carry) — saf hesaplama çekirdeği.

Canlı motor (agents/carry_agent.py) ve backtest (backtest/carry_backtest.py) bu dosyadaki
fonksiyonları birebir aynı şekilde kullanır; böylece test edilen kural ile çalışan kural aynıdır.

Kural (3 yıllık veride önceden belirlenmiş parametrelerle doğrulandı):
  - Evrendeki her coin için son `lookback_h` saatin fonlama oranları toplanır.
  - Fonlaması en DÜŞÜK k coin LONG, en YÜKSEK k coin SHORT (piyasa-nötr).
  - Her bacak ters-volatilite ile ağırlıklanır: hedef_vol / sqrt(N) / coin_vol.
  - Brüt kaldıraç tavanı uygulanır.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence

HOURS_YEAR = 24 * 365


def realized_vol_ann(closes: Sequence[float], lookback_h: int) -> float | None:
    """Saatlik kapanışlardan yıllıklandırılmış volatilite. Yetersiz veri -> None."""
    xs = [float(c) for c in closes[-(lookback_h + 1):] if c and c > 0]
    if len(xs) < max(24 * 10, 2):
        return None
    rets = [xs[i] / xs[i - 1] - 1.0 for i in range(1, len(xs))]
    n = len(rets)
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / (n - 1)
    if var <= 0:
        return None
    return math.sqrt(var) * math.sqrt(HOURS_YEAR)


def rank_signals(funding_sums: Dict[str, float], k: int) -> Dict[str, int]:
    """+1 = LONG (düşük fonlama), -1 = SHORT (yüksek fonlama). Eşitlikte sembol adı belirleyici."""
    items = sorted(funding_sums.items(), key=lambda kv: (kv[1], kv[0]))
    n = len(items)
    if n < 2 * k:
        k = n // 2
    sig: Dict[str, int] = {}
    for s, _ in items[:k]:
        sig[s] = 1
    for s, _ in items[n - k:] if k > 0 else []:
        sig[s] = -1
    return sig


def compute_target_weights(
    closes: Dict[str, List[float]],
    funding_sums: Dict[str, float],
    k: int = 5,
    vol_lookback_h: int = 24 * 30,
    target_vol_ann: float = 0.20,
    gross_cap: float = 3.0,
    universe_size: int | None = None,
    scale: float = 1.0,
) -> Dict[str, float]:
    """
    Hedef ağırlıklar (özsermayenin oranı olarak, işaretli). Örn. 0.12 = özsermayenin %12'si kadar LONG notional.
    Yalnızca hem fiyatı hem fonlaması olan coinler sıralamaya girer.
    """
    eligible = {s: f for s, f in funding_sums.items() if s in closes and f is not None and not math.isnan(f)}
    vols = {s: realized_vol_ann(closes[s], vol_lookback_h) for s in eligible}
    eligible = {s: f for s, f in eligible.items() if vols.get(s)}
    n_univ = universe_size or len(eligible)
    if not eligible or n_univ <= 0:
        return {}
    sig = rank_signals(eligible, k)
    per_asset = target_vol_ann / math.sqrt(n_univ)
    w = {s: max(-1.0, min(1.0, d * per_asset / vols[s])) for s, d in sig.items()}
    gross = sum(abs(v) for v in w.values())
    if gross > gross_cap > 0:
        w = {s: v * gross_cap / gross for s, v in w.items()}
    return {s: v * scale for s, v in w.items()}


def plan_orders(
    target_w: Dict[str, float],
    positions_qty: Dict[str, float],
    prices: Dict[str, float],
    equity: float,
    min_trade_usdt: float = 10.0,
) -> Dict[str, float]:
    """
    Hedef ağırlıktan hedef miktara geçiş için gereken miktar değişimleri (sembol -> delta qty).
    Hedefi olmayan açık pozisyonlar kapatılır. Çok küçük ayarlamalar (devir/komisyon tasarrufu) atlanır;
    yön değişimi ve tam kapanış her zaman yapılır.
    """
    deltas: Dict[str, float] = {}
    for s in set(target_w) | set(positions_qty):
        p = prices.get(s)
        if not p or p <= 0:
            continue
        cur = positions_qty.get(s, 0.0)
        tgt = target_w.get(s, 0.0) * equity / p
        d = tgt - cur
        if abs(d) * p < 1e-9:
            continue
        closing = tgt == 0.0 and cur != 0.0
        flipping = cur != 0.0 and tgt != 0.0 and (cur > 0) != (tgt > 0)
        if not closing and not flipping and abs(d) * p < min_trade_usdt:
            continue
        deltas[s] = d
    return deltas


def drawdown_scale(equity: float, peak: float, current_scale: float,
                   cut_dd: float = -0.10, restore_dd: float = -0.05, reduced: float = 0.5) -> float:
    """Portföy kesicisi: tepeden -%10 düşüşte risk yarıya iner, -%5'in üstüne dönünce tam riske döner."""
    if peak <= 0:
        return current_scale
    dd = equity / peak - 1.0
    if dd <= cut_dd:
        return reduced
    if dd >= restore_dd:
        return 1.0
    return current_scale


# ======================================================================================
# v3 Çok faktörlü karışım: trend (TSMOM) + kesitsel momentum + fonlama faktörü
# --------------------------------------------------------------------------------------
# Tek faktörler dönemden döneme yer değiştiriyor (2020-23: momentum/trend güçlü, fonlama zayıf;
# 2023-26: fonlama güçlü, kesitsel momentum zayıf). Sonuçlar görülmeden ÖNCE tanımlanmış bu 3'lü
# karışım iki dönemde de Sharpe ~1.1 verdi. Her kol, ex-ante (kovaryans tabanlı) volatilitesine göre
# eşit riske ölçeklenir.
# ======================================================================================
def _per_asset_vol_weights(signs: Dict[str, float], vols: Dict[str, float], target_vol_ann: float, n_univ: int):
    per_asset = target_vol_ann / math.sqrt(max(1, n_univ))
    return {s: max(-1.0, min(1.0, d * per_asset / vols[s])) for s, d in signs.items() if d and vols.get(s)}


def tsmom_weights(closes: Dict[str, List[float]], vols: Dict[str, float], lookback_h: int = 24 * 28,
                  target_vol_ann: float = 0.20, n_univ: int | None = None) -> Dict[str, float]:
    """Zaman-serisi momentum: son 28 günün getirisi pozitifse LONG, negatifse SHORT (ters-vol ağırlıklı)."""
    sig = {}
    for s, c in closes.items():
        if len(c) > lookback_h and c[-1 - lookback_h] > 0:
            r = c[-1] / c[-1 - lookback_h] - 1.0
            sig[s] = 1.0 if r > 0 else (-1.0 if r < 0 else 0.0)
    return _per_asset_vol_weights(sig, vols, target_vol_ann, n_univ or len(closes))


def xsmom_weights(closes: Dict[str, List[float]], vols: Dict[str, float], k: int = 5, lookback_h: int = 24 * 30,
                  skip_h: int = 24, target_vol_ann: float = 0.20, n_univ: int | None = None) -> Dict[str, float]:
    """Kesitsel momentum: son 30 günün (son 1 gün hariç) en iyi k coini LONG, en kötü k coini SHORT."""
    score = {}
    for s, c in closes.items():
        if len(c) > lookback_h and c[-1 - lookback_h] > 0:
            score[s] = c[-1 - skip_h] / c[-1 - lookback_h] - 1.0
    # rank_signals düşük değeri LONG yapar -> momentum için işareti çevir
    sig = rank_signals({s: -v for s, v in score.items()}, k)
    return _per_asset_vol_weights(sig, vols, target_vol_ann, n_univ or len(closes))


def funding_weights(funding_sums: Dict[str, float], vols: Dict[str, float], k: int = 5,
                    target_vol_ann: float = 0.20, n_univ: int | None = None) -> Dict[str, float]:
    sig = rank_signals({s: f for s, f in funding_sums.items() if vols.get(s)}, k)
    return _per_asset_vol_weights(sig, vols, target_vol_ann, n_univ or len(funding_sums))


def ex_ante_vol(weights: Dict[str, float], closes: Dict[str, List[float]], lookback_h: int = 24 * 30) -> float | None:
    """Ağırlık vektörünün son `lookback_h` saatlik getiri kovaryansıyla yıllık volatilitesi: sqrt(w' Σ w)."""
    import numpy as np
    syms = [s for s, w in weights.items() if w and len(closes.get(s, [])) > lookback_h // 2]
    if not syms:
        return None
    n = min(lookback_h + 1, min(len(closes[s]) for s in syms))
    M = np.array([closes[s][-n:] for s in syms], dtype=float)
    R = M[:, 1:] / M[:, :-1] - 1.0
    if R.shape[1] < 48:
        return None
    w = np.array([weights[s] for s in syms])
    port = w @ R
    v = float(np.std(port, ddof=1)) * math.sqrt(HOURS_YEAR)
    return v if v > 0 else None


def combine_sleeves(sleeves: Dict[str, Dict[str, float]], closes: Dict[str, List[float]],
                    portfolio_target_vol: float = 0.10, vol_lookback_h: int = 24 * 30,
                    gross_cap: float = 3.0, max_mult: float = 3.0) -> Dict[str, float]:
    """Her kolu (target/√N)/ex-ante-vol ile ölçekleyip toplar; brüt kaldıraç tavanı uygular."""
    active = {k: w for k, w in sleeves.items() if w}
    if not active:
        return {}
    per = portfolio_target_vol / math.sqrt(len(active))
    total: Dict[str, float] = {}
    for _, w in active.items():
        v = ex_ante_vol(w, closes, vol_lookback_h)
        if not v:
            continue
        m = min(max_mult, per / v)
        for s, x in w.items():
            total[s] = total.get(s, 0.0) + m * x
    gross = sum(abs(v) for v in total.values())
    if gross > gross_cap > 0:
        total = {s: v * gross_cap / gross for s, v in total.items()}
    return {s: v for s, v in total.items() if abs(v) > 1e-9}
