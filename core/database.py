"""
Database Layer - SQLite for Signals & Counterfactual (What-If) Paper Trades
Tracks real performance if the trade had been taken, without risking real funds.
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from config import DB_PATH

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Veritabanı tablolarını oluşturur, WAL modunu aktif eder ve eksik sütunları günceller."""
    with get_db_connection() as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        cursor = conn.cursor()
        
        # Sinyaller ve Sanal İşlemler Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,          -- 'LONG' veya 'SHORT'
                leverage INTEGER DEFAULT 10,
                entry_min REAL NOT NULL,
                entry_max REAL NOT NULL,
                actual_entry_price REAL,
                stop_loss REAL NOT NULL,
                take_profit_1 REAL NOT NULL,
                take_profit_2 REAL NOT NULL,
                risk_reward REAL NOT NULL,
                risk_grade TEXT NOT NULL,          -- 'Grade A', 'Grade B', 'Grade C'
                news_summary TEXT,
                ta_reasons TEXT,
                chart_entry_png TEXT,
                chart_exit_png TEXT,
                status TEXT DEFAULT 'ACTIVE',      -- 'ACTIVE', 'ACTIVE_BE', 'HIT_TP', 'HIT_SL', 'CLOSED_BE', 'TIMEOUT_EXIT', 'TRAILING_STOP_EXIT'
                entered_at TIMESTAMP,
                closed_at TIMESTAMP,
                exit_price REAL,
                simulated_pnl_pct REAL DEFAULT 0.0, -- Net Marjin PnL (Komisyon Düşülmüş Gerçek Kâr/Zarar %)
                gross_pnl_pct REAL DEFAULT 0.0,     -- Brüt Marjin PnL (%)
                fee_pct REAL DEFAULT 0.0,           -- Ödenen Taker Komisyonu (% Marjin bazlı)
                allocated_margin_usdt REAL DEFAULT 100.0, -- Tahsis Edilen Teminat ($)
                risk_usd REAL DEFAULT 20.0,         -- Riske Edilen Miktar ($)
                highest_price REAL DEFAULT 0.0,     -- Pozisyon boyunca görülen en yüksek fiyat (Trailing Stop için)
                lowest_price REAL DEFAULT 999999999.0, -- Pozisyon boyunca görülen en düşük fiyat (Trailing Stop için)
                trailing_stop REAL DEFAULT 0.0      -- Dinamik İz Süren Stop Seviyesi
            )
        """)
        
        # Otomatik Migrasyon: Mevcut veritabanında eksik sütunlar varsa ekle
        cursor.execute("PRAGMA table_info(signals)")
        existing_cols = {row["name"] for row in cursor.fetchall()}
        new_cols = {
            "gross_pnl_pct": "REAL DEFAULT 0.0",
            "fee_pct": "REAL DEFAULT 0.0",
            "allocated_margin_usdt": "REAL DEFAULT 100.0",
            "risk_usd": "REAL DEFAULT 20.0",
            "highest_price": "REAL DEFAULT 0.0",
            "lowest_price": "REAL DEFAULT 999999999.0",
            "trailing_stop": "REAL DEFAULT 0.0",
            "ladder_step": "INTEGER DEFAULT 0",
            "ladder_name": "TEXT DEFAULT ''",
            "debate_json": "TEXT DEFAULT ''"
        }
        for col_name, col_def in new_cols.items():
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE signals ADD COLUMN {col_name} {col_def}")
                except Exception:
                    pass

        # Geçmiş performans metrikleri için index
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)")

        # FAST BOT TABLOLARI (1m Seri Hızlı Scalping - Bağımsız Kasa)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fast_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                leverage INTEGER DEFAULT 10,
                entry_min REAL NOT NULL,
                entry_max REAL NOT NULL,
                actual_entry_price REAL,
                stop_loss REAL NOT NULL,
                take_profit_1 REAL NOT NULL,
                take_profit_2 REAL NOT NULL,
                risk_reward REAL NOT NULL,
                risk_grade TEXT NOT NULL,
                news_summary TEXT,
                ta_reasons TEXT,
                chart_entry_png TEXT,
                chart_exit_png TEXT,
                status TEXT DEFAULT 'ACTIVE',
                entered_at TIMESTAMP,
                closed_at TIMESTAMP,
                exit_price REAL,
                simulated_pnl_pct REAL DEFAULT 0.0,
                gross_pnl_pct REAL DEFAULT 0.0,
                fee_pct REAL DEFAULT 0.0,
                allocated_margin_usdt REAL DEFAULT 75.0,
                risk_usd REAL DEFAULT 15.0,
                highest_price REAL DEFAULT 0.0,
                lowest_price REAL DEFAULT 999999999.0,
                trailing_stop REAL DEFAULT 0.0,
                ladder_step INTEGER DEFAULT 0,
                ladder_name TEXT DEFAULT '',
                fast_meta TEXT DEFAULT ''
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fast_signals_status ON fast_signals(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fast_signals_symbol ON fast_signals(symbol)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fast_scanner_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                time_str TEXT NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                details TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fast_scanner_logs_id ON fast_scanner_logs(id DESC)")

        # SÜPER FAST BOT TABLOLARI (Saniyelik HFT Scalping - Bağımsız $1000 Kasa)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS super_fast_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                leverage INTEGER DEFAULT 10,
                entry_min REAL NOT NULL,
                entry_max REAL NOT NULL,
                actual_entry_price REAL,
                stop_loss REAL NOT NULL,
                take_profit_1 REAL NOT NULL,
                take_profit_2 REAL NOT NULL,
                risk_reward REAL NOT NULL,
                risk_grade TEXT NOT NULL,
                news_summary TEXT,
                ta_reasons TEXT,
                chart_entry_png TEXT,
                chart_exit_png TEXT,
                status TEXT DEFAULT 'ACTIVE',
                entered_at TIMESTAMP,
                closed_at TIMESTAMP,
                exit_price REAL,
                simulated_pnl_pct REAL DEFAULT 0.0,
                gross_pnl_pct REAL DEFAULT 0.0,
                fee_pct REAL DEFAULT 0.0,
                allocated_margin_usdt REAL DEFAULT 35.0,
                risk_usd REAL DEFAULT 7.5,
                highest_price REAL DEFAULT 0.0,
                lowest_price REAL DEFAULT 999999999.0,
                trailing_stop REAL DEFAULT 0.0,
                ladder_step INTEGER DEFAULT 0,
                ladder_name TEXT DEFAULT '',
                super_fast_meta TEXT DEFAULT ''
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_super_fast_signals_status ON super_fast_signals(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_super_fast_signals_symbol ON super_fast_signals(symbol)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS super_fast_scanner_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                time_str TEXT NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                details TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_super_fast_scanner_logs_id ON super_fast_scanner_logs(id DESC)")

        # Scanner Ofis Masası Günlükleri Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scanner_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                time_str TEXT NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                details TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scanner_logs_id ON scanner_logs(id DESC)")

        # Sağ Alt Canlı Haber Masası Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL,
                title TEXT NOT NULL UNIQUE,
                time_str TEXT NOT NULL,
                sentiment TEXT NOT NULL,
                link TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_items_id ON news_items(id DESC)")

        # Ajanlar Arası Yatırım Komitesi Tartışma Odası Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS committee_debates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                time_str TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                consensus_verdict TEXT NOT NULL,
                consensus_score REAL NOT NULL,
                decision_summary TEXT NOT NULL,
                debate_json TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_debates_id ON committee_debates(id DESC)")

        # Tauric Research / TradingAgents Esinli Episodik Hafıza & Öz-Eleştiri Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_reflections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                time_str TEXT NOT NULL,
                signal_id INTEGER,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                status TEXT NOT NULL,
                pnl_pct REAL NOT NULL,
                lesson TEXT NOT NULL,
                reflection_json TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reflections_id ON trade_reflections(id DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reflections_sym ON trade_reflections(symbol)")

        # Otonom Kendi Kendini Geliştirme ve Parametre Kalibrasyon Tablosu (Self-Tuning Engine)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS self_tuning_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                time_str TEXT NOT NULL,
                trades_analyzed INTEGER NOT NULL,
                win_rate REAL NOT NULL,
                profit_factor REAL NOT NULL,
                expectancy REAL NOT NULL,
                tuning_summary TEXT NOT NULL,
                params_json TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tuning_id ON self_tuning_logs(id DESC)")

        # Günlük Durum ve Zirve Kâr Takip Tablosu (High-Water Mark State)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Günlük Bilanço ve PnL Arşiv Tablosu (23:59 Kapanış Mührü)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_pnl_archive (
                date_str TEXT PRIMARY KEY,
                total_trades INTEGER,
                win_count INTEGER,
                loss_count INTEGER,
                win_rate REAL,
                net_dollar_gain REAL,
                net_pnl_pct REAL,
                closing_balance REAL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()

def add_scanner_log_db(symbol: str, status: str, reason: str, details: str = ""):
    """Taranan paritenin kabul/ret gerekçesini kalıcı olarak kaydeder."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        time_str = datetime.now().strftime("%H:%M:%S")
        cursor.execute("""
            INSERT INTO scanner_logs (time_str, symbol, status, reason, details)
            VALUES (?, ?, ?, ?, ?)
        """, (time_str, symbol, status, reason, details))
        conn.commit()

def get_scanner_logs_db(limit: int = 40) -> List[Dict]:
    """Ofis masası için taranan son coin kararlarını getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT time_str as time, symbol, status, reason, details
            FROM scanner_logs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

def save_news_item_db(source: str, title: str, time_str: str, sentiment: str, link: str = ""):
    """Haber masası için tekil haber kaydeder."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO news_items (source, title, time_str, sentiment, link)
            VALUES (?, ?, ?, ?, ?)
        """, (source, title, time_str, sentiment, link))
        conn.commit()

def get_news_feed_db(limit: int = 25) -> List[Dict]:
    """Ofis haber masası için en son kripto haberlerini getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT source, title, time_str as time, sentiment, link
            FROM news_items
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

