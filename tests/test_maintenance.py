"""Bakım: temizlik, depolama raporu, CSV dışa aktarma, yedek ve Telegram gönderimi."""
import io
import os
import sqlite3
import time
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

import config
from core import maintenance as mt


def _conn():
    c = sqlite3.connect(str(config.DB_PATH), timeout=30)
    c.row_factory = sqlite3.Row
    return c


@pytest.fixture()
def carry_rows():
    """carry_* tablolarına örnek kayıtlar (biri formül enjeksiyonu denemesi içerir)."""
    from agents.carry_agent import SQLiteCarryStore
    st = SQLiteCarryStore(config.DB_PATH)
    with _conn() as c:
        for t in ("carry_fills", "carry_equity", "carry_rebalances"):
            c.execute(f"DELETE FROM {t}")
    st.record_fill({"ts": "2026-11-19 20:58:56", "ts_ms": 1, "symbol": "BTCUSDT", "side": "SELL", "qty": 0.000283,
                    "price": 1.5, "notional": 17.56, "fee": 0.0088, "realized_pnl": -1.25, "reason": "=HACK()"})
    st.record_equity({"ts_ms": 2, "ts": "2026-11-19 21:00:00", "equity": 999.6, "gross_exposure": 576.4,
                      "net_exposure": 28.7, "n_positions": 14, "scale": 1.0})
    st.record_rebalance({"ts": "2026-11-19 20:58:56", "ts_ms": 1, "equity": 999.6, "n_orders": 14,
                         "turnover_usdt": 576.0, "fees": 0.29, "scale": 1.0, "reason": "ilk_kurulum", "signal": {"BTCUSDT": 0.01}})
    return st


def _seed_logs(old_n=3, new_n=2):
    old = "2020-01-01 00:00:00"
    new = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        c.execute("DELETE FROM scanner_logs")
        c.execute("DELETE FROM committee_debates")
        for i in range(old_n):
            c.execute("INSERT INTO scanner_logs (created_at, time_str, symbol, status, reason) VALUES (?,?,?,?,?)",
                      (old, "00:00", f"OLD{i}", "ELENDİ", "x" * 200))
            c.execute("INSERT INTO committee_debates (created_at, time_str, symbol, direction, consensus_verdict, "
                      "consensus_score, decision_summary, debate_json) VALUES (?,?,?,?,?,?,?,?)",
                      (old, "00:00", f"OLD{i}", "LONG", "RED", 1.0, "s", "{}"))
        for i in range(new_n):
            c.execute("INSERT INTO scanner_logs (created_at, time_str, symbol, status, reason) VALUES (?,?,?,?,?)",
                      (new, "00:00", f"NEW{i}", "ELENDİ", "y"))


# ---------------- temizlik ----------------
def test_cleanup_removes_only_old_diagnostic_rows(carry_rows):
    _seed_logs(old_n=12, new_n=2)
    res = mt.cleanup_old_data(retention_days=30, vacuum_min_mb=0, batch=5)  # küçük parti: döngü de test edilir
    with _conn() as c:
        left = [r["symbol"] for r in c.execute("SELECT symbol FROM scanner_logs")]
        assert sorted(left) == ["NEW0", "NEW1"]
        assert c.execute("SELECT COUNT(*) FROM committee_debates").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM carry_fills").fetchone()[0] == 1   # işlem geçmişi korunur
    assert res["deleted_rows"]["scanner_logs"] == 12 and res["deleted_rows"]["committee_debates"] == 12
    assert res["deleted_total"] == 24
    assert res["error"] is None
    assert res["vacuumed"] is True                # eşik 0: sıkıştırma gerçekten çalışır
    assert mt.load_state()["last_cleanup"]["deleted_total"] == 24


def test_cleanup_removes_old_chart_files():
    cd = config.CHARTS_DIR
    old, new = cd / "old_chart.png", cd / "new_chart.png"
    old.write_bytes(b"x" * 1000)
    new.write_bytes(b"y" * 1000)
    t = time.time() - 40 * 86400
    os.utime(old, (t, t))
    res = mt.cleanup_old_data(retention_days=30, vacuum_min_mb=10_000)
    assert not old.exists() and new.exists()
    assert res["charts_removed"] == 1 and res["vacuumed"] is False
    new.unlink()


