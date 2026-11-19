"""Faz 2: Backtest motoru — lookahead koruması, oluşmakta olan mum, uçtan uca çalışma."""
import math
import random

from backtest.data import INTERVAL_MS
from backtest.engine import SimMarket, BacktestConfig, BacktestEngine, committee_confidence, quality_score
from backtest.report import summarize


def _synthetic(symbols, days=12, seed=1, start_ms=1_700_000_000_000 // 3_600_000 * 3_600_000):
    rnd = random.Random(seed)
    data = {}
    n = days * 1440
    for k, s in enumerate(symbols):
        px = 100.0 + k
        m1 = []
        for i in range(n):
            drift = 0.00002 * math.sin(i / 2000.0)
            o = px
            c = max(0.01, o * (1 + drift + rnd.gauss(0, 0.0012)))
            h = max(o, c) * (1 + abs(rnd.gauss(0, 0.0006)))
            lo = min(o, c) * (1 - abs(rnd.gauss(0, 0.0006)))
            v = 1000 + rnd.random() * 500
            m1.append({"timestamp": start_ms + i * 60_000, "open": o, "high": h, "low": lo, "close": c,
                       "volume": v, "quote_volume": v * c, "taker_buy_volume": v * rnd.random()})
            px = c
        data[s] = {"1m": m1}
        for iv in ("15m", "30m", "1h", "4h"):
            step = INTERVAL_MS[iv] // 60_000
            agg = []
            for j in range(0, n - step + 1, step):
                b = m1[j:j + step]
                agg.append({"timestamp": b[0]["timestamp"], "open": b[0]["open"], "high": max(x["high"] for x in b),
                            "low": min(x["low"] for x in b), "close": b[-1]["close"], "volume": sum(x["volume"] for x in b),
                            "quote_volume": sum(x["quote_volume"] for x in b), "taker_buy_volume": sum(x["taker_buy_volume"] for x in b)})
            data[s][iv] = agg
    return data, start_ms


def test_simmarket_has_no_lookahead():
    data, start = _synthetic(["AAAUSDT"], days=2)
    m = SimMarket(data)
    m.now_ms = start + 15 * 60_000 * 10 + 7 * 60_000  # 10. 15m mumu kapanmış, 7 dakika ilerlemiş
    closed = m.closed("AAAUSDT", "15m", 100)
    assert len(closed) == 10
    assert all(c["timestamp"] + INTERVAL_MS["15m"] <= m.now_ms for c in closed)
    f = m.forming("AAAUSDT", "15m")
    one_min = data["AAAUSDT"]["1m"]
    first = (start + 15 * 60_000 * 10 - start) // 60_000
    expected = one_min[first:first + 7]
    assert f["open"] == expected[0]["open"] and f["close"] == expected[-1]["close"]
    assert f["high"] == max(b["high"] for b in expected)
    # Gelecekteki 1m mumu kullanılmamalı
    assert f["close"] != one_min[first + 7]["close"]


def test_quality_and_committee_formula():
    assert committee_confidence(78, 60, 68) == 9.1
    assert committee_confidence(200, 60, 68) == 9.8
    q = quality_score(60.0, 9.1, 2.0, "Grade A (10x ...)")
    assert q == round(21.0 + 22.75 + 4.0 + 16.0, 1)


def test_engine_end_to_end_synthetic():
    syms = ["AAAUSDT", "BBBUSDT"]
    data, start = _synthetic(syms + ["BTCUSDT"], days=12)
    cfg = BacktestConfig(symbols=syms, start_ms=start + 10 * 86_400_000, end_ms=start + 12 * 86_400_000,
                         use_mc_gate=False, use_quality_gate=False, use_btc_shield=False, mc_simulations=200)
    res = BacktestEngine(cfg, data).run()
    s = summarize(res["trades"])
    assert s["trades"] + s["open_at_end"] == len(res["trades"])
    assert sum(res["rejections"].values()) > 0
    for t in res["trades"]:
        assert t["strategy_version"].endswith("-backtest")
        assert t["entered_at"] >= "2023"  # simüle saat yazılmış olmalı
    # Gerçek DB'ye dokunulmadı ve saat sıfırlandı
    from core import timeutil
    assert timeutil._CLOCK_OVERRIDE is None