def save_committee_debate_db(symbol: str, direction: str, verdict: str, score: float, decision_summary: str, debate_dict: Dict) -> int:
    """Yatırım komitesi tartışmasını veritabanına kaydeder."""
    import json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        time_str = datetime.now().strftime("%H:%M:%S")
        cursor.execute("""
            INSERT INTO committee_debates (time_str, symbol, direction, consensus_verdict, consensus_score, decision_summary, debate_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (time_str, symbol, direction, verdict, score, decision_summary, json.dumps(debate_dict, ensure_ascii=False)))
        conn.commit()
        return cursor.lastrowid

def get_latest_debates_db(limit: int = 10) -> List[Dict]:
    """Son yapılan yatırım komitesi tartışmalarını döner."""
    import json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, created_at, time_str, symbol, direction, consensus_verdict, consensus_score, decision_summary, debate_json
            FROM committee_debates
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        debates = []
        for row in cursor.fetchall():
            d = dict(row)
            try:
                d["debate_data"] = json.loads(d["debate_json"])
            except Exception:
                d["debate_data"] = {}
            debates.append(d)
        return debates

def save_trade_reflection_db(
    signal_id: Optional[int],
    symbol: str,
    direction: str,
    status: str,
    pnl_pct: float,
    lesson: str,
    reflection_dict: Optional[Dict] = None
) -> int:
    """Kapanan işlem sonrası çıkarılan öz-eleştiri ve dersi kalıcı hafızaya kaydeder."""
    import json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        time_str = datetime.now().strftime("%H:%M:%S")
        refl_json = json.dumps(reflection_dict or {}, ensure_ascii=False)
        cursor.execute("""
            INSERT INTO trade_reflections (time_str, signal_id, symbol, direction, status, pnl_pct, lesson, reflection_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (time_str, signal_id, symbol, direction, status, pnl_pct, lesson, refl_json))
        conn.commit()
        return cursor.lastrowid

def get_recent_reflections_db(limit: int = 10, symbol: Optional[str] = None) -> List[Dict]:
    """Geçmiş işlem derslerini hafızadan çeker (Tüm piyasa veya belirli parite)."""
    import json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if symbol:
            cursor.execute("""
                SELECT id, created_at, time_str, signal_id, symbol, direction, status, pnl_pct, lesson, reflection_json
                FROM trade_reflections
                WHERE symbol = ?
                ORDER BY id DESC
                LIMIT ?
            """, (symbol, limit))
        else:
            cursor.execute("""
                SELECT id, created_at, time_str, signal_id, symbol, direction, status, pnl_pct, lesson, reflection_json
                FROM trade_reflections
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
        
        reflections = []
        for row in cursor.fetchall():
            r = dict(row)
            try:
                r["reflection_data"] = json.loads(r["reflection_json"]) if r["reflection_json"] else {}
            except Exception:
                r["reflection_data"] = {}
            reflections.append(r)
        return reflections

def save_tuning_log_db(
    trades_analyzed: int,
    win_rate: float,
    profit_factor: float,
    expectancy: float,
    tuning_summary: str,
    params_dict: Dict
) -> int:
    """Otonom parametre kalibrasyon raporunu kaydeder."""
    import json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        time_str = datetime.now().strftime("%H:%M:%S")
        p_json = json.dumps(params_dict or {}, ensure_ascii=False)
        cursor.execute("""
            INSERT INTO self_tuning_logs (time_str, trades_analyzed, win_rate, profit_factor, expectancy, tuning_summary, params_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (time_str, trades_analyzed, win_rate, profit_factor, expectancy, tuning_summary, p_json))
        conn.commit()
        return cursor.lastrowid

def get_latest_tuning_log_db() -> Optional[Dict]:
    """En son yapılan otonom kalibrasyon kaydını döner."""
    import json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, created_at, time_str, trades_analyzed, win_rate, profit_factor, expectancy, tuning_summary, params_json
            FROM self_tuning_logs
            ORDER BY id DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["params"] = json.loads(d["params_json"]) if d["params_json"] else {}
        except Exception:
            d["params"] = {}
        return d

def get_tuning_logs_db(limit: int = 10) -> List[Dict]:
    """Tüm otonom kalibrasyon geçmişini döner."""
    import json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, created_at, time_str, trades_analyzed, win_rate, profit_factor, expectancy, tuning_summary, params_json
            FROM self_tuning_logs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        logs = []
        for row in cursor.fetchall():
            d = dict(row)
            try:
                d["params"] = json.loads(d["params_json"]) if d["params_json"] else {}
            except Exception:
                d["params"] = {}
            logs.append(d)
        return logs

def save_signal(data: Dict) -> int:
    """Yeni sinyali kaydeder ve doğrudan aktif sanal işlem olarak başlatır."""
    import json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry_price = data.get("actual_entry_price") or data.get("current_price") or data["entry_min"]
        debate_json_str = data.get("debate_json")
        if isinstance(debate_json_str, dict):
            debate_json_str = json.dumps(debate_json_str, ensure_ascii=False)
        elif not debate_json_str:
            debate_json_str = ""

        cursor.execute("""
            INSERT INTO signals (
                symbol, direction, leverage, entry_min, entry_max,
                actual_entry_price, entered_at,
                stop_loss, take_profit_1, take_profit_2, risk_reward,
                risk_grade, news_summary, ta_reasons, chart_entry_png, status,
                allocated_margin_usdt, risk_usd, highest_price, lowest_price,
                debate_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?)
        """, (
            data["symbol"], data["direction"], data.get("leverage", 10),
            data["entry_min"], data["entry_max"],
            entry_price, current_time,
            data["stop_loss"], data["take_profit_1"], data["take_profit_2"],
            data["risk_reward"], data["risk_grade"],
            data.get("news_summary", ""), data.get("ta_reasons", ""),
            data.get("chart_entry_png", ""),
            data.get("allocated_margin_usdt", 100.0),
            data.get("risk_usd", 20.0),
            entry_price, entry_price,
            debate_json_str
        ))
        conn.commit()
        return cursor.lastrowid

def get_active_positions_count() -> int:
    """Açık ve aktif işlem sayısını döner (Kasa Kalkanı kontrolü için)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals WHERE status IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')")
        return cursor.fetchone()[0]

def get_today_trades_count() -> int:
    """Bugün (Türkiye Saati ile 00:00'dan itibaren) açılan toplam işlem sayısını döner (Aşırı İşlem / Komisyon Kalkanı)."""
    from datetime import datetime, timezone, timedelta
    tr_tz = timezone(timedelta(hours=3))
    now_tr = datetime.now(timezone.utc).astimezone(tr_tz)
    today_start_tr = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = today_start_tr.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals WHERE created_at >= ?", (today_start,))
        row = cursor.fetchone()
        return row[0] if row else 0

def get_today_net_dollar_loss() -> float:
    """Bugün (Türkiye Saati ile 00:00'dan itibaren) kapanan işlemlerin net dolar bazlı toplam kaybını kontrol eder (Circuit Breaker)."""
    from datetime import datetime, timezone, timedelta
    tr_tz = timezone(timedelta(hours=3))
    now_tr = datetime.now(timezone.utc).astimezone(tr_tz)
    today_start_tr = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = today_start_tr.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                SUM(COALESCE(allocated_margin_usdt, 150.0) * (simulated_pnl_pct / 100.0)) as net_dollar
            FROM signals
            WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')
              AND closed_at >= ?
              AND simulated_pnl_pct IS NOT NULL
        """, (today_start,))
        row = cursor.fetchone()
        net_dollar = (row["net_dollar"] if row and row["net_dollar"] is not None else 0.0)
        if net_dollar < 0:
            return abs(round(net_dollar, 2))
        return 0.0

def get_today_net_dollar_pnl() -> float:
    """Bugün (Türkiye Saati ile 00:00'dan itibaren) kapanan işlemlerin net dolar bazlı kâr/zararını döner (+ veya -)."""
    from datetime import datetime, timezone, timedelta
    tr_tz = timezone(timedelta(hours=3))
    now_tr = datetime.now(timezone.utc).astimezone(tr_tz)
    today_start_tr = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = today_start_tr.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                SUM(COALESCE(allocated_margin_usdt, 150.0) * (simulated_pnl_pct / 100.0)) as net_dollar
            FROM signals
            WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')
              AND closed_at >= ?
              AND simulated_pnl_pct IS NOT NULL
        """, (today_start,))
        row = cursor.fetchone()
        net_dollar = (row["net_dollar"] if row and row["net_dollar"] is not None else 0.0)
        return round(net_dollar, 2)

def get_and_update_today_peak_profit(current_pnl: float):
    """
    Günün en yüksek net kârını (Daily High-Water Mark) takip eder.
    Döner: (peak_profit, profit_floor, is_locked)
    - Zirve kâr güncellenir.
    - Eğer zirve >= 30$ ve anlık kâr taban kârın (floor) altına indiyse is_locked = True döner.
    """
    from datetime import datetime, timezone, timedelta
    tr_tz = timezone(timedelta(hours=3))
    today_key = "peak_pnl_" + datetime.now(timezone.utc).astimezone(tr_tz).strftime("%Y_%m_%d")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS system_state (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute("SELECT value FROM system_state WHERE key = ?", (today_key,))
        row = cursor.fetchone()
        prev_peak = float(row["value"]) if row else 0.0

        peak = max(prev_peak, current_pnl)
        if peak != prev_peak or not row:
            cursor.execute("INSERT OR REPLACE INTO system_state (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (today_key, str(peak)))
            conn.commit()

    floor = 0.0
    if peak >= 75.0:
        floor = 55.0
    elif peak >= 50.0:
        floor = 35.0
    elif peak >= 30.0:
        floor = 15.0

    is_locked = (peak >= 30.0 and current_pnl <= floor)
    return round(peak, 2), round(floor, 2), is_locked

def get_active_and_pending_signals() -> List[Dict]:
    """Halen takip edilmesi gereken aktif veya giriş bekleyen sinyalleri getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM signals 
            WHERE status IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')
            ORDER BY created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

def get_recently_traded_symbols(within_minutes: int = 45) -> set:
    """Son belirlenen dakikada işlem açılmış veya kapatılmış coinleri döner (Tekrar aynı coine girmemek için)."""
    from datetime import datetime, timedelta
    cutoff_time = (datetime.now() - timedelta(minutes=within_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT symbol FROM signals
            WHERE status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'PENDING_ENTRY')
               OR (closed_at IS NOT NULL AND closed_at >= ?)
               OR (entered_at IS NOT NULL AND entered_at >= ?)
        """, (cutoff_time, cutoff_time))
        return {row["symbol"] for row in cursor.fetchall()}

def get_last_loss_closed_time() -> Optional[str]:
    """Son kapanan zararlı işlemin kapanış zamanını döner (Soğuma karantinası için)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT closed_at FROM signals
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')
              AND simulated_pnl_pct < 0
              AND closed_at IS NOT NULL
            ORDER BY closed_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        return row["closed_at"] if row else None

def update_signal_status(signal_id: int, updates: Dict):
    """Sinyal durumunu ve sonuçlarını günceller."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        fields = []
        values = []
        for k, v in updates.items():
            fields.append(f"{k} = ?")
            values.append(v)
        values.append(signal_id)
        query = f"UPDATE signals SET {', '.join(fields)} WHERE id = ?"
        cursor.execute(query, values)
        conn.commit()

def get_all_signals(limit: int = 50) -> List[Dict]:
    """Tüm sinyalleri (aktif ve geçmiş) sıralı olarak getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM signals 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

def get_performance_stats() -> Dict:
    """Tüm sanal işlemlerin kaldıraçlı performans özetini hesaplar (Net komisyonlu ve gerçek marjinli tam fon hesabı)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN 1 ELSE 0 END) as loss_count,
                SUM(CASE WHEN simulated_pnl_pct = 0 THEN 1 ELSE 0 END) as be_count,
                AVG(simulated_pnl_pct) as avg_pnl_pct,
                SUM(simulated_pnl_pct) as total_pnl_pct,
                SUM(gross_pnl_pct) as total_gross_pnl_pct,
                SUM(fee_pct) as total_fee_pct,
                SUM(COALESCE(allocated_margin_usdt, 200.0) * (simulated_pnl_pct / 100.0)) as actual_net_dollar_gain,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN (COALESCE(allocated_margin_usdt, 200.0) * (simulated_pnl_pct / 100.0)) ELSE 0 END) as sum_dollar_wins,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN ABS(COALESCE(allocated_margin_usdt, 200.0) * (simulated_pnl_pct / 100.0)) ELSE 0 END) as sum_dollar_losses
            FROM signals
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')
              AND simulated_pnl_pct IS NOT NULL
        """)
        row = dict(cursor.fetchone() or {})
        total = row.get("total_trades") or 0
        wins = row.get("win_count") or 0
        losses = row.get("loss_count") or 0
        sum_wins = row.get("sum_dollar_wins") or 0.0
        sum_losses = row.get("sum_dollar_losses") or 0.0

        row["win_rate"] = round((wins / total * 100), 2) if total > 0 else 0.0
        row["profit_factor"] = round((sum_wins / sum_losses), 2) if sum_losses > 0 else (99.0 if sum_wins > 0 else 0.0)
        
        # Net ve Brüt PnL yuvarlama
        total_pnl = row.get("total_pnl_pct") or 0.0
        row["total_pnl_pct"] = round(total_pnl, 2)
        row["total_gross_pnl_pct"] = round(row.get("total_gross_pnl_pct") or 0.0, 2)
        row["total_fee_pct"] = round(row.get("total_fee_pct") or 0.0, 2)
        row["sum_wins"] = round(sum_wins, 2)
        row["sum_losses"] = round(sum_losses, 2)
        
        # 1000 USDT Fon Kasası: Gerçek tahsis edilen marjinler üzerinden kuruşu kuruşuna net dolar hesabı
        net_dollar_gain = row.get("actual_net_dollar_gain") or 0.0
        row["net_dollar_gain"] = round(net_dollar_gain, 2)
        row["portfolio_balance"] = round(1000.0 + net_dollar_gain, 2)

        # ========================================================
        # BUGÜNKÜ NET PnL (TÜRKİYE SAATİ 00:00 - 23:59 ARASI)
        # 23:59:59'da otomatik sıfırlanır ve arka planda arşivlenir
        # ========================================================
        from datetime import datetime, timezone, timedelta
        tr_tz = timezone(timedelta(hours=3))
        now_tr = datetime.now(timezone.utc).astimezone(tr_tz)
        today_start_tr = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = today_start_tr.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        today_date_str = now_tr.strftime("%Y-%m-%d")

        cursor.execute("""
            SELECT 
                COUNT(*) as today_trades,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN 1 ELSE 0 END) as today_wins,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN 1 ELSE 0 END) as today_losses,
                SUM(simulated_pnl_pct) as today_net_pnl_pct,
                SUM(COALESCE(allocated_margin_usdt, 200.0) * (simulated_pnl_pct / 100.0)) as today_dollar_gain
            FROM signals
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')
              AND closed_at >= ?
              AND simulated_pnl_pct IS NOT NULL
        """, (today_start,))
        t_row = dict(cursor.fetchone() or {})
        t_trades = t_row.get("today_trades") or 0
        t_wins = t_row.get("today_wins") or 0
        t_losses = t_row.get("today_losses") or 0
        t_dollar = round(t_row.get("today_dollar_gain") or 0.0, 2)
        t_pct = round(t_row.get("today_net_pnl_pct") or 0.0, 2)
        t_wr = round((t_wins / t_trades * 100.0), 1) if t_trades > 0 else 0.0

        row["today_trades"] = t_trades
        row["today_wins"] = t_wins
        row["today_losses"] = t_losses
        row["today_win_rate"] = t_wr
        row["today_dollar_gain"] = t_dollar
        row["today_net_pnl_pct"] = t_pct
        row["today_date_str"] = today_date_str

        # Arka Planda Günlük Bilanço Arşivini Güncelle / Mühürle
        try:
            check_and_auto_archive_daily_pnl()
        except Exception:
            pass

        return row

def check_and_auto_archive_daily_pnl():
    """
    Geçmiş ve bugünkü günlerin kapanış bilançolarını kontrol eder.
    Her günün net PnL'ini daily_pnl_archive tablosuna kalıcı olarak mühürler.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT substr(closed_at, 1, 10) as c_date
            FROM signals
            WHERE closed_at IS NOT NULL
              AND status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')
        """)
        distinct_dates = [r["c_date"] for r in cursor.fetchall() if r["c_date"]]

        for d_str in distinct_dates:
            d_start = f"{d_str} 00:00:00"
            d_end = f"{d_str} 23:59:59"
            cursor.execute("""
                SELECT 
                    COUNT(*) as t_count,
                    SUM(CASE WHEN simulated_pnl_pct > 0 THEN 1 ELSE 0 END) as w_count,
                    SUM(CASE WHEN simulated_pnl_pct < 0 THEN 1 ELSE 0 END) as l_count,
                    SUM(simulated_pnl_pct) as net_pct,
                    SUM(COALESCE(allocated_margin_usdt, 200.0) * (simulated_pnl_pct / 100.0)) as net_dollar
                FROM signals
                WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')
                  AND closed_at >= ? AND closed_at <= ?
                  AND simulated_pnl_pct IS NOT NULL
            """, (d_start, d_end))
            r = cursor.fetchone()
            if r and (r["t_count"] or 0) > 0:
                t_cnt = r["t_count"] or 0
                w_cnt = r["w_count"] or 0
                l_cnt = r["l_count"] or 0
                net_p = round(r["net_pct"] or 0.0, 2)
                net_d = round(r["net_dollar"] or 0.0, 2)
                wr = round((w_cnt / t_cnt * 100.0), 1) if t_cnt > 0 else 0.0

                cursor.execute("""
                    INSERT OR REPLACE INTO daily_pnl_archive 
                    (date_str, total_trades, win_count, loss_count, win_rate, net_dollar_gain, net_pnl_pct, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (d_str, t_cnt, w_cnt, l_cnt, wr, net_d, net_p))
        conn.commit()

def get_daily_pnl_archive_db(limit: int = 30) -> List[Dict]:
    """Kalıcı olarak arşivlenen günlük PnL kayıtlarını döner."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_pnl_archive ORDER BY date_str DESC LIMIT ?", (limit,))
        return [dict(r) for r in cursor.fetchall()]

def close_single_signal_db(symbol: str, client=None) -> Optional[Dict]:
    """Belirtilen paritedeki açık pozisyonu anlık piyasa fiyatıyla manuel olarak kapatır."""
    clean_sym = symbol.upper().strip()
    if not clean_sym.endswith("USDT") and not clean_sym.endswith("USDT.P"):
        clean_sym = f"{clean_sym}USDT"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM signals 
            WHERE symbol = ? AND status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'PENDING_ENTRY')
            ORDER BY id DESC LIMIT 1
        """, (clean_sym,))
        row = cursor.fetchone()
        if not row:
            return None
        sig = dict(row)

    sig_id = sig["id"]
    direction = sig["direction"]
    leverage = sig.get("leverage") or 10
    entry_price = sig.get("actual_entry_price") or sig["entry_min"]
    exit_price = entry_price

    if client:
        try:
            tickers = client.get_24hr_tickers()
            if clean_sym in tickers:
                exit_price = tickers[clean_sym].get("lastPrice", entry_price)
        except Exception:
            pass

    raw_change = ((exit_price - entry_price) / entry_price) if direction == "LONG" else ((entry_price - exit_price) / entry_price)
    gross_pnl_pct = round(raw_change * leverage * 100, 2)
    fee_pct = round(0.10 * leverage, 2)
    net_pnl_pct = round(gross_pnl_pct - fee_pct, 2)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE signals SET
                status = 'MANUAL_CLOSE',
                closed_at = ?,
                exit_price = ?,
                simulated_pnl_pct = ?,
                gross_pnl_pct = ?,
                fee_pct = ?
            WHERE id = ?
        """, (now_str, exit_price, net_pnl_pct, gross_pnl_pct, fee_pct, sig_id))
        conn.commit()

    sig["status"] = "MANUAL_CLOSE"
    sig["closed_at"] = now_str
    sig["exit_price"] = exit_price
    sig["simulated_pnl_pct"] = net_pnl_pct
    sig["gross_pnl_pct"] = gross_pnl_pct
    sig["fee_pct"] = fee_pct

    # Tauric Reflection kaydı
    try:
        from core.reflection import ReflectorEngine
        ReflectorEngine.reflect_on_trade({
            "signal_id": sig_id,
            "symbol": clean_sym,
            "direction": direction,
            "status": "MANUAL_CLOSE",
            "pnl_pct": net_pnl_pct,
            "gross_pnl_pct": gross_pnl_pct,
            "fee_pct": fee_pct,
            "leverage": leverage
        })
    except Exception:
        pass

    return sig

def close_all_active_signals_db(client=None) -> int:
    """Açık olan tüm aktif pozisyonları anlık piyasa fiyatıyla kapatır ve PnL defterine kaydeder."""
    active_signals = get_active_and_pending_signals()
    if not active_signals:
        return 0

    tickers = {}
    if client:
        try:
            tickers = client.get_24hr_tickers()
        except Exception:
            pass

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    closed_count = 0

    with get_db_connection() as conn:
        cursor = conn.cursor()
        for sig in active_signals:
            sig_id = sig["id"]
            symbol = sig["symbol"]
            direction = sig["direction"]
            leverage = sig.get("leverage") or 10
            entry_price = sig.get("actual_entry_price") or sig["entry_min"]

            # Anlık güncel fiyat
            exit_price = entry_price
            if tickers and symbol in tickers:
                exit_price = tickers[symbol].get("lastPrice", entry_price)

            raw_change = ((exit_price - entry_price) / entry_price) if direction == "LONG" else ((entry_price - exit_price) / entry_price)
            gross_pnl_pct = round(raw_change * leverage * 100, 2)
            fee_pct = round(0.10 * leverage, 2)
            net_pnl_pct = round(gross_pnl_pct - fee_pct, 2)

            cursor.execute("""
                UPDATE signals SET
                    status = 'MANUAL_CLOSE',
                    closed_at = ?,
                    exit_price = ?,
                    simulated_pnl_pct = ?,
                    gross_pnl_pct = ?,
                    fee_pct = ?
                WHERE id = ?
            """, (now_str, exit_price, net_pnl_pct, gross_pnl_pct, fee_pct, sig_id))
            closed_count += 1

            # Tauric Reflection kaydı
            try:
                from core.reflection import ReflectorEngine
                ReflectorEngine.reflect_on_trade({
                    "signal_id": sig_id,
                    "symbol": symbol,
                    "direction": direction,
                    "status": "MANUAL_CLOSE",
                    "pnl_pct": net_pnl_pct,
                    "gross_pnl_pct": gross_pnl_pct,
                    "fee_pct": fee_pct,
                    "leverage": leverage
                })
            except Exception:
                pass
        conn.commit()

    return closed_count

def clear_closed_trades_db():
    """Kapanan tamamlanmış işlem defterini temizler (Aktif pozisyonlara dokunmaz)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM signals WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')")
        conn.commit()

def get_current_equity() -> float:
    """Anlık toplam fon kasasını (Bileşik Kasa Değeri) döner (Örn: $1,000 + Net Dolar PnL)."""
    try:
        stats = get_performance_stats()
        return float(stats.get("portfolio_balance", 1000.0))
    except Exception:
        return 1000.0

def generate_daily_summary_report() -> Dict:
    """Son 24 saat içinde gerçekleşen tüm işlemleri, net kâr/zararı ve gün sonu özetini derler."""
    from datetime import datetime, timedelta, timezone
    tr_tz = timezone(timedelta(hours=3))
    now_tr = datetime.now(timezone.utc).astimezone(tr_tz)

    cutoff = datetime.now() - timedelta(hours=24)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM signals
            WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')
              AND closed_at IS NOT NULL
              AND closed_at >= ?
            ORDER BY closed_at ASC
        """, (cutoff_str,))
        trades_24h = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""
            SELECT * FROM signals
            WHERE status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')
            ORDER BY created_at DESC
        """)
        active_trades = [dict(r) for r in cursor.fetchall()]

    stats = get_performance_stats()
    current_equity = stats.get("portfolio_balance", 1000.0)

    total_count = len(trades_24h)
    wins = [t for t in trades_24h if (t.get("simulated_pnl_pct") or 0.0) > 0]
    losses = [t for t in trades_24h if (t.get("simulated_pnl_pct") or 0.0) < 0]
    bes = [t for t in trades_24h if (t.get("simulated_pnl_pct") or 0.0) == 0]

    total_net_pnl_pct = sum((t.get("simulated_pnl_pct") or 0.0) for t in trades_24h)
    total_gross_pnl_pct = sum((t.get("gross_pnl_pct") or 0.0) for t in trades_24h)
    total_fee_pct = sum((t.get("fee_pct") or 0.0) for t in trades_24h)

    # Dolar bazlı kâr/zarar hesabı (allocated_margin * pnl_pct / 100)
    total_dollar_gain = sum(
        (t.get("allocated_margin_usdt") or 150.0) * ((t.get("simulated_pnl_pct") or 0.0) / 100.0)
        for t in trades_24h
    )

    win_rate = (len(wins) / total_count * 100.0) if total_count > 0 else 0.0

    return {
        "date_str": now_tr.strftime("%d.%m.%Y"),
        "time_str": now_tr.strftime("%H:%M"),
        "total_trades": total_count,
        "win_count": len(wins),
        "loss_count": len(losses),
        "be_count": len(bes),
        "win_rate": round(win_rate, 1),
        "net_pnl_pct": round(total_net_pnl_pct, 2),
        "gross_pnl_pct": round(total_gross_pnl_pct, 2),
        "fee_pct": round(total_fee_pct, 2),
        "dollar_pnl": round(total_dollar_gain, 2),
        "current_equity": round(current_equity, 2),
        "trades": trades_24h,
        "active_trades": active_trades
    }

def format_daily_telegram_message(report: Dict) -> str:
    """Gün sonu raporunu profesyonel Telegram Markdown mesajı formatına dönüştürür."""
    date_str = report["date_str"]
    time_str = report["time_str"]
    total = report["total_trades"]
    wins = report["win_count"]
    losses = report["loss_count"]
    win_rate = report["win_rate"]
    net_pnl = report["net_pnl_pct"]
    dollar_pnl = report["dollar_pnl"]
    equity = report["current_equity"]

    pnl_sign = "+" if dollar_pnl >= 0 else ""
    pnl_emoji = "🟢" if dollar_pnl >= 0 else "🔴"
    pct_sign = "+" if net_pnl >= 0 else ""

    lines = []
    lines.append("🏆 *GÜN SONU PERFORMANS VE İŞLEM RAPORU*")
    lines.append(f"🗓️ *Dönem:* Son 24 Saat | *Tarih:* `{date_str}` ({time_str})")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💼 *Güncel Fon Kasası:* `${equity:,.2f} USDT`")
    lines.append(f"{pnl_emoji} *24s Net Kâr / Zarar:* *{pnl_sign}${dollar_pnl:.2f}* ({pct_sign}%{net_pnl:.2f})")
    lines.append(f"🎯 *24s İşlem Sayısı:* `{total}` adet")
    lines.append(f"✅ *Kazanan (Win):* `{wins}` | 🛑 *Kaybeden (Loss):* `{losses}`")
    lines.append(f"📊 *Günlük Kazanma Oranı:* *%{win_rate:.1f}*")
    lines.append(f"💸 *Ödenen Komisyon:* `-%{report['fee_pct']:.2f}`")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    if total == 0:
        lines.append("😴 *Son 24 saatte tamamlanan işlem bulunmuyor.*\n(Piyasa testere/ölü bantta seyrettiği veya filtrelerimiz koruduğu için sermaye riske atılmadı).")
    else:
        lines.append("📋 *SON 24 SAATTE KAPANAN POZİSYONLAR:*")
        for i, t in enumerate(report["trades"], 1):
            sym = t.get("symbol", "")
            d = t.get("direction", "")
            lev = t.get("leverage", 10)
            pnl = t.get("simulated_pnl_pct", 0.0)
            sign = "+" if pnl > 0 else ""
            status = t.get("status", "")
            status_badge = "🎯 TP" if "TP" in status else ("🪜 LADDER" if "LADDER" in status else ("🛡️ BE" if "BE" in status else ("⏱️ ZAMAN AŞIMI" if "TIMEOUT" in status else "🛑 SL")))
            entry = t.get("actual_entry_price") or t.get("entry_min", 0.0)
            exit_p = t.get("exit_price", 0.0)
            t_margin = t.get("allocated_margin_usdt") or 150.0
            t_dollar = round(t_margin * (pnl / 100.0), 2)
            t_dollar_sign = "+" if t_dollar >= 0 else ""
            
            pnl_icon = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")
            lines.append(f"{i}. {pnl_icon} *{sym}* ({d} {lev}x) ➔ *{sign}%{pnl:.2f}* ({t_dollar_sign}${t_dollar:.2f})")
            lines.append(f"   ↳ Fiyat: `{entry}` ➔ `{exit_p}` | [{status_badge}]")

    active = report.get("active_trades", [])
    if active:
        lines.append("\n⏳ *ŞU AN HALEN AÇIK OLAN POZİSYONLAR:*")
        for a in active:
            lines.append(f"• `{a.get('symbol')}` ({a.get('direction')} {a.get('leverage', 10)}x) | Giriş: `{a.get('actual_entry_price')}` | Stop: `{a.get('stop_loss')}`")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🤖 *AI Ticaret Ofisi:* _10,000 Monte Carlo simülasyonu ve Dinamik Bileşik Kasa Kalkanı devrededir._")

    return "\n".join(lines)


def check_side_stoploss_guard(
    direction: str,
    max_consecutive_losses: int = 2,
    cooldown_minutes: int = 120
) -> Tuple[bool, str]:
    """
    Freqtrade Esinli 'Side-Specific Stoploss Guard' (Yön Bazlı Seri Zarar Kalkanı).
    Belirli bir yönde (örn. SHORT) son işlemleri denetler.
    Eğer son `max_consecutive_losses` işlem ardışık zarar ile kapanmışsa ve son zarardan bu yana
    `cooldown_minutes` dolmamışsa, o yönü kilitler (True, kilit_nedeni).
    LONG tarafı veya kârlı yön asla engellenmez.
    """
    from datetime import datetime, timezone, timedelta
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, symbol, direction, status, simulated_pnl_pct, closed_at
                FROM signals
                WHERE direction = ?
                  AND status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')
                  AND closed_at IS NOT NULL
                ORDER BY closed_at DESC, id DESC
                LIMIT 10
            """, (direction,))
            rows = cursor.fetchall()
            if not rows:
                return False, ""

            consecutive_losses = 0
            last_loss_closed_at = None

            for r in rows:
                pnl = float(r["simulated_pnl_pct"] or 0.0)
                if pnl < 0:
                    consecutive_losses += 1
                    if last_loss_closed_at is None:
                        last_loss_closed_at = r["closed_at"]
                else:
                    # Kârlı veya başa-baş bir işlem görüldüğü an seri kırılır
                    break

            if consecutive_losses >= max_consecutive_losses and last_loss_closed_at:
                loss_dt = datetime.strptime(str(last_loss_closed_at)[:19], "%Y-%m-%d %H:%M:%S")
                now = datetime.utcnow()
                elapsed_min = (now - loss_dt).total_seconds() / 60.0
                if elapsed_min < cooldown_minutes:
                    remaining_min = int(cooldown_minutes - elapsed_min)
                    reason = (
                        f"🛡️ FREQTRADE SIDE GUARD: {direction} yönünde peş peşe {consecutive_losses} zarar kaydedildi. "
                        f"Son kayıptan bu yana {elapsed_min:.0f} dk geçti. Sermaye koruması devrede: "
                        f"{direction} işlemleri {remaining_min} dakika daha donduruldu (LONG serbest)."
                    )
                    return True, reason
    except Exception as e:
        pass

    return False, ""


