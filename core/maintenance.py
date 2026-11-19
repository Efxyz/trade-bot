"""
Bakım: depolama raporu, eski tanı kayıtlarının temizliği, CSV dışa aktarma ve gece yedeği.

- Temizlik yalnızca eski SMC motorunun tanı kayıtlarına (tarama, komite, gölge, haber) ve grafik
  resimlerine dokunur. İşlem geçmişi (signals, carry_*) ve özetler asla silinmez.
- Yedek: işlem tablolarının tutarlı bir kopyası (SQLite backup API) + okunabilir CSV'ler, tek zip.
  Gizli anahtarlar (API key, token, PIN…) yedekten çıkarılır. Telegram'a gönderilir, son N kopya diskte tutulur.
"""
from __future__ import annotations

import csv
import io
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import config

# Tablo -> zaman sütunu. Bunlar eski SMC motorunun tanı kayıtlarıdır; saklama süresinden eskiler silinir.
LOG_TABLES: Dict[str, str] = {
    "scanner_logs": "created_at",
    "committee_debates": "created_at",
    "shadow_rejections": "created_at",
    "coin_news_investigations": "created_at",
    "news_items": "created_at",
    "fast_scanner_logs": "created_at",
    "super_fast_scanner_logs": "created_at",
}
# Yedekte satırları boşaltılan (şeması korunan) tablolar: hacimli tanı kayıtları
BACKUP_EMPTY_TABLES = set(LOG_TABLES)
# system_state anahtarında bu parçalardan biri geçiyorsa yedeğe girmez
SECRET_KEY_PARTS = ("key", "token", "secret", "pin", "password", "passwd", "credential")

DB_FMT = "%Y-%m-%d %H:%M:%S"
_LOCK = threading.Lock()          # temizlik / yedek aynı anda tek kez çalışır
_CACHE: Dict[str, tuple] = {}     # kısa süreli rapor/zip önbelleği


# --------------------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------------------
def _db_path() -> Path:
    return Path(config.DB_PATH)


def _data_dir() -> Path:
    return Path(config.DATA_DIR)


def _charts_dir() -> Path:
    return Path(config.CHARTS_DIR)


def backup_dir() -> Path:
    d = _data_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_path() -> Path:
    return _data_dir() / "maintenance_state.json"


