"""
All-in-One Trading Office Dashboard for Binance Futures Trade Bot (v2.2.0)
Visualizes the active trading desk like a real office:
- Live Interactive Binance Futures Bitcoin Candlestick Chart (15m, 1h, 4h, 1D)
- Active Scalps with Real SVG Candlestick Charts & Exact Green TP / Red SL levels
- Scanner & Analysis Desk: Live feed of coins examined and why approved/rejected
- News & Sentiment Desk (Sağ Alt): Live market news with Bullish/Bearish tags
- Bottom PnL Ledger & Realized Vault
"""
import os
import sys
import json
import webbrowser
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, render_template_string, send_from_directory, request
import functools

from config import (
    CHARTS_DIR,
    DB_PATH,
    MAX_CONCURRENT_TRADES,
    BINANCE_ROUNDTRIP_FEE_PCT,
    PORTFOLIO_EQUITY_USDT
)
from core.binance_client import BinanceFuturesClient
from core.timeutil import utc_now
from core.database import (
    get_all_signals,
    get_active_and_pending_signals,
    get_performance_stats
)
from agents.scanner_agent import get_scanner_logs, add_scanner_log
from agents.news_agent import get_live_news_feed, NewsAgent

app = Flask(__name__)
client = BinanceFuturesClient()
news_agent = NewsAgent()

import hmac
import time as _time

_WEAK_PINS = {"", "6004", "0000", "1234", "123456", "admin", "password"}


def _load_admin_pin():
    """ADMIN_PIN ortam değişkenini okur. Tanımsız/zayıfsa yönetim uç noktaları kapalı kalır (varsayılan PIN yoktur)."""
    pin = str(os.getenv("ADMIN_PIN") or "").strip()
    if pin.lower() in _WEAK_PINS or len(pin) < 6:
        print("🔒 [Güvenlik] ADMIN_PIN tanımlı değil veya zayıf (en az 6 karakter, varsayılan 6004 kabul edilmez). "
              "Yönetim butonları ADMIN_PIN ortam değişkeni ayarlanana kadar devre dışı.")
        return None
    return pin


ADMIN_PIN = _load_admin_pin()
_PIN_MAX_FAILS = 5
_PIN_LOCK_SECONDS = 15 * 60
_pin_fail_log: dict = {}
_pin_fail_lock = threading.Lock()


def _client_ip() -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    return (fwd.split(",")[0].strip() if fwd else "") or (request.remote_addr or "unknown")


def check_admin_pin_request():
    """(ok, http_status, mesaj) döner. IP başına 5 hatalı denemede 15 dk kilitler (kaba kuvvet koruması)."""
    if not ADMIN_PIN:
        return False, 503, "🔒 Sunucuda ADMIN_PIN tanımlı değil. Yönetim işlemleri için ortam değişkenine en az 6 karakterlik bir PIN ekleyin."
    ip = _client_ip()
    now = _time.time()
    with _pin_fail_lock:
        fails, first_ts = _pin_fail_log.get(ip, (0, now))
        if fails >= _PIN_MAX_FAILS and now - first_ts < _PIN_LOCK_SECONDS:
            return False, 429, "🔒 Çok fazla hatalı PIN denemesi. 15 dakika sonra tekrar deneyin."
        if now - first_ts >= _PIN_LOCK_SECONDS:
            fails, first_ts = 0, now
    pin = request.headers.get("X-Admin-Pin") or (request.get_json(silent=True) or {}).get("pin") or ""
    if pin and hmac.compare_digest(str(pin).strip().encode(), ADMIN_PIN.encode()):
        with _pin_fail_lock:
            _pin_fail_log.pop(ip, None)
        return True, 200, ""
    with _pin_fail_lock:
        _pin_fail_log[ip] = (fails + 1, first_ts)
    return False, 401, "🔒 Yetkisiz Erişim: Bu işlem için geçerli Yönetici Güvenlik PIN kodu gereklidir!"


