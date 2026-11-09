"""
Market Scanner Agent & Office Log Buffer
Stores real-time decision logs of all evaluated coins: why approved, why rejected.
Rotates through the entire Binance Futures universe and enforces cooldowns.
"""
from typing import List, Dict, Set
from collections import deque
from datetime import datetime
import time
from core.binance_client import BinanceFuturesClient
from config import MIN_24H_VOLUME_USDT

# Shared live activity logs for the Trading Office Terminal
SCANNER_ACTIVITY_LOGS = deque(maxlen=50)

# Cooldown tracking: symbol -> timestamp of last evaluation (Çift Kademeli Dinamik Soğuma)
_SCANNED_COOLDOWN: Dict[str, float] = {}
COOLDOWN_HOT_SECONDS = 90  # Sıcak volatilite liderleri için 90 sn (Sürekli radar altında)
COOLDOWN_ROTATION_SECONDS = 180  # Genel piyasa rotasyonu için 3 dk (Eski 15 dk hantallığına son)
_ROTATION_INDEX = 0

# Son 1 saat içindeki kontrol sıklığı takibi
_HOURLY_CHECK_TIMESTAMPS: Dict[str, List[float]] = {}

def record_check_and_get_hourly_count(symbol: str) -> int:
    """Belirtilen coinin son 1 saat içindeki kontrol edilme sayısını günceller ve döner."""
    now = time.time()
    past_checks = _HOURLY_CHECK_TIMESTAMPS.get(symbol, [])
    valid_checks = [t for t in past_checks if (now - t) <= 3600]
    valid_checks.append(now)
    _HOURLY_CHECK_TIMESTAMPS[symbol] = valid_checks
    return len(valid_checks)

def add_scanner_log(symbol: str, status: str, reason: str, details: str = ""):
    time_str = datetime.now().strftime("%H:%M:%S")
    hourly_count = record_check_and_get_hourly_count(symbol)
    hourly_badge = f"[Son 1 Saatte {hourly_count}. kontrol]"
    full_reason = f"{reason} | {hourly_badge}" if hourly_badge not in reason else reason
    entry = {
        "time": time_str,
        "symbol": symbol,
        "status": status,     # "APPROVED" (Fırsat) veya "REJECTED" (Elendi)
        "reason": full_reason, # Neden elendi/onaylandı ve saatte kaçıncı kontrol olduğu
        "details": details
    }
    SCANNER_ACTIVITY_LOGS.appendleft(entry)
    try:
        from core.database import add_scanner_log_db
        add_scanner_log_db(symbol, status, full_reason, details)
    except Exception:
        pass

def get_scanner_logs() -> List[Dict]:
    try:
        from core.database import get_scanner_logs_db
        db_logs = get_scanner_logs_db(limit=50)
        if db_logs:
            return db_logs
    except Exception:
        pass
    return list(SCANNER_ACTIVITY_LOGS)

# Sentetik Hisse Senetleri, Kaldıraçlı Borsa ETF'leri ve Emtialar Kara Listesi (%100 Saf Kripto Kalkanı)
SYNTHETIC_STOCK_BLACKLIST = {
    # 1. ABD Hisse Senetleri & Pre-Market Çiftleri
    "AAPLUSDT", "AMZNUSDT", "GOOGLUSDT", "MSFTUSDT", "METAUSDT", "NFLXUSDT",
    "NVDAUSDT", "TSLAUSDT", "AMDUSDT", "INTCUSDT", "QCOMUSDT", "AVGOUSDT",
    "ARMUSDT", "SMCIUSDT", "PLTRUSDT", "COINUSDT", "MSTRUSDT", "DELLUSDT",
    "IRENUSDT", "CRCLUSDT", "SKUUUSDT", "MUUUSDT", "MUUSDT", "SNDKUSDT",
    "SKHYNIXUSDT", "TSMUSDT", "AAOIUSDT", "CXMTUSDT", "BABAUSDT", "PDDUSDT",
    
    # 2. Kaldıraçlı Borsa & Endeks ETF'leri
    "SOXLUSDT", "SOXSUSDT", "SQQQUSDT", "TQQQUSDT", "SPYUSDT", "QQQUSDT",
    "KORUUSDT", "SPCXUSDT",
    
    # 3. Geleneksel Emtia & Ham Madde Çiftleri (Gap/Hafta Sonu Fitil Riski)
    "XAUUSDT", "XAGUSDT", "BZUSDT", "CLUSDT", "COPPERUSDT"
}