def _connect(path: Optional[Path] = None) -> sqlite3.Connection:
    c = sqlite3.connect(str(path or _db_path()), timeout=60.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=60000")
    return c


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dir_size(path: Path) -> tuple:
    total, files = 0, 0
    if not path.exists():
        return 0, 0
    for root, _, names in os.walk(path):
        for n in names:
            try:
                total += os.path.getsize(os.path.join(root, n))
                files += 1
            except OSError:
                pass
    return total, files


def _fsize(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


def _mb(b: float) -> float:
    return round(b / 1_048_576, 2)


def load_state() -> Dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(patch: Dict) -> Dict:
    st = load_state()
    st.update(patch)
    tmp = _state_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _state_path())
    return st


def telegram_configured() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


# --------------------------------------------------------------------------------------
# Depolama raporu
# --------------------------------------------------------------------------------------
def storage_report(use_cache: bool = True) -> Dict:
    if use_cache and "storage" in _CACHE and time.time() - _CACHE["storage"][0] < 60:
        return _CACHE["storage"][1]
    db = _db_path()
    db_b, wal_b, shm_b = _fsize(db), _fsize(Path(str(db) + "-wal")), _fsize(Path(str(db) + "-shm"))
    charts_b, charts_n = _dir_size(_charts_dir())
    backups_b, backups_n = _dir_size(_data_dir() / "backups")
    total_b, _ = _dir_size(_data_dir())
    other_b = max(0, total_b - db_b - wal_b - shm_b - charts_b - backups_b)

    tables: List[Dict] = []
    reclaim_b = 0
    try:
        with _connect() as c:
            names = [r["name"] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            owner = {r["name"]: r["tbl_name"] for r in c.execute("SELECT name, tbl_name FROM sqlite_master")}
            sizes: Dict[str, int] = {}
            try:
                for r in c.execute("SELECT name, SUM(pgsize) AS b FROM dbstat GROUP BY name"):
                    t = owner.get(r["name"], r["name"])
                    sizes[t] = sizes.get(t, 0) + int(r["b"] or 0)
            except sqlite3.OperationalError:
                pass  # dbstat derlenmemişse yalnızca satır sayıları
            for n in names:
                try:
                    cnt = c.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]
                except sqlite3.OperationalError:
                    cnt = None
                tables.append({"table": n, "rows": cnt, "mb": _mb(sizes[n]) if n in sizes else None,
                               "kind": "log" if n in LOG_TABLES else ("v3" if n.startswith("carry_") else "core")})
            page = c.execute("PRAGMA page_size").fetchone()[0]
            free = c.execute("PRAGMA freelist_count").fetchone()[0]
            reclaim_b = int(page) * int(free)
    except sqlite3.Error:
        pass
    tables.sort(key=lambda t: ((t["mb"] or 0), (t["rows"] or 0)), reverse=True)
    limit_b = config.STORAGE_LIMIT_MB * 1_048_576
    rep = {
        "limit_mb": config.STORAGE_LIMIT_MB,
        "used_mb": _mb(total_b),
        "used_pct": round(total_b / limit_b * 100, 1) if limit_b else None,
        "parts": [
            {"name": "Veritabanı", "mb": _mb(db_b)},
            {"name": "Veritabanı günlüğü (WAL)", "mb": _mb(wal_b + shm_b)},
            {"name": "Grafik resimleri", "mb": _mb(charts_b), "files": charts_n},
            {"name": "Yedekler", "mb": _mb(backups_b), "files": backups_n},
            {"name": "Diğer", "mb": _mb(other_b)},
        ],
        "reclaimable_mb": _mb(reclaim_b),
        "tables": tables,
        "retention_days": config.DATA_RETENTION_DAYS,
        "generated": _utc_now().strftime(DB_FMT),
    }
    _CACHE["storage"] = (time.time(), rep)
    return rep


# --------------------------------------------------------------------------------------
# Temizlik
# --------------------------------------------------------------------------------------
def cleanup_old_data(retention_days: Optional[int] = None, vacuum_min_mb: Optional[float] = None,
                     batch: int = 5000) -> Dict:
    """
    Saklama süresinden eski tanı kayıtlarını ve grafik resimlerini siler; boşalan alan yeterliyse VACUUM yapar.
    Silme küçük partilerle yapılır (WAL dosyası şişmesin, volume dolmasın).
    """
    days = int(retention_days if retention_days is not None else config.DATA_RETENTION_DAYS)
    vac_min = float(vacuum_min_mb if vacuum_min_mb is not None else config.VACUUM_MIN_RECLAIM_MB)
    cutoff = (_utc_now() - timedelta(days=days)).strftime(DB_FMT)
    before = storage_report(use_cache=False)["used_mb"]
    deleted: Dict[str, int] = {}
    with _connect() as c:
        for t, col in LOG_TABLES.items():
            n_total = 0
            try:
                while True:
                    cur = c.execute(f'DELETE FROM "{t}" WHERE rowid IN '
                                    f'(SELECT rowid FROM "{t}" WHERE "{col}" < ? LIMIT ?)', (cutoff, batch))
                    c.commit()
                    n_total += max(0, cur.rowcount)
                    if cur.rowcount < batch:
                        break
                    c.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except sqlite3.OperationalError:
                continue  # tablo yoksa
            if n_total:
                deleted[t] = n_total
    # Grafik resimleri
    cutoff_ts = time.time() - days * 86400
    files_removed, files_bytes = 0, 0
    cd = _charts_dir()
    if cd.exists():
        for f in cd.iterdir():
            try:
                if f.is_file() and f.stat().st_mtime < cutoff_ts:
                    files_bytes += f.stat().st_size
                    f.unlink()
                    files_removed += 1
            except OSError:
                pass
    # Alanı geri kazan
    vacuumed, vac_err = False, None
    try:
        with _connect() as c:
            page = c.execute("PRAGMA page_size").fetchone()[0]
            free_b = page * c.execute("PRAGMA freelist_count").fetchone()[0]
            db_b = _fsize(_db_path())
        limit_b = config.STORAGE_LIMIT_MB * 1_048_576
        used_b = _dir_size(_data_dir())[0]
        need_b = (db_b - free_b) * 1.2  # VACUUM yeni içeriği WAL'a yazar: yeni boyut kadar boş yer gerekir
        if free_b >= vac_min * 1_048_576 and (limit_b - used_b) > need_b:
            c2 = sqlite3.connect(str(_db_path()), timeout=120.0, isolation_level=None)
            try:
                c2.execute("PRAGMA busy_timeout=120000")
                c2.execute("VACUUM")
                vacuumed = True
            finally:
                c2.close()
        with _connect() as c:
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error as e:
        vac_err = str(e)
    after = storage_report(use_cache=False)["used_mb"]
    res = {
        "time": _utc_now().strftime(DB_FMT), "retention_days": days, "cutoff": cutoff,
        "deleted_rows": deleted, "deleted_total": sum(deleted.values()),
        "charts_removed": files_removed, "charts_mb": _mb(files_bytes),
        "vacuumed": vacuumed, "error": vac_err,
        "used_mb_before": before, "used_mb_after": after, "freed_mb": round(before - after, 2),
    }
    _save_state({"last_cleanup": res})
    return res


# --------------------------------------------------------------------------------------
# CSV dışa aktarma
# --------------------------------------------------------------------------------------
EXPORTS = [
    ("v3_dolumlar.csv",
     "SELECT ts AS zaman_utc, symbol AS coin, side AS islem, qty AS miktar, price AS fiyat, notional AS tutar_usdt, "
     "fee AS komisyon_usdt, realized_pnl AS gerceklesen_kz_usdt, reason AS sebep FROM carry_fills ORDER BY ts_ms, id"),
    ("v3_dengelemeler.csv",
     "SELECT ts AS zaman_utc, reason AS sebep, n_orders AS emir_sayisi, turnover_usdt AS devir_usdt, fees AS maliyet_usdt, "
     "equity AS ozsermaye_usdt, scale AS risk_olcegi, signal_json AS fonlama_7g_yuzde FROM carry_rebalances ORDER BY ts_ms, id"),
    ("v3_kasa_saatlik.csv",
     "SELECT ts AS zaman_utc, equity AS ozsermaye_usdt, gross_exposure AS brut_pozisyon_usdt, "
     "net_exposure AS net_pozisyon_usdt, n_positions AS pozisyon_sayisi, scale AS risk_olcegi FROM carry_equity ORDER BY ts_ms"),
    ("smc_islemler.csv", "SELECT * FROM signals ORDER BY id"),
    ("smc_gunluk_ozet.csv", "SELECT * FROM daily_pnl_archive ORDER BY date_str"),
]

README_TXT = """Trade Bot kayıt dışa aktarımı
=============================
Oluşturulma: {created} UTC
Biçim: {fmt_desc}

v3_dolumlar.csv        v3 motorunun her alım/satımı (komisyon ve gerçekleşen K/Z dahil)
v3_dengelemeler.csv    Her günlük dengeleme (sebep, emir sayısı, devir, maliyet, özsermaye)
v3_kasa_saatlik.csv    Saat başı özsermaye ve pozisyon büyüklüğü
v3_acik_pozisyonlar.csv  Dışa aktarma anındaki açık pozisyonlar
smc_islemler.csv       Eski SMC motorunun bütün işlemleri (ham tablo)
smc_gunluk_ozet.csv    Eski SMC motorunun günlük özetleri

Tüm zamanlar UTC'dir (Türkiye saati = UTC+3). İşlemler sanaldır (paper trading).
"""


def _fmt_cell(v, tr: bool):
    if v is None:
        return ""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, float):
        s = f"{v:.8f}".rstrip("0").rstrip(".") if abs(v) < 1e15 else repr(v)
        if s in ("-0", ""):
            s = "0"
        return s.replace(".", ",") if tr else s
    if isinstance(v, int):
        return v
    s = str(v)
    # CSV formül enjeksiyonu koruması (Excel = + - @ ile başlayan metni formül sanar)
    if s[:1] in ("=", "+", "-", "@", "\t", "\r"):
        try:
            float(s)
        except ValueError:
            s = "'" + s
    return s