# ==============================================================================
# ⚡ FAST BOT VERİTABANI VE İŞLEM YÖNETİM KATMANI (1m SERİ İŞLEMLER / BAĞIMSIZ KASA)
# ==============================================================================

def save_fast_signal(data: Dict) -> int:
    """FAST bot için yeni 1m hızlı scalping sinyalini kaydeder ve doğrudan aktif pozisyona alır."""
    import json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry_price = data.get("actual_entry_price") or data.get("current_price") or data["entry_min"]
        fast_meta_str = data.get("fast_meta")
        if isinstance(fast_meta_str, dict):
            fast_meta_str = json.dumps(fast_meta_str, ensure_ascii=False)
        elif not fast_meta_str:
            fast_meta_str = ""

        cursor.execute("""
            INSERT INTO fast_signals (
                symbol, direction, leverage, entry_min, entry_max,
                actual_entry_price, entered_at,
                stop_loss, take_profit_1, take_profit_2, risk_reward,
                risk_grade, news_summary, ta_reasons, chart_entry_png, status,
                allocated_margin_usdt, risk_usd, highest_price, lowest_price,
                fast_meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?)
        """, (
            data["symbol"], data["direction"], data.get("leverage", 10),
            data["entry_min"], data["entry_max"],
            entry_price, current_time,
            data["stop_loss"], data["take_profit_1"], data.get("take_profit_2", data["take_profit_1"]),
            data.get("risk_reward", 1.5), data.get("risk_grade", "FAST Scalp"),
            data.get("news_summary", "⚡ FAST 1m Sinyali"), data.get("ta_reasons", ""),
            data.get("chart_entry_png", ""),
            data.get("allocated_margin_usdt", 75.0),
            data.get("risk_usd", 15.0),
            entry_price, entry_price,
            fast_meta_str
        ))
        conn.commit()
        return cursor.lastrowid

