"""
Database Layer - SQLite for Signals & Counterfactual (What-If) Paper Trades
Tracks real performance if the trade had been taken, without risking real funds.
"""
import sqlite3
import json
import threading
import time
import random
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any, Callable, Union
from config import DB_PATH

_THREAD_LOCAL = threading.local()

def get_db_connection():
    """
    Thread-safe bağlantı havuzu ve optimize edilmiş SQLite konfigürasyonu.
    Her thread için connection'ı yeniden kullanır, PRAGMA busy_timeout=60000 ve WAL modunu zorlar.
    """
    conn = getattr(_THREAD_LOCAL, 'conn', None)
    if conn is not None:
        try:
            conn.execute("SELECT 1;")
            return conn
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            try:
                conn.close()
            except Exception:
                pass
            conn = None
            _THREAD_LOCAL.conn = None

    conn = sqlite3.connect(DB_PATH, timeout=60.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=60000;")
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    _THREAD_LOCAL.conn = conn
    return conn

def execute_with_retry(func: Callable[[], Any], max_retries: int = 5, base_delay: float = 0.05) -> Any:
    """
    Veritabanı işlemlerini 'database is locked' / 'busy' hatalarına karşı
    exponential backoff ve jitter ile otomatik olarak yeniden dener.
    """
    last_err = None
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            last_err = e
            err_msg = str(e).lower()
            if "locked" in err_msg or "busy" in err_msg:
                sleep_sec = base_delay * (2 ** attempt) + random.uniform(0.01, 0.05)
                time.sleep(sleep_sec)
            else:
                raise e
    if last_err:
        raise last_err

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
            "debate_json": "TEXT DEFAULT ''",
            "partial_tp_taken": "INTEGER DEFAULT 0",
            "realized_pnl_usd": "REAL DEFAULT 0.0",
            "entry_limit_2": "REAL DEFAULT 0.0",
            "entry_limit_2_hit": "INTEGER DEFAULT 0",
            "is_pair_trade": "INTEGER DEFAULT 0",
            "pair_symbol": "TEXT DEFAULT ''",
            "timeframe": "TEXT DEFAULT '15m'",
            "trade_horizon": "TEXT DEFAULT 'Kısa Vade (15m)'"
        }
        for col_name, col_def in new_cols.items():
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE signals ADD COLUMN {col_name} {col_def}")
                except Exception:
                    pass

        # FAST ve SÜPER FAST Tabloları İçin de Taktiksel Sütun Migrasyonu
        tactical_cols = {
            "partial_tp_taken": "INTEGER DEFAULT 0",
            "realized_pnl_usd": "REAL DEFAULT 0.0",
            "entry_limit_2": "REAL DEFAULT 0.0",
            "entry_limit_2_hit": "INTEGER DEFAULT 0",
            "is_pair_trade": "INTEGER DEFAULT 0",
            "pair_symbol": "TEXT DEFAULT ''"
        }
        for tbl in ["fast_signals", "super_fast_signals"]:
            try:
                cursor.execute(f"PRAGMA table_info({tbl})")
                tbl_cols = {row["name"] for row in cursor.fetchall()}
                for c_name, c_def in tactical_cols.items():
                    if c_name not in tbl_cols:
                        cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN {c_name} {c_def}")
            except Exception:
                pass

        # Geçmiş performans metrikleri için index
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)")

        # Kalıcı Gün Sonu Telegram Rapor Takip Defteri (Restart / gece yarısı atlama koruması)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_report_sent_log (
                date_str TEXT PRIMARY KEY,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO daily_report_sent_log (date_str) VALUES ('2026-11-16')")

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

        # Coine Özel Haber Kararlandırma Konseyi Raporları Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS coin_news_investigations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                time_str TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                news_score REAL NOT NULL,
                verdict TEXT NOT NULL,
                is_vetoed INTEGER DEFAULT 0,
                veto_reason TEXT DEFAULT '',
                pos_multiplier REAL DEFAULT 1.0,
                funding_rate_pct REAL DEFAULT 0.0,
                article_count INTEGER DEFAULT 0,
                council_debate_json TEXT DEFAULT '[]',
                top_articles_json TEXT DEFAULT '[]',
                summary TEXT DEFAULT ''
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_coin_news_inv_id ON coin_news_investigations(id DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_coin_news_inv_symbol ON coin_news_investigations(symbol)")

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

        # Otonom Öğrenme Motoru - Sürekli Kendi Kendini Eğitme & Keşif Raporları Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_learning_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                time_str TEXT NOT NULL,
                epoch_num INTEGER NOT NULL,
                status TEXT NOT NULL,
                health_score INTEGER NOT NULL,
                trades_analyzed INTEGER NOT NULL,
                win_rate REAL NOT NULL,
                profit_factor REAL NOT NULL,
                expectancy REAL NOT NULL,
                regime_diagnosis TEXT NOT NULL,
                loss_attribution_json TEXT NOT NULL,
                win_factors_json TEXT NOT NULL,
                hypotheses_json TEXT NOT NULL,
                parameter_deltas_json TEXT NOT NULL,
                summary TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_epoch ON autonomous_learning_reports(epoch_num DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_id ON autonomous_learning_reports(id DESC)")

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

        # Shadow Logging / Filtre Ablasyonu Tablosu (Reddedilen Adayların Pasif Performans Takibi)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shadow_rejections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                timeframe TEXT DEFAULT '15m',
                filter_stage TEXT NOT NULL,
                reject_reason TEXT DEFAULT '',
                confluence_score INTEGER DEFAULT 0,
                entry_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit_1 REAL NOT NULL,
                outcome TEXT DEFAULT 'PENDING',
                evaluated_at TIMESTAMP,
                simulated_r REAL DEFAULT 0.0
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

def save_coin_news_investigation_db(inv_data: Dict) -> int:
    """Coine özel haber konseyi araştırma ve kararlandırma sonucunu veritabanına kaydeder."""
    import json
    from datetime import datetime, timezone, timedelta
    tr_tz = timezone(timedelta(hours=3))
    now_tr = datetime.now(timezone.utc).astimezone(tr_tz)
    time_str = now_tr.strftime("%H:%M:%S")

    symbol = str(inv_data.get("symbol", "")).upper()
    direction = str(inv_data.get("direction", "LONG")).upper()
    news_score = float(inv_data.get("news_score", 50.0))
    verdict = str(inv_data.get("verdict", "NÖTR"))
    is_vetoed = 1 if inv_data.get("is_vetoed") else 0
    veto_reason = str(inv_data.get("veto_reason", ""))
    pos_multiplier = float(inv_data.get("pos_multiplier", 1.0))
    funding_rate_pct = float(inv_data.get("funding_rate_pct", 0.0))
    article_count = int(inv_data.get("article_count", 0))
    council_debate = inv_data.get("council_debate", [])
    top_articles = inv_data.get("top_articles", [])
    summary = str(inv_data.get("summary", ""))

    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Tablonun varlığını garantiye al
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS coin_news_investigations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                time_str TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                news_score REAL NOT NULL,
                verdict TEXT NOT NULL,
                is_vetoed INTEGER DEFAULT 0,
                veto_reason TEXT DEFAULT '',
                pos_multiplier REAL DEFAULT 1.0,
                funding_rate_pct REAL DEFAULT 0.0,
                article_count INTEGER DEFAULT 0,
                council_debate_json TEXT DEFAULT '[]',
                top_articles_json TEXT DEFAULT '[]',
                summary TEXT DEFAULT ''
            )
        """)
        cursor.execute("""
            INSERT INTO coin_news_investigations (
                time_str, symbol, direction, news_score, verdict,
                is_vetoed, veto_reason, pos_multiplier, funding_rate_pct,
                article_count, council_debate_json, top_articles_json, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            time_str, symbol, direction, news_score, verdict,
            is_vetoed, veto_reason, pos_multiplier, funding_rate_pct,
            article_count,
            json.dumps(council_debate, ensure_ascii=False) if isinstance(council_debate, (list, dict)) else str(council_debate),
            json.dumps(top_articles, ensure_ascii=False) if isinstance(top_articles, (list, dict)) else str(top_articles),
            summary
        ))
        conn.commit()
        return cursor.lastrowid

