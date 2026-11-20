"""Canlı ↔ backtest takibi (gölge backtest) testleri."""
import json
import math
import random
from dataclasses import replace

import pytest

from agents import carry_shadow as cs
from agents.carry_agent import CarryEngine, MemoryCarryStore, SQLiteCarryStore, HOUR_MS, _fmt
from test_carry import SYMS, params as carry_params

DAY = 24 * HOUR_MS
T_LIVE = 1_700_006_400_000 - (1_700_006_400_000 % DAY) + 40 * DAY   # UTC gece yarısı; öncesinde 40 günlük geçmiş


def make_series(syms=SYMS, days_before=40, days_after=12, seed=7):
    """Rastgele yürüyüş fiyatlar (farklı eğilimler) ve Binance gibi saat başından 1 ms sonra yazılan fonlama olayları."""
    rnd = random.Random(seed)
    start = T_LIVE - days_before * DAY
    n = (days_before + days_after) * 24
    kl, fu = {}, {}
    for i, s in enumerate(syms):
        p, drift = 100.0 + 10 * i, (i - len(syms) / 2) * 0.00004
        rows = []
        for h in range(n):
            p *= math.exp(drift + rnd.gauss(0, 0.006))
            rows.append([start + h * HOUR_MS, p])
        kl[s] = rows
        fu[s] = [[start + j * 8 * HOUR_MS + 1, rnd.gauss(0.0001 * (i - 6), 0.00005)] for j in range(n // 8)]
    return kl, fu


def fake_fetch(kl, fu, calls=None):
    def f(symbols, start_ms, end_ms, funding_end_ms=None):
        if calls is not None:
            calls.append((tuple(symbols), start_ms, end_ms, funding_end_ms))
        fe = end_ms if funding_end_ms is None else funding_end_ms
        k = {s: [r for r in kl[s] if r[0] >= start_ms and r[0] + HOUR_MS <= end_ms] for s in symbols if s in kl}
        u = {s: [r for r in fu[s] if start_ms <= r[0] <= fe] for s in symbols if s in fu}
        return k, u
    return f


def base_params(**kw):
    p = carry_params(sleeves=("trend", "xsmom", "funding"), tranches=7, portfolio_target_vol=0.20,
                    dd_cut=-0.20, dd_restore=-0.10)
    return replace(p, **kw)


def run_live(tmp_path, kl, fu, t0=T_LIVE, days=5, skip=None, live_params=None, change_at=None, base=None,
             offset_ms=30_000):
    """
    'Canlı' motor: tüm seriler üzerinde (yalnızca kapanmış mumları görür) saatte bir, saat başından offset_ms sonra adım atar.
    change_at anında risk %10 -> %20 (deploy gibi). skip=(a, b): bu aralıkta adım yok (kesinti).
    """
    base = base or base_params()
    data = cs.SeriesData(kl, fu)
    store = SQLiteCarryStore(tmp_path / "live.db")
    eng = CarryEngine(data, store, live_params or cs.params_for(base, 0.10))
    times = [t0] + [h + offset_ms for h in range(cs.floor_hour(t0) + HOUR_MS, t0 + days * DAY + 1, HOUR_MS)]
    for t in times:
        if skip and skip[0] <= t < skip[1]:
            continue
        if change_at is not None and t >= change_at and eng.p.portfolio_target_vol != base.portfolio_target_vol:
            eng.p = replace(base, fee_rate=eng.p.fee_rate)
        data.t = t
        eng.step()
    return eng, store, times[-1]


# ---------------- veri ----------------
def test_series_data_matches_backtest_sim_data(tmp_path, monkeypatch):
    import backtest.carry_backtest as bt
    kl, fu = make_series(SYMS[:3])
    for s in kl:
        (tmp_path / f"{s}_1h.json").write_text(json.dumps([[t, c, c, c, c, 0.0] for t, c in kl[s]]))
        (tmp_path / f"{s}_funding.json").write_text(json.dumps(fu[s]))
    monkeypatch.setattr(bt, "CACHE", tmp_path)
    sim, ser = bt.SimCarryData(list(kl)), cs.SeriesData(kl, fu)
    for t in (T_LIVE, T_LIVE + 30 * 60_000, T_LIVE + 5 * DAY + 60_000):
        sim.t = ser.t = t
        assert ser.prices(list(kl)) == sim.prices(list(kl))
        for s in kl:
            assert ser.hourly_closes(s, 721) == sim.hourly_closes(s, 721)
            assert ser.funding_history(s, t - 7 * DAY + 1, t) == sim.funding_history(s, t - 7 * DAY + 1, t)


def test_series_data_spot_prices_only_at_given_time():
    kl, fu = make_series(SYMS[:2])
    d = cs.SeriesData(kl, fu, spot={T_LIVE + 1234: {SYMS[0]: 77.0}})
    d.t = T_LIVE + 1234
    p = d.prices(SYMS[:2])
    assert p[SYMS[0]] == 77.0 and p[SYMS[1]] == kl[SYMS[1]][40 * 24 - 1][1]
    d.t = T_LIVE + HOUR_MS
    assert d.prices(SYMS[:1])[SYMS[0]] != 77.0


def test_step_times_start_then_hourly_with_offset():
    t = cs.step_times(T_LIVE + 20 * 60_000, T_LIVE + 3 * HOUR_MS)
    assert t == [T_LIVE + 20 * 60_000] + [T_LIVE + h * HOUR_MS + cs.STEP_OFFSET_MS for h in (1, 2, 3)]
    assert cs.step_times(T_LIVE, T_LIVE)[0] == T_LIVE


# ---------------- uçtan uca ----------------
def test_shadow_reproduces_live_engine_exactly_including_risk_change(tmp_path):
    kl, fu = make_series()
    base = base_params()
    change = T_LIVE + 2 * DAY + 13 * HOUR_MS + 45 * 60_000      # gün ortasında deploy
    live, store, last = run_live(tmp_path, kl, fu, change_at=change, base=base)
    assert live.state["risk_changes"] and live.state["risk_changes"][0]["from"] == 0.10
    calls = []
    res = cs.run_shadow(store=store, now_ms=last + 10 * 60_000, fetch=fake_fetch(kl, fu, calls), base_params=base)
    assert res["status"] == "ok" and res["verdict"] == "uyumlu", res.get("reasons")
    assert abs(res["diff_pp"]) < 1e-9 and res["max_gap_pp"] < 1e-9
    assert res["live"]["n_rebalances"] == res["shadow"]["n_rebalances"] == 5
    assert res["live"]["n_fills"] == res["shadow"]["n_fills"] > 0
    assert res["live"]["fees"] == pytest.approx(res["shadow"]["fees"], abs=1e-9)
    assert res["live"]["funding"] == pytest.approx(res["shadow"]["funding"], abs=1e-9)
    assert res["positions"]["side_ratio"] == 1.0 and res["positions"]["weight_gap_pct"] < 1e-6
    assert res["rebalance_days"] == {"missed": [], "extra": [], "late": []}
    assert res["risk_changes"][0]["to"] == 0.20 and res["params"]["target_vol"] == 0.20
    # Fonlama, son adımdaki ödemeyi (saat başı + 1 ms) kapsayacak kadar ileriden istenir
    assert calls[0][3] == calls[0][2] + cs.STEP_OFFSET_MS
    assert len(res["curve"]) == res["hours"] and all(c[1] == pytest.approx(c[2], abs=0.006) for c in res["curve"])
    assert cs.load_result(store)["run_at"] == res["run_at"]           # carry_state'e kaydedildi
    assert store.load()["capital"] == 1000.0                          # canlı durum bozulmadı


def test_shadow_off_hour_start_uses_spot_prices_and_caches_them(tmp_path):
    kl, fu = make_series()
    base = base_params()
    t0 = T_LIVE + 20 * 60_000 + 7_000
    live, store, last = run_live(tmp_path, kl, fu, t0=t0, days=3, live_params=base, base=base)
    ref = cs.SeriesData(kl, fu)
    ref.t = t0
    spot_calls = []

    def spot(symbols, t_ms):
        spot_calls.append(t_ms)
        return ref.prices(symbols)

    res = cs.run_shadow(store=store, now_ms=last + 10 * 60_000, fetch=fake_fetch(kl, fu), base_params=base, fetch_spot=spot)
    assert res["verdict"] == "uyumlu" and abs(res["diff_pp"]) < 1e-9, res.get("reasons")
    assert spot_calls == [t0] and res["live_start_ms"] == t0 and res["spot_t0"]
    res2 = cs.run_shadow(store=store, now_ms=last + 20 * 60_000, fetch=fake_fetch(kl, fu), base_params=base, fetch_spot=spot)
    assert res2["status"] == "ok" and spot_calls == [t0]                # ikinci koşu kayıtlı fiyatları kullanır


def test_shadow_flags_missed_rebalance_day(tmp_path):
    kl, fu = make_series()
    base = base_params()
    skip = (T_LIVE + 2 * DAY + 22 * HOUR_MS, T_LIVE + 4 * DAY + HOUR_MS)   # 3. günün dengelemesi kaçar
    live, store, last = run_live(tmp_path, kl, fu, skip=skip, live_params=base, base=base)
    res = cs.run_shadow(store=store, now_ms=last + 10 * 60_000, fetch=fake_fetch(kl, fu), base_params=base)
    day3 = _fmt(T_LIVE + 3 * DAY)[:10]
    assert res["rebalance_days"]["missed"] == [day3]
    assert res["rebalance_days"]["late"]                                # 4. gün dengelemesi geç yapıldı
    assert res["verdict"] in ("izle", "sapma")
    assert any("Dengeleme yapılmayan gün" in r for r in res["reasons"])


def test_shadow_flags_accounting_difference(tmp_path):
    kl, fu = make_series()
    base = base_params()
    live, store, last = run_live(tmp_path, kl, fu, live_params=replace(base, fee_rate=0.02), base=base)
    res = cs.run_shadow(store=store, now_ms=last + 10 * 60_000, fetch=fake_fetch(kl, fu), base_params=base)
    assert res["live"]["fees"] > 10 * res["shadow"]["fees"] > 0
    assert res["diff_pp"] < -1.0 and res["verdict"] in ("izle", "sapma")


def test_shadow_waits_for_first_full_hour(tmp_path):
    kl, fu = make_series()
    base = base_params()
    data = cs.SeriesData(kl, fu)
    store = MemoryCarryStore()
    eng = CarryEngine(data, store, base)
    data.t = T_LIVE + 2 * 60_000
    eng.step()
    called = []
    res = cs.run_shadow(store=store, now_ms=T_LIVE + 4 * 60_000, fetch=lambda *a, **k: called.append(1), base_params=base)
    assert res["status"] == "ok" and res["verdict"] == "veri_az" and not called


def test_failed_run_keeps_previous_result_and_backs_off(tmp_path):
    kl, fu = make_series()
    base = base_params()
    live, store, last = run_live(tmp_path, kl, fu, days=2, live_params=base, base=base)
    good = cs.run_shadow(store=store, now_ms=last + 10 * 60_000, fetch=fake_fetch(kl, fu), base_params=base)

    def boom(*a, **k):
        raise cs.ShadowDataError("Binance hız sınırı (429)")

    now = last + 7 * HOUR_MS
    bad = cs.run_shadow(store=store, now_ms=now, fetch=boom, base_params=base)
    assert bad["status"] == "hata" and "429" in bad["error"]
    kept = cs.load_result(store)
    assert kept["run_at"] == good["run_at"] and kept["verdict"] == good["verdict"]
    assert "429" in kept["last_error"]["error"]
    assert not cs.is_due(kept, now + 10 * 60_000, None)                 # 30 dk bekler
    assert cs.is_due(kept, now + 31 * 60_000, None)
    assert not cs.is_running()


def test_is_due_rules():
    run = T_LIVE
    res = {"run_ms": run, "end_ms": cs.floor_hour(run - 5 * 60_000)}
    assert cs.is_due(None, run, None)
    assert not cs.is_due(res, run + HOUR_MS, None, every_h=6)
    assert cs.is_due(res, run + 6 * HOUR_MS, None, every_h=6)
    reb = res["end_ms"] + 2 * HOUR_MS + 23_000                          # karşılaştırmada olmayan yeni dengeleme
    assert not cs.is_due(res, reb + 5 * 60_000, reb, every_h=6)          # 10 dk dolmadı
    assert cs.is_due(res, reb + 11 * 60_000, reb, every_h=6)
    covered = res["end_ms"] + 23_000                                     # aynı saatteki dengeleme zaten dahil
    assert not cs.is_due(res, run + 2 * HOUR_MS, covered, every_h=6)


# ---------------- Binance çekimi ----------------
class _Resp:
    def __init__(self, data, code=200):
        self._d, self.status_code, self.text = data, code, json.dumps(data)

    def json(self):
        return self._d


class _Sess:
    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params)))
        return self.handler(url, params)