def update_fast_signal_status(signal_id: int, updates: Dict):
    """FAST bot işlem durumunu veya fiyatlarını günceller."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        set_clauses = []
        values = []
        for key, value in updates.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)
        values.append(signal_id)
        sql = f"UPDATE fast_signals SET {', '.join(set_clauses)} WHERE id = ?"
        cursor.execute(sql, values)
        conn.commit()

def get_fast_active_and_pending_signals() -> List[Dict]:
    """FAST bot açık ve aktif scalping işlemlerini getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM fast_signals
            WHERE status IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')
            ORDER BY id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

def get_fast_all_signals(limit: int = 50) -> List[Dict]:
    """FAST bot tüm geçmiş ve aktif işlemlerini getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM fast_signals
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

def get_fast_performance_stats() -> Dict:
    """FAST botun bağımsız $1000 USDT kasalı kaldıraçlı performans özetini hesaplar."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN 1 ELSE 0 END) as loss_count,
                SUM(CASE WHEN simulated_pnl_pct = 0 THEN 1 ELSE 0 END) as be_count,
                AVG(simulated_pnl_pct) as avg_pnl_pct,
                SUM(simulated_pnl_pct) as total_pnl_pct,
                SUM(gross_pnl_pct) as total_gross_pnl_pct,
                SUM(fee_pct) as total_fee_pct,
                SUM(COALESCE(allocated_margin_usdt, 75.0) * (simulated_pnl_pct / 100.0)) as actual_net_dollar_gain,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN (COALESCE(allocated_margin_usdt, 75.0) * (simulated_pnl_pct / 100.0)) ELSE 0 END) as sum_dollar_wins,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN ABS(COALESCE(allocated_margin_usdt, 75.0) * (simulated_pnl_pct / 100.0)) ELSE 0 END) as sum_dollar_losses
            FROM fast_signals
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')
              AND simulated_pnl_pct IS NOT NULL
        """)
        row = dict(cursor.fetchone() or {})
        total = row.get("total_trades") or 0
        wins = row.get("win_count") or 0
        losses = row.get("loss_count") or 0
        sum_wins = row.get("sum_dollar_wins") or 0.0
        sum_losses = row.get("sum_dollar_losses") or 0.0

        row["win_rate"] = round((wins / total * 100), 2) if total > 0 else 0.0
        row["profit_factor"] = round((sum_wins / sum_losses), 2) if sum_losses > 0 else (99.0 if sum_wins > 0 else 0.0)
        
        total_pnl = row.get("total_pnl_pct") or 0.0
        row["total_pnl_pct"] = round(total_pnl, 2)
        row["total_gross_pnl_pct"] = round(row.get("total_gross_pnl_pct") or 0.0, 2)
        row["total_fee_pct"] = round(row.get("total_fee_pct") or 0.0, 2)
        row["sum_wins"] = round(sum_wins, 2)
        row["sum_losses"] = round(sum_losses, 2)
        
        # FAST Bot Bağımsız $1000 Kasa Bakiyesi
        net_dollar_gain = row.get("actual_net_dollar_gain") or 0.0
        row["net_dollar_gain"] = round(net_dollar_gain, 2)
        row["portfolio_balance"] = round(1000.0 + net_dollar_gain, 2)

        # Günlük FAST PnL
        from datetime import datetime, timezone, timedelta
        tr_tz = timezone(timedelta(hours=3))
        now_tr = datetime.now(timezone.utc).astimezone(tr_tz)
        today_start_tr = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = today_start_tr.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            SELECT 
                COUNT(*) as today_trades,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN 1 ELSE 0 END) as today_wins,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN 1 ELSE 0 END) as today_losses,
                SUM(simulated_pnl_pct) as today_net_pnl_pct,
                SUM(fee_pct) as today_fee_pct,
                SUM(COALESCE(allocated_margin_usdt, 75.0) * (simulated_pnl_pct / 100.0)) as today_dollar_gain
            FROM fast_signals
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')
              AND closed_at >= ?
              AND simulated_pnl_pct IS NOT NULL
        """, (today_start,))
        t_row = dict(cursor.fetchone() or {})
        t_trades = t_row.get("today_trades") or 0
        t_wins = t_row.get("today_wins") or 0
        t_losses = t_row.get("today_losses") or 0
        t_dollar = round(t_row.get("today_dollar_gain") or 0.0, 2)
        t_pct = round(t_row.get("today_net_pnl_pct") or 0.0, 2)
        t_wr = round((t_wins / t_trades * 100.0), 1) if t_trades > 0 else 0.0

        row["today_trades"] = t_trades
        row["today_wins"] = t_wins
        row["today_losses"] = t_losses
        row["today_fee_pct"] = round(t_row.get("today_fee_pct") or 0.0, 2)
        row["today_net_pnl_pct"] = t_pct
        row["today_dollar_gain"] = t_dollar
        row["today_win_rate"] = t_wr
        row["today_date_str"] = now_tr.strftime("%Y-%m-%d")

        return row

