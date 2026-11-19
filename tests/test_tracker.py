"""Faz 1b: Gerçekçi takip (fitil temasları, kayma, muhafazakâr sıralama, Basamak 1 muhasebesi, fonlama)."""
from datetime import datetime

import pytest

import core.binance_streamer as streamer
from agents.tracker_agent import CounterfactualTrackerAgent
from config import ESTIMATED_SLIPPAGE_PCT, BINANCE_ROUNDTRIP_FEE_PCT


class FakeClient:
    def __init__(self, last_price=100.0, funding=0.0):
        self.last_price = last_price
        self.funding = funding

    def get_24hr_tickers(self):
        return {"TESTUSDT": {"symbol": "TESTUSDT", "lastPrice": self.last_price}}

    def get_klines(self, *a, **k):
        return []

    def get_funding_rate(self, symbol):
        return {"lastFundingRate": self.funding}


@pytest.fixture()
def tracker(monkeypatch):
    monkeypatch.setattr(CounterfactualTrackerAgent, "generate_outcome_chart", lambda *a, **k: "")
    import core.reflection as refl
    monkeypatch.setattr(refl.ReflectorEngine, "reflect_on_trade", staticmethod(lambda d: {"lesson": "test"}))
    streamer._TICK_EXTREMES.clear()
    streamer._LIVE_PRICES.clear()
    return CounterfactualTrackerAgent(FakeClient())


def _open(direction="LONG", entry=100.0, sl=99.0, tp1=102.0, tp2=103.0, margin=100.0):
    from core.database import save_signal
    return save_signal({
        "symbol": "TESTUSDT", "direction": direction, "leverage": 10, "entry_min": entry, "entry_max": entry,
        "actual_entry_price": entry, "stop_loss": sl, "take_profit_1": tp1, "take_profit_2": tp2,
        "risk_reward": 2.0, "risk_grade": "Grade A", "allocated_margin_usdt": margin, "risk_usd": 11.0,
        "timeframe": "15m",
    })


def _row(sid):
    from core.database import get_db_connection
    return dict(get_db_connection().execute("SELECT * FROM signals WHERE id=?", (sid,)).fetchone())


def _ticks(*prices):
    for p in prices:
        streamer._record_tick_for_test("TESTUSDT", p)


def test_wick_through_stop_is_caught(clean_signals, tracker):
    sid = _open()
    _ticks(100.5, 98.9, 100.2)  # fitil SL'i deldi, fiyat geri döndü
    res = tracker.update_tracked_trades(evaluate_shadows=False)
    r = _row(sid)
    assert r["status"] == "HIT_SL" and len(res) == 1
    expected_exit = 99.0 * (1 - ESTIMATED_SLIPPAGE_PCT / 100)
    assert r["exit_price"] == pytest.approx(expected_exit)
    raw = (expected_exit - 100) / 100
    assert r["simulated_pnl_pct"] == pytest.approx(round(raw * 1000 - BINANCE_ROUNDTRIP_FEE_PCT * 10, 2), abs=0.02)


def test_no_close_when_wick_stays_above_stop(clean_signals, tracker):
    sid = _open()
    _ticks(100.2, 99.3, 100.1)
    tracker.update_tracked_trades(evaluate_shadows=False)
    assert _row(sid)["status"] == "ACTIVE"


def test_tp_and_sl_same_interval_conservative_stop(clean_signals, tracker):
    sid = _open()
    _ticks(102.5, 98.5, 100.0)
    tracker.update_tracked_trades(evaluate_shadows=False)
    r = _row(sid)
    assert r["status"] == "HIT_SL"
    assert int(r["partial_tp_taken"] or 0) == 0


def test_short_wick_stop(clean_signals, tracker):
    sid = _open(direction="SHORT", sl=101.0, tp1=98.0, tp2=97.0)
    _ticks(99.8, 101.2, 100.0)
    tracker.update_tracked_trades(evaluate_shadows=False)
    r = _row(sid)
    assert r["status"] == "HIT_SL"
    assert r["exit_price"] == pytest.approx(101.0 * (1 + ESTIMATED_SLIPPAGE_PCT / 100))


def test_step1_partial_profit_is_real_not_floored(clean_signals, tracker, legacy_ladder):
    sid = _open()
    _ticks(100.55, 100.35)  # tepe tetiği (+%0.50) geçti, anlık +%0.35
    tracker.update_tracked_trades(evaluate_shadows=False)
    r = _row(sid)
    assert int(r["partial_tp_taken"]) == 2 and int(r["ladder_step"]) == 1
    exec_pct = 0.35
    expected = round(100.0 * 0.35 * ((exec_pct * 10 - BINANCE_ROUNDTRIP_FEE_PCT * 10) / 100), 2)
    assert r["realized_pnl_usd"] == pytest.approx(expected, abs=0.011)
    assert expected < 100.0 * 0.35 * 0.03  # eski max(3.0) tabanı bu değeri şişirirdi
    assert r["status"] == "ACTIVE_BE"  # yeni stop (-%0.10) anlık fiyatın altında: pozisyon açık kalır