def test_storage_report_shape(carry_rows):
    rep = mt.storage_report(use_cache=False)
    assert rep["limit_mb"] == config.STORAGE_LIMIT_MB
    assert {p["name"] for p in rep["parts"]} >= {"Veritabanı", "Grafik resimleri", "Yedekler"}
    names = {t["table"]: t for t in rep["tables"]}
    assert names["carry_fills"]["rows"] == 1 and names["carry_fills"]["kind"] == "v3"
    assert names["scanner_logs"]["kind"] == "log"


# ---------------- CSV ----------------
def _read_zip(data):
    return zipfile.ZipFile(io.BytesIO(data))


def test_export_tr_format_excel_friendly(carry_rows):
    z = _read_zip(mt.build_export_zip("tr", positions=[{"symbol": "ETHUSDT", "side": "SHORT", "qty": -0.03,
                                                         "avg_price": 1760.66, "price": 1754.44, "notional": -52.6,
                                                         "upnl": 0.19, "opened": "2026-11-19 20:58:56"}]))
    names = set(z.namelist())
    assert {"v3_dolumlar.csv", "v3_dengelemeler.csv", "v3_kasa_saatlik.csv", "v3_acik_pozisyonlar.csv", "OKUBENI.txt"} <= names
    raw = z.read("v3_dolumlar.csv").decode("utf-8")
    assert raw.startswith("﻿")
    header, row = raw.lstrip("﻿").strip().split("\r\n")[:2]
    assert header.split(";")[:3] == ["zaman_utc", "coin", "islem"]
    cells = row.split(";")
    assert "1,5" in cells                    # virgüllü ondalık
    assert "0,000283" in cells               # küçük sayılar bilimsel gösterime dönmez
    assert "'=HACK()" in cells               # formül enjeksiyonu etkisiz
    assert "-1,25" in cells                  # negatif sayı formül sanılmaz, sayı kalır
    pos = z.read("v3_acik_pozisyonlar.csv").decode("utf-8")
    assert "ETHUSDT;SHORT;-0,03;1760,66" in pos


def test_export_std_format(carry_rows):
    z = _read_zip(mt.build_export_zip("std"))
    raw = z.read("v3_dolumlar.csv").decode("utf-8")
    assert not raw.startswith("﻿")
    row = raw.strip().split("\n")[1].split(",")
    assert "1.5" in row and "0.000283" in row


# ---------------- yedek ----------------
def test_backup_sanitizes_secrets_and_prunes(carry_rows, monkeypatch):
    _seed_logs(old_n=2, new_n=2)
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('gemini_api_key', 'AIza-SECRET')")
        c.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('quota_reset_utc', '2026-11-19 00:00:00')")
    for f in mt.backup_dir().glob("*.zip"):
        f.unlink()
    t0 = datetime(2026, 11, 20, 0, 20, tzinfo=timezone.utc)
    calls = {"n": 0}

    def fake_now():
        calls["n"] += 1
        return t0 + timedelta(minutes=calls["n"])
    monkeypatch.setattr(mt, "_utc_now", fake_now)
    for _ in range(3):
        b = mt.create_backup(keep=2)
    files = sorted(mt.backup_dir().glob("tradebot_yedek_*.zip"))
    assert len(files) == 2 and files[-1].name == b["file"]
    assert b["secret_keys_removed"] >= 1
    z = zipfile.ZipFile(files[-1])
    assert "trading_bot_yedek.db" in z.namelist() and "csv/v3_dolumlar.csv" in z.namelist()
    tmp = mt.backup_dir() / "_kontrol.db"
    tmp.write_bytes(z.read("trading_bot_yedek.db"))
    try:
        c = sqlite3.connect(str(tmp))
        keys = {r[0] for r in c.execute("SELECT key FROM system_state")}
        assert "gemini_api_key" not in keys and "quota_reset_utc" in keys
        assert c.execute("SELECT COUNT(*) FROM scanner_logs").fetchone()[0] == 0     # hacimli tanı kayıtları yok
        assert c.execute("SELECT COUNT(*) FROM carry_fills").fetchone()[0] == 1       # işlem geçmişi var
        c.close()
    finally:
        tmp.unlink()
    # Canlı DB'deki anahtar yerinde kalır (yalnızca kopya temizlenir)
    with _conn() as c:
        assert c.execute("SELECT value FROM system_state WHERE key='gemini_api_key'").fetchone()[0] == "AIza-SECRET"
        c.execute("DELETE FROM system_state WHERE key='gemini_api_key'")