def add_fast_scanner_log_db(symbol: str, status: str, reason: str, details: str = ""):
    """FAST bot taranan parite kararlarını kaydeder."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        time_str = datetime.now().strftime("%H:%M:%S")
        cursor.execute("""
            INSERT INTO fast_scanner_logs (time_str, symbol, status, reason, details)
            VALUES (?, ?, ?, ?, ?)
        """, (time_str, symbol, status, reason, details))
        conn.commit()

def get_fast_scanner_logs_db(limit: int = 40) -> List[Dict]:
    """FAST ofis masası için taranan son 1m kararlarını getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT time_str as time, symbol, status, reason, details
            FROM fast_scanner_logs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

def close_all_fast_positions_db(client=None) -> int:
    """FAST bot tüm açık pozisyonları anlık fiyattan kapatır."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, symbol, direction, actual_entry_price, leverage, allocated_margin_usdt
            FROM fast_signals
            WHERE status IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')
        """)
        active_trades = cursor.fetchall()
        if not active_trades:
            return 0

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        closed_count = 0

        for t in active_trades:
            sig_id = t["id"]
            symbol = t["symbol"]
            direction = t["direction"]
            entry_p = float(t["actual_entry_price"])
            lev = int(t["leverage"] or 10)
            margin = float(t["allocated_margin_usdt"] or 75.0)

            exit_price = entry_p
            if client:
                try:
                    price_info = client.get_ticker_price(symbol)
                    if price_info and "price" in price_info:
                        exit_price = float(price_info["price"])
                except Exception:
                    pass

            raw_gain_pct = ((exit_price - entry_p) / entry_p) * 100.0 if direction == "LONG" else ((entry_p - exit_price) / entry_p) * 100.0
            gross_margin = raw_gain_pct * lev
            fee_pct = 0.10 * lev
            net_margin = gross_margin - fee_pct

            cursor.execute("""
                UPDATE fast_signals
                SET status = 'EMERGENCY_CLOSED',
                    closed_at = ?,
                    exit_price = ?,
                    gross_pnl_pct = ?,
                    fee_pct = ?,
                    simulated_pnl_pct = ?
                WHERE id = ?
            """, (current_time, exit_price, round(gross_margin, 2), round(fee_pct, 2), round(net_margin, 2), sig_id))
            closed_count += 1

        conn.commit()
        return closed_count