def _csv_bytes(header: List[str], rows, tr: bool) -> bytes:
    buf = io.StringIO()
    if tr:
        buf.write("﻿")  # Excel'in UTF-8 Türkçe karakterleri doğru okuması için BOM
    w = csv.writer(buf, delimiter=";" if tr else ",", lineterminator="\r\n" if tr else "\n")
    w.writerow(header)
    for r in rows:
        w.writerow([_fmt_cell(v, tr) for v in r])
    return buf.getvalue().encode("utf-8")


def _query_csv(c: sqlite3.Connection, sql: str, tr: bool) -> Optional[bytes]:
    try:
        cur = c.execute(sql)
    except sqlite3.OperationalError:
        return None  # tablo yoksa atla
    header = [d[0] for d in cur.description]
    return _csv_bytes(header, cur.fetchall(), tr)


def build_export_zip(fmt: str = "tr", positions: Optional[List[Dict]] = None, db_path: Optional[Path] = None) -> bytes:
    """Kayıtların CSV zip'i. fmt='tr': Türkçe Excel (; ayraç, virgüllü ondalık, BOM); 'std': standart CSV."""
    tr = fmt != "std"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z, _connect(db_path) as c:
        for name, sql in EXPORTS:
            data = _query_csv(c, sql, tr)
            if data is not None:
                z.writestr(name, data)
        if positions is not None:
            cols = ["symbol", "side", "qty", "avg_price", "price", "notional", "upnl", "opened"]
            hdr = ["coin", "yon", "miktar", "ort_giris", "fiyat", "tutar_usdt", "acik_kz_usdt", "acilis_utc"]
            z.writestr("v3_acik_pozisyonlar.csv", _csv_bytes(hdr, [[p.get(k) for k in cols] for p in positions], tr))
        z.writestr("OKUBENI.txt", README_TXT.format(
            created=_utc_now().strftime(DB_FMT),
            fmt_desc="Türkçe Excel (noktalı virgül ayraç, virgüllü ondalık)" if tr else "Standart CSV (virgül ayraç, noktalı ondalık)"))
    return out.getvalue()


