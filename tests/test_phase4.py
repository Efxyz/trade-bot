"""Faz 4: kod temizliği regresyonları."""


def test_equity_matches_performance_stats(clean_signals):
    from core.database import save_signal, update_signal_status, get_current_equity, get_performance_stats
    from core.timeutil import utc_now_str
    for sym, pnl in (("AUSDT", 10.0), ("BUSDT", -5.0)):
        sid = save_signal({"symbol": sym, "direction": "LONG", "leverage": 10, "entry_min": 1, "entry_max": 1,
                           "actual_entry_price": 1, "stop_loss": 0.99, "take_profit_1": 1.02, "take_profit_2": 1.03,
                           "risk_reward": 2, "risk_grade": "Grade A", "allocated_margin_usdt": 100.0, "risk_usd": 11})
        update_signal_status(sid, {"status": "HIT_SL", "simulated_pnl_pct": pnl, "closed_at": utc_now_str()})
    assert get_current_equity() == 1005.0
    assert get_performance_stats()["portfolio_balance"] == 1005.0


def test_template_loaded_from_file():
    import dashboard
    assert dashboard.HTML_OFFICE_TEMPLATE.lstrip().lower().startswith("<!doctype html")
    assert "adminFetch" in dashboard.HTML_OFFICE_TEMPLATE


def test_index_renders(monkeypatch):
    import dashboard
    dashboard.app.config["TESTING"] = True
    r = dashboard.app.test_client().get("/")
    assert r.status_code == 200 and b"<html" in r.data.lower()


def test_legacy_db_functions_still_exported():
    import core.database as db
    for name in ("get_fast_performance_stats", "get_super_fast_performance_stats", "close_all_fast_positions_db"):
        assert callable(getattr(db, name))


def test_dead_engine_files_removed():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    for f in ("fast_engine.py", "super_fast_engine.py", "agents/fast_ta_agent.py", "agents/super_fast_tracker_agent.py"):
        assert not (root / f).exists()