def test_gap_without_ticks_uses_worse_price(clean_signals, monkeypatch):
    monkeypatch.setattr(CounterfactualTrackerAgent, "generate_outcome_chart", lambda *a, **k: "")
    import core.reflection as refl
    monkeypatch.setattr(refl.ReflectorEngine, "reflect_on_trade", staticmethod(lambda d: {"lesson": "t"}))
    streamer._TICK_EXTREMES.clear()
    streamer._LIVE_PRICES.clear()
    t = CounterfactualTrackerAgent(FakeClient(last_price=97.0))  # WS yok, REST fiyatı stopun çok altında
    sid = _open()
    t.update_tracked_trades(evaluate_shadows=False)
    r = _row(sid)
    assert r["status"] == "HIT_SL"
    assert r["exit_price"] == pytest.approx(97.0 * (1 - ESTIMATED_SLIPPAGE_PCT / 100))


def test_funding_is_charged_on_close(clean_signals, monkeypatch):
    from core.database import get_db_connection
    monkeypatch.setattr(CounterfactualTrackerAgent, "generate_outcome_chart", lambda *a, **k: "")
    import core.reflection as refl
    monkeypatch.setattr(refl.ReflectorEngine, "reflect_on_trade", staticmethod(lambda d: {"lesson": "t"}))
    streamer._TICK_EXTREMES.clear()
    streamer._LIVE_PRICES.clear()
    t = CounterfactualTrackerAgent(FakeClient(funding=0.0005))
    sid = _open()
    # 17 saat önce açılmış gibi: en az 2 uzlaşma geçer
    from core.timeutil import utc_now
    from datetime import timedelta
    past = (utc_now() - timedelta(hours=17)).strftime("%Y-%m-%d %H:%M:%S")
    get_db_connection().execute("UPDATE signals SET entered_at=? WHERE id=?", (past, sid))
    get_db_connection().commit()
    _ticks(100.0, 98.0, 98.5)
    t.update_tracked_trades(evaluate_shadows=False)
    r = _row(sid)
    assert r["status"] == "HIT_SL"
    assert r["funding_usd"] >= 2 * 1000 * 0.0005 - 1e-9  # LONG pozitif fonlamada öder
    import config
    assert r["strategy_version"] == config.STRATEGY_VERSION


def test_funding_settlement_counter():
    from core.accounting import count_funding_settlements, estimate_funding_usd, apply_funding_to_pnl
    a = datetime(2026, 1, 1, 7, 30)
    assert count_funding_settlements(a, datetime(2026, 1, 1, 7, 59)) == 0
    assert count_funding_settlements(a, datetime(2026, 1, 1, 8, 0)) == 1
    assert count_funding_settlements(a, datetime(2026, 1, 2, 0, 1)) == 3
    assert estimate_funding_usd(a, datetime(2026, 1, 1, 9), 1000, 0.0001, True) == pytest.approx(0.1)
    assert estimate_funding_usd(a, datetime(2026, 1, 1, 9), 1000, 0.0001, False) == pytest.approx(-0.1)
    assert apply_funding_to_pnl(5.0, 6.0, 100.0, 1.0) == (4.0, 6.0)


def test_realtime_loop_starts_and_stops(monkeypatch):
    import main
    calls = []

    class Dummy:
        _tracker_thread = None
        import threading as _t
        _tracker_stop = _t.Event()
        notifier = None

        class tracker:
            @staticmethod
            def update_tracked_trades(notifier=None, evaluate_shadows=True):
                calls.append(evaluate_shadows)
                return []

    d = Dummy()
    th = main.TradingBotOrchestrator.start_tracker_loop(d, interval_sec=0.05)
    import time
    time.sleep(0.3)
    main.TradingBotOrchestrator.stop_tracker_loop(d)
    th.join(timeout=2)
    assert len(calls) >= 3 and all(c is False for c in calls)


def test_ladder_not_applied_when_stop_touched_same_interval(clean_signals, tracker):
    """Regresyon: fiyat aynı aralıkta stopu delip sonra +%2.5 yükselirse işlem kârla değil stopla kapanmalı."""
    sid = _open()
    _ticks(98.9, 102.5, 100.0)
    tracker.update_tracked_trades(evaluate_shadows=False)
    r = _row(sid)
    assert r["status"] == "HIT_SL"
    assert r["simulated_pnl_pct"] < 0


def test_manual_close_applies_slippage(clean_signals):
    from core.database import close_single_signal_db
    streamer._LIVE_PRICES.clear()
    sid = _open()
    streamer._record_tick_for_test("TESTUSDT", 101.0)
    closed = close_single_signal_db(sid, client=FakeClient(last_price=101.0))
    assert closed["status"] == "MANUAL_CLOSE"
    assert closed["exit_price"] == pytest.approx(101.0 * (1 - ESTIMATED_SLIPPAGE_PCT / 100))


def test_wide_ladder_default_locks_breakeven_at_1r(clean_signals, tracker):
    """v2.1 varsayılanı: +%1.0'da stop giriş+%0.15'e çekilir, kısmi satış yapılmaz."""
    sid = _open()
    _ticks(100.6)
    tracker.update_tracked_trades(evaluate_shadows=False)
    assert int(_row(sid)["ladder_step"] or 0) == 0  # +%0.6 artık basamak tetiklemez
    _ticks(101.05, 100.9)
    tracker.update_tracked_trades(evaluate_shadows=False)
    r = _row(sid)
    assert int(r["ladder_step"]) == 1 and int(r["partial_tp_taken"] or 0) == 0
    assert r["stop_loss"] == pytest.approx(100.15)
    assert float(r["allocated_margin_usdt"]) == 100.0
