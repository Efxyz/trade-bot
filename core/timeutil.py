"""
Tek zaman kaynağı: Veritabanına yazılan ve karşılaştırılan TÜM zaman damgaları naive UTC'dir
("%Y-%m-%d %H:%M:%S"). SQLite CURRENT_TIMESTAMP de UTC yazar; böylece created_at / entered_at /
closed_at sütunları sunucunun saat diliminden (Windows TSİ, Railway UTC) bağımsız olarak tutarlı kalır.
Türkiye saati (TSİ) yalnızca gün sınırları ve görüntüleme için kullanılır.
"""
from datetime import datetime, timedelta, timezone

TR_TZ = timezone(timedelta(hours=3))
DB_FMT = "%Y-%m-%d %H:%M:%S"


def utc_now() -> datetime:
    """Naive UTC 'şimdi' (DB sütunlarıyla doğrudan karşılaştırılabilir)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_now_str() -> str:
    return utc_now().strftime(DB_FMT)


def parse_db_ts(value) -> datetime:
    """DB zaman damgasını (naive UTC) datetime'a çevirir."""
    return datetime.strptime(str(value).replace("T", " ")[:19], DB_FMT)


def minutes_since(value) -> float:
    return (utc_now() - parse_db_ts(value)).total_seconds() / 60.0


def tr_day_start_utc_str(days_ago: int = 0) -> str:
    """Bugünün (veya days_ago gün öncesinin) TSİ 00:00 anını naive UTC metni olarak döner."""
    now_tr = datetime.now(timezone.utc).astimezone(TR_TZ)
    start_tr = (now_tr - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start_tr.astimezone(timezone.utc).strftime(DB_FMT)


def db_ts_to_epoch_ms(value) -> int:
    return int(parse_db_ts(value).replace(tzinfo=timezone.utc).timestamp() * 1000)