# --------------------------------------------------------------------------------------
# Yedek
# --------------------------------------------------------------------------------------
def _sanitize_copy(path: Path) -> Dict:
    removed_keys = 0
    c = sqlite3.connect(str(path), isolation_level=None)
    try:
        c.execute("PRAGMA journal_mode=DELETE")
        for t in BACKUP_EMPTY_TABLES:
            try:
                c.execute(f'DELETE FROM "{t}"')
            except sqlite3.OperationalError:
                pass
        try:
            keys = [r[0] for r in c.execute("SELECT key FROM system_state")]
            for k in keys:
                if any(part in str(k).lower() for part in SECRET_KEY_PARTS):
                    c.execute("DELETE FROM system_state WHERE key = ?", (k,))
                    removed_keys += 1
        except sqlite3.OperationalError:
            pass
        c.execute("VACUUM")
    finally:
        c.close()
    return {"secret_keys_removed": removed_keys}


def create_backup(keep: Optional[int] = None, positions: Optional[List[Dict]] = None) -> Dict:
    """Tutarlı DB kopyası (hacimli tanı kayıtları ve gizli anahtarlar hariç) + CSV'ler -> zip. Son `keep` kopya saklanır."""
    keep = int(keep if keep is not None else config.BACKUP_KEEP)
    stamp = _utc_now().strftime("%Y%m%d_%H%M%S")
    tmpdir = Path(tempfile.mkdtemp(prefix="tradebot_backup_"))
    try:
        copy = tmpdir / "trading_bot_yedek.db"
        src = _connect()
        dst = sqlite3.connect(str(copy))
        try:
            src.backup(dst)  # canlı DB'nin tutarlı anlık görüntüsü
        finally:
            dst.close()
            src.close()
        info = _sanitize_copy(copy)
        out = backup_dir() / f"tradebot_yedek_{stamp}.zip"
        part = out.with_suffix(".part")
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copy, "trading_bot_yedek.db")
            with zipfile.ZipFile(io.BytesIO(build_export_zip("tr", positions, db_path=copy))) as ez:
                for n in ez.namelist():
                    z.writestr("csv/" + n, ez.read(n))
        os.replace(part, out)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    olds = sorted(backup_dir().glob("tradebot_yedek_*.zip"))
    for f in olds[:-keep] if keep > 0 else []:
        try:
            f.unlink()
        except OSError:
            pass
    return {"path": str(out), "file": out.name, "mb": _mb(out.stat().st_size),
            "time": _utc_now().strftime(DB_FMT), **info}


