"""
Binance Futures Zero-Latency WebSocket Streamer
Streams real-time sub-second trade ticks and volume flow directly from Binance Futures:
wss://fstream.binance.com/stream?streams=...
Provides real-time sub-second prices for active positions and tracks volume spikes.
"""
import json
import time
import ssl
import threading
from typing import Dict, List, Set, Optional
from collections import deque, defaultdict
import websocket

# Thread-safe in-memory tick cache
_LIVE_PRICES: Dict[str, float] = {}
_PRICE_LOCK = threading.Lock()

# Volume and whale trade tracker
# symbol -> deque of (timestamp, trade_usdt_value)
_RECENT_TRADES: Dict[str, deque] = defaultdict(lambda: deque(maxlen=40))
_HOT_SYMBOLS_SET: Set[str] = set()
_HOT_SYMBOLS_QUEUE: deque = deque(maxlen=20)
_QUEUE_LOCK = threading.Lock()

_STREAMER_ACTIVE = False
_LAST_EVENT_TIME = 0.0
_STREAMER_THREAD: Optional[threading.Thread] = None
_CURRENT_WS = None

# Default high-liquidity stream targets (can be dynamically extended with active positions)
DEFAULT_STREAM_PAIRS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT",
    "SUIUSDT", "FETUSDT", "NEARUSDT", "AVAXUSDT", "APTUSDT",
    "LINKUSDT", "ADAUSDT", "BNBUSDT", "ARBUSDT", "OPUSDT",
    "1000PEPEUSDT", "WIFUSDT", "RENDERUSDT", "TAOUSDT", "TIAUSDT"
]
_SUBSCRIBED_PAIRS: Set[str] = set(DEFAULT_STREAM_PAIRS)

def _build_ws_url() -> str:
    streams = [f"{s.lower()}@trade" for s in _SUBSCRIBED_PAIRS]
    return f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"

def add_stream_symbol(symbol: str):
    """Yeni açılan pozisyonu canlı WebSocket akışına anında ekler (Dinamik SUBSCRIBE)."""
    global _CURRENT_WS
    if symbol and symbol not in _SUBSCRIBED_PAIRS:
        _SUBSCRIBED_PAIRS.add(symbol)
        if _CURRENT_WS and _STREAMER_ACTIVE:
            try:
                sub_msg = json.dumps({
                    "method": "SUBSCRIBE",
                    "params": [f"{symbol.lower()}@trade"],
                    "id": int(time.time() * 1000)
                })
                _CURRENT_WS.send(sub_msg)
            except Exception:
                pass

def _run_streamer():
    global _STREAMER_ACTIVE, _LAST_EVENT_TIME, _CURRENT_WS

    while True:
        ws = None
        try:
            url = _build_ws_url()
            ws = websocket.create_connection(
                url,
                sslopt={"cert_reqs": ssl.CERT_NONE},
                timeout=12
            )
            _CURRENT_WS = ws
            _STREAMER_ACTIVE = True

            while True:
                msg = ws.recv()
                if not msg:
                    break

                now = time.time()
                _LAST_EVENT_TIME = now

                payload = json.loads(msg)
                trade_data = payload.get("data", {})
                sym = trade_data.get("s")
                p_str = trade_data.get("p")
                q_str = trade_data.get("q")

                if sym and p_str:
                    price = float(p_str)
                    qty = float(q_str) if q_str else 0.0
                    trade_val = price * qty

                    with _PRICE_LOCK:
                        _LIVE_PRICES[sym] = price

                    # 1 Dakikalık ani balina işlem hacmini takip et (>50.000$ tek işlem veya hızlı akış)
                    trades = _RECENT_TRADES[sym]
                    trades.append((now, trade_val))

                    # Son 30 saniyedeki toplam işlem büyüklüğü
                    recent_sum = sum(v for t, v in trades if now - t <= 30.0)
                    if recent_sum >= 80_000.0 or trade_val >= 40_000.0:
                        with _QUEUE_LOCK:
                            if sym not in _HOT_SYMBOLS_SET:
                                _HOT_SYMBOLS_SET.add(sym)
                                _HOT_SYMBOLS_QUEUE.append({
                                    "symbol": sym,
                                    "recent_volume_usdt": round(recent_sum, 0),
                                    "last_trade_val": round(trade_val, 0),
                                    "detected_at": now
                                })

        except Exception:
            _STREAMER_ACTIVE = False
            time.sleep(2)
        finally:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass
        time.sleep(1)

def start_streamer():
    """Arka planda kesintisiz Binance Futures WebSocket dinleyicisini başlatır."""
    global _STREAMER_THREAD
    if _STREAMER_THREAD and _STREAMER_THREAD.is_alive():
        return
    _STREAMER_THREAD = threading.Thread(target=_run_streamer, daemon=True, name="BinanceWsStreamer")
    _STREAMER_THREAD.start()

def get_live_price(symbol: str) -> Optional[float]:
    """Milisaniyelik canlı fiyatı döner."""
    with _PRICE_LOCK:
        return _LIVE_PRICES.get(symbol)

def get_all_live_prices() -> Dict[str, float]:
    """Tüm canlı fiyat sözlüğünün kopyasını döner."""
    with _PRICE_LOCK:
        return dict(_LIVE_PRICES)

def pop_hot_symbols() -> List[Dict]:
    """Ani balina hacmi patlaması yaşayan sıcak pariteleri kuyruktan çeker."""
    with _QUEUE_LOCK:
        hot = list(_HOT_SYMBOLS_QUEUE)
        _HOT_SYMBOLS_QUEUE.clear()
        _HOT_SYMBOLS_SET.clear()
        return hot

def is_streamer_connected() -> bool:
    """WebSocket hattının canlı ve veri akışı sağladığını doğrular."""
    return _STREAMER_ACTIVE and (time.time() - _LAST_EVENT_TIME < 6.0)
