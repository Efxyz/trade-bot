"""v3 Fonlama Faktörü Motoru testleri."""
import math
from dataclasses import replace

import pytest

from agents.carry_agent import (CarryEngine, CarryParams, MemoryCarryStore, SQLiteCarryStore, HOUR_MS,
                                last_scheduled_rebalance)
from core.carry_strategy import (combine_sleeves, compute_target_weights, drawdown_scale, ex_ante_vol, plan_orders,
                                 rank_signals, realized_vol_ann, tsmom_weights, xsmom_weights)

T0 = 1_700_006_400_000 - (1_700_006_400_000 % (24 * HOUR_MS))  # UTC gün başı


class FakeData:
    """Deterministik sahte piyasa: sabit/oynak fiyatlar ve elle verilen fonlama olayları."""

    def __init__(self, syms, funding_rate=None, n_hist=800):
        self.syms = syms
        self.t = T0
        self.px = {s: 100.0 + 10 * i for i, s in enumerate(syms)}
        self.hist = {s: [self.px[s] * (1 + 0.01 * math.sin(j * (i + 1) / 7)) for j in range(n_hist)]
                     for i, s in enumerate(syms)}
        self.rate = funding_rate or {s: 0.0001 * (i - len(syms) / 2) for i, s in enumerate(syms)}
        self.funding_calls = 0

    def now_ms(self):
        return self.t

    def hourly_closes(self, s, n):
        return self.hist[s][-n:]

    def funding_history(self, s, start, end):
        self.funding_calls += 1
        out = []
        t = (start // (8 * HOUR_MS)) * 8 * HOUR_MS
        while t <= end:
            if t >= start and t >= T0 - 30 * 24 * HOUR_MS:
                out.append({"time": t, "rate": self.rate[s]})
            t += 8 * HOUR_MS
        return out

    def prices(self, syms):
        return {s: self.px[s] for s in syms if s in self.px}


SYMS = [f"C{i}USDT" for i in range(12)]


def params(**kw):
    base = CarryParams(universe=SYMS, capital=1000.0, k=3, tranches=1, rebalance_weekday=0, rebalance_hour=0,
                       fee_rate=0.0005, slippage_rate=0.0002, min_trade_usdt=1.0, sleeves=("funding",))
    return replace(base, **kw)


# ---------------- saf fonksiyonlar ----------------
def test_rank_signals_low_funding_long_high_short():
    sig = rank_signals({"A": -0.01, "B": 0.0, "C": 0.02, "D": 0.05}, k=1)
    assert sig == {"A": 1, "D": -1}


def test_target_weights_market_neutral_and_capped():
    closes = {s: [100 * (1 + 0.01 * math.sin(j / 5)) for j in range(800)] for s in SYMS}
    fs = {s: i * 0.001 for i, s in enumerate(SYMS)}
    w = compute_target_weights(closes, fs, k=3, gross_cap=3.0)
    assert sum(1 for v in w.values() if v > 0) == 3 and sum(1 for v in w.values() if v < 0) == 3
    assert abs(sum(w.values())) < 1e-9          # aynı volatilite -> tam nötr
    assert sum(abs(v) for v in w.values()) <= 3.0 + 1e-9
    assert all(w[s] > 0 for s in SYMS[:3]) and all(w[s] < 0 for s in SYMS[-3:])


def test_realized_vol_needs_history():
    assert realized_vol_ann([100.0] * 50, 720) is None


def test_plan_orders_skips_small_but_keeps_close_and_flip():
    d = plan_orders({"A": 0.1, "B": -0.1}, {"A": 0.99, "B": 1.0, "C": 0.5}, {"A": 100, "B": 100, "C": 100}, 1000, 5.0)
    assert "A" not in d                 # 1 USDT'lik ayarlama atlanır
    assert d["B"] == pytest.approx(-2.0)  # yön değişimi her zaman
    assert d["C"] == pytest.approx(-0.5)  # hedefte olmayan kapanır


def test_drawdown_scale_hysteresis():
    assert drawdown_scale(890, 1000, 1.0) == 0.5
    assert drawdown_scale(930, 1000, 0.5) == 0.5
    assert drawdown_scale(960, 1000, 0.5) == 1.0


def test_last_scheduled_rebalance_monday():
    # 2023-11-15 Çarşamba 10:00 UTC -> 2023-11-13 Pazartesi 00:00
    now = 1_700_042_400_000
    assert last_scheduled_rebalance(now, 0, 0) == 1_699_833_600_000


# ---------------- motor ----------------
def test_engine_initial_rebalance_and_accounting_identity():
    data = FakeData(SYMS)
    eng = CarryEngine(data, MemoryCarryStore(), params())
    eng.step()
    st = eng.state
    assert st["n_rebalances"] == 1 and len(st["positions"]) == 6
    # Fiyat değişmeden: özsermaye = sermaye - komisyon - kayma maliyeti
    eq = eng.equity(data.prices(SYMS))
    slip = sum(f["notional"] for f in eng.store.fills) * 0.0002 / 1.0002
    assert eq == pytest.approx(1000 - st["fees_paid"] - slip, rel=1e-3)
    # Fiyat %10 artınca PnL = Σ qty·Δp
    before = eng.equity(data.prices(SYMS))
    for s in SYMS:
        data.px[s] *= 1.10
    after = eng.equity(data.prices(SYMS))
    expected = sum(p["qty"] * data.px[s] / 1.10 * 0.10 for s, p in st["positions"].items())
    assert after - before == pytest.approx(expected, rel=1e-9)


def test_funding_sign_long_pays_short_receives():
    rate = {s: 0.001 for s in SYMS}  # hepsi pozitif fonlama
    rate[SYMS[0]] = -0.002
    data = FakeData(SYMS, funding_rate=rate)
    eng = CarryEngine(data, MemoryCarryStore(), params(k=1))
    eng.step()                                  # LONG C0 (düşük), SHORT C11 (yüksek: ama hepsi 0.001 -> isim sırası)
    pos = eng.state["positions"]
    cash0 = eng.state["cash"]
    data.t += 9 * HOUR_MS                       # en az bir 8 saatlik ödeme
    eng.step()
    paid = sum(p["qty"] * data.px[s] * rate[s] for s, p in pos.items())
    n_settle = len([e for e in data.funding_history(SYMS[0], T0 + 1, data.t) if T0 < e["time"] <= data.t])
    assert n_settle >= 1
    assert eng.state["cash"] - cash0 == pytest.approx(-paid * n_settle, rel=1e-9)
    # LONG negatif oranda fonlama ALIR, SHORT pozitif oranda ALIR -> toplam fonlama ödemesi negatif (gelir)
    assert eng.state["funding_paid"] < 0


def test_funding_uses_qty_held_at_settlement():
    data = FakeData(SYMS)
    eng = CarryEngine(data, MemoryCarryStore(), params())
    eng.step()
    q_hist = eng.state["qty_history"]
    assert len(q_hist) == 1
    # Ödeme anı dengelemeyle AYNI an -> eski (boş) pozisyon geçerli
    assert eng._qty_at(next(iter(eng.state["positions"])), q_hist[0][0]) == 0.0


def test_weekly_schedule_rebalances_once_per_week():
    data = FakeData(SYMS)
    eng = CarryEngine(data, MemoryCarryStore(), params())
    for _ in range(24 * 15):
        eng.step()
        data.t += HOUR_MS
    assert eng.state["n_rebalances"] in (2, 3)  # ilk kurulum + 2 pazartesi (başlangıç gününe göre)


def test_tranches_average_signals_daily():
    data = FakeData(SYMS)
    eng = CarryEngine(data, MemoryCarryStore(), params(tranches=7))
    for _ in range(24 * 3):
        eng.step()
        data.t += HOUR_MS
    assert eng.state["n_rebalances"] == 3
    assert len(eng.state["tranche_weights"]) == 3
    # İlk 2 gün sinyal farklıysa ortalama alınır; burada fonlama sabit -> aynı hedef
    w = eng._combined_target()
    assert set(w) == set(eng.state["tranche_weights"][-1])


def test_drawdown_cut_halves_exposure_immediately():
    data = FakeData(SYMS)
    eng = CarryEngine(data, MemoryCarryStore(), params())
    eng.step()
    g0, _ = eng.exposures(data.prices(SYMS))
    # LONG'ları çökert: özsermaye -%10'un altına
    for s, p in eng.state["positions"].items():
        data.px[s] *= 0.4 if p["qty"] > 0 else 1.6
    data.t += HOUR_MS
    eng.step()
    assert eng.state["scale"] == 0.5
    assert eng.state["n_rebalances"] == 2
    g1, _ = eng.exposures(data.prices(SYMS))
    eq = eng.equity(data.prices(SYMS))
    assert g1 / eq < g0 / 1000 * 0.75


def test_sqlite_store_roundtrip(tmp_path):
    store = SQLiteCarryStore(tmp_path / "c.db")
    data = FakeData(SYMS)
    eng = CarryEngine(data, store, params())
    eng.step()
    eng2 = CarryEngine(data, SQLiteCarryStore(tmp_path / "c.db"), params())
    assert eng2.state["positions"] == eng.state["positions"]
    assert len(store.recent("carry_fills")) == 6
    assert len(store.recent("carry_equity")) == 1
    assert len(store.recent("carry_rebalances")) == 1


def test_missing_price_skips_step():
    data = FakeData(SYMS)
    eng = CarryEngine(data, MemoryCarryStore(), params())
    eng.step()
    held = next(iter(eng.state["positions"]))
    del data.px[held]
    assert eng.step() == {"skipped": True}


def test_dashboard_carry_endpoints(monkeypatch, tmp_path):
    import agents.carry_agent as ca
    import dashboard
    data = FakeData(SYMS)
    eng = CarryEngine(data, SQLiteCarryStore(tmp_path / "d.db"), params())
    eng.step()
    monkeypatch.setattr(ca, "_ENGINE", eng)
    c = dashboard.app.test_client()
    r = c.get("/api/carry")
    assert r.status_code == 200
    j = r.get_json()
    assert len(j["positions"]) == 6 and j["n_rebalances"] == 1 and len(j["fills"]) == 6
    assert c.get("/carry").status_code == 200


# ---------------- çok faktörlü karışım ----------------
def _trend_closes():
    up = [100 * (1.0005 ** j) * (1 + 0.003 * math.sin(j)) for j in range(800)]
    dn = [100 * (0.9995 ** j) * (1 + 0.003 * math.sin(j)) for j in range(800)]
    return {"UP": up, "DN": dn}


def test_tsmom_long_uptrend_short_downtrend():
    c = _trend_closes()
    vols = {s: realized_vol_ann(v, 720) for s, v in c.items()}
    w = tsmom_weights(c, vols, 24 * 28, 0.2, 2)
    assert w["UP"] > 0 and w["DN"] < 0


def test_xsmom_skips_last_day_and_ranks():
    c = {f"S{i}": [100 * ((1 + 0.0001 * i) ** j) * (1 + 0.002 * math.sin(j)) for j in range(800)] for i in range(6)}
    vols = {s: realized_vol_ann(v, 720) for s, v in c.items()}
    w = xsmom_weights(c, vols, k=2)
    assert w["S5"] > 0 and w["S4"] > 0 and w["S0"] < 0 and w["S1"] < 0
    assert "S2" not in w and "S3" not in w


def test_combine_sleeves_targets_vol_and_caps_gross():
    c = _trend_closes()
    sleeves = {"a": {"UP": 0.5}, "b": {"DN": -0.5}}
    w = combine_sleeves(sleeves, c, portfolio_target_vol=0.10, gross_cap=3.0)
    for name, sl in sleeves.items():
        s = next(iter(sl))
        v = ex_ante_vol({s: w[s]}, c)
        assert v == pytest.approx(0.10 / math.sqrt(2), rel=1e-6)
    w2 = combine_sleeves(sleeves, c, portfolio_target_vol=100.0, gross_cap=0.5)
    assert sum(abs(x) for x in w2.values()) == pytest.approx(0.5)


def test_engine_multifactor_default_sleeves():
    data = FakeData(SYMS)
    eng = CarryEngine(data, MemoryCarryStore(), params(sleeves=("trend", "xsmom", "funding")))
    eng.step()
    assert eng.state["n_rebalances"] == 1 and eng.state["positions"]
    assert set(eng._last_sleeves) == {"trend", "xsmom", "funding"}
    g, _ = eng.exposures(data.prices(SYMS))
    assert g <= 3.0 * 1000 * 1.01


def test_config_default_is_multifactor():
    import config
    assert config.CARRY_SLEEVES == ["trend", "xsmom", "funding"]


def test_smc_engine_disabled_by_default():
    import config
    assert config.ENABLE_SMC_ENGINE is False
    assert config.ENABLE_CARRY_ENGINE is True
