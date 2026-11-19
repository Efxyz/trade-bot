"""Faz 0: güvenlik, risk notu puanı, Basamak 1 muhasebesi ve öz-kalibrasyon kilidi."""
import pytest


@pytest.fixture()
def app_client():
    import dashboard
    dashboard.ADMIN_PIN = "test-pin-123456"
    dashboard._pin_fail_log.clear()
    dashboard.app.config["TESTING"] = True
    return dashboard.app.test_client()


@pytest.mark.parametrize("path", [
    "/api/scan", "/api/tuning/run-autonomous", "/api/ai/chat",
    "/api/ai/analyze", "/api/ai/review-positions", "/api/close-all-positions",
])
def test_protected_endpoints_reject_without_pin(app_client, path):
    r = app_client.post(path, json={})
    assert r.status_code == 401


def test_news_investigate_requires_pin(app_client):
    assert app_client.get("/api/news/investigate?symbol=BTC").status_code == 401


def test_pin_bruteforce_lockout(app_client):
    for _ in range(5):
        assert app_client.post("/api/close-all-positions", headers={"X-Admin-Pin": "wrong"}).status_code == 401
    # Doğru PIN bile kilit süresince reddedilir
    r = app_client.post("/api/close-all-positions", headers={"X-Admin-Pin": "test-pin-123456"})
    assert r.status_code == 429


def test_pin_query_string_not_accepted(app_client):
    assert app_client.post("/api/close-all-positions?pin=test-pin-123456").status_code == 401


def test_missing_or_weak_pin_disables_admin(monkeypatch):
    import dashboard
    for weak in ["", "6004", "12345"]:
        monkeypatch.setenv("ADMIN_PIN", weak)
        assert dashboard._load_admin_pin() is None
    monkeypatch.setenv("ADMIN_PIN", "strong-pin-xyz")
    assert dashboard._load_admin_pin() == "strong-pin-xyz"


def test_admin_disabled_returns_503(app_client):
    import dashboard
    dashboard.ADMIN_PIN = None
    r = app_client.post("/api/close-all-positions", headers={"X-Admin-Pin": "anything"})
    assert r.status_code == 503


def test_tuning_get_is_read_only(app_client, monkeypatch):
    from core.self_tuning_engine import SelfTuningEngine
    called = []
    monkeypatch.setattr(SelfTuningEngine, "run_autonomous_training_cycle", classmethod(lambda cls, *a, **k: called.append(1)))
    r = app_client.get("/api/tuning")
    assert r.status_code == 200 and "current_params" in r.get_json()
    assert not called


@pytest.mark.parametrize("grade,score", [
    ("Grade A+ (20x Sniper / Ultra Dar Stop)", 20.0),
    ("Grade A (10x Düşük Risk / İstikrarlı Scalp)", 16.0),
    ("Grade B (10x Orta Risk / Standart Fırsat)", 12.0),
    ("Grade C (10x Yüksek Risk / Spekülatif Şişme)", 8.0),
    ("Grade A (Piyasa-Nötr Pair)", 16.0),
    ("", 10.0),
])
def test_grade_to_score(grade, score):
    from main import grade_to_score
    assert grade_to_score(grade) == score


def test_self_tuning_frozen_ignores_file_and_never_writes(tmp_path, monkeypatch):
    import json
    import config
    import core.self_tuning_engine as ste
    f = tmp_path / "adaptive.json"
    f.write_text(json.dumps({"schema_version": 2, "min_confluence_score": 60}), encoding="utf-8")
    monkeypatch.setattr(ste, "ADAPTIVE_CONFIG_PATH", f)
    params = ste.SelfTuningEngine.get_current_params()
    assert params["min_confluence_score"] == config.MIN_CONFLUENCE_SCORE
    before = f.read_text(encoding="utf-8")
    ste.SelfTuningEngine.run_autonomous_training_cycle(min_trades_required=0, auto_commit=True)
    assert f.read_text(encoding="utf-8") == before
