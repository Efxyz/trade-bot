"""Ortak test kurulumu: her test oturumu izole geçici bir veri klasörü kullanır (gerçek DB'ye dokunulmaz)."""
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="tradebot_test_")
os.environ["TRADEBOT_DATA_DIR"] = _TMP
os.environ.setdefault("ADMIN_PIN", "test-pin-123456")
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""
os.environ["GEMINI_API_KEY"] = ""

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    from core.database import init_db
    init_db()
    yield


@pytest.fixture()
def clean_signals():
    from core.database import get_db_connection
    conn = get_db_connection()
    conn.execute("DELETE FROM signals")
    conn.commit()
    yield conn
    conn.execute("DELETE FROM signals")
    conn.commit()


@pytest.fixture()
def legacy_ladder(monkeypatch):
    """Eski dar merdiven (Basamak 1: +%0.50 tetik, %35 kısmi satış) davranışını açıkça etkinleştirir."""
    import config
    import agents.tracker_agent as tr
    monkeypatch.setattr(tr, "LADDER_STEPS", config.LEGACY_LADDER_STEPS)
    monkeypatch.setattr(tr, "ATR_LADDER_ENABLED", True)
    monkeypatch.setattr(config, "LADDER_STEP1_PARTIAL_PCT", 0.35)
    yield