def test_fetch_market_paginates_and_keeps_only_closed_bars():
    end = T_LIVE + 3000 * HOUR_MS
    start = T_LIVE

    def handler(url, p):
        if url.endswith("/klines"):
            n = min(1500, (p["endTime"] - p["startTime"]) // HOUR_MS + 1)
            return _Resp([[p["startTime"] + i * HOUR_MS, "1", "1", "1", str(1 + i), "0", 0, "0"] for i in range(n)])
        rows = [{"fundingTime": t, "fundingRate": "0.0001"} for t in range(p["startTime"], p["endTime"] + 1, 8 * HOUR_MS)]
        return _Resp(rows[:1000])

    sess = _Sess(handler)
    kl, fu = cs.fetch_market(["BTCUSDT"], start, end, session=sess, pause_s=0, funding_end_ms=end + 60_000)
    ts = [r[0] for r in kl["BTCUSDT"]]
    assert ts[0] == start and ts[-1] == end - HOUR_MS and len(ts) == 3000 and len(set(ts)) == 3000
    assert sum(1 for u, _ in sess.calls if u.endswith("/klines")) == 2
    assert all(r[0] <= end + 60_000 for r in fu["BTCUSDT"]) and len(fu["BTCUSDT"]) == 376   # iki uç dahil


def test_fetch_market_raises_on_rate_limit_without_retrying():
    sess = _Sess(lambda url, p: _Resp({"code": -1003}, 429))
    with pytest.raises(cs.ShadowDataError):
        cs.fetch_market(["BTCUSDT"], T_LIVE, T_LIVE + 10 * HOUR_MS, session=sess, pause_s=0)
    assert len(sess.calls) == 1


def test_fetch_spot_prices_uses_minute_bar():
    t = T_LIVE + 5 * 60_000 + 50_000
    sess = _Sess(lambda url, p: _Resp([[p["startTime"], "10.0", "11", "9", "10.5", "0"]]))
    out = cs.fetch_spot_prices(["BTCUSDT"], t, session=sess, pause_s=0)
    assert out == {"BTCUSDT": 10.5} and sess.calls[0][1]["interval"] == "1m"
    assert cs.fetch_spot_prices(["BTCUSDT"], t - 40_000, session=sess, pause_s=0) == {"BTCUSDT": 10.0}


# ---------------- panel ve Telegram ----------------
def test_shadow_api_endpoints(tmp_path, monkeypatch):
    import agents.carry_agent as ca
    import dashboard
    kl, fu = make_series()
    base = base_params()
    live, store, last = run_live(tmp_path, kl, fu, days=2, live_params=base, base=base)
    monkeypatch.setattr(ca, "_ENGINE", live)
    c = dashboard.app.test_client()
    assert c.get("/api/carry/shadow").get_json()["status"] == "yok"
    cs.run_shadow(store=store, now_ms=last + 10 * 60_000, fetch=fake_fetch(kl, fu), base_params=base)
    j = c.get("/api/carry/shadow").get_json()
    assert j["verdict"] == "uyumlu" and j["running"] is False and j["enabled"] is True and j["curve"]
    dashboard._pin_fail_log.clear()                 # önceki testlerin hatalı PIN denemeleri kilide yol açmasın
    assert c.post("/api/carry/shadow/run").status_code == 401
    monkeypatch.setattr(cs, "run_in_background", lambda: True)
    r = c.post("/api/carry/shadow/run", headers={"X-Admin-Pin": "test-pin-123456"})
    assert r.status_code == 202
    home = c.get("/").get_data(as_text=True)
    assert "/api/carry/shadow" in home and "Canlı ↔ Backtest takibi" in home


def test_tracking_line_in_daily_report(tmp_path):
    from agents import v3_telegram as tg
    kl, fu = make_series()
    base = base_params()
    live, store, last = run_live(tmp_path, kl, fu, days=2, live_params=base, base=base)
    assert "Backtest takibi" not in tg.daily_report_message(live, final=True)
    res = cs.run_shadow(store=store, now_ms=last + 10 * 60_000, fetch=fake_fetch(kl, fu), base_params=base)
    msg = tg.daily_report_message(live, final=True)
    assert "Backtest takibi: ✅ Uyumlu" in msg and "fark 0.00 puan" in msg
    assert msg.count("*") % 2 == 0 and msg.count("`") % 2 == 0 and "_" not in msg
    bad = dict(res, verdict="sapma", diff_pp=-2.5)
    line = tg.tracking_line(bad, last)
    assert "🔴 Sapma var" in line and "−2.50 puan" in line and "panelde" in line
    assert tg.tracking_line(res, res["run_ms"] + 27 * HOUR_MS) is None  # bayat sonuç gösterilmez
    assert tg.tracking_line({"status": "ok", "run_ms": last, "verdict": "veri_az"}, last) == "🧪 Backtest takibi: veri birikiyor"