def clear_fast_closed_trades_db():
    """FAST bot kapanmış geçmiş işlem kayıtlarını temizler."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM fast_signals WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')")
        conn.commit()

def check_fast_side_stoploss_guard(direction: str, max_consecutive_losses: int = 2, cooldown_minutes: int = 30) -> Tuple[bool, str]:
    """FAST bot için yön bazlı seri zarar kalkanı."""
    from datetime import datetime, timezone, timedelta
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, symbol, direction, status, simulated_pnl_pct, closed_at
                FROM fast_signals
                WHERE direction = ?
                  AND status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')
                  AND closed_at IS NOT NULL
                ORDER BY closed_at DESC, id DESC
                LIMIT 10
            """, (direction,))
            rows = cursor.fetchall()
            if not rows:
                return False, ""

            consecutive_losses = 0
            last_loss_closed_at = None

            for r in rows:
                pnl = float(r["simulated_pnl_pct"] or 0.0)
                if pnl < 0:
                    consecutive_losses += 1
                    if last_loss_closed_at is None:
                        last_loss_closed_at = r["closed_at"]
                else:
                    break

            if consecutive_losses >= max_consecutive_losses and last_loss_closed_at:
                loss_dt = datetime.strptime(str(last_loss_closed_at)[:19], "%Y-%m-%d %H:%M:%S")
                now = datetime.utcnow()
                elapsed_min = (now - loss_dt).total_seconds() / 60.0
                if elapsed_min < cooldown_minutes:
                    remaining_min = int(cooldown_minutes - elapsed_min)
                    reason = f"⚡ FAST YÖN KALKANI: {direction} yönünde peş peşe {consecutive_losses} zarar. {remaining_min} dk donduruldu."
                    return True, reason
    except Exception:
        pass
    return False, ""


def generate_fast_hourly_summary_report() -> Dict:
    """FAST Bot için son 1 saatte tamamlanan işlemleri, açık pozisyonları ve kümülatif PnL'i derler."""
    from datetime import datetime, timedelta, timezone
    tr_tz = timezone(timedelta(hours=3))
    now_tr = datetime.now(timezone.utc).astimezone(tr_tz)

    cutoff = datetime.now() - timedelta(hours=1)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM fast_signals
            WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')
              AND closed_at IS NOT NULL
              AND closed_at >= ?
            ORDER BY closed_at ASC
        """, (cutoff_str,))
        trades_1h = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""
            SELECT * FROM fast_signals
            WHERE status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')
            ORDER BY created_at DESC
        """)
        active_trades = [dict(r) for r in cursor.fetchall()]

    stats = get_fast_performance_stats()
    current_equity = stats.get("portfolio_balance", 1000.0)

    total_count = len(trades_1h)
    wins = [t for t in trades_1h if (t.get("simulated_pnl_pct") or 0.0) > 0]
    losses = [t for t in trades_1h if (t.get("simulated_pnl_pct") or 0.0) < 0]
    bes = [t for t in trades_1h if (t.get("simulated_pnl_pct") or 0.0) == 0]

    total_net_pnl_pct = sum((t.get("simulated_pnl_pct") or 0.0) for t in trades_1h)
    total_gross_pnl_pct = sum((t.get("gross_pnl_pct") or 0.0) for t in trades_1h)
    total_fee_pct = sum((t.get("fee_pct") or 0.0) for t in trades_1h)

    # Dolar bazlı kâr/zarar hesabı (allocated_margin * pnl_pct / 100)
    total_dollar_gain = sum(
        (t.get("allocated_margin_usdt") or 75.0) * ((t.get("simulated_pnl_pct") or 0.0) / 100.0)
        for t in trades_1h
    )

    win_rate = (len(wins) / total_count * 100.0) if total_count > 0 else 0.0

    return {
        "date_str": now_tr.strftime("%d.%m.%Y"),
        "time_str": now_tr.strftime("%H:%M"),
        "total_trades": total_count,
        "win_count": len(wins),
        "loss_count": len(losses),
        "be_count": len(bes),
        "win_rate": round(win_rate, 1),
        "net_pnl_pct": round(total_net_pnl_pct, 2),
        "gross_pnl_pct": round(total_gross_pnl_pct, 2),
        "fee_pct": round(total_fee_pct, 2),
        "dollar_pnl": round(total_dollar_gain, 2),
        "current_equity": round(current_equity, 2),
        "trades": trades_1h,
        "active_trades": active_trades,
        "overall_stats": stats
    }


def format_fast_hourly_telegram_message(report: Dict) -> str:
    """FAST 1-saatlik raporunu Telegram Markdown formatına dönüştürür."""
    date_str = report["date_str"]
    time_str = report["time_str"]
    total_1h = report["total_trades"]
    wins_1h = report["win_count"]
    losses_1h = report["loss_count"]
    win_rate_1h = report["win_rate"]
    net_pnl_1h = report["net_pnl_pct"]
    dollar_pnl_1h = report["dollar_pnl"]
    equity = report["current_equity"]
    stats = report.get("overall_stats", {})

    pnl_sign_1h = "+" if dollar_pnl_1h >= 0 else ""
    pnl_emoji_1h = "🟢" if dollar_pnl_1h > 0 else ("🔴" if dollar_pnl_1h < 0 else "⚪")
    pct_sign_1h = "+" if net_pnl_1h >= 0 else ""

    # Günlük FAST Verileri
    today_trades = stats.get("today_trades", 0)
    today_wins = stats.get("today_wins", 0)
    today_losses = stats.get("today_losses", 0)
    today_dollar = stats.get("today_dollar_gain", 0.0)
    today_pct = stats.get("today_net_pnl_pct", 0.0)
    today_wr = round((today_wins / today_trades * 100.0), 1) if today_trades > 0 else 0.0
    today_sign = "+" if today_dollar >= 0 else ""
    today_emoji = "🟢" if today_dollar > 0 else ("🔴" if today_dollar < 0 else "⚪")

    # Kümülatif Genel Toplam
    all_trades = stats.get("total_trades", 0)
    all_net_dollar = stats.get("net_dollar_gain", 0.0)
    all_wr = stats.get("win_rate", 0.0)
    all_sign = "+" if all_net_dollar >= 0 else ""
    all_emoji = "🟢" if all_net_dollar > 0 else ("🔴" if all_net_dollar < 0 else "⚪")

    lines = []
    lines.append("⚡ *FAST SCALPER (1m) SAATLİK RAPOR*")
    lines.append(f"⏱️ *Saat:* `{time_str}` | *Tarih:* `{date_str}` (TSİ)")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💼 *FAST Fon Kasası:* `${equity:,.2f} USDT`")
    lines.append(f"{pnl_emoji_1h} *Son 1 Saat PnL:* *{pnl_sign_1h}${dollar_pnl_1h:.2f}* ({pct_sign_1h}%{net_pnl_1h:.2f})")
    lines.append(f"🎯 *Son 1 Saat İşlem:* `{total_1h}` adet (✅ `{wins_1h}` Win | 🛑 `{losses_1h}` Loss)")
    if total_1h > 0:
        lines.append(f"📊 *1 Saatlik Win Rate:* *%{win_rate_1h:.1f}*")
    lines.append(f"💸 *1 Saatlik Komisyon:* `-%{report['fee_pct']:.2f}`")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    if total_1h == 0:
        lines.append("😴 *Son 1 saatte tamamlanan işlem bulunmuyor.*")
        lines.append("_(1 dakikalık mikro trendlerde yüksek confluence şartı taranıyor)._\n")
    else:
        lines.append("📋 *SON 1 SAATTE KAPANAN İŞLEMLER:*")
        for i, t in enumerate(report["trades"], 1):
            sym = t.get("symbol", "")
            d = t.get("direction", "")
            lev = t.get("leverage", 10)
            pnl = t.get("simulated_pnl_pct", 0.0)
            sign = "+" if pnl > 0 else ""
            status = t.get("status", "")
            status_badge = "🎯 TP" if "TP" in status else ("🪜 LADDER" if "LADDER" in status else ("🛡️ BE" if "BE" in status else ("⏱️ ZAMAN AŞIMI" if "TIMEOUT" in status else "🛑 SL")))
            t_margin = t.get("allocated_margin_usdt") or 75.0
            t_dollar = round(t_margin * (pnl / 100.0), 2)
            t_dollar_sign = "+" if t_dollar >= 0 else ""
            pnl_icon = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")

            lines.append(f"{i}. {pnl_icon} *{sym}* ({d} {lev}x) ➔ *{sign}%{pnl:.2f}* ({t_dollar_sign}${t_dollar:.2f}) [{status_badge}]")
        lines.append("")

    active = report.get("active_trades", [])
    if active:
        lines.append(f"📡 *AÇIKTA BEKLEYEN POZİSYONLAR ({len(active)}/10):*")
        for a in active:
            lines.append(f"• `{a.get('symbol')}` ({a.get('direction')} {a.get('leverage', 10)}x) | Giriş: `{a.get('actual_entry_price') or a.get('entry_min')}` | Stop: `{a.get('stop_loss')}`")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📊 *GÜNLÜK & GENEL TOPLAM SONUÇ:*")
    lines.append(f"• *Bugünkü FAST PnL:* {today_emoji} *{today_sign}${today_dollar:.2f}* ({today_sign}%{today_pct:.2f}) | `{today_trades}` İşlem (WR: %{today_wr})")
    lines.append(f"• *Kümülatif Toplam:* {all_emoji} *{all_sign}${all_net_dollar:.2f}* | `{all_trades}` İşlem | WR: *%{all_wr:.1f}*")
    lines.append(f"• *Kasa Durumu:* Başlangıç: $1,000.00 ➔ Güncel: *${equity:,.2f}*")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚡ _FAST Scalper: 1 Dakikalık Çoklu-Ajan Mikro Motoru_")

    return "\n".join(lines)


