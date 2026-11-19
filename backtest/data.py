"""
Geçmiş mum verisi indirme ve disk önbelleği (Binance USDT-M Futures halka açık REST API).
İndirilen veriler data/backtest_cache/ altında JSON olarak saklanır; tekrar çalıştırmada ağ kullanılmaz.
"""
import json
import time
from pathlib import Path
from typing import Dict, List

import requests

from config import BINANCE_FUTURES_BASE_URL, BASE_DIR

CACHE_DIR = BASE_DIR / "data" / "backtest_cache"
INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000, "4h": 14_400_000}


def _to_candle(item) -> Dict:
    return {
        "timestamp": int(item[0]),
        "open": float(item[1]),
        "high": float(item[2]),
        "low": float(item[3]),
        "close": float(item[4]),
        "volume": float(item[5]),
        "quote_volume": float(item[7]),
        "taker_buy_volume": float(item[9]) if len(item) > 9 else 0.0,
    }


def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int, session=None, pause: float = 0.12) -> List[Dict]:
    """[start_ms, end_ms) aralığındaki kapanmış mumları sayfalı olarak indirir."""
    sess = session or requests.Session()
    out: List[Dict] = []
    step = INTERVAL_MS[interval]
    cursor = start_ms
    while cursor < end_ms:
        params = {"symbol": symbol, "interval": interval, "startTime": cursor, "endTime": end_ms - 1, "limit": 1500}
        for attempt in range(5):
            resp = sess.get(f"{BINANCE_FUTURES_BASE_URL}/fapi/v1/klines", params=params, timeout=20)
            if resp.status_code in (418, 429):
                time.sleep(int(resp.headers.get("Retry-After", 30)))
                continue
            resp.raise_for_status()
            break
        rows = resp.json()
        if not rows:
            break
        out.extend(_to_candle(r) for r in rows)
        cursor = int(rows[-1][0]) + step
        time.sleep(pause)
    # Yalnızca tamamen kapanmış mumlar
    return [c for c in out if c["timestamp"] + step <= end_ms]


def load_klines(symbol: str, interval: str, start_ms: int, end_ms: int, refresh: bool = False) -> List[Dict]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{symbol}_{interval}_{start_ms}_{end_ms}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch_klines(symbol, interval, start_ms, end_ms)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def aligned_window(days: int, warmup_days: int, now_ms: int = None) -> (int, int):
    """Son 'days' günü + ısınma süresini kapsayan, 1 saatlik sınıra hizalı [start, end) penceresi."""
    now_ms = now_ms or int(time.time() * 1000)
    end_ms = (now_ms // 3_600_000) * 3_600_000
    start_ms = end_ms - (days + warmup_days) * 86_400_000
    return start_ms, end_ms