class MarketScannerAgent:
    def __init__(self, client: BinanceFuturesClient, min_volume: float = MIN_24H_VOLUME_USDT):
        self.client = client
        self.min_volume = min_volume

    def scan_opportunities(self, limit: int = 25, exclude_symbols: Set[str] = None) -> List[Dict]:
        """
        Binance Futures'taki likit USDT.P kripto çiftleri arasında yüksek frekanslı turbo rotasyon yapar.
        - Sentetik tokenize hisseleri ve illikit pariteleri filtreler.
        - Çift Kademeli Dinamik Soğuma (Dual-Tier Cooldown):
          * Sıcak Volatilite Liderleri (Top 10): 90 saniye soğuma (sürekli radar altında)
          * Genel Piyasa Rotasyonu: 180 saniye soğuma (tüm 250+ coin 5 dakikada taranır)
        - Her döngüde 25 parite (10 Volatilite Lideri + 15 Rotasyon) taranır.
        """
        global _ROTATION_INDEX, _SCANNED_COOLDOWN
        now = time.time()
        exclude_symbols = exclude_symbols or set()

        all_tickers = self.client.get_24hr_tickers()
        
        liquid_tickers = [
            t for t in all_tickers.values()
            if t["quoteVolume"] >= self.min_volume 
            and t["symbol"] not in exclude_symbols
            and t["symbol"] not in SYNTHETIC_STOCK_BLACKLIST
            and not any(t["symbol"].startswith(s) for s in ["DELL", "MSTR", "IREN", "NVDA", "TSLA", "SQQQ", "SOXL", "SOXS", "AAPL", "AMZN", "MSFT", "GOOGL", "SKHYNIX", "SNDK"])
        ]

        if not liquid_tickers:
            return []

        # 1. Havuz: Taze Volatilite / Hacim Liderleri (Son 90 sn taranmamışlar)
        fresh_movers = [
            t for t in liquid_tickers
            if (now - _SCANNED_COOLDOWN.get(t["symbol"], 0)) >= COOLDOWN_HOT_SECONDS
        ]
        sorted_movers = sorted(
            fresh_movers,
            key=lambda x: abs(x["priceChangePercent"]),
            reverse=True
        )
        pool_movers = sorted_movers[:10]
        selected_symbols = {t["symbol"] for t in pool_movers}

        # 2. Havuz: Tüm Piyasa Sıralı Rotasyonu (Kalan 200+ coini baştan sona hızla tarar)
        remaining_tickers = [
            t for t in liquid_tickers
            if t["symbol"] not in selected_symbols and (now - _SCANNED_COOLDOWN.get(t["symbol"], 0)) >= COOLDOWN_ROTATION_SECONDS
        ]
        # Eğer soğuma süresi yüzünden coin kalmadıysa süresi en eski olanları al
        if len(remaining_tickers) < 15:
            remaining_tickers = [t for t in liquid_tickers if t["symbol"] not in selected_symbols]

        # Piyasa rotasyon penceresi (her döngü 15 parite ileri kayar)
        n_rem = len(remaining_tickers)
        pool_rotation = []
        if n_rem > 0:
            start_idx = _ROTATION_INDEX % n_rem
            _ROTATION_INDEX = (start_idx + 15) % n_rem
            # Dairesel seçim
            for i in range(min(15, n_rem)):
                idx = (start_idx + i) % n_rem
                pool_rotation.append(remaining_tickers[idx])

        candidates = (pool_movers + pool_rotation)[:limit]

        # Seçilen coinleri soğuma zaman damgasıyla işaretle
        for c in candidates:
            _SCANNED_COOLDOWN[c["symbol"]] = now

        return candidates