def latest_backup() -> Optional[Path]:
    files = sorted(backup_dir().glob("tradebot_yedek_*.zip"))
    return files[-1] if files else None


# --------------------------------------------------------------------------------------
# Gece bakımı ve zamanlayıcı
# --------------------------------------------------------------------------------------
def _engine_summary() -> Dict:
    try:
        from agents.carry_agent import get_live_engine
        eng = get_live_engine()
        s = eng.snapshot()
        return {"equity": s["equity"], "pnl": s["pnl"], "pnl_pct": s["pnl_pct"], "n_fills": s["n_fills"],
                "positions": s["positions"]}
    except Exception:
        return {}


def run_backup(notifier=None, send_telegram: Optional[bool] = None) -> Dict:
    eng = _engine_summary()
    b = create_backup(positions=eng.get("positions"))
    tg = "kapalı"
    send = config.BACKUP_TELEGRAM if send_telegram is None else send_telegram
    if send:
        if notifier is None or not getattr(notifier, "has_telegram", False):
            tg = "telegram_ayarli_degil"
        elif b["mb"] > 45:
            notifier.send_text_message(f"🗄️ Günlük yedek oluşturuldu ama Telegram sınırı için çok büyük ({b['mb']} MB). "
                                       f"Panelden indirilebilir.")
            tg = "cok_buyuk"
        else:
            rep = storage_report(use_cache=False)
            cap = (f"🗄️ Günlük yedek · {b['time'][:16]} UTC\n"
                   + (f"Özsermaye ${eng['equity']:,.2f} ({eng['pnl_pct']:+.2f}%) · {eng['n_fills']} dolum\n" if eng else "")
                   + f"Disk {rep['used_mb']:.0f}/{rep['limit_mb']:.0f} MB · yedek {b['mb']} MB")
            tg = "gonderildi" if notifier.send_document(b["path"], cap) else "hata"
    b["telegram"] = tg
    _save_state({"last_backup": {k: v for k, v in b.items() if k != "path"}})
    return b


def run_nightly(notifier=None) -> Dict:
    """Temizlik -> yedek -> Telegram. Aynı anda tek çalışma."""
    if not _LOCK.acquire(blocking=False):
        return {"skipped": "zaten_calisiyor"}
    try:
        out: Dict = {}
        try:
            out["cleanup"] = cleanup_old_data()
        except Exception as e:
            out["cleanup_error"] = str(e)
        try:
            out["backup"] = run_backup(notifier)
        except Exception as e:
            out["backup_error"] = str(e)
        _save_state({"last_run_date": _utc_now().strftime("%Y-%m-%d"), "last_run": _utc_now().strftime(DB_FMT),
                     "last_errors": {k: v for k, v in out.items() if k.endswith("_error")}})
        return out
    finally:
        _LOCK.release()