def get_coin_news_investigations_db(limit: int = 25) -> List[Dict]:
    """Son coine özel haber konseyi araştırmalarını getirir."""
    import json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Tablo henüz oluşmamışsa hata vermesin
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS coin_news_investigations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                time_str TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                news_score REAL NOT NULL,
                verdict TEXT NOT NULL,
                is_vetoed INTEGER DEFAULT 0,
                veto_reason TEXT DEFAULT '',
                pos_multiplier REAL DEFAULT 1.0,
                funding_rate_pct REAL DEFAULT 0.0,
                article_count INTEGER DEFAULT 0,
                council_debate_json TEXT DEFAULT '[]',
                top_articles_json TEXT DEFAULT '[]',
                summary TEXT DEFAULT ''
            )
        """)
        cursor.execute("""
            SELECT id, created_at, time_str, symbol, direction, news_score,
                   verdict, is_vetoed, veto_reason, pos_multiplier,
                   funding_rate_pct, article_count, council_debate_json,
                   top_articles_json, summary
            FROM coin_news_investigations
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        rows = []
        for r in cursor.fetchall():
            d = dict(r)
            try:
                d["council_debate"] = json.loads(d.get("council_debate_json") or "[]")
            except Exception:
                d["council_debate"] = []
            try:
                d["top_articles"] = json.loads(d.get("top_articles_json") or "[]")
            except Exception:
                d["top_articles"] = []
            rows.append(d)
        return rows

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

def save_learning_report_db(report_data: Dict) -> int:
    """Otonom öğrenme döngüsü raporunu veritabanına kaydeder."""
    import json
    from datetime import datetime, timezone, timedelta
    tr_tz = timezone(timedelta(hours=3))
    now_tr = datetime.now(timezone.utc).astimezone(tr_tz)
    time_str = now_tr.strftime("%H:%M:%S")

    epoch_num = int(report_data.get("epoch_num", 1))
    status = str(report_data.get("status", "AUTO_APPROVED"))
    health_score = int(report_data.get("health_score", 75))
    trades_analyzed = int(report_data.get("trades_analyzed", 0))
    win_rate = float(report_data.get("win_rate", 50.0))
    profit_factor = float(report_data.get("profit_factor", 1.0))
    expectancy = float(report_data.get("expectancy", 0.0))
    regime_diagnosis = str(report_data.get("regime_diagnosis", "Piyasa analizi yapıldı."))
    loss_attr = report_data.get("loss_attribution", [])
    win_factors = report_data.get("win_factors", [])
    hypotheses = report_data.get("hypotheses", [])
    param_deltas = report_data.get("parameter_deltas", [])
    summary = str(report_data.get("summary", ""))

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_learning_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                time_str TEXT NOT NULL,
                epoch_num INTEGER NOT NULL,
                status TEXT NOT NULL,
                health_score INTEGER NOT NULL,
                trades_analyzed INTEGER NOT NULL,
                win_rate REAL NOT NULL,
                profit_factor REAL NOT NULL,
                expectancy REAL NOT NULL,
                regime_diagnosis TEXT NOT NULL,
                loss_attribution_json TEXT NOT NULL,
                win_factors_json TEXT NOT NULL,
                hypotheses_json TEXT NOT NULL,
                parameter_deltas_json TEXT NOT NULL,
                summary TEXT NOT NULL
            )
        """)
        cursor.execute("""
            INSERT INTO autonomous_learning_reports (
                time_str, epoch_num, status, health_score, trades_analyzed,
                win_rate, profit_factor, expectancy, regime_diagnosis,
                loss_attribution_json, win_factors_json, hypotheses_json,
                parameter_deltas_json, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            time_str, epoch_num, status, health_score, trades_analyzed,
            win_rate, profit_factor, expectancy, regime_diagnosis,
            json.dumps(loss_attr, ensure_ascii=False) if isinstance(loss_attr, (list, dict)) else str(loss_attr),
            json.dumps(win_factors, ensure_ascii=False) if isinstance(win_factors, (list, dict)) else str(win_factors),
            json.dumps(hypotheses, ensure_ascii=False) if isinstance(hypotheses, (list, dict)) else str(hypotheses),
            json.dumps(param_deltas, ensure_ascii=False) if isinstance(param_deltas, (list, dict)) else str(param_deltas),
            summary
        ))
        conn.commit()
        return cursor.lastrowid