def require_admin_pin(func):
    """
    Kritik yönetim, tarama ve yapay zeka (ücretli API) uç noktalarını yetkisiz erişime karşı korur.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        ok, code, msg = check_admin_pin_request()
        if not ok:
            return jsonify({"status": "error", "success": False, "message": msg, "error": msg}), code
        return func(*args, **kwargs)
    return wrapper

_orchestrator = None

# Arayüz şablonu ayrı dosyada tutulur (templates/office.html) — Jinja render_template_string ile işlenir
HTML_OFFICE_TEMPLATE = (Path(__file__).resolve().parent / "templates" / "office.html").read_text(encoding="utf-8")

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

V3_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "v3.html"


@app.route("/")
def index():
    """Ana panel: v3 Çok Faktörlü Motor terminali."""
    return V3_TEMPLATE_PATH.read_text(encoding="utf-8")


@app.route("/legacy")
def legacy_index():
    """Eski SMC tarama paneli (SMC motoru yeni işlem açmıyor; geçmiş ve açık SMC işlemleri için)."""
    return render_template_string(HTML_OFFICE_TEMPLATE)


@app.route("/carry")
def carry_page():
    from flask import redirect
    return redirect("/", code=302)


@app.route("/api/v3/market")
def api_v3_market():
    """Motor evrenindeki coinlerin son fiyatı ve 24 saatlik değişimi (salt-okunur, 20 sn önbellekli kaynak)."""
    try:
        from config import CARRY_UNIVERSE
        from core.binance_client import BinanceFuturesClient
        t = BinanceFuturesClient().get_24hr_tickers() or {}
        out = [{"symbol": s, "price": t[s]["lastPrice"], "change_pct": t[s]["priceChangePercent"],
                "quote_volume": t[s]["quoteVolume"]} for s in CARRY_UNIVERSE if s in t]
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _maintenance_notifier():
    if _orchestrator is not None and getattr(_orchestrator, "notifier", None) is not None:
        return _orchestrator.notifier
    from agents.notifier_agent import NotifierAgent
    return NotifierAgent()


@app.route("/api/system/storage")
def api_system_storage():
    """Disk kullanımı, tablo boyutları, bakım ve yedek durumu (salt-okunur)."""
    try:
        import config as cfg
        from core import maintenance as mt
        rep = dict(mt.storage_report())
        st = mt.load_state()
        latest = mt.latest_backup()
        rep["maintenance"] = {
            "auto": cfg.ENABLE_AUTO_MAINTENANCE, "running": mt.is_running(),
            "schedule_utc": f"{cfg.MAINTENANCE_HOUR_UTC:02d}:{cfg.MAINTENANCE_MINUTE_UTC:02d}",
            "next_run": mt.next_run(), "due_now": mt.due_now(), "last_run": st.get("last_run"),
            "last_cleanup": st.get("last_cleanup"), "last_backup": st.get("last_backup"),
            "last_errors": st.get("last_errors", {}),
        }
        rep["backup"] = {"telegram_configured": mt.telegram_configured(), "telegram_enabled": cfg.BACKUP_TELEGRAM,
                         "keep": cfg.BACKUP_KEEP, "latest": latest.name if latest else None}
        return jsonify(rep)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/export/records.zip")
def api_export_records():
    """Tüm işlem kayıtları CSV olarak (zip). ?fmt=std -> standart CSV; varsayılan Türkçe Excel biçimi."""
    from flask import Response
    from core import maintenance as mt
    fmt = "std" if request.args.get("fmt") == "std" else "tr"
    key = f"export_{fmt}"
    cached = mt._CACHE.get(key)
    if cached and _time.time() - cached[0] < 30:
        data = cached[1]
    else:
        positions = None
        try:
            from agents.carry_agent import get_live_engine
            positions = get_live_engine().snapshot()["positions"]
        except Exception:
            pass
        data = mt.build_export_zip(fmt, positions)
        mt._CACHE[key] = (_time.time(), data)
    name = f"tradebot_kayitlar_{mt._utc_now():%Y%m%d_%H%M}{'_std' if fmt == 'std' else ''}.zip"
    return Response(data, mimetype="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.route("/api/system/cleanup", methods=["POST"])
@require_admin_pin
def api_system_cleanup():
    from core import maintenance as mt
    if mt.run_in_background("cleanup"):
        return jsonify({"success": True, "message": "Temizlik başlatıldı."}), 202
    return jsonify({"success": False, "message": "Başka bir bakım işlemi sürüyor."}), 409


@app.route("/api/system/backup", methods=["POST"])
@require_admin_pin
def api_system_backup():
    from core import maintenance as mt
    if mt.run_in_background("backup", _maintenance_notifier()):
        return jsonify({"success": True, "message": "Yedek hazırlanıyor."}), 202
    return jsonify({"success": False, "message": "Başka bir bakım işlemi sürüyor."}), 409


@app.route("/api/system/backup/latest")
@require_admin_pin
def api_system_backup_latest():
    from core import maintenance as mt
    p = mt.latest_backup()
    if not p:
        return jsonify({"success": False, "message": "Henüz yedek yok."}), 404
    return send_from_directory(str(p.parent), p.name, as_attachment=True)


@app.route("/api/carry")
def api_carry():
    """v3 Çok Faktörlü Motor durumu (salt-okunur)."""
    try:
        from agents.carry_agent import get_live_engine
        eng = get_live_engine()
        snap = eng.snapshot()
        eq = list(reversed(eng.store.recent("carry_equity", limit=24 * 120)))
        snap["equity_curve"] = [{"t": r["ts"], "v": round(r["equity"], 2)} for r in eq]
        snap["fills"] = eng.store.recent("carry_fills", limit=60)
        snap["rebalances"] = [{k: v for k, v in r.items() if k != "signal_json"}
                              for r in eng.store.recent("carry_rebalances", limit=30)]
        return jsonify(snap)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/charts/<path:filename>")
def serve_chart(filename):
    return send_from_directory(CHARTS_DIR, filename)

_terminal_cache = {
    "btc_regime": {"status": "NEUTRAL", "btc_price": 0, "summary": "Piyasa taranıyor..."},
    "stats": {},
    "total_unrealized_pnl": 0.0,
    "total_unrealized_dollar": 0.0,
    "active_positions": [],
    "scanner_logs": [],
    "news_feed": [],
    "coin_news_investigations": [],
    "trade_history": [],
    "committee_debates": [],
    "trade_reflections": [],
    "learning_reports": [],
    "tuning_info": {},
    "timeline_quotas": {"total": {"used": 0, "max": 15}, "15m": {"used": 0, "max": 6}, "30m": {"used": 0, "max": 5}, "1h": {"used": 0, "max": 4}}
}

# İlk açılışta ekranın boş kalmaması veya gidip gelmemesi için DB'den anında besle
try:
    from core.database import (
        get_scanner_logs_db, get_news_feed_db, get_coin_news_investigations_db, get_performance_stats,
        get_all_signals, get_active_and_pending_signals, get_latest_debates_db,
        get_recent_reflections_db, get_learning_reports_db,
        get_fast_performance_stats, get_fast_active_and_pending_signals,
        get_fast_all_signals, get_fast_scanner_logs_db
    )
    from core.self_tuning_engine import SelfTuningEngine
    _terminal_cache["stats"] = get_performance_stats() or {}
    _terminal_cache["scanner_logs"] = get_scanner_logs_db(limit=40) or []
    _terminal_cache["news_feed"] = get_news_feed_db(limit=25) or []
    _terminal_cache["coin_news_investigations"] = get_coin_news_investigations_db(limit=25) or []
    _terminal_cache["learning_reports"] = get_learning_reports_db(limit=15) or []
    _all_init = get_all_signals(limit=40) or []
    _terminal_cache["trade_history"] = [s for s in _all_init if s.get("status") not in ("ACTIVE", "PENDING_ENTRY", "ACTIVE_BE", "ACTIVE_LADDER", "ACTIVE_PARTIAL_TP1")]
    _terminal_cache["active_positions"] = get_active_and_pending_signals() or []
    _terminal_cache["committee_debates"] = get_latest_debates_db(limit=8) or []
    _terminal_cache["trade_reflections"] = get_recent_reflections_db(limit=15) or []
    _terminal_cache["tuning_info"] = SelfTuningEngine.run_autonomous_training_cycle(auto_commit=True) or {}
except Exception:
    pass
_cache_lock = threading.Lock()
_updater_started = False

def update_terminal_cache_loop():
    """Arka planda piyasa ve pozisyon verilerini kesintisiz ve hatasız günceller (Sıfır Donma, Sıfır Gidip Gelme)."""
    global _terminal_cache
    cached_tickers = {}
    cached_klines = {}
    cached_fast_klines = {}

    import time
    while True:
        try:
            # 1. Binance Tickers
            try:
                fresh_tickers = client.get_24hr_tickers()
                if fresh_tickers:
                    cached_tickers = fresh_tickers
            except Exception:
                pass

            # 2. BTC Rejimi
            try:
                btc_regime = client.get_btc_regime()
            except Exception:
                with _cache_lock:
                    btc_regime = _terminal_cache.get("btc_regime", {"status": "NEUTRAL", "btc_price": 0})

            # 3. İstatistikler & Veritabanı
            try:
                stats = get_performance_stats()
                active_signals = get_active_and_pending_signals()
                all_sigs = get_all_signals(limit=40)
                history = [s for s in all_sigs if s.get("status") not in ("ACTIVE", "PENDING_ENTRY", "ACTIVE_BE", "ACTIVE_LADDER", "ACTIVE_PARTIAL_TP1")]
                scanner_logs = get_scanner_logs()
                news_feed = get_live_news_feed()
                if not news_feed:
                    news_feed = news_agent.fetch_latest_market_news()
                debates = get_latest_debates_db(limit=8)
                reflections = get_recent_reflections_db(limit=15)
                coin_investigations = get_coin_news_investigations_db(limit=25)
                learning_reports = get_learning_reports_db(limit=15)

                # Otonom Kendi Kendini Eğitme Kontrolü (Her 3 dakikada bir otomatik eğitim döngüsü)
                if not hasattr(update_terminal_cache_loop, "_last_auto_train_ts"):
                    update_terminal_cache_loop._last_auto_train_ts = time.time()
                if time.time() - update_terminal_cache_loop._last_auto_train_ts > 180:
                    try:
                        SelfTuningEngine.run_autonomous_training_cycle(auto_commit=True)
                        update_terminal_cache_loop._last_auto_train_ts = time.time()
                        learning_reports = get_learning_reports_db(limit=15)
                    except Exception:
                        pass

                # Bağımsız Gün Sonu & Shadow Telegram Rapor Zamanlayıcısı (Her 60 sn kontrol)
                if not hasattr(update_terminal_cache_loop, "_last_daily_report_check_ts"):
                    update_terminal_cache_loop._last_daily_report_check_ts = 0.0
                if time.time() - update_terminal_cache_loop._last_daily_report_check_ts > 60:
                    update_terminal_cache_loop._last_daily_report_check_ts = time.time()
                    try:
                        from datetime import timezone, timedelta
                        from core.database import is_daily_report_sent_db, mark_daily_report_sent_db
                        from agents.notifier_agent import NotifierAgent
                        now_tr = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=3)))
                        today_tr = now_tr.strftime("%Y-%m-%d")
                        yest_tr = (now_tr - timedelta(days=1)).strftime("%Y-%m-%d")
                        if not is_daily_report_sent_db(yest_tr):
                            rep_y = NotifierAgent().send_daily_summary_report(target_date_str=yest_tr)
                            if rep_y.get("sent", False):
                                mark_daily_report_sent_db(yest_tr)
                        if now_tr.hour == 23 and now_tr.minute >= 50 and not is_daily_report_sent_db(today_tr):
                            rep_t = NotifierAgent().send_daily_summary_report(target_date_str=today_tr)
                            if rep_t.get("sent", False):
                                mark_daily_report_sent_db(today_tr)
                    except Exception:
                        pass
            except Exception:
                with _cache_lock:
                    stats = _terminal_cache.get("stats", {})
                    active_signals = []
                    history = _terminal_cache.get("trade_history", [])
                    scanner_logs = _terminal_cache.get("scanner_logs", [])
                    news_feed = _terminal_cache.get("news_feed", [])
                    coin_investigations = _terminal_cache.get("coin_news_investigations", [])
                    learning_reports = _terminal_cache.get("learning_reports", [])
                    debates = _terminal_cache.get("committee_debates", [])
                    reflections = _terminal_cache.get("trade_reflections", [])

            # FAST Bot devre dışı (saniyelik ölü SQLite sorguları kaldırıldı)
            FAST_MAX_CONCURRENT_TRADES = 0
            fast_stats = {}
            fast_active_signals = []
            fast_history = []
            fast_scanner_logs = []

            # 4. Standart Aktif Pozisyonlar ve Çizgi Fiyatları
            active_positions = []
            total_unrealized_pnl = 0.0
            total_unrealized_dollar = 0.0

            from core.binance_streamer import get_live_price, is_streamer_connected
            from core.database import reconcile_partial_pnl

            for sig in active_signals:
                symbol = sig["symbol"]
                ws_price = get_live_price(symbol)
                ticker = cached_tickers.get(symbol, {})
                entry_price = float(sig.get("actual_entry_price") or sig["entry_min"] or 0.0)
                live_price = float(ws_price if ws_price else ticker.get("lastPrice", entry_price) or entry_price)
                leverage = sig.get("leverage", 10)
                direction = sig["direction"]

                gross_pnl_pct = 0.0
                fee_pct = round(BINANCE_ROUNDTRIP_FEE_PCT * leverage, 2)
                net_pnl_pct = 0.0
                if entry_price > 0:
                    if direction == "LONG":
                        raw_diff = (live_price - entry_price) / entry_price
                    else:
                        raw_diff = (entry_price - live_price) / entry_price
                    gross_pnl_pct = round(raw_diff * leverage * 100, 2)
                    net_pnl_pct = round(gross_pnl_pct - fee_pct, 2)

                pos_margin = float(sig.get("allocated_margin_usdt") or 200.0)
                partial_tp_taken = int(sig.get("partial_tp_taken") or 0)
                realized_usd = float(sig.get("realized_pnl_usd") or 0.0)
                net_pnl_pct, gross_pnl_pct, orig_margin = reconcile_partial_pnl(
                    pos_margin, partial_tp_taken, realized_usd, net_pnl_pct, fee_pct
                )
                if entry_price > 0 or partial_tp_taken > 0:
                    total_unrealized_pnl += net_pnl_pct
                pos_dollar_gain = round(orig_margin * (net_pnl_pct / 100.0), 2)
                total_unrealized_dollar += pos_dollar_gain

                # Mum verisini çek (100 mumluk ortak önbellekten beslenerek REST yükünü azalt)
                try:
                    klines = client.get_klines(symbol, interval="15m", limit=100)
                    if klines:
                        cached_klines[symbol] = klines[-16:]
                except Exception:
                    pass

                entered_str = sig.get("entered_at") or sig.get("created_at")
                elapsed_str = "1 dk"
                if entered_str:
                    try:
                        t_str = str(entered_str).replace('T', ' ').split('.')[0]
                        dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
                        diff_sec = max(0, int((utc_now() - dt).total_seconds()))
                        mins = diff_sec // 60
                        secs = diff_sec % 60
                        if mins == 0:
                            elapsed_str = f"{secs} sn"
                        elif mins < 60:
                            elapsed_str = f"{mins} dk"
                        else:
                            elapsed_str = f"{mins // 60} sa {mins % 60} dk"
                    except Exception:
                        pass

                sig_dict = dict(sig)
                sig_dict["elapsed_str"] = elapsed_str
                sig_dict["live_price"] = live_price
                sig_dict["unrealized_pnl_pct"] = net_pnl_pct
                sig_dict["unrealized_pnl_dollar"] = pos_dollar_gain
                sig_dict["allocated_margin_usdt"] = pos_margin
                sig_dict["gross_pnl_pct"] = gross_pnl_pct
                sig_dict["fee_pct"] = fee_pct
                sig_dict["ladder_step"] = sig.get("ladder_step") or 0
                sig_dict["ladder_name"] = sig.get("ladder_name") or ""
                sig_dict["recent_candles"] = cached_klines.get(symbol, [])
                active_positions.append(sig_dict)

            # 5 & 6. FAST / SÜPER FAST Scalper devre dışı (boş önbellek değerleri)
            fast_active_positions = []
            fast_total_unrealized_pnl = 0.0
            fast_total_unrealized_dollar = 0.0
            SUPER_FAST_MAX_CONCURRENT_TRADES = 0
            super_fast_stats = {}
            super_fast_active_positions = []
            super_fast_total_unrealized_pnl = 0.0
            super_fast_total_unrealized_dollar = 0.0
            super_fast_history = []
            super_fast_scanner_logs = []

            # Vade Kotaları Bilgisini Derle
            try:
                from core.database import get_today_trades_count_by_timeframe, get_today_trades_count
                from config import DAILY_MAX_TRADES_15M, DAILY_MAX_TRADES_30M, DAILY_MAX_TRADES_1H, DAILY_BASE_MAX_TRADES
                t_counts = get_today_trades_count_by_timeframe()
                t_total = get_today_trades_count()
                sum_used = t_counts.get("15m", 0) + t_counts.get("30m", 0) + t_counts.get("1h", 0)
                used_final = max(t_total, sum_used)
                timeline_quotas = {
                    "total": {"used": used_final, "max": DAILY_BASE_MAX_TRADES},
                    "15m": {"used": t_counts.get("15m", 0), "max": DAILY_MAX_TRADES_15M},
                    "30m": {"used": t_counts.get("30m", 0), "max": DAILY_MAX_TRADES_30M},
                    "1h": {"used": t_counts.get("1h", 0), "max": DAILY_MAX_TRADES_1H}
                }
            except Exception:
                timeline_quotas = _terminal_cache.get("timeline_quotas", {
                    "total": {"used": 0, "max": 15},
                    "15m": {"used": 0, "max": 6},
                    "30m": {"used": 0, "max": 5},
                    "1h": {"used": 0, "max": 4}
                })

            # Atomik Olarak Önbelleği Güncelle
            with _cache_lock:
                _terminal_cache = {
                    "ws_connected": is_streamer_connected(),
                    "btc_regime": btc_regime,
                    "stats": stats,
                    "max_concurrent_trades": MAX_CONCURRENT_TRADES,
                    "timeline_quotas": timeline_quotas,
                    "total_unrealized_pnl": round(total_unrealized_pnl, 2),
                    "total_unrealized_dollar": round(total_unrealized_dollar, 2),
                    "active_positions": active_positions,
                    "scanner_logs": scanner_logs if scanner_logs else _terminal_cache.get("scanner_logs", []),
                    "news_feed": news_feed if news_feed else _terminal_cache.get("news_feed", []),
                    "coin_news_investigations": coin_investigations if coin_investigations else _terminal_cache.get("coin_news_investigations", []),
                    "trade_history": history if history else _terminal_cache.get("trade_history", []),
                    "committee_debates": debates if debates else _terminal_cache.get("committee_debates", []),
                    "trade_reflections": reflections if reflections else _terminal_cache.get("trade_reflections", []),
                    "tuning_info": _terminal_cache.get("tuning_info", {}),
                    "learning_reports": learning_reports if learning_reports else _terminal_cache.get("learning_reports", []),
                    # FAST Scalper (1m) Bağımsız Alanı
                    "fast_stats": fast_stats,
                    "fast_max_concurrent_trades": FAST_MAX_CONCURRENT_TRADES,
                    "fast_total_unrealized_pnl": round(fast_total_unrealized_pnl, 2),
                    "fast_total_unrealized_dollar": round(fast_total_unrealized_dollar, 2),
                    "fast_active_positions": fast_active_positions,
                    "fast_trade_history": fast_history if fast_history else _terminal_cache.get("fast_trade_history", []),
                    "fast_scanner_logs": fast_scanner_logs if fast_scanner_logs else _terminal_cache.get("fast_scanner_logs", []),
                    # SÜPER FAST Scalper (Saniyelik) Bağımsız Alanı
                    "super_fast_stats": super_fast_stats,
                    "super_fast_max_concurrent_trades": SUPER_FAST_MAX_CONCURRENT_TRADES,
                    "super_fast_total_unrealized_pnl": round(super_fast_total_unrealized_pnl, 2),
                    "super_fast_total_unrealized_dollar": round(super_fast_total_unrealized_dollar, 2),
                    "super_fast_active_positions": super_fast_active_positions,
                    "super_fast_trade_history": super_fast_history if super_fast_history else _terminal_cache.get("super_fast_trade_history", []),
                    "super_fast_scanner_logs": super_fast_scanner_logs if super_fast_scanner_logs else _terminal_cache.get("super_fast_scanner_logs", [])
                }

        except Exception:
            pass

        time.sleep(1.2)

@app.route("/api/data")
def api_data():
    with _cache_lock:
        return jsonify(_terminal_cache)


@app.route("/api/audit/live", methods=["GET"])
@require_admin_pin
def api_audit_live():
    """Canlı Railway veritabanındaki tüm botların son işlemlerini, açık pozisyonları ve shadow ablasyon özetini döndürür."""
    from core.database import (
        get_db_connection,
        get_current_equity,
        get_fast_performance_stats,
        get_super_fast_performance_stats,
        get_shadow_ablation_summary,
    )
    hours = max(1, min(168, int(request.args.get("hours", 36))))
    cutoff_expr = f"-{hours} hours"
    fast_stats = get_fast_performance_stats() or {}
    sf_stats = get_super_fast_performance_stats() or {}
    result = {
        "server_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "hours": hours,
        "telegram_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")),
        "equities": {
            "standard": round(float(get_current_equity()), 2),
            "fast": round(float(fast_stats.get("portfolio_balance", 1000.0)), 2),
            "super_fast": round(float(sf_stats.get("portfolio_balance", 1000.0)), 2),
        },
        "bots": {},
        "shadow_ablation": get_shadow_ablation_summary(),
        "daily_reports_sent": [],
        "recent_scanner_logs": [],
    }
    with get_db_connection() as conn:
        cur = conn.cursor()
        for bot_key, tbl in [("standard", "signals"), ("fast", "fast_signals"), ("super_fast", "super_fast_signals")]:
            try:
                cur.execute(f"""
                    SELECT id, created_at, closed_at, symbol, direction, leverage, status,
                           actual_entry_price, exit_price, stop_loss, take_profit_1,
                           simulated_pnl_pct, gross_pnl_pct, fee_pct, allocated_margin_usdt, risk_usd
                    FROM {tbl}
                    WHERE created_at >= datetime('now', ?)
                       OR status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1', 'PENDING_ENTRY', 'PENDING')
                    ORDER BY id DESC
                    LIMIT 60
                """, (cutoff_expr,))
                result["bots"][bot_key] = [dict(r) for r in cur.fetchall()]
            except Exception as e:
                result["bots"][bot_key] = {"error": str(e)}
        try:
            cur.execute("""
                SELECT created_at, time_str, symbol, status, reason, details
                FROM scanner_logs
                ORDER BY id DESC
                LIMIT 20
            """)
            result["recent_scanner_logs"] = [dict(r) for r in cur.fetchall()]
        except Exception:
            pass
        try:
            cur.execute("""
                SELECT date_str, sent_at
                FROM daily_report_sent_log
                ORDER BY date_str DESC
                LIMIT 10
            """)
            result["daily_reports_sent"] = [dict(r) for r in cur.fetchall()]
        except Exception:
            pass
    return jsonify(result)

@app.route("/api/news/coin-investigations", methods=["GET"])
def api_news_coin_investigations():
    from core.database import get_coin_news_investigations_db
    limit = int(request.args.get("limit", 25))
    return jsonify(get_coin_news_investigations_db(limit=limit))

@app.route("/api/news/investigate", methods=["GET", "POST"])
@require_admin_pin
def api_news_investigate():
    global _terminal_cache
    if request.method == "POST" and request.is_json:
        data = request.get_json() or {}
        symbol = data.get("symbol", "BTC")
        direction = data.get("direction", "LONG")
    else:
        symbol = request.args.get("symbol", "BTC")
        direction = request.args.get("direction", "LONG")
    
    if not symbol:
        return jsonify({"success": False, "error": "Sembol belirtilmelidir (örn: SOL, BTC)"}), 400
    
    try:
        from agents.news_agent import NewsAgent
        from core.database import get_coin_news_investigations_db
        agent = NewsAgent()
        clean_sym = symbol.strip().upper()
        if not clean_sym.endswith("USDT") and not clean_sym.endswith("BUSD"):
            clean_sym += "USDT"
        inv = agent.investigate_coin_news(clean_sym, direction.strip().upper())
        
        # Önbelleği de anında güncelle
        with _cache_lock:
            _terminal_cache["coin_news_investigations"] = get_coin_news_investigations_db(limit=25)
            
        return jsonify({"success": True, "data": inv})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/reflections")
def api_reflections():
    from core.database import get_recent_reflections_db
    return jsonify(get_recent_reflections_db(limit=30))

@app.route("/api/tuning", methods=["GET"])
def api_tuning():
    # Salt-okunur: GET isteği parametre değiştirmez veya eğitim döngüsü başlatmaz
    from core.self_tuning_engine import SelfTuningEngine
    from core.database import get_latest_learning_report_db
    return jsonify({"current_params": SelfTuningEngine.get_current_params(), "latest_report": get_latest_learning_report_db()})

@app.route("/api/tuning/reports", methods=["GET"])
def api_tuning_reports():
    from core.database import get_learning_reports_db
    limit = int(request.args.get("limit", 15))
    return jsonify(get_learning_reports_db(limit=limit))

@app.route("/api/tuning/run-autonomous", methods=["POST"])
@require_admin_pin
def api_tuning_run_autonomous():
    global _terminal_cache
    from core.self_tuning_engine import SelfTuningEngine
    from core.database import get_learning_reports_db
    res = SelfTuningEngine.run_autonomous_training_cycle(auto_commit=True)
    with _cache_lock:
        _terminal_cache["tuning_info"] = res
        _terminal_cache["learning_reports"] = get_learning_reports_db(limit=15)
    return jsonify({"success": True, "data": res})

@app.route("/api/tuning/calibrate", methods=["POST"])
@require_admin_pin
def api_tuning_calibrate():
    global _terminal_cache
    from core.self_tuning_engine import SelfTuningEngine
    from core.database import get_learning_reports_db
    res = SelfTuningEngine.run_calibration_cycle(min_trades_required=5)
    with _cache_lock:
        _terminal_cache["tuning_info"] = res
        _terminal_cache["learning_reports"] = get_learning_reports_db(limit=15)
    return jsonify(res)

@app.route("/api/scan", methods=["POST"])
@require_admin_pin
def api_scan():
    global _orchestrator
    if _orchestrator:
        threading.Thread(target=_orchestrator.run_cycle, daemon=True).start()
        return jsonify({"status": "Scan started in background"})
    else:
        from main import TradingBotOrchestrator
        orch = TradingBotOrchestrator()
        threading.Thread(target=orch.run_cycle, daemon=True).start()
        return jsonify({"status": "Scan triggered"})

@app.route("/api/close-position", methods=["POST"])
@require_admin_pin
def api_close_single_position():
    data = request.get_json(silent=True) or {}
    symbol = data.get("symbol") or request.args.get("symbol")
    sig_id = data.get("signal_id") or request.args.get("signal_id")
    target = sig_id if sig_id else symbol

    if not target:
        return jsonify({"status": "error", "message": "Parite (symbol) veya Sinyal ID belirtilmedi"}), 400

    from core.database import (
        close_single_signal_db, get_performance_stats, get_all_signals, get_active_and_pending_signals
    )
    closed_sig = close_single_signal_db(target, client=client)
    if not closed_sig:
        return jsonify({"status": "error", "message": f"{target} için aktif pozisyon bulunamadı veya işlem zaten kapanmış"}), 404

    with _cache_lock:
        active_sigs = get_active_and_pending_signals() or []
        _terminal_cache["active_positions"] = active_sigs
        _terminal_cache["stats"] = get_performance_stats()
        _all_init = get_all_signals(limit=40) or []
        _terminal_cache["trade_history"] = [
            s for s in _all_init if s.get("status") not in ("ACTIVE", "PENDING_ENTRY", "ACTIVE_BE", "ACTIVE_LADDER", "ACTIVE_PARTIAL_TP1")
        ]

    return jsonify({
        "status": "success",
        "message": f"{closed_sig.get('symbol')} pozisyonu piyasa fiyatından kapatıldı.",
        "signal": closed_sig
    })

@app.route("/api/close-positions-group", methods=["POST"])
@require_admin_pin
def api_close_positions_group():
    data = request.get_json(silent=True) or {}
    group = data.get("group") or request.args.get("group")
    if not group or group.lower() not in ("profit", "kar", "green", "loss", "zarar", "red"):
        return jsonify({"status": "error", "message": "Geçerli bir grup belirtilmedi ('profit' veya 'loss')"}), 400

    from core.database import (
        close_positions_by_outcome_db, get_performance_stats, get_all_signals, get_active_and_pending_signals
    )
    res = close_positions_by_outcome_db(group, client=client)

    with _cache_lock:
        active_sigs = get_active_and_pending_signals() or []
        _terminal_cache["active_positions"] = active_sigs
        _terminal_cache["stats"] = get_performance_stats()
        _all_init = get_all_signals(limit=40) or []
        _terminal_cache["trade_history"] = [
            s for s in _all_init if s.get("status") not in ("ACTIVE", "PENDING_ENTRY", "ACTIVE_BE", "ACTIVE_LADDER", "ACTIVE_PARTIAL_TP1")
        ]

    return jsonify({
        "status": "success",
        "group": res.get("group"),
        "count": res.get("count", 0),
        "closed": res.get("closed", []),
        "message": f"{res.get('count', 0)} adet pozisyon piyasa fiyatından kapatıldı."
    })

@app.route("/api/close-all-positions", methods=["POST"])
@require_admin_pin
def api_close_all_positions():
    from core.database import close_all_active_signals_db, get_performance_stats, get_all_signals
    count = close_all_active_signals_db(client=client)
    with _cache_lock:
        _terminal_cache["active_positions"] = []
        _terminal_cache["total_unrealized_pnl"] = 0.0
        _terminal_cache["total_unrealized_dollar"] = 0.0
        _terminal_cache["stats"] = get_performance_stats()
        _all_init = get_all_signals(limit=40) or []
        _terminal_cache["trade_history"] = [s for s in _all_init if s.get("status") not in ("ACTIVE", "PENDING_ENTRY", "ACTIVE_BE", "ACTIVE_LADDER", "ACTIVE_PARTIAL_TP1")]
    return jsonify({"status": "closed", "count": count})

@app.route("/api/clear-history", methods=["POST"])
@require_admin_pin
def api_clear_history():
    from core.database import clear_closed_trades_db, get_performance_stats
    clear_closed_trades_db()
    with _cache_lock:
        _terminal_cache["trade_history"] = []
        _terminal_cache["stats"] = get_performance_stats()
    return jsonify({"status": "cleared"})


@app.route("/api/reset-quota", methods=["POST"])
@require_admin_pin
def api_reset_quota():
    """Bugünkü işlem kotasını geçmiş işlemleri silmeden sıfırlar."""
    from core.database import (
        reset_today_trade_quota_db,
        get_today_trades_count_by_timeframe,
        get_today_trades_count,
    )
    from config import (
        DAILY_MAX_TRADES_15M,
        DAILY_MAX_TRADES_30M,
        DAILY_MAX_TRADES_1H,
        DAILY_BASE_MAX_TRADES,
    )
    reset_at_utc = reset_today_trade_quota_db()
    t_counts = get_today_trades_count_by_timeframe()
    t_total = get_today_trades_count()
    used_final = max(t_total, t_counts.get("15m", 0) + t_counts.get("30m", 0) + t_counts.get("1h", 0))
    timeline_quotas = {
        "total": {"used": used_final, "max": DAILY_BASE_MAX_TRADES},
        "15m": {"used": t_counts.get("15m", 0), "max": DAILY_MAX_TRADES_15M},
        "30m": {"used": t_counts.get("30m", 0), "max": DAILY_MAX_TRADES_30M},
        "1h": {"used": t_counts.get("1h", 0), "max": DAILY_MAX_TRADES_1H},
    }
    with _cache_lock:
        _terminal_cache["timeline_quotas"] = timeline_quotas
    return jsonify({"status": "reset", "reset_at_utc": reset_at_utc, "timeline_quotas": timeline_quotas})


@app.route("/api/ai/status", methods=["GET"])
def api_ai_status():
    from core.database import get_gemini_api_key
    key = get_gemini_api_key()
    masked = f"{key[:4]}...{key[-4:]}" if len(key) >= 10 else ("***" if key else "")
    return jsonify({"configured": bool(key), "masked_key": masked, "model": "gemini-3-flash-preview"})


@app.route("/api/ai/config", methods=["POST"])
@require_admin_pin
def api_ai_config():
    from core.database import set_gemini_api_key_db, get_gemini_api_key
    data = request.get_json(silent=True) or {}
    api_key = str(data.get("api_key") or "").strip()
    set_gemini_api_key_db(api_key)
    saved = get_gemini_api_key()
    masked = f"{saved[:4]}...{saved[-4:]}" if len(saved) >= 10 else ("***" if saved else "")
    return jsonify({"status": "saved", "configured": bool(saved), "masked_key": masked})


@app.route("/api/ai/analyze", methods=["POST"])
@require_admin_pin
def api_ai_analyze():
    try:
        from agents.ai_analyst_agent import AIAnalystAgent
        data = request.get_json(silent=True) or {}
        symbol = str(data.get("symbol") or "").strip()
        timeframe = str(data.get("timeframe") or "15m").strip()
        image_b64 = str(data.get("image_b64") or "").strip()
        image_mime = str(data.get("image_mime") or "image/png").strip()
        user_prompt = str(data.get("user_prompt") or "").strip()
        if not symbol and not image_b64:
            return jsonify({"status": "error", "message": "Sembol veya grafik görseli gereklidir."}), 400
        res = AIAnalystAgent().analyze_chart_or_coin_with_ai(
            client=client,
            symbol=symbol,
            timeframe=timeframe,
            image_b64=image_b64,
            image_mime=image_mime,
            user_prompt=user_prompt
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/ai/chat", methods=["POST"])
@require_admin_pin
def api_ai_chat():
    try:
        from agents.ai_analyst_agent import AIAnalystAgent
        data = request.get_json(silent=True) or {}
        message = str(data.get("message") or "").strip()
        history = data.get("history") or []
        symbol = str(data.get("symbol") or "").strip()
        timeframe = str(data.get("timeframe") or "15m").strip()
        if not message:
            return jsonify({"status": "error", "message": "Mesaj boş olamaz."}), 400
        res = AIAnalystAgent().chat_with_strategist(
            client=client,
            message=message,
            history=history,
            symbol=symbol,
            timeframe=timeframe
        )
        return jsonify(res), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/ai/review-positions", methods=["POST"])
@require_admin_pin
def api_ai_review_positions():
    try:
        from agents.ai_analyst_agent import AIAnalystAgent
        res = AIAnalystAgent().review_open_positions_suitability(client=client)
        return jsonify(res), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/ai/train-history", methods=["POST"])
@require_admin_pin
def api_ai_train_history():
    try:
        from agents.ai_analyst_agent import AIAnalystAgent
        data = request.get_json(silent=True) or {}
        limit = int(data.get("limit") or 50)
        res = AIAnalystAgent().train_from_trade_history(limit=max(10, min(200, limit)))
        return jsonify(res), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/ai/save-lesson", methods=["POST"])
@require_admin_pin
def api_ai_save_lesson():
    try:
        from core.database import save_trade_reflection_db
        data = request.get_json(silent=True) or {}
        symbol = str(data.get("symbol") or "GENERAL").upper().strip()
        lesson = str(data.get("lesson") or "").strip()
        if not lesson:
            return jsonify({"status": "error", "message": "Ders metni boş olamaz."}), 400
        save_trade_reflection_db(
            signal_id=None,
            symbol=symbol,
            direction="BOTH",
            status="AI_MENTOR_LESSON",
            pnl_pct=0.0,
            lesson=lesson,
            reflection_dict={"source": "Patron-AI Mentor Tartışması", "lesson": lesson}
        )
        return jsonify({"status": "saved"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ========================================================
# FAST BOT ÖZEL API ENDPOINT'LERİ (BAĞIMSIZ KONTROL & 1m SCALPING)
# ========================================================
_fast_orchestrator = None

def get_fast_orchestrator():
    return None

@app.route("/api/fast/data")
def api_fast_data():
    return jsonify({"status": "disabled", "bot_mode": "fast", "active_positions": [], "trade_history": [], "scanner_logs": []})

@app.route("/api/fast/scan", methods=["POST"])
def api_fast_scan():
    return jsonify({"status": "disabled", "message": "FAST stratejisi kaldirildi"})

@app.route("/api/fast/close-all-positions", methods=["POST"])
@require_admin_pin
def api_fast_close_all_positions():
    from core.database import close_all_fast_positions_db, get_fast_performance_stats, get_fast_all_signals
    count = close_all_fast_positions_db(client=client)
    with _cache_lock:
        _terminal_cache["fast_active_positions"] = []
        _terminal_cache["fast_total_unrealized_pnl"] = 0.0
        _terminal_cache["fast_stats"] = get_fast_performance_stats()
        _all_fast = get_fast_all_signals(limit=40) or []
        _terminal_cache["fast_trade_history"] = [s for s in _all_fast if s.get("status") not in ("ACTIVE", "PENDING_ENTRY", "ACTIVE_BE", "ACTIVE_LADDER", "ACTIVE_PARTIAL_TP1")]
    return jsonify({"status": "closed", "count": count})

@app.route("/api/fast/clear-history", methods=["POST"])
@require_admin_pin
def api_fast_clear_history():
    from core.database import clear_fast_closed_trades_db, get_fast_performance_stats
    clear_fast_closed_trades_db()
    with _cache_lock:
        _terminal_cache["fast_trade_history"] = []
        _terminal_cache["fast_stats"] = get_fast_performance_stats()
    return jsonify({"status": "cleared"})

@app.route("/api/fast/reset-all", methods=["POST"])
@require_admin_pin
def api_fast_reset_all():
    from core.database import reset_fast_bot_db, get_fast_performance_stats
    reset_fast_bot_db()
    with _cache_lock:
        _terminal_cache["fast_active_positions"] = []
        _terminal_cache["fast_total_unrealized_pnl"] = 0.0
        _terminal_cache["fast_trade_history"] = []
        _terminal_cache["fast_scanner_logs"] = []
        _terminal_cache["fast_stats"] = get_fast_performance_stats()
    return jsonify({"status": "reset", "bot": "fast", "equity": 1000.0})

# ========================================================
# SÜPER FAST BOT ÖZEL API ENDPOINT'LERİ (SANİYELİK HFT)
# ========================================================
_super_fast_orchestrator = None

def get_super_fast_orchestrator():
    return None

@app.route("/api/superfast/data")
def api_super_fast_data():
    return jsonify({"status": "disabled", "bot_mode": "superfast", "active_positions": [], "trade_history": [], "scanner_logs": []})

@app.route("/api/superfast/scan", methods=["POST"])
def api_super_fast_scan():
    orch = get_super_fast_orchestrator()
    if not orch:
        return jsonify({"status": "disabled", "message": "SÜPER FAST stratejisi devre dışı"})
    threading.Thread(target=orch.run_cycle, daemon=True).start()
    return jsonify({"status": "Super FAST scan started in background"})

@app.route("/api/superfast/close-all-positions", methods=["POST"])
@require_admin_pin
def api_super_fast_close_all_positions():
    from core.database import close_all_super_fast_positions_db, get_super_fast_performance_stats, get_super_fast_all_signals
    count = close_all_super_fast_positions_db(client=client)
    with _cache_lock:
        _terminal_cache["super_fast_active_positions"] = []
        _terminal_cache["super_fast_total_unrealized_pnl"] = 0.0
        _terminal_cache["super_fast_stats"] = get_super_fast_performance_stats()
        _all_super = get_super_fast_all_signals(limit=50) or []
        _terminal_cache["super_fast_trade_history"] = [s for s in _all_super if s.get("status") not in ("ACTIVE", "PENDING_ENTRY", "ACTIVE_BE", "ACTIVE_LADDER", "ACTIVE_PARTIAL_TP1")]
    return jsonify({"status": "closed", "count": count})

@app.route("/api/superfast/clear-history", methods=["POST"])
@require_admin_pin
def api_super_fast_clear_history():
    from core.database import clear_super_fast_closed_trades_db, get_super_fast_performance_stats
    clear_super_fast_closed_trades_db()
    with _cache_lock:
        _terminal_cache["super_fast_trade_history"] = []
        _terminal_cache["super_fast_stats"] = get_super_fast_performance_stats()
    return jsonify({"status": "cleared"})

@app.route("/api/superfast/reset-all", methods=["POST"])
@require_admin_pin
def api_super_fast_reset_all():
    from core.database import reset_super_fast_bot_db, get_super_fast_performance_stats
    reset_super_fast_bot_db()
    with _cache_lock:
        _terminal_cache["super_fast_active_positions"] = []
        _terminal_cache["super_fast_total_unrealized_pnl"] = 0.0
        _terminal_cache["super_fast_trade_history"] = []
        _terminal_cache["super_fast_scanner_logs"] = []
        _terminal_cache["super_fast_stats"] = get_super_fast_performance_stats()
    return jsonify({"status": "reset", "bot": "superfast", "equity": 1000.0})

import socket

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def start_dashboard(orchestrator=None, port=5000, auto_open=True):
    global _orchestrator, _fast_orchestrator, _super_fast_orchestrator, _updater_started
    _orchestrator = orchestrator
    print("ℹ️ [Motor Durumu] Yalnızca 3-Vadeli Ana Strateji Motoru aktif (FAST / SÜPER FAST devre dışı).")

    # Bulut ve Yerel Ortam Dinamik Port ve Host Desteği (Railway, Render, VPS uyumlu)
    port = int(os.environ.get("PORT", port))
    host = os.environ.get("HOST", "0.0.0.0")

    if not _updater_started:
        threading.Thread(target=update_terminal_cache_loop, daemon=True, name="CacheUpdater").start()
        _updater_started = True

    url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"
    # Yerel ortamda port kullanımını denetle (Bulut ortamında kontrolü her zaman atla)
    is_cloud = bool(
        os.environ.get("RAILWAY_ENVIRONMENT_NAME") or
        os.environ.get("RAILWAY_SERVICE_ID") or
        os.environ.get("RAILWAY_PROJECT_ID") or
        os.environ.get("RAILWAY_ENVIRONMENT") or
        os.environ.get("RENDER") or
        os.environ.get("PORT")
    )
    if not is_cloud and is_port_in_use(port):
        print(f"\n🌐 [Canlı Ofis Terminali Zaten Aktif]: {url}")
        if auto_open:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        return None

    def run_app():
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        try:
            app.run(host=host, port=port, debug=False, use_reloader=False)
        except Exception as e:
            print(f"❌ [DashboardServer Hata] Port: {port}, Host: {host} -> {e}")

    server_thread = threading.Thread(target=run_app, daemon=True, name="DashboardServer")
    server_thread.start()
    print(f"\n🌐 [Canlı Ofis Terminali Hazır]: {url}")

    if auto_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    return server_thread

if __name__ == "__main__":
    print("🚀 [Başlatılıyor] Binance Futures AI Ticaret Ofisi...")
    from main import TradingBotOrchestrator
    orch = TradingBotOrchestrator()
    start_dashboard(orchestrator=orch, auto_open=False)

    # 7/24 Kesintisiz Arka Plan Döngüsünü Başlat
    threading.Thread(target=orch.run_forever, kwargs={"skip_dashboard": True}, daemon=True).start()

    print("Kapatmak için Ctrl+C tuşlarına basabilirsiniz.")
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        print("\nTerminal kapatıldı.")
