"""
Database Layer - SQLite for Signals & Counterfactual (What-If) Paper Trades
Tracks real performance if the trade had been taken, without risking real funds.
"""
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
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
    today_start = datetime.now(timezone.utc).astimezone(tr_tz).strftime("%Y-%m-%d 00:00:00")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals WHERE created_at >= ?", (today_start,))
        row = cursor.fetchone()
        return row[0] if row else 0

def get_today_net_dollar_loss() -> float:
    """Bugün (Türkiye Saati ile 00:00'dan itibaren) kapanan işlemlerin net dolar bazlı toplam kaybını kontrol eder (Circuit Breaker)."""
    from datetime import datetime, timezone, timedelta
    tr_tz = timezone(timedelta(hours=3))
    today_start = datetime.now(timezone.utc).astimezone(tr_tz).strftime("%Y-%m-%d 00:00:00")
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

        return row

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