def get_learning_reports_db(limit: int = 15) -> List[Dict]:
    """Geçmiş otonom öğrenme ve keşif raporlarını döner."""
    import json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_learning_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                time_str TEXT NOT NULL,
                epoch_num INTEGER NOT NULL,
                status TEXT NOT NULL,
                health_score INTEGER NOT NULL,
                trades_analyzed INTEGER NOT NULL,
                win_rate REAL NOT NULL,
                profit_factor REAL NOT NULL,
                expectancy REAL NOT NULL,
                regime_diagnosis TEXT NOT NULL,
                loss_attribution_json TEXT NOT NULL,
                win_factors_json TEXT NOT NULL,
                hypotheses_json TEXT NOT NULL,
                parameter_deltas_json TEXT NOT NULL,
                summary TEXT NOT NULL
            )
        """)
        cursor.execute("""
            SELECT id, created_at, time_str, epoch_num, status, health_score,
                   trades_analyzed, win_rate, profit_factor, expectancy,
                   regime_diagnosis, loss_attribution_json, win_factors_json,
                   hypotheses_json, parameter_deltas_json, summary
            FROM autonomous_learning_reports
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        rows = []
        for r in cursor.fetchall():
            d = dict(r)
            try:
                d["loss_attribution"] = json.loads(d.get("loss_attribution_json") or "[]")
            except Exception:
                d["loss_attribution"] = []
            try:
                d["win_factors"] = json.loads(d.get("win_factors_json") or "[]")
            except Exception:
                d["win_factors"] = []
            try:
                d["hypotheses"] = json.loads(d.get("hypotheses_json") or "[]")
            except Exception:
                d["hypotheses"] = []
            try:
                d["parameter_deltas"] = json.loads(d.get("parameter_deltas_json") or "[]")
            except Exception:
                d["parameter_deltas"] = []
            rows.append(d)
        return rows

def get_latest_learning_report_db() -> Optional[Dict]:
    """En son yapılan otonom öğrenme raporunu döner."""
    reports = get_learning_reports_db(limit=1)
    return reports[0] if reports else None

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

        timeframe = data.get("timeframe", "15m")
        trade_horizon = data.get("trade_horizon", "Kısa Vade (15m)")
        entry_limit_2 = data.get("entry_limit_2", 0.0)

        cursor.execute("""
            INSERT INTO signals (
                symbol, direction, leverage, entry_min, entry_max,
                actual_entry_price, entered_at,
                stop_loss, take_profit_1, take_profit_2, risk_reward,
                risk_grade, news_summary, ta_reasons, chart_entry_png, status,
                allocated_margin_usdt, risk_usd, highest_price, lowest_price,
                debate_json, entry_limit_2, timeframe, trade_horizon
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?, ?, ?, ?)
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
            debate_json_str,
            entry_limit_2,
            timeframe,
            trade_horizon
        ))
        conn.commit()
        return cursor.lastrowid

def get_active_positions_count() -> int:
    """Açık ve aktif işlem sayısını döner (Kasa Kalkanı kontrolü için)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals WHERE status IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')")
        return cursor.fetchone()[0]

def get_today_trades_count(timeframe: Optional[str] = None) -> int:
    """
    Bugün (Türkiye Saati ile 00:00'dan itibaren) açılan işlem sayısını döner.
    timeframe belirtilirse ('15m', '30m', '1h') yalnızca o zaman dilimindeki işlemleri sayar.
    """
    from datetime import datetime, timezone, timedelta
    tr_tz = timezone(timedelta(hours=3))
    now_tr = datetime.now(timezone.utc).astimezone(tr_tz)
    today_start_tr = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = today_start_tr.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if timeframe:
            clean_tf = str(timeframe).lower().strip()
            cursor.execute("""
                SELECT COUNT(*) FROM signals 
                WHERE created_at >= ? AND (
                    LOWER(COALESCE(timeframe, '')) = ? OR 
                    LOWER(COALESCE(trade_horizon, '')) LIKE ?
                )
            """, (today_start, clean_tf, f"%{clean_tf}%"))
        else:
            cursor.execute("SELECT COUNT(*) FROM signals WHERE created_at >= ?", (today_start,))
        row = cursor.fetchone()
        return row[0] if row else 0

def get_today_trades_count_by_timeframe() -> Dict[str, int]:
    """Bugün açılan işlemleri zaman dilimine göre döner: {'15m': X, '30m': Y, '1h': Z}"""
    return {
        "15m": get_today_trades_count("15m"),
        "30m": get_today_trades_count("30m"),
        "1h": get_today_trades_count("1h")
    }

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
            WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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
            WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
              AND closed_at >= ?
              AND simulated_pnl_pct IS NOT NULL
        """, (today_start,))
        row = cursor.fetchone()
        net_dollar = (row["net_dollar"] if row and row["net_dollar"] is not None else 0.0)
        return round(net_dollar, 2)

def get_open_unprotected_risk_usdt() -> float:
    """Henüz BE+ korumasına (Basamak 1 / Kısmi TP) ulaşmamış açık pozisyonların toplam SL+komisyon riskini ($) döner."""
    total_risk = 0.0
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT actual_entry_price, entry_min, stop_loss, leverage, allocated_margin_usdt,
                       ladder_step, partial_tp_taken
                FROM signals
                WHERE status IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
            """)
            for r in cursor.fetchall():
                if int(r["ladder_step"] or 0) > 0 or int(r["partial_tp_taken"] or 0) > 0:
                    continue
                entry = float(r["actual_entry_price"] or r["entry_min"] or 0.0)
                sl = float(r["stop_loss"] or 0.0)
                lev = int(r["leverage"] or 10)
                margin = float(r["allocated_margin_usdt"] or 150.0)
                if entry > 0 and sl > 0:
                    sl_pct = abs(entry - sl) / entry * 100.0
                    fee_pct = 0.10 * lev
                    total_risk += margin * ((sl_pct * lev + fee_pct) / 100.0)
    except Exception:
        return 0.0
    return round(total_risk, 2)