class FakeNotifier:
    def __init__(self, ok=True, has=True):
        self.has_telegram = has
        self.ok = ok
        self.docs = []

    def send_document(self, path, caption=""):
        self.docs.append((path, caption))
        return self.ok

    def send_text_message(self, text):
        return True


def test_run_backup_telegram_states(carry_rows):
    n = FakeNotifier()
    b = mt.run_backup(n, send_telegram=True)
    assert b["telegram"] == "gonderildi" and len(n.docs) == 1 and "Günlük yedek" in n.docs[0][1]
    assert mt.load_state()["last_backup"]["telegram"] == "gonderildi"
    assert "path" not in mt.load_state()["last_backup"]
    assert mt.run_backup(FakeNotifier(has=False), send_telegram=True)["telegram"] == "telegram_ayarli_degil"
    assert mt.run_backup(FakeNotifier(ok=False), send_telegram=True)["telegram"] == "hata"


def test_run_nightly_records_date(carry_rows):
    out = mt.run_nightly(FakeNotifier())
    assert "cleanup" in out and "backup" in out
    assert mt.load_state()["last_run_date"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")


def test_next_run_and_due_now(monkeypatch):
    d = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)
    assert mt.next_run(d) == "2026-11-21 00:20:00"
    assert mt.next_run(d.replace(hour=0, minute=5)) == "2026-11-20 00:20:00"
    monkeypatch.setattr(mt, "load_state", lambda: {"last_run_date": "2026-11-19"})
    assert mt.due_now(d) is True
    monkeypatch.setattr(mt, "load_state", lambda: {"last_run_date": "2026-11-20"})
    assert mt.due_now(d) is False


def test_is_due():
    d = datetime(2026, 11, 20, 0, 10, tzinfo=timezone.utc)
    assert mt.is_due(d, None, 0, 20) is False                       # saatinden önce
    assert mt.is_due(d.replace(minute=25), None, 0, 20) is True
    assert mt.is_due(d.replace(minute=25), "2026-11-20", 0, 20) is False  # bugün zaten çalıştı
    assert mt.is_due(d.replace(hour=15), "2026-11-19", 0, 20) is True     # deploy sonrası telafi


# ---------------- Telegram ----------------
def test_send_document_and_token_redaction(tmp_path, monkeypatch, capsys):
    import agents.notifier_agent as na
    f = tmp_path / "y.zip"
    f.write_bytes(b"PK")
    sent = {}

    class R:
        status_code = 200
        text = "ok"

    def fake_post(url, data=None, files=None, timeout=None):
        sent.update(url=url, data=data, name=files["document"][0])
        return R()
    monkeypatch.setattr(na.requests, "post", fake_post)
    n = na.NotifierAgent(bot_token="123:SECRETTOKEN", chat_id="42")
    assert n.send_document(str(f), "cap") is True
    assert sent["url"].endswith("/sendDocument") and sent["data"]["chat_id"] == "42" and sent["name"] == "y.zip"

    def boom(url, data=None, files=None, timeout=None):
        raise RuntimeError(f"Max retries exceeded with url: {url}")
    monkeypatch.setattr(na.requests, "post", boom)
    monkeypatch.setattr(na.time, "sleep", lambda s: None)
    assert n.send_document(str(f), "cap") is False
    out = capsys.readouterr().out
    assert "SECRETTOKEN" not in out and "***" in out


# ---------------- uç noktalar ----------------
def test_endpoints(carry_rows, monkeypatch):
    import dashboard
    monkeypatch.setattr(dashboard, "_pin_fail_log", {})
    c = dashboard.app.test_client()
    pin = {"X-Admin-Pin": os.environ["ADMIN_PIN"]}
    j = c.get("/api/system/storage").get_json()
    assert "used_mb" in j and "maintenance" in j and "backup" in j
    r = c.get("/api/export/records.zip")
    assert r.status_code == 200 and r.mimetype == "application/zip"
    assert "attachment" in r.headers["Content-Disposition"]
    assert "v3_dolumlar.csv" in _read_zip(r.data).namelist()
    assert c.post("/api/system/cleanup").status_code == 401
    assert c.post("/api/system/cleanup", headers=pin).status_code == 202
    for _ in range(200):
        if not mt.is_running():
            break
        time.sleep(0.05)
    mt.create_backup(keep=3)
    assert c.get("/api/system/backup/latest").status_code == 401
    r = c.get("/api/system/backup/latest", headers=pin)
    assert r.status_code == 200 and r.data[:2] == b"PK"