# ==============================================================================
# SÜPER FAST BOT METOTLARI (SANİYELİK HFT & BAĞIMSIZ $1000 KASA)
# ==============================================================================

def save_super_fast_signal(data: Dict) -> int:
    """Yeni bir Süper FAST saniyelik mikro pozisyonunu kaydeder."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry_price = data.get("actual_entry_price") or data["entry_min"]
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO super_fast_signals (
                symbol, direction, leverage, entry_min, entry_max,
                actual_entry_price, entered_at,
                stop_loss, take_profit_1, take_profit_2, risk_reward,
                risk_grade, news_summary, ta_reasons, chart_entry_png, status,
                allocated_margin_usdt, risk_usd, highest_price, lowest_price,
                super_fast_meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?)
        """, (
            data["symbol"], data["direction"], data.get("leverage", 10),
            data["entry_min"], data["entry_max"],
            entry_price, current_time,
            data["stop_loss"], data["take_profit_1"], data.get("take_profit_2", data["take_profit_1"]),
            data.get("risk_reward", 1.4), data.get("risk_grade", "Süper FAST HFT"),
            data.get("news_summary", "⚡⚡ SÜPER FAST Saniyelik"), data.get("ta_reasons", ""),
            data.get("chart_entry_png", ""),
            data.get("allocated_margin_usdt", 35.0), data.get("risk_usd", 7.5),
            entry_price, entry_price,
            json.dumps(data.get("super_fast_meta", {}))
        ))
        conn.commit()
        return cursor.lastrowid


def update_super_fast_signal_status(signal_id: int, updates: Dict):
    """Süper FAST sinyalinin durumunu veya canlı kâr/zararını günceller."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        set_clauses = []
        values = []
        for key, val in updates.items():
            if key in ("super_fast_meta",) and isinstance(val, (dict, list)):
                val = json.dumps(val)
            set_clauses.append(f"{key} = ?")
            values.append(val)
        values.append(signal_id)
        sql = f"UPDATE super_fast_signals SET {', '.join(set_clauses)} WHERE id = ?"
        cursor.execute(sql, values)
        conn.commit()


def get_super_fast_active_and_pending_signals() -> List[Dict]:
    """Süper FAST bot açık ve aktif saniyelik scalping işlemlerini getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM super_fast_signals
            WHERE status IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')
            ORDER BY id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_super_fast_all_signals(limit: int = 50) -> List[Dict]:
    """Süper FAST bot son sinyallerini ve işlemlerini getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM super_fast_signals
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_super_fast_performance_stats() -> Dict:
    """Süper FAST botun bağımsız $1000 USDT kasalı kaldıraçlı performans özetini hesaplar."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN 1 ELSE 0 END) as loss_count,
                SUM(CASE WHEN simulated_pnl_pct = 0 THEN 1 ELSE 0 END) as be_count,
                AVG(simulated_pnl_pct) as avg_pnl_pct,
                SUM(simulated_pnl_pct) as total_pnl_pct,
                SUM(gross_pnl_pct) as total_gross_pnl_pct,
                SUM(fee_pct) as total_fee_pct,
                SUM(COALESCE(allocated_margin_usdt, 35.0) * (simulated_pnl_pct / 100.0)) as actual_net_dollar_gain,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN (COALESCE(allocated_margin_usdt, 35.0) * (simulated_pnl_pct / 100.0)) ELSE 0 END) as sum_dollar_wins,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN ABS(COALESCE(allocated_margin_usdt, 35.0) * (simulated_pnl_pct / 100.0)) ELSE 0 END) as sum_dollar_losses
            FROM super_fast_signals
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')
              AND simulated_pnl_pct IS NOT NULL
        """)
        row = dict(cursor.fetchone() or {})
        total = row.get("total_trades") or 0
        wins = row.get("win_count") or 0
        losses = row.get("loss_count") or 0
        sum_wins = row.get("sum_dollar_wins") or 0.0
        sum_losses = row.get("sum_dollar_losses") or 0.0

        row["win_rate"] = round((wins / total * 100), 2) if total > 0 else 0.0
        row["profit_factor"] = round((sum_wins / sum_losses), 2) if sum_losses > 0 else (99.0 if sum_wins > 0 else 0.0)
        
        total_pnl = row.get("total_pnl_pct") or 0.0
        row["total_pnl_pct"] = round(total_pnl, 2)
        row["total_gross_pnl_pct"] = round(row.get("total_gross_pnl_pct") or 0.0, 2)
        row["total_fee_pct"] = round(row.get("total_fee_pct") or 0.0, 2)
        row["sum_wins"] = round(sum_wins, 2)
        row["sum_losses"] = round(sum_losses, 2)
        
        # Süper FAST Bağımsız $1000 Kasa Bakiyesi
        net_dollar_gain = row.get("actual_net_dollar_gain") or 0.0
        row["net_dollar_gain"] = round(net_dollar_gain, 2)
        row["portfolio_balance"] = round(1000.0 + net_dollar_gain, 2)

        # Günlük Süper FAST PnL
        from datetime import datetime, timezone, timedelta
        tr_tz = timezone(timedelta(hours=3))
        now_tr = datetime.now(timezone.utc).astimezone(tr_tz)
        today_start_tr = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = today_start_tr.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            SELECT 
                COUNT(*) as today_trades,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN 1 ELSE 0 END) as today_wins,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN 1 ELSE 0 END) as today_losses,
                SUM(simulated_pnl_pct) as today_net_pnl_pct,
                SUM(fee_pct) as today_fee_pct,
                SUM(COALESCE(allocated_margin_usdt, 35.0) * (simulated_pnl_pct / 100.0)) as today_dollar_gain
            FROM super_fast_signals
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')
              AND closed_at >= ?
              AND simulated_pnl_pct IS NOT NULL
        """, (today_start,))
        today_row = dict(cursor.fetchone() or {})
        t_trades = today_row.get("today_trades") or 0
        t_wins = today_row.get("today_wins") or 0

        row["today_trades"] = t_trades
        row["today_wins"] = t_wins
        row["today_losses"] = today_row.get("today_losses") or 0
        row["today_fee_pct"] = round(today_row.get("today_fee_pct") or 0.0, 2)
        row["today_net_pnl_pct"] = round(today_row.get("today_net_pnl_pct") or 0.0, 2)
        row["today_dollar_gain"] = round(today_row.get("today_dollar_gain") or 0.0, 2)
        row["today_win_rate"] = round((t_wins / t_trades * 100.0), 1) if t_trades > 0 else 0.0
        row["today_date_str"] = now_tr.strftime("%Y-%m-%d")

        return row


def add_super_fast_scanner_log_db(symbol: str, status: str, reason: str, details: str = ""):
    """Süper FAST tarayıcı olayını veritabanına kaydeder."""
    time_str = datetime.now().strftime("%H:%M:%S")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO super_fast_scanner_logs (time_str, symbol, status, reason, details)
            VALUES (?, ?, ?, ?, ?)
        """, (time_str, symbol, status, reason, details))
        conn.commit()


def get_super_fast_scanner_logs_db(limit: int = 50) -> List[Dict]:
    """Süper FAST bot son tarama kayıtlarını getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT time_str as time, symbol, status, reason, details
            FROM super_fast_scanner_logs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def close_all_super_fast_positions_db(client=None) -> int:
    """Tüm açık Süper FAST pozisyonlarını anlık piyasa fiyatıyla acilen kapatır."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    closed_count = 0

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM super_fast_signals WHERE status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')")
        open_trades = [dict(r) for r in cursor.fetchall()]

        if not open_trades:
            return 0

        tickers = {}
        if client:
            try:
                tickers = client.get_24hr_tickers()
            except Exception:
                pass

        for t in open_trades:
            sig_id = t["id"]
            sym = t["symbol"]
            direction = t["direction"]
            entry_p = float(t["actual_entry_price"])
            lev = int(t["leverage"] or 10)

            ticker = tickers.get(sym, {})
            exit_price = ticker.get("lastPrice", entry_p)

            if direction == "LONG":
                raw_diff = (exit_price - entry_p) / entry_p
            else:
                raw_diff = (entry_p - exit_price) / entry_p

            gross_margin = raw_diff * lev * 100.0
            fee_pct = 0.10 * lev
            net_margin = gross_margin - fee_pct

            cursor.execute("""
                UPDATE super_fast_signals
                SET status = 'EMERGENCY_CLOSED',
                    closed_at = ?,
                    exit_price = ?,
                    gross_pnl_pct = ?,
                    fee_pct = ?,
                    simulated_pnl_pct = ?
                WHERE id = ?
            """, (current_time, exit_price, round(gross_margin, 2), round(fee_pct, 2), round(net_margin, 2), sig_id))
            closed_count += 1

        conn.commit()
        return closed_count


def clear_super_fast_closed_trades_db():
    """Süper FAST bot kapanmış geçmiş işlem kayıtlarını temizler."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM super_fast_signals WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')")
        conn.commit()