def get_horizon_score_adjustments_db(lookback_per_tf: int = 15) -> Dict[str, int]:
    """
    Her vade (15m, 30m, 1h) için son kapanmış işlemlere göre dinamik performans ayarlaması döner.
    - Zayıf/eksi beklentili vadeye -6 (barajı +6 yükseltir)
    - Güçlü kârlı vadeye +3 öncelik bonusu verir.
    """
    adj = {"15m": 0, "30m": 0, "1h": 0}
    try:
        buckets: Dict[str, List[float]] = {"15m": [], "30m": [], "1h": []}
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timeframe, trade_horizon, simulated_pnl_pct
                FROM signals
                WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
                  AND simulated_pnl_pct IS NOT NULL
                ORDER BY COALESCE(closed_at, created_at) DESC, id DESC
                LIMIT 60
            """)
            for r in cursor.fetchall():
                tf = str(r["timeframe"] or "").lower().strip()
                if tf not in buckets:
                    hz = str(r["trade_horizon"] or "").lower()
                    tf = "1h" if "1h" in hz else ("30m" if "30m" in hz else "15m")
                if len(buckets[tf]) < lookback_per_tf:
                    buckets[tf].append(float(r["simulated_pnl_pct"] or 0.0))

        for tf, pnls in buckets.items():
            if len(pnls) < 6:
                continue
            wr = (sum(1 for p in pnls if p > 0) / len(pnls)) * 100.0
            exp = sum(pnls) / len(pnls)
            if exp < 0.0 or wr < 52.0:
                adj[tf] = -6
            elif wr >= 68.0 and exp > 0.0:
                adj[tf] = 3
    except Exception:
        pass
    return adj

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

    from config import DAILY_TRAILING_PROFIT_MIN_USDT, DAILY_TRAILING_PROFIT_RATIO
    floor = round(peak * DAILY_TRAILING_PROFIT_RATIO, 2) if peak >= DAILY_TRAILING_PROFIT_MIN_USDT else 0.0
    is_locked = (peak >= DAILY_TRAILING_PROFIT_MIN_USDT and current_pnl <= floor)
    return round(peak, 2), round(floor, 2), is_locked

def is_symbol_locked_by_other_bot(symbol: str, current_bot: str, direction: Optional[str] = None) -> Tuple[bool, str]:
    """
    Multi-Bot Anti-Collision & Anti-Hedging Kalkanı (Kurumsal Çoklu-Motor Protokolü).
    Diğer botların (Standard, FAST, SÜPER FAST) bu sembol üzerinde aktif pozisyonu olup olmadığını denetler:
    1. Zıt Yönlü Kilit (Anti-Hedging): Bir bot LONG iken diğer bot SHORT açamaz (çift komisyon yakımı ve nötr delta önlenir).
    2. Çift Maruziyet Kilidi (Anti-Collision): Başka bir motor aynı sembolde pozisyondaysa yeni işlem engellenir (aynı varlığa yığılma riski önlenir).
    Returns: (is_locked: bool, reason: str)
    """
    bot_tables = {
        "standard": "signals",
        "main": "signals",
        "fast": "fast_signals",
        "super_fast": "super_fast_signals",
        "superfast": "super_fast_signals"
    }

    current_bot_key = current_bot.lower()
    active_statuses = "('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')"
    bots_to_check = [
        ("Standard Bot (15m)", "signals"),
        ("FAST Bot (1m)", "fast_signals"),
        ("SÜPER FAST Bot (1s)", "super_fast_signals")
    ]

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for b_name, tbl in bots_to_check:
                # Kendi tablosunu atla
                if bot_tables.get(current_bot_key) == tbl:
                    continue

                cursor.execute(f"""
                    SELECT id, symbol, direction, status, created_at 
                    FROM {tbl} 
                    WHERE symbol = ? AND status IN {active_statuses}
                    LIMIT 1
                """, (symbol,))
                row = cursor.fetchone()
                if row:
                    other_dir = row["direction"]
                    # 1. Zıt yönlü pozisyon: Kesinlikle engelle
                    if direction and direction.upper() != other_dir.upper():
                        return True, f"Anti-Hedging Kilidi: {symbol} üzerinde {b_name} zıt yönlü ({other_dir}) işlemde! Çapraz komisyon yakımı engellendi."
                    # 2. Aynı varlıkta çakışma: Başka bir bot zaten devrede
                    return True, f"Anti-Collision Kilidi: {symbol} üzerinde {b_name} zaten açık bir ({other_dir}) pozisyona sahip! Çift risk engellendi."
    except Exception as e:
        print(f"⚠️ [is_symbol_locked_by_other_bot Hata]: {e}")
        return False, ""

    return False, ""

def get_active_and_pending_signals() -> List[Dict]:
    """Halen takip edilmesi gereken aktif veya giriş bekleyen sinyalleri getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM signals 
            WHERE status IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
              AND simulated_pnl_pct < 0
              AND closed_at IS NOT NULL
            ORDER BY closed_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        return row["closed_at"] if row else None