def run_in_background(kind: str, notifier=None) -> bool:
    """Panel düğmeleri: 'cleanup' | 'backup' | 'nightly'. Başka bir bakım çalışıyorsa False döner."""
    if _LOCK.locked():
        return False

    def _job():
        if not _LOCK.acquire(blocking=False):
            return
        try:
            if kind == "cleanup":
                cleanup_old_data()
            elif kind == "backup":
                run_backup(notifier)
        except Exception as e:
            _save_state({"last_errors": {f"{kind}_error": str(e)}})
            print(f"⚠️ [Bakım] {kind} hatası: {e}")
        finally:
            _LOCK.release()

    if kind == "nightly":
        threading.Thread(target=run_nightly, args=(notifier,), daemon=True, name="MaintenanceManual").start()
    else:
        threading.Thread(target=_job, daemon=True, name=f"Maintenance-{kind}").start()
    return True


def is_running() -> bool:
    return _LOCK.locked()


def is_due(now_utc: datetime, last_run_date: Optional[str], hour: int, minute: int) -> bool:
    if now_utc.hour * 60 + now_utc.minute < hour * 60 + minute:
        return False
    return last_run_date != now_utc.strftime("%Y-%m-%d")


def next_run(now_utc: Optional[datetime] = None) -> str:
    """Takvimdeki bir sonraki bakım anı (bugünkü kaçırıldıysa `due_now` ayrıca bildirilir)."""
    now = now_utc or _utc_now()
    t = now.replace(hour=config.MAINTENANCE_HOUR_UTC, minute=config.MAINTENANCE_MINUTE_UTC, second=0, microsecond=0)
    if t <= now:
        t += timedelta(days=1)
    return t.strftime(DB_FMT)


def due_now(now_utc: Optional[datetime] = None) -> bool:
    return is_due(now_utc or _utc_now(), load_state().get("last_run_date"),
                  config.MAINTENANCE_HOUR_UTC, config.MAINTENANCE_MINUTE_UTC)


_SCHED_THREAD: Optional[threading.Thread] = None


def start_scheduler(notifier=None, check_seconds: int = 300, startup_delay: int = 120) -> Optional[threading.Thread]:
    global _SCHED_THREAD
    if not config.ENABLE_AUTO_MAINTENANCE:
        print("⏸️ [Bakım] ENABLE_AUTO_MAINTENANCE=false, otomatik temizlik/yedek kapalı.")
        return None
    if _SCHED_THREAD and _SCHED_THREAD.is_alive():
        return _SCHED_THREAD

    def _loop():
        time.sleep(startup_delay)
        while True:
            try:
                if is_due(_utc_now(), load_state().get("last_run_date"),
                          config.MAINTENANCE_HOUR_UTC, config.MAINTENANCE_MINUTE_UTC):
                    print("🧹 [Bakım] Gece bakımı başladı (temizlik + yedek)...")
                    r = run_nightly(notifier)
                    c = r.get("cleanup", {})
                    b = r.get("backup", {})
                    print(f"🧹 [Bakım] Bitti: {c.get('deleted_total', 0)} kayıt, {c.get('charts_removed', 0)} grafik silindi, "
                          f"{c.get('freed_mb', 0)} MB boşaldı · yedek {b.get('file')} ({b.get('mb')} MB, Telegram: {b.get('telegram')})")
            except Exception as e:
                print(f"⚠️ [Bakım] Zamanlayıcı hatası: {e}")
            time.sleep(check_seconds)

    _SCHED_THREAD = threading.Thread(target=_loop, daemon=True, name="MaintenanceScheduler")
    _SCHED_THREAD.start()
    print(f"🧹 [Bakım] Gece bakımı her gün {config.MAINTENANCE_HOUR_UTC:02d}:{config.MAINTENANCE_MINUTE_UTC:02d} UTC "
          f"({config.DATA_RETENTION_DAYS} gün saklama, son {config.BACKUP_KEEP} yedek).")
    return _SCHED_THREAD