def check_super_fast_side_stoploss_guard(direction: str, max_consecutive_losses: int = 3, cooldown_minutes: int = 15) -> Tuple[bool, str]:
    """Süper FAST bot için yön bazlı seri zarar kalkanı."""
    from datetime import datetime, timezone, timedelta
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, symbol, direction, status, simulated_pnl_pct, closed_at
                FROM super_fast_signals
                WHERE direction = ?
                  AND status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')
                  AND closed_at IS NOT NULL
                ORDER BY closed_at DESC, id DESC
                LIMIT 10
            """, (direction,))
            rows = cursor.fetchall()
            if not rows:
                return False, ""

            consecutive_losses = 0
            last_loss_closed_at = None

            for r in rows:
                pnl = float(r["simulated_pnl_pct"] or 0.0)
                if pnl < 0:
                    consecutive_losses += 1
                    if last_loss_closed_at is None:
                        last_loss_closed_at = r["closed_at"]
                else:
                    break

            if consecutive_losses >= max_consecutive_losses and last_loss_closed_at:
                loss_dt = datetime.strptime(str(last_loss_closed_at)[:19], "%Y-%m-%d %H:%M:%S")
                now = datetime.utcnow()
                elapsed_min = (now - loss_dt).total_seconds() / 60.0
                if elapsed_min < cooldown_minutes:
                    remaining_min = int(cooldown_minutes - elapsed_min)
                    reason = f"⚡⚡ SÜPER FAST YÖN KALKANI: {direction} yönünde peş peşe {consecutive_losses} zarar. {remaining_min} dk donduruldu."
                    return True, reason
    except Exception:
        pass
    return False, ""


def generate_super_fast_hourly_summary_report() -> Dict:
    """Süper FAST Bot için son 1 saatte tamamlanan saniyelik işlemleri, açık pozisyonları ve PnL'i derler."""
    from datetime import datetime, timedelta, timezone
    tr_tz = timezone(timedelta(hours=3))
    now_tr = datetime.now(timezone.utc).astimezone(tr_tz)

    cutoff = datetime.now() - timedelta(hours=1)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM super_fast_signals
            WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')
              AND closed_at IS NOT NULL
              AND closed_at >= ?
            ORDER BY closed_at ASC
        """, (cutoff_str,))
        trades_1h = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""
            SELECT * FROM super_fast_signals
            WHERE status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER')
            ORDER BY created_at DESC
        """)
        active_trades = [dict(r) for r in cursor.fetchall()]

    stats = get_super_fast_performance_stats()
    current_equity = stats.get("portfolio_balance", 1000.0)

    total_count = len(trades_1h)
    wins = [t for t in trades_1h if (t.get("simulated_pnl_pct") or 0.0) > 0]
    losses = [t for t in trades_1h if (t.get("simulated_pnl_pct") or 0.0) < 0]
    bes = [t for t in trades_1h if (t.get("simulated_pnl_pct") or 0.0) == 0]

    total_net_pnl_pct = sum((t.get("simulated_pnl_pct") or 0.0) for t in trades_1h)
    total_gross_pnl_pct = sum((t.get("gross_pnl_pct") or 0.0) for t in trades_1h)
    total_fee_pct = sum((t.get("fee_pct") or 0.0) for t in trades_1h)

    total_dollar_gain = sum(
        (t.get("allocated_margin_usdt") or 35.0) * ((t.get("simulated_pnl_pct") or 0.0) / 100.0)
        for t in trades_1h
    )

    win_rate = (len(wins) / total_count * 100.0) if total_count > 0 else 0.0

    return {
        "date_str": now_tr.strftime("%d.%m.%Y"),
        "time_str": now_tr.strftime("%H:%M"),
        "total_trades": total_count,
        "win_count": len(wins),
        "loss_count": len(losses),
        "be_count": len(bes),
        "win_rate": round(win_rate, 1),
        "net_pnl_pct": round(total_net_pnl_pct, 2),
        "gross_pnl_pct": round(total_gross_pnl_pct, 2),
        "fee_pct": round(total_fee_pct, 2),
        "dollar_pnl": round(total_dollar_gain, 2),
        "current_equity": round(current_equity, 2),
        "trades": trades_1h,
        "active_trades": active_trades,
        "overall_stats": stats
    }


def format_super_fast_hourly_telegram_message(report: Dict) -> str:
    """Süper FAST 1-saatlik raporunu Telegram Markdown formatına dönüştürür."""
    date_str = report["date_str"]
    time_str = report["time_str"]
    total_1h = report["total_trades"]
    wins_1h = report["win_count"]
    losses_1h = report["loss_count"]
    win_rate_1h = report["win_rate"]
    net_pnl_1h = report["net_pnl_pct"]
    dollar_pnl_1h = report["dollar_pnl"]
    equity = report["current_equity"]
    stats = report.get("overall_stats", {})

    pnl_sign_1h = "+" if dollar_pnl_1h >= 0 else ""
    pnl_emoji_1h = "🟢" if dollar_pnl_1h > 0 else ("🔴" if dollar_pnl_1h < 0 else "⚪")
    pct_sign_1h = "+" if net_pnl_1h >= 0 else ""

    today_trades = stats.get("today_trades", 0)
    today_wins = stats.get("today_wins", 0)
    today_losses = stats.get("today_losses", 0)
    today_dollar = stats.get("today_dollar_gain", 0.0)
    today_pct = stats.get("today_net_pnl_pct", 0.0)
    today_wr = round((today_wins / today_trades * 100.0), 1) if today_trades > 0 else 0.0
    today_sign = "+" if today_dollar >= 0 else ""
    today_emoji = "🟢" if today_dollar > 0 else ("🔴" if today_dollar < 0 else "⚪")

    all_trades = stats.get("total_trades", 0)
    all_net_dollar = stats.get("net_dollar_gain", 0.0)
    all_wr = stats.get("win_rate", 0.0)
    all_sign = "+" if all_net_dollar >= 0 else ""
    all_emoji = "🟢" if all_net_dollar > 0 else ("🔴" if all_net_dollar < 0 else "⚪")

    lines = []
    lines.append("⚡⚡ *SÜPER FAST (Saniyelik HFT) SAATLİK RAPOR*")
    lines.append(f"⏱️ *Saat:* `{time_str}` | *Tarih:* `{date_str}` (TSİ)")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💼 *Süper FAST Fon Kasası:* `${equity:,.2f} USDT`")
    lines.append(f"{pnl_emoji_1h} *Son 1 Saat PnL:* *{pnl_sign_1h}${dollar_pnl_1h:.2f}* ({pct_sign_1h}%{net_pnl_1h:.2f})")
    lines.append(f"🎯 *Son 1 Saat İşlem:* `{total_1h}` adet (✅ `{wins_1h}` Win | 🛑 `{losses_1h}` Loss)")
    if total_1h > 0:
        lines.append(f"📊 *1 Saatlik Win Rate:* *%{win_rate_1h:.1f}*")
    lines.append(f"💸 *1 Saatlik Komisyon:* `-%{report['fee_pct']:.2f}`")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    if total_1h == 0:
        lines.append("😴 *Son 1 saatte tamamlanan saniyelik işlem bulunmuyor.*")
        lines.append("_(Saniyelik mikro dalgalanmalarda emir akış momentumu taranıyor)._\n")
    else:
        lines.append("📋 *SON 1 SAATTE KAPANAN MİKRO İŞLEMLER:*")
        for i, t in enumerate(report["trades"], 1):
            sym = t.get("symbol", "")
            d = t.get("direction", "")
            lev = t.get("leverage", 10)
            pnl = t.get("simulated_pnl_pct", 0.0)
            sign = "+" if pnl > 0 else ""
            status = t.get("status", "")
            status_badge = "🎯 TP" if "TP" in status else ("🪜 LADDER" if "LADDER" in status else ("🛡️ BE" if "BE" in status else ("⏱️ ZAMAN AŞIMI" if "TIMEOUT" in status else "🛑 SL")))
            t_margin = t.get("allocated_margin_usdt") or 35.0
            t_dollar = round(t_margin * (pnl / 100.0), 2)
            t_dollar_sign = "+" if t_dollar >= 0 else ""
            pnl_icon = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")

            lines.append(f"{i}. {pnl_icon} *{sym}* ({d} {lev}x) ➔ *{sign}%{pnl:.2f}* ({t_dollar_sign}${t_dollar:.2f}) [{status_badge}]")
        lines.append("")

    active = report.get("active_trades", [])
    if active:
        lines.append(f"📡 *AÇIKTA BEKLEYEN MİKRO POZİSYONLAR ({len(active)}/20):*")
        for a in active:
            lines.append(f"• `{a.get('symbol')}` ({a.get('direction')} {a.get('leverage', 10)}x) | Giriş: `{a.get('actual_entry_price') or a.get('entry_min')}` | Stop: `{a.get('stop_loss')}`")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📊 *GÜNLÜK & GENEL TOPLAM SONUÇ:*")
    lines.append(f"• *Bugünkü Süper FAST PnL:* {today_emoji} *{today_sign}${today_dollar:.2f}* ({today_sign}%{today_pct:.2f}) | `{today_trades}` İşlem (WR: %{today_wr})")
    lines.append(f"• *Kümülatif Toplam:* {all_emoji} *{all_sign}${all_net_dollar:.2f}* | `{all_trades}` İşlem | WR: *%{all_wr:.1f}*")
    lines.append(f"• *Kasa Durumu:* Başlangıç: $1,000.00 ➔ Güncel: *${equity:,.2f}*")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚡⚡ _SÜPER FAST: Saniyelik Mikro-Tick Yüksek Frekans Motoru_")

    return "\n".join(lines)