def get_last_loss_for(symbol: str, direction: str) -> Optional[str]:
    """Belirli bir sembol ve yönde son kapanan zararlı işlemin kapanış zamanını döner (Sembol+Yön Soğuma Kalkanı)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT closed_at FROM signals
            WHERE symbol = ? AND direction = ?
              AND status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
              AND simulated_pnl_pct < 0
              AND closed_at IS NOT NULL
            ORDER BY closed_at DESC
            LIMIT 1
        """, (symbol, direction))
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
    """Tüm sinyalleri (aktif ve geçmiş) son kapatılan en üstte olacak şekilde getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM signals 
            ORDER BY COALESCE(closed_at, created_at) DESC, id DESC 
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
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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
              AND status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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
                WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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

_PARTIAL_REMAINING_RATIOS = {0: 1.00, 1: 0.50, 2: 0.65, 3: 0.325}

def reconcile_partial_pnl(
    allocated_margin: float,
    partial_tp_taken: int,
    realized_pnl_usd: float,
    net_pnl_pct: float,
    fee_pct: float,
    final_status: str = ""
) -> Tuple[float, float, float]:
    """Kısmi kâr alımı (Basamak 1 %35 veya TP1 %50) yapılmış pozisyonun toplam net PnL ve orijinal marjinini hesaplar."""
    ratio = _PARTIAL_REMAINING_RATIOS.get(int(partial_tp_taken or 0), 1.00)
    if ratio == 1.00:
        return net_pnl_pct, round(net_pnl_pct + fee_pct, 2), allocated_margin
    orig_margin = round(allocated_margin / ratio, 2)
    runner_usd = allocated_margin * (net_pnl_pct / 100.0)
    total_dollar_pnl = realized_pnl_usd + runner_usd
    if final_status == "CLOSED_BE" and total_dollar_pnl < 0.25:
        total_dollar_pnl = max(0.25, round(orig_margin * 0.0025, 2))
    merged_net = round((total_dollar_pnl / orig_margin) * 100.0, 2) if orig_margin > 0 else net_pnl_pct
    merged_gross = round(merged_net + fee_pct, 2)
    return merged_net, merged_gross, orig_margin

def close_single_signal_db(symbol_or_id: Union[str, int], client=None) -> Optional[Dict]:
    """Belirtilen sinyal ID veya paritedeki açık pozisyonu anlık piyasa fiyatıyla manuel olarak kapatır."""
    is_id = False
    sig_id_target = None
    clean_sym = ""

    if isinstance(symbol_or_id, int):
        is_id = True
        sig_id_target = symbol_or_id
    elif isinstance(symbol_or_id, str) and symbol_or_id.strip().isdigit() and int(symbol_or_id.strip()) > 0:
        is_id = True
        sig_id_target = int(symbol_or_id.strip())
    else:
        clean_sym = str(symbol_or_id).upper().strip()
        if not clean_sym.endswith("USDT") and not clean_sym.endswith("USDT.P"):
            clean_sym = f"{clean_sym}USDT"

    active_statuses = ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'PENDING_ENTRY', 'ACTIVE_PARTIAL_TP1')

    with get_db_connection() as conn:
        cursor = conn.cursor()
        if is_id:
            cursor.execute("""
                SELECT * FROM signals 
                WHERE id = ? AND status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'PENDING_ENTRY', 'ACTIVE_PARTIAL_TP1')
                LIMIT 1
            """, (sig_id_target,))
        else:
            cursor.execute("""
                SELECT * FROM signals 
                WHERE symbol = ? AND status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'PENDING_ENTRY', 'ACTIVE_PARTIAL_TP1')
                ORDER BY id DESC LIMIT 1
            """, (clean_sym,))
        row = cursor.fetchone()
        if not row:
            return None
        sig = dict(row)

    sig_id = sig["id"]
    clean_sym = sig["symbol"]
    direction = sig["direction"]
    leverage = sig.get("leverage") or 10
    entry_price = float(sig.get("actual_entry_price") or sig.get("entry_min") or 0.0)
    exit_price = entry_price

    # 1. En hızlı ve hassas: WebSocket canlı fiyatı
    try:
        from core.binance_streamer import get_live_price
        ws_p = get_live_price(clean_sym)
        if ws_p and float(ws_p) > 0:
            exit_price = float(ws_p)
    except Exception:
        pass

    # 2. WebSocket yoksa veya sıfırsa REST API fiyatı
    if exit_price == entry_price and client:
        try:
            tickers = client.get_24hr_tickers()
            if clean_sym in tickers:
                exit_price = float(tickers[clean_sym].get("lastPrice", entry_price))
        except Exception:
            try:
                t = client.get_ticker(clean_sym)
                if t and "lastPrice" in t:
                    exit_price = float(t["lastPrice"])
            except Exception:
                pass

    raw_change = ((exit_price - entry_price) / entry_price) if direction == "LONG" else ((entry_price - exit_price) / entry_price) if entry_price > 0 else 0.0
    gross_pnl_pct = round(raw_change * leverage * 100, 2)
    fee_pct = round(0.10 * leverage, 2)
    net_pnl_pct = round(gross_pnl_pct - fee_pct, 2)

    # Kısmi kâr (Basamak 1 veya TP1) alınmışsa birleşik kâr ve orijinal marjini koru
    partial_tp_taken = int(sig.get("partial_tp_taken") or 0)
    allocated_margin = float(sig.get("allocated_margin_usdt") or 200.0)
    prev_realized_usd = float(sig.get("realized_pnl_usd") or 0.0)
    net_pnl_pct, gross_pnl_pct, final_margin_to_save = reconcile_partial_pnl(
        allocated_margin, partial_tp_taken, prev_realized_usd, net_pnl_pct, fee_pct, "MANUAL_CLOSE"
    )

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
                fee_pct = ?,
                allocated_margin_usdt = ?
            WHERE id = ?
        """, (now_str, exit_price, net_pnl_pct, gross_pnl_pct, fee_pct, final_margin_to_save, sig_id))
        conn.commit()

    sig["status"] = "MANUAL_CLOSE"
    sig["closed_at"] = now_str
    sig["exit_price"] = exit_price
    sig["simulated_pnl_pct"] = net_pnl_pct
    sig["gross_pnl_pct"] = gross_pnl_pct
    sig["fee_pct"] = fee_pct
    sig["allocated_margin_usdt"] = final_margin_to_save

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

    # Telegram Anlık Bildirimi
    try:
        from agents.notifier_agent import NotifierAgent
        notifier = NotifierAgent()
        if notifier.has_telegram:
            sign_char = "+" if net_pnl_pct >= 0 else ""
            dollar_gain = round(final_margin_to_save * (net_pnl_pct / 100.0), 2)
            dollar_str = f"+${dollar_gain:.2f}" if dollar_gain >= 0 else f"-${abs(dollar_gain):.2f}"
            msg = (
                f"👤 <b>[MANUEL KAPATMA - PİYASA EMRİ]</b>\n\n"
                f"🪙 <b>Parite:</b> <code>{clean_sym}</code> ({direction} {leverage}x)\n"
                f"💵 <b>Giriş:</b> <code>{entry_price}</code> ➡️ <b>Çıkış:</b> <code>{exit_price}</code>\n"
                f"📊 <b>Net Getiri:</b> <b>{sign_char}{net_pnl_pct:.2f}% ({dollar_str})</b>\n"
                f"📌 <b>Durum:</b> İşlem kullanıcı tarafından market fiyatından kapatıldı."
            )
            notifier.send_text_message(msg)
    except Exception:
        pass

    return sig

