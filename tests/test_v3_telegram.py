"""v3 Telegram mesajları, gün hesabı, dengeleme bildirimi ve komutlar."""
import pytest

import config
from agents import v3_telegram as tg
from agents.carry_agent import CarryEngine, SQLiteCarryStore, HOUR_MS
from test_carry import FakeData, SYMS, params, T0


def _balanced(text: str) -> bool:
    """Telegram Markdown: * ve ` işaretleri çift olmalı, alt çizgi olmamalı (mesaj bozulmasın)."""
    return text.count("*") % 2 == 0 and text.count("`") % 2 == 0 and "_" not in text


class Notif:
    def __init__(self):
        self.has_telegram = True
        self.msgs = []

    def send_text_message(self, text):
        self.msgs.append(text)
        return True

    def send_document(self, path, caption=""):
        return True


@pytest.fixture()
def engine(tmp_path):
    data = FakeData(SYMS)
    n = Notif()
    eng = CarryEngine(data, SQLiteCarryStore(tmp_path / "tg.db"), params(sleeves=("trend", "xsmom", "funding"), tranches=7),
                      notifier=n)
    for _ in range(24 * 2 + 5):           # 2 gün + 5 saat: 3 dengeleme, saatlik kasa kayıtları
        eng.step()
        data.t += HOUR_MS
    data.t -= HOUR_MS
    eng.notif = n
    return eng


def test_compute_day_uses_tr_calendar_day(engine):
    snap = engine.snapshot()
    # T0 UTC gece yarısı = 03:00 TSİ. T0'ın TSİ günü: başlangıç kasası sermaye (motor o gün başladı)
    day0 = tg.today_tr(T0)
    d = tg.compute_day(engine.store, 1000.0, snap, day0, engine.data.now_ms())
    start, end = tg.day_window(day0)
    assert end - start == 24 * HOUR_MS
    fills = [f for f in engine.store.recent("carry_fills", 1000) if start <= f["ts_ms"] < end]
    assert d["n_fills"] == len(fills) > 0
    assert d["fees"] == pytest.approx(sum(f["fee"] for f in fills))
    assert d["equity_start"] == 1000.0 and d["is_today"] is False
    assert d["funding"] is not None                     # yeni sütunlar sayesinde günlük fonlama hesaplanır
    # Bugün: bitiş kasası canlı değer
    today = tg.today_tr(engine.data.now_ms())
    d2 = tg.compute_day(engine.store, 1000.0, snap, today, engine.data.now_ms())
    assert d2["is_today"] is True and d2["equity_end"] == pytest.approx(snap["equity"])


def test_messages_render_and_are_markdown_safe(engine, monkeypatch):
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "trade-bot.example.app")
    snap = engine.snapshot()
    msgs = {
        "start": tg.startup_message(snap),
        "status": tg.status_text(engine),
        "pos": tg.positions_text(engine),
        "report": tg.daily_report_message(engine, final=True),
        "help": tg.help_text(),
    }
    for name, m in msgs.items():
        assert _balanced(m), name
    assert "https://trade-bot.example.app" in msgs["start"] and "/durum" in msgs["start"]
    assert "Kasa" in msgs["status"] and "Bugün" in msgs["status"] and "LONG" in msgs["status"]
    assert msgs["pos"].count("`") == 2 * len(snap["positions"])
    assert "Gün Sonu Raporu" in msgs["report"] and "dolum" in msgs["report"]
    assert all(f"/{c}" in msgs["help"] for c, _ in tg.COMMANDS)


def test_rebalance_message_lists_changes():
    before = {"AUSDT": 1.0, "BUSDT": -2.0, "CUSDT": 3.0, "DUSDT": 1.0}
    after = {"AUSDT": 1.5, "BUSDT": 2.0, "EUSDT": -1.0, "DUSDT": 1.0}
    row = {"ts": "2026-11-20 00:00:00", "reason": "gunluk_dilim", "n_orders": 4, "turnover_usdt": 96.0, "fees": 0.07}
    m = tg.rebalance_message(row, before, after, 1012.4, {"capital": 1000.0, "scale": 1.0})
    assert "Günlük dengeleme" in m and "20.11 03:00 TSİ" in m
    assert "Açılan: E (S)" in m and "Kapanan: C" in m and "Yön değiştiren: B (S→L)" in m
    assert "Boyutu ayarlanan: 1 coin" in m        # A büyüdü, D aynı
    assert "3 LONG / 1 SHORT" in m and "+1.24%" in m   # A, B (yön değiştirdi), D LONG; E SHORT
    assert _balanced(m)


