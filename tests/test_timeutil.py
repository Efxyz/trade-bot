"""Faz 1a: Tüm DB zaman damgaları UTC; sunucu saat diliminden bağımsız tutarlılık."""
from datetime import datetime, timezone, timedelta


def _base_signal(**kw):
    d = {"symbol": "TESTUSDT", "direction": "LONG", "leverage": 10, "entry_min": 100.0, "entry_max": 100.1,
         "actual_entry_price": 100.0, "stop_loss": 99.0, "take_profit_1": 102.0, "take_profit_2": 103.0,
         "risk_reward": 2.0, "risk_grade": "Grade A", "allocated_margin_usdt": 100.0, "risk_usd": 11.0}
    d.update(kw)
    return d


def test_utc_helpers():
    from core.timeutil import utc_now, tr_day_start_utc_str, parse_db_ts
    real_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((utc_now() - real_utc).total_seconds()) < 2
    start = parse_db_ts(tr_day_start_utc_str())
    # TSİ 00:00 = UTC 21:00 (önceki gün)
    assert start.hour == 21 and start.minute == 0
    assert timedelta(0) <= real_utc - start <= timedelta(hours=24)


def test_entered_at_and_created_at_both_utc(clean_signals):
    from core.database import save_signal, get_db_connection
    from core.timeutil import utc_now, parse_db_ts
    sid = save_signal(_base_signal())
    row = get_db_connection().execute("SELECT created_at, entered_at FROM signals WHERE id=?", (sid,)).fetchone()
    created, entered = parse_db_ts(row["created_at"]), parse_db_ts(row["entered_at"])
    assert abs((created - entered).total_seconds()) < 5
    assert abs((utc_now() - entered).total_seconds()) < 5


def test_recently_traded_includes_partial_tp1(clean_signals):
    from core.database import save_signal, update_signal_status, get_recently_traded_symbols, get_db_connection
    sid = save_signal(_base_signal(symbol="PARTUSDT"))
    update_signal_status(sid, {"status": "ACTIVE_PARTIAL_TP1"})
    get_db_connection().execute("UPDATE signals SET entered_at='2000-01-01 00:00:00' WHERE id=?", (sid,))
    get_db_connection().commit()
    assert "PARTUSDT" in get_recently_traded_symbols(within_minutes=45)


def test_today_pnl_counts_only_today(clean_signals):
    from core.database import save_signal, update_signal_status, get_today_net_dollar_pnl
    from core.timeutil import utc_now_str, tr_day_start_utc_str, parse_db_ts
    a = save_signal(_base_signal(symbol="AUSDT"))
    update_signal_status(a, {"status": "HIT_SL", "simulated_pnl_pct": -10.0, "closed_at": utc_now_str()})
    b = save_signal(_base_signal(symbol="BUSDT"))
    yesterday = (parse_db_ts(tr_day_start_utc_str()) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    update_signal_status(b, {"status": "HIT_SL", "simulated_pnl_pct": -50.0, "closed_at": yesterday})
    assert get_today_net_dollar_pnl() == -10.0