def close_positions_by_outcome_db(outcome: str, client=None) -> Dict:
    """
    Kârda veya zararda olan tüm aktif pozisyonları anlık piyasa fiyatından kapatır.
    outcome: 'profit' / 'kar' (kârdakiler) veya 'loss' / 'zarar' (zarardakiler)
    """
    from core.binance_streamer import get_live_price
    target_group = (outcome or "").lower().strip()
    active_signals = get_active_and_pending_signals()
    if not active_signals:
        return {"status": "success", "group": target_group, "count": 0, "closed": [], "message": "Aktif pozisyon bulunamadı"}

    tickers = {}
    if client:
        try:
            tickers = client.get_24hr_tickers()
        except Exception:
            pass

    target_group = outcome.lower().strip()
    closed_list = []

    for sig in active_signals:
        sig_id = sig["id"]
        symbol = sig["symbol"]
        direction = sig["direction"]
        leverage = sig.get("leverage") or 10
        entry_price = float(sig.get("actual_entry_price") or sig.get("entry_min") or 0.0)

        # Anlık canlı fiyatı al
        exit_price = entry_price
        ws_p = get_live_price(symbol)
        if ws_p and float(ws_p) > 0:
            exit_price = float(ws_p)
        elif tickers and symbol in tickers:
            exit_price = float(tickers[symbol].get("lastPrice", entry_price))

        raw_change = ((exit_price - entry_price) / entry_price) if direction == "LONG" else ((entry_price - exit_price) / entry_price) if entry_price > 0 else 0.0
        gross_pnl_pct = round(raw_change * leverage * 100, 2)
        fee_pct = round(0.10 * leverage, 2)
        net_pnl_pct = round(gross_pnl_pct - fee_pct, 2)

        is_candidate = False
        if target_group in ("profit", "green", "kar"):
            if net_pnl_pct > 0:
                is_candidate = True
        elif target_group in ("loss", "red", "zarar"):
            if net_pnl_pct < 0:
                is_candidate = True

        if is_candidate:
            closed_res = close_single_signal_db(sig_id, client=client)
            if closed_res:
                closed_list.append(closed_res)

    return {
        "status": "success",
        "group": target_group,
        "count": len(closed_list),
        "closed": closed_list
    }

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

            p_taken = int(sig.get("partial_tp_taken") or 0)
            a_margin = float(sig.get("allocated_margin_usdt") or 200.0)
            p_realized = float(sig.get("realized_pnl_usd") or 0.0)
            net_pnl_pct, gross_pnl_pct, final_margin_to_save = reconcile_partial_pnl(
                a_margin, p_taken, p_realized, net_pnl_pct, fee_pct, "MANUAL_CLOSE"
            )

            cursor.execute("""
                UPDATE signals SET
                    status = 'MANUAL_CLOSE',
                    closed_at = ?,
                    exit_price = ?,
                    simulated_pnl_pct = ?,
                    gross_pnl_pct = ?,
                    fee_pct = ?,
                    allocated_margin_usdt = ?
                WHERE id = ?
            """, (now_str, exit_price, net_pnl_pct, gross_pnl_pct, fee_pct, final_margin_to_save, sig_id))
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
        cursor.execute("DELETE FROM signals WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')")
        conn.commit()

def get_current_equity() -> float:
    """Anlık toplam fon kasasını (Bileşik Kasa Değeri) döner (Örn: $1,000 + Net Dolar PnL)."""
    try:
        stats = get_performance_stats()
        return float(stats.get("portfolio_balance", 1000.0))
    except Exception:
        return 1000.0

def is_daily_report_sent_db(date_str: str) -> bool:
    """Belirtilen TSİ günü (YYYY-MM-DD) için gün sonu Telegram raporunun gönderilip gönderilmediğini döner."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM daily_report_sent_log WHERE date_str = ?", (date_str,))
            return cursor.fetchone() is not None
    except Exception:
        return False

def mark_daily_report_sent_db(date_str: str):
    """Belirtilen TSİ günü (YYYY-MM-DD) için gün sonu Telegram raporunu kalıcı olarak işaretler."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO daily_report_sent_log (date_str) VALUES (?)", (date_str,))
            conn.commit()
    except Exception:
        pass

def generate_daily_summary_report(target_date_str: Optional[str] = None) -> Dict:
    """Belirtilen TSİ gününün (veya bugünün) kapanan işlemlerini, net kâr/zararını ve gün sonu özetini derler."""
    from datetime import datetime, timedelta, timezone
    tr_tz = timezone(timedelta(hours=3))
    now_tr = datetime.now(timezone.utc).astimezone(tr_tz)

    if target_date_str:
        base_tr = datetime.strptime(target_date_str[:10], "%Y-%m-%d").replace(tzinfo=tr_tz)
        day_start_tr = base_tr.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end_tr = base_tr.replace(hour=23, minute=59, second=59, microsecond=999999)
        day_start_utc = day_start_tr.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        day_end_utc = day_end_tr.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        report_date_label = base_tr.strftime("%d.%m.%Y")
        report_time_label = now_tr.strftime("%H:%M") if target_date_str[:10] == now_tr.strftime("%Y-%m-%d") else "23:59 (Telafi)"
    else:
        day_start_tr = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start_tr.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        day_end_utc = None
        report_date_label = now_tr.strftime("%d.%m.%Y")
        report_time_label = now_tr.strftime("%H:%M")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        if day_end_utc is not None:
            cursor.execute("""
                SELECT * FROM signals
                WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
                  AND closed_at IS NOT NULL
                  AND closed_at >= ? AND closed_at <= ?
                ORDER BY closed_at DESC, id DESC
            """, (day_start_utc, day_end_utc))
            trades = [dict(r) for r in cursor.fetchall()]
            period_type = f"{report_date_label} (TSİ 00:00 - 23:59)"
        else:
            cursor.execute("""
                SELECT * FROM signals
                WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
                  AND closed_at IS NOT NULL
                  AND closed_at >= ?
                ORDER BY closed_at DESC, id DESC
            """, (day_start_utc,))
            trades = [dict(r) for r in cursor.fetchall()]
            period_type = "Bugün (TSİ 00:00 - 23:59)"

            # Eğer bugün henüz hiç işlem kapanmamışsa (ve belirli bir gün sorulmamışsa) son 24 saate bak
            if not trades:
                cutoff = datetime.utcnow() - timedelta(hours=24)
                cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("""
                    SELECT * FROM signals
                    WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
                      AND closed_at IS NOT NULL
                      AND closed_at >= ?
                    ORDER BY closed_at DESC, id DESC
                """, (cutoff_str,))
                trades = [dict(r) for r in cursor.fetchall()]
                if trades:
                    period_type = "Son 24 Saat"

        cursor.execute("""
            SELECT * FROM signals
            WHERE status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
            ORDER BY created_at DESC
        """)
        active_trades = [dict(r) for r in cursor.fetchall()]

    stats = get_performance_stats()
    current_equity = stats.get("portfolio_balance", 1000.0)

    total_count = len(trades)
    wins = [t for t in trades if (t.get("simulated_pnl_pct") or 0.0) > 0]
    losses = [t for t in trades if (t.get("simulated_pnl_pct") or 0.0) < 0]
    bes = [t for t in trades if (t.get("simulated_pnl_pct") or 0.0) == 0]

    total_net_pnl_pct = sum((t.get("simulated_pnl_pct") or 0.0) for t in trades)
    total_gross_pnl_pct = sum((t.get("gross_pnl_pct") or 0.0) for t in trades)
    total_fee_pct = sum((t.get("fee_pct") or 0.0) for t in trades)

    # Dolar bazlı kâr/zarar hesabı (allocated_margin * pnl_pct / 100)
    total_dollar_gain = sum(
        (t.get("allocated_margin_usdt") or 150.0) * ((t.get("simulated_pnl_pct") or 0.0) / 100.0)
        for t in trades
    )

    win_rate = (len(wins) / total_count * 100.0) if total_count > 0 else 0.0

    # Vade dağılımı (15m, 30m, 1h)
    c_15m = 0
    c_30m = 0
    c_1h = 0
    for t in trades:
        tf = (t.get("timeframe") or "").lower()
        hz = (t.get("trade_horizon") or "").lower()
        if tf == "1h" or "1h" in hz or "uzun" in hz:
            c_1h += 1
        elif tf == "30m" or "30m" in hz or "orta" in hz:
            c_30m += 1
        else:
            c_15m += 1

    return {
        "date_str": report_date_label,
        "time_str": report_time_label,
        "period_type": period_type,
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
        "c_15m": c_15m,
        "c_30m": c_30m,
        "c_1h": c_1h,
        "trades": trades,
        "active_trades": active_trades
    }