def test_engine_sends_rebalance_notification_only_when_orders(engine):
    msgs = [m for m in engine.notif.msgs if "dengeleme" in m.lower() or "kurulum" in m.lower()]
    assert msgs and "İlk kurulum" in msgs[0]
    assert all(_balanced(m) for m in msgs)


def test_formatters():
    assert tg.usd(-3.456, True) == "−$3.46" and tg.usd(0.001, True) == "$0.00" and tg.usd(12, True) == "+$12.00"
    assert tg.pct(1.234) == "+1.23%" and tg.pct(-0.001) == "0.00%"
    assert tg.funding_text(-2.19) == "+$2.19 gelir" and tg.funding_text(0.5) == "−$0.50 ödeme"
    assert tg.utc_to_tr("2026-11-19 21:00:00") == "20.11 00:00"


# ---------------- komutlar ----------------
class Orch:
    def __init__(self, notifier):
        self.notifier = notifier
        self.client = None
        self.ran_cycle = False

    def run_cycle(self):
        self.ran_cycle = True


def _agent(monkeypatch, engine):
    import agents.carry_agent as ca
    from agents.telegram_command_agent import TelegramCommandAgent
    monkeypatch.setattr(ca, "_ENGINE", engine)
    monkeypatch.setattr(config, "ENABLE_SMC_ENGINE", False)
    n = Notif()
    orch = Orch(n)
    return TelegramCommandAgent(orch, bot_token="1:x", chat_id="42"), n, orch


def test_v3_commands(engine, monkeypatch):
    from core import maintenance as mt
    agent, n, orch = _agent(monkeypatch, engine)
    agent._handle_command("/durum")
    agent._handle_command("/pozisyonlar@effe_trade_bot")      # menüden gelen biçim
    agent._handle_command("/rapor")
    agent._handle_command("/yardim")
    assert "v3 Durum" in n.msgs[0] and "Açık Pozisyonlar" in n.msgs[1]
    assert "şu ana kadar" in n.msgs[2] and "Komutlar" in n.msgs[3]
    calls = []
    monkeypatch.setattr(mt, "run_in_background", lambda kind, notifier=None: calls.append(kind) or True)
    agent._handle_command("/yedek")
    assert calls == ["backup"] and "Yedek hazırlanıyor" in n.msgs[-1]
    agent._handle_command("/tara")
    assert orch.ran_cycle is False and "SMC tarama motoru kapalı" in n.msgs[-1]


def test_unknown_v3_command_falls_back_to_legacy(engine, monkeypatch):
    agent, n, _ = _agent(monkeypatch, engine)
    assert agent._handle_v3("/kapat", []) is False   # eski SMC komutları değişmeden çalışır
    assert agent._handle_v3("/btc", []) is False


def test_daily_report_hook_uses_v3_when_smc_disabled(engine, monkeypatch):
    import agents.carry_agent as ca
    import main
    monkeypatch.setattr(ca, "_ENGINE", engine)
    monkeypatch.setattr(config, "ENABLE_SMC_ENGINE", False)
    n = Notif()
    fake = type("O", (), {"notifier": n})()
    rep = main.TradingBotOrchestrator._send_daily_report(fake, tg.today_tr(engine.data.now_ms()))
    assert rep == {"sent": True} and "Gün Sonu Raporu" in n.msgs[-1]
    msg = main.TradingBotOrchestrator._startup_message(fake)
    assert "Trade Bot v3 aktif" in msg and "10x" not in msg


def test_equity_schema_migration(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    c = sqlite3.connect(str(db))
    c.execute("CREATE TABLE carry_equity (ts_ms INTEGER PRIMARY KEY, ts TEXT, equity REAL, gross_exposure REAL, "
              "net_exposure REAL, n_positions INTEGER, scale REAL)")
    c.execute("INSERT INTO carry_equity VALUES (1, 't', 1000, 0, 0, 0, 1)")
    c.commit()
    c.close()
    st = SQLiteCarryStore(db)
    cols = {r[1] for r in sqlite3.connect(str(db)).execute("PRAGMA table_info(carry_equity)")}
    assert {"fees_paid", "funding_paid", "realized_pnl"} <= cols
    assert st.equity_at_or_before(5)["equity"] == 1000 and st.equity_at_or_before(5)["funding_paid"] is None