def format_daily_telegram_message(report: Dict) -> str:
    """Gün sonu raporunu gereksiz fazlalıklardan arındırılmış, profesyonel ve sade Telegram formatına dönüştürür."""
    date_str = report["date_str"]
    time_str = report["time_str"]
    total = report["total_trades"]
    wins = report["win_count"]
    losses = report["loss_count"]
    bes = report.get("be_count", 0)
    win_rate = report["win_rate"]
    net_pnl = report["net_pnl_pct"]
    dollar_pnl = report["dollar_pnl"]
    equity = report["current_equity"]
    c15 = report.get("c_15m", 0)
    c30 = report.get("c_30m", 0)
    c1h = report.get("c_1h", 0)
    fee = report.get("fee_pct", 0.0)

    pnl_sign = "+" if dollar_pnl >= 0 else ""
    pnl_emoji = "🟢" if dollar_pnl > 0 else ("🔴" if dollar_pnl < 0 else "⚪")
    pct_sign = "+" if net_pnl >= 0 else ""

    lines = []
    lines.append("🏆 *GÜN SONU PERFORMANS RAPORU*")
    lines.append(f"🗓️ `{date_str}` (TSİ {time_str}) | *Günlük Bilanço*")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💼 *Fon Kasası:* `${equity:,.2f} USDT`")
    lines.append(f"{pnl_emoji} *Günlük Net PnL:* *{pnl_sign}${dollar_pnl:.2f}* ({pct_sign}%{net_pnl:.2f})")
    be_str = f" | 🛡️ {bes}BE" if bes > 0 else ""
    lines.append(f"🎯 *Toplam İşlem:* `{total}` adet (🟢 {wins}W | 🔴 {losses}L{be_str})")
    lines.append(f"📊 *Win Rate (WR):* *%{win_rate:.1f}* | *Komisyon:* `-%{fee:.2f}`")
    lines.append(f"⏱️ *Vade Dağılımı:* `⚡15m: {c15} • 🎯30m: {c30} • 👑1h: {c1h}`")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")

    if total == 0:
        lines.append("\n😴 *Bugün tamamlanan işlem bulunmuyor.*")
        lines.append("_(Sermaye koruma kalkanı devrede, gereksiz risk alınmadı.)_")
    else:
        lines.append("\n📋 *GÜNÜN KAPANAN İŞLEMLERİ:*")
        for t in report["trades"][:15]:
            sym = t.get("symbol", "").replace("USDT", "")
            d = t.get("direction", "LONG")
            lev = t.get("leverage", 10)
            pnl = t.get("simulated_pnl_pct", 0.0)
            status = t.get("status", "")

            # Çıkış etiketi
            if "TP" in status:
                badge = "🎯 TP"
            elif "LADDER" in status:
                badge = "🪜 Kâr Al"
            elif "BE" in status:
                badge = "🛡️ BE+"
            elif "TIMEOUT" in status:
                badge = "⏱️ Süre Aşımı"
            elif "MANUAL" in status:
                badge = "🛑 El İle"
            else:
                badge = "🛑 SL"

            # Vade rozeti
            tf = (t.get("timeframe") or "").lower()
            hz = (t.get("trade_horizon") or "").lower()
            if tf == "1h" or "1h" in hz or "uzun" in hz:
                tf_tag = "👑1h"
            elif tf == "30m" or "30m" in hz or "orta" in hz:
                tf_tag = "🎯30m"
            else:
                tf_tag = "⚡15m"

            t_margin = t.get("allocated_margin_usdt") or 150.0
            t_dollar = round(t_margin * (pnl / 100.0), 2)
            dollar_abs = abs(t_dollar)
            pnl_abs = abs(pnl)

            if t_dollar > 0:
                dollar_str = f"+${dollar_abs:.2f}"
            elif t_dollar < 0:
                dollar_str = f"-${dollar_abs:.2f}"
            else:
                dollar_str = "$0.00"

            if pnl > 0:
                pct_str = f"+%{pnl_abs:.1f}"
            elif pnl < 0:
                pct_str = f"-%{pnl_abs:.1f}"
            else:
                pct_str = "%0.0"

            icon = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")

            # Tek satırda temiz ve kompakt format
            lines.append(f"• {icon} *{sym}* ({d} {lev}x • {tf_tag}) ➔ *{dollar_str}* ({pct_str}) [{badge}]")

        if len(report["trades"]) > 15:
            lines.append(f"_...ve {len(report['trades']) - 15} diğer işlem daha._")

    active = report.get("active_trades", [])
    if active:
        lines.append(f"\n⏳ *AÇIK POZİSYONLAR ({len(active)}):*")
        for a in active:
            a_sym = a.get("symbol", "").replace("USDT", "")
            a_tf = a.get("timeframe") or ("1h" if "1h" in (a.get("trade_horizon") or "") else ("30m" if "30m" in (a.get("trade_horizon") or "") else "15m"))
            lines.append(f"• `{a_sym}` ({a.get('direction')} {a.get('leverage', 10)}x • {a_tf}) | Giriş: `${a.get('actual_entry_price') or a.get('entry_min')}`")

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
                  AND status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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
            WHERE status IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
            ORDER BY id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

def get_fast_all_signals(limit: int = 50) -> List[Dict]:
    """FAST bot tüm geçmiş ve aktif işlemlerini son kapatılan en üstte olacak şekilde getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM fast_signals
            ORDER BY COALESCE(closed_at, created_at) DESC, id DESC
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
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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
            WHERE status IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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
        cursor.execute("DELETE FROM fast_signals WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')")
        conn.commit()

def reset_fast_bot_db():
    """FAST bot (1m) tüm açık ve kapalı işlemlerini ve tarama günlüklerini sıfırlar. Kasa $1000'dan temiz başlar."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM fast_signals;")
        cursor.execute("DELETE FROM fast_scanner_logs;")
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
                  AND status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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
            WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
              AND closed_at IS NOT NULL
              AND closed_at >= ?
            ORDER BY closed_at ASC
        """, (cutoff_str,))
        trades_1h = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""
            SELECT * FROM fast_signals
            WHERE status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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
            WHERE status IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
            ORDER BY id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_super_fast_all_signals(limit: int = 50) -> List[Dict]:
    """Süper FAST bot son sinyallerini ve işlemlerini son kapatılan en üstte olacak şekilde getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM super_fast_signals
            ORDER BY COALESCE(closed_at, created_at) DESC, id DESC
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
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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
        cursor.execute("SELECT * FROM super_fast_signals WHERE status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')")
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
        cursor.execute("DELETE FROM super_fast_signals WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')")
        conn.commit()


def reset_super_fast_bot_db():
    """Süper FAST bot (1s) tüm açık ve kapalı işlemlerini ve tarama günlüklerini sıfırlar. Kasa $1000'dan temiz başlar."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM super_fast_signals;")
        cursor.execute("DELETE FROM super_fast_scanner_logs;")
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
                  AND status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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
            WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
              AND closed_at IS NOT NULL
              AND closed_at >= ?
            ORDER BY closed_at ASC
        """, (cutoff_str,))
        trades_1h = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""
            SELECT * FROM super_fast_signals
            WHERE status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
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


def save_shadow_rejection(data: dict) -> int:
    """Filtrelerin reddettiği bir adayı pasif olarak shadow_rejections tablosuna kaydeder (30 dk mükerrer korumalı)."""
    try:
        symbol = data.get("symbol", "")
        direction = data.get("direction", "")
        filter_stage = data.get("filter_stage", "UNKNOWN")
        entry_price = float(data.get("entry_price") or 0.0)
        stop_loss = float(data.get("stop_loss") or 0.0)
        take_profit_1 = float(data.get("take_profit_1") or 0.0)
        if not symbol or not direction or entry_price <= 0 or stop_loss <= 0 or take_profit_1 <= 0:
            return 0
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM shadow_rejections
                WHERE symbol = ? AND direction = ? AND filter_stage = ?
                  AND created_at >= datetime('now', '-30 minutes')
                LIMIT 1
            """, (symbol, direction, filter_stage))
            if cursor.fetchone():
                return 0
            cursor.execute("""
                INSERT INTO shadow_rejections (
                    symbol, direction, timeframe, filter_stage, reject_reason,
                    confluence_score, entry_price, stop_loss, take_profit_1
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol,
                direction,
                data.get("timeframe", "15m"),
                filter_stage,
                str(data.get("reject_reason", ""))[:300],
                int(data.get("confluence_score") or 0),
                entry_price,
                stop_loss,
                take_profit_1,
            ))
            conn.commit()
            return cursor.lastrowid or 0
    except Exception:
        return 0


def get_pending_shadow_rejections(limit: int = 15) -> list:
    """Henüz sonucu değerlendirilmemiş shadow ret kayıtlarını döndürür."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM shadow_rejections
                WHERE outcome = 'PENDING'
                  AND created_at <= datetime('now', '-15 minutes')
                ORDER BY created_at ASC
                LIMIT ?
            """, (limit,))
            return [dict(r) for r in cursor.fetchall()]
    except Exception:
        return []


def update_shadow_rejection(shadow_id: int, outcome: str, simulated_r: float):
    """Shadow ret kaydının varsayımsal TP/SL sonucunu günceller."""
    try:
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE shadow_rejections
                SET outcome = ?, simulated_r = ?, evaluated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (outcome, round(float(simulated_r), 2), shadow_id))
            conn.commit()
    except Exception:
        pass


def get_shadow_ablation_summary() -> list:
    """Her filtre aşamasının elenen adaylardaki gerçek TP/SL isabet istatistiğini döndürür."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    filter_stage,
                    COUNT(*) AS total_logged,
                    SUM(CASE WHEN outcome = 'WOULD_WIN_TP1' THEN 1 ELSE 0 END) AS would_win,
                    SUM(CASE WHEN outcome = 'WOULD_LOSE_SL' THEN 1 ELSE 0 END) AS would_lose,
                    ROUND(AVG(CASE WHEN outcome IN ('WOULD_WIN_TP1', 'WOULD_LOSE_SL') THEN simulated_r END), 2) AS avg_r
                FROM shadow_rejections
                GROUP BY filter_stage
                ORDER BY total_logged DESC
            """)
            return [dict(r) for r in cursor.fetchall()]
    except Exception:
        return []






