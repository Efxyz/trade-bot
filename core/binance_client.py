"""
Binance Futures (USDT-M Perpetual / USDT.P) Client
Provides fast, direct REST access to Binance Futures.
Uses native Python structures for maximum speed and zero native DLL issues.
"""
import time
import threading
import requests
from typing import List, Dict, Optional
from config import BINANCE_FUTURES_BASE_URL

class BinanceFuturesClient:
    # Tüm bot örneklerinin (Dashboard, Standart, FAST, SÜPER FAST) ortak kullandığı merkezi hafıza
    _cache: Dict[str, any] = {}
    _cache_lock = threading.Lock()
    _rate_limited_until: float = 0.0

    def __init__(self, base_url: str = BINANCE_FUTURES_BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "TradeBot/1.0 (BinanceFuturesAnalyzer)"
        })

    @classmethod
    def is_rate_limited(cls) -> bool:
        return time.time() < cls._rate_limited_until

    def _is_rate_limited(self) -> bool:
        return time.time() < BinanceFuturesClient._rate_limited_until

    def _handle_response(self, resp: requests.Response) -> bool:
        """Rate limit denetimi (429/418 yakalama ve ağırlık kontrolü)."""
        if resp.status_code in (429, 418):
            retry_after = 30
            try:
                retry_after = int(resp.headers.get("Retry-After", 30))
            except Exception:
                pass
            BinanceFuturesClient._rate_limited_until = time.time() + max(retry_after, 20)
            print(f"⚠️ [Binance Rate Limit {resp.status_code}] {max(retry_after, 20)} saniye merkezi koruma/soğuma moduna geçildi.")
            return False

        # Binance 1m ağırlık takibi (Max 1200) - 750 ve 900 eşiklerinde proaktif frenleme
        used_weight = resp.headers.get("x-mbx-used-weight-1m")
        if used_weight:
            try:
                w = int(used_weight)
                if w >= 900:
                    time.sleep(0.50)
                elif w >= 750:
                    time.sleep(0.20)
            except Exception:
                pass
        return True

    def get_exchange_info(self) -> List[Dict]:
        """Binance Futures'taki tüm USDT-M Perpetual (USDT.P) çiftlerini getirir (15 dk Cache)."""
        cache_key = "exchange_info"
        now = time.time()
        with BinanceFuturesClient._cache_lock:
            if cache_key in BinanceFuturesClient._cache:
                data, exp = BinanceFuturesClient._cache[cache_key]
                if now < exp:
                    return data

        if self._is_rate_limited():
            with BinanceFuturesClient._cache_lock:
                return BinanceFuturesClient._cache.get(cache_key, ([], 0))[0]

        url = f"{self.base_url}/fapi/v1/exchangeInfo"
        try:
            resp = self.session.get(url, timeout=10)
            if not self._handle_response(resp):
                with BinanceFuturesClient._cache_lock:
                    return BinanceFuturesClient._cache.get(cache_key, ([], 0))[0]
            resp.raise_for_status()
            data = resp.json()
            
            perpetuals = [
                s for s in data.get("symbols", [])
                if s.get("contractType") == "PERPETUAL" 
                and s.get("quoteAsset") == "USDT"
                and s.get("status") == "TRADING"
            ]
            with BinanceFuturesClient._cache_lock:
                BinanceFuturesClient._cache[cache_key] = (perpetuals, now + 900.0)
            return perpetuals
        except Exception as e:
            print(f"⚠️ [Binance get_exchange_info Hata]: {e}")
            with BinanceFuturesClient._cache_lock:
                return BinanceFuturesClient._cache.get(cache_key, ([], 0))[0]

    def get_24hr_tickers(self) -> Dict[str, Dict]:
        """Tüm vadeli çiftlerin 24 saatlik hacim, fiyat değişimi ve tepe/dip verilerini getirir (8s Cache)."""
        cache_key = "24hr_tickers"
        now = time.time()
        with BinanceFuturesClient._cache_lock:
            if cache_key in BinanceFuturesClient._cache:
                data, exp = BinanceFuturesClient._cache[cache_key]
                if now < exp:
                    return data

        if self._is_rate_limited():
            with BinanceFuturesClient._cache_lock:
                return BinanceFuturesClient._cache.get(cache_key, ({}, 0))[0]

        url = f"{self.base_url}/fapi/v1/ticker/24hr"
        try:
            resp = self.session.get(url, timeout=12)
            if not self._handle_response(resp):
                with BinanceFuturesClient._cache_lock:
                    return BinanceFuturesClient._cache.get(cache_key, ({}, 0))[0]
            resp.raise_for_status()
            tickers = resp.json()
            
            results = {}
            for t in tickers:
                symbol = t.get("symbol", "")
                if symbol.endswith("USDT"):
                    results[symbol] = {
                        "symbol": symbol,
                        "lastPrice": float(t.get("lastPrice", 0.0)),
                        "priceChangePercent": float(t.get("priceChangePercent", 0.0)),
                        "quoteVolume": float(t.get("quoteVolume", 0.0)),
                        "highPrice": float(t.get("highPrice", 0.0)),
                        "lowPrice": float(t.get("lowPrice", 0.0)),
                        "count": int(t.get("count", 0))
                    }
            with BinanceFuturesClient._cache_lock:
                BinanceFuturesClient._cache[cache_key] = (results, now + 20.0)
            return results
        except Exception as e:
            print(f"⚠️ [Binance get_24hr_tickers Hata]: {e}")
            with BinanceFuturesClient._cache_lock:
                return BinanceFuturesClient._cache.get(cache_key, ({}, 0))[0]

    def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> List[Dict]:
        """
        Belirtilen sembol için mum (OHLCV) verilerini çeker (Akıllı TTL Önbellekli).
        Dönen liste: [{'timestamp': ms, 'open': float, 'high': float, 'low': float, 'close': float, 'volume': float}, ...]
        """
        cache_key = f"klines_{symbol}_{interval}_{limit}"
        now = time.time()
        with BinanceFuturesClient._cache_lock:
            if cache_key in BinanceFuturesClient._cache:
                data, exp = BinanceFuturesClient._cache[cache_key]
                if now < exp:
                    return data

        if self._is_rate_limited():
            with BinanceFuturesClient._cache_lock:
                return BinanceFuturesClient._cache.get(cache_key, ([], 0))[0]

        url = f"{self.base_url}/fapi/v1/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        try:
            resp = self.session.get(url, params=params, timeout=8)
            if not self._handle_response(resp):
                with BinanceFuturesClient._cache_lock:
                    return BinanceFuturesClient._cache.get(cache_key, ([], 0))[0]
            resp.raise_for_status()
            raw = resp.json()

            candles = []
            for item in raw:
                candles.append({
                    "timestamp": int(item[0]),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                    "quote_volume": float(item[7])
                })
            
            # Dinamik TTL: 1m için 15s, 5m için 30s, 15m/1h için 60s (Binance limit kalkanı)
            ttl = 15.0 if interval == "1m" else (30.0 if interval == "5m" else 60.0)
            with BinanceFuturesClient._cache_lock:
                BinanceFuturesClient._cache[cache_key] = (candles, now + ttl)
            return candles
        except Exception as e:
            print(f"⚠️ [Binance get_klines Hata] {symbol} {interval}: {e}")
            with BinanceFuturesClient._cache_lock:
                return BinanceFuturesClient._cache.get(cache_key, ([], 0))[0]

    def get_funding_rate(self, symbol: str) -> Optional[Dict]:
        """Sembolün anlık fonlama oranını (Funding Rate) getirir (60s Cache)."""
        cache_key = f"funding_{symbol}"
        now = time.time()
        with BinanceFuturesClient._cache_lock:
            if cache_key in BinanceFuturesClient._cache:
                data, exp = BinanceFuturesClient._cache[cache_key]
                if now < exp:
                    return data

        if self._is_rate_limited():
            with BinanceFuturesClient._cache_lock:
                return BinanceFuturesClient._cache.get(cache_key, (None, 0))[0]

        url = f"{self.base_url}/fapi/v1/premiumIndex"
        params = {"symbol": symbol}
        try:
            resp = self.session.get(url, params=params, timeout=5)
            if not self._handle_response(resp):
                with BinanceFuturesClient._cache_lock:
                    return BinanceFuturesClient._cache.get(cache_key, (None, 0))[0]
            if resp.status_code == 200:
                data = resp.json()
                res = {
                    "lastFundingRate": float(data.get("lastFundingRate", 0.0)),
                    "markPrice": float(data.get("markPrice", 0.0)),
                    "indexPrice": float(data.get("indexPrice", 0.0))
                }
                with BinanceFuturesClient._cache_lock:
                    BinanceFuturesClient._cache[cache_key] = (res, now + 60.0)
                return res
        except Exception:
            pass
        with BinanceFuturesClient._cache_lock:
            return BinanceFuturesClient._cache.get(cache_key, (None, 0))[0]

    def get_book_ticker(self, symbol: str) -> Optional[Dict]:
        """
        Sembolün anlık en iyi alış (bid) ve en iyi satış (ask) fiyatlarını getirir (3s Cache).
        """
        cache_key = f"book_{symbol}"
        now = time.time()
        with BinanceFuturesClient._cache_lock:
            if cache_key in BinanceFuturesClient._cache:
                data, exp = BinanceFuturesClient._cache[cache_key]
                if now < exp:
                    return data

        if self._is_rate_limited():
            with BinanceFuturesClient._cache_lock:
                return BinanceFuturesClient._cache.get(cache_key, (None, 0))[0]

        url = f"{self.base_url}/fapi/v1/ticker/bookTicker"
        params = {"symbol": symbol}
        try:
            resp = self.session.get(url, params=params, timeout=4)
            if not self._handle_response(resp):
                with BinanceFuturesClient._cache_lock:
                    return BinanceFuturesClient._cache.get(cache_key, (None, 0))[0]
            if resp.status_code == 200:
                data = resp.json()
                bid = float(data.get("bidPrice", 0.0))
                ask = float(data.get("askPrice", 0.0))
                spread_pct = ((ask - bid) / bid * 100.0) if bid > 0 else 0.0
                res = {
                    "bidPrice": bid,
                    "askPrice": ask,
                    "bidQty": float(data.get("bidQty", 0.0)),
                    "askQty": float(data.get("askQty", 0.0)),
                    "spread_pct": round(spread_pct, 4)
                }
                with BinanceFuturesClient._cache_lock:
                    BinanceFuturesClient._cache[cache_key] = (res, now + 3.0)
                return res
        except Exception:
            pass
        with BinanceFuturesClient._cache_lock:
            return BinanceFuturesClient._cache.get(cache_key, (None, 0))[0]

    def get_ticker_price(self, symbol: str) -> Optional[Dict]:
        """Sembolün anlık son fiyatını getirir (2s Cache)."""
        cache_key = f"price_{symbol}"
        now = time.time()
        with BinanceFuturesClient._cache_lock:
            if cache_key in BinanceFuturesClient._cache:
                data, exp = BinanceFuturesClient._cache[cache_key]
                if now < exp:
                    return data

        if self._is_rate_limited():
            with BinanceFuturesClient._cache_lock:
                return BinanceFuturesClient._cache.get(cache_key, (None, 0))[0]

        url = f"{self.base_url}/fapi/v1/ticker/price"
        params = {"symbol": symbol}
        try:
            resp = self.session.get(url, params=params, timeout=4)
            if not self._handle_response(resp):
                with BinanceFuturesClient._cache_lock:
                    return BinanceFuturesClient._cache.get(cache_key, (None, 0))[0]
            if resp.status_code == 200:
                data = resp.json()
                res = {
                    "symbol": data.get("symbol"),
                    "price": float(data.get("price", 0.0))
                }
                with BinanceFuturesClient._cache_lock:
                    BinanceFuturesClient._cache[cache_key] = (res, now + 2.0)
                return res
        except Exception:
            pass
        with BinanceFuturesClient._cache_lock:
            return BinanceFuturesClient._cache.get(cache_key, (None, 0))[0]

    def get_btc_regime(self) -> Dict:
        """
        BTCUSDT piyasa durumunu ve çöküş riskini analiz eder (BTC Market Shield).
        Altcoin işlemlerinde likidite avından korunmak için kritik önemdedir.
        """
        try:
            klines_1h = self.get_klines("BTCUSDT", interval="1h", limit=50)
            if not klines_1h or len(klines_1h) < 10:
                return {"status": "NEUTRAL", "summary": "BTC verisi eksik", "block_longs": False}

            current_btc = klines_1h[-1]["close"]
            price_3h_ago = klines_1h[-4]["close"] if len(klines_1h) >= 4 else klines_1h[0]["close"]
            change_3h_pct = ((current_btc - price_3h_ago) / price_3h_ago) * 100

            # 1h EMA20 hesapla
            closes = [c["close"] for c in klines_1h]
            k = 2 / (20 + 1)
            ema20 = closes[0]
            for p in closes[1:]:
                ema20 = (p - ema20) * k + ema20

            # 0. Hafta Sonu / Ölü Testere Piyasa Kalkanı (BTC Dead Chop Shield & Otonom Kalibrasyon)
            from config import BTC_CHOP_MIN_RANGE_4H_PCT
            try:
                from core.self_tuning_engine import SelfTuningEngine
                active_chop_limit = SelfTuningEngine.get_current_params().get("btc_chop_min_range_4h_pct", BTC_CHOP_MIN_RANGE_4H_PCT)
            except Exception:
                active_chop_limit = BTC_CHOP_MIN_RANGE_4H_PCT

            recent_4h = klines_1h[-4:]
            high_4h = max(k["high"] for k in recent_4h)
            low_4h = min(k["low"] for k in recent_4h)
            range_4h_pct = ((high_4h - low_4h) / current_btc) * 100.0 if current_btc > 0 else 1.0

            if range_4h_pct < active_chop_limit:
                high_target = round(low_4h * (1.0 + (active_chop_limit / 100.0)), 1)
                low_target = round(high_4h * (1.0 - (active_chop_limit / 100.0)), 1)
                detailed = (
                    f"📌 <strong>Mevcut Durum:</strong> BTC son 4 saatte sadece %{range_4h_pct:.2f} dalgalandı (${low_4h:,.0f} - ${high_4h:,.0f}). Güvenli işlem için en az %{active_chop_limit:.2f} hareket aranıyor.<br>"
                    f"⛔ <strong>Giriş Yapılmama Nedeni:</strong> Hacimsiz ölü testere piyasalarında 10x/20x kaldıraçlı işlemler sahte fitillerle stop patlatır. Kasa sermayesini ($1.000) korumak için altcoin işlemleri donduruldu.<br>"
                    f"🎯 <strong>Beklenen Şart:</strong> Fiyatın <strong>${high_target:,.0f}</strong> üzerine çıkması veya <strong>${low_target:,.0f}</strong> altına inerek yön kazanması bekleniyor."
                )
                return {
                    "status": "DEAD_CHOP",
                    "btc_price": current_btc,
                    "change_3h_pct": round(change_3h_pct, 2),
                    "range_4h_pct": round(range_4h_pct, 2),
                    "high_4h": round(high_4h, 1),
                    "low_4h": round(low_4h, 1),
                    "active_chop_limit": active_chop_limit,
                    "high_target": high_target,
                    "low_target": low_target,
                    "block_longs": True,
                    "block_all_entries": True,
                    "summary": f"💤 BTC Ölü Testere Piyasada (4s bant: %{range_4h_pct:.2f} < %{active_chop_limit}). Altcoin işlemleri donduruldu.",
                    "detailed_reason": detailed
                }

            # 1. Acil Durum: Ani BTC Düşüşü (Dump Alert)
            if change_3h_pct <= -1.8:
                return {
                    "status": "DUMP_ALERT",
                    "btc_price": current_btc,
                    "change_3h_pct": round(change_3h_pct, 2),
                    "block_longs": True,
                    "summary": f"🚨 DİKKAT: BTC son saatlerde ani düşüş yaşıyor (%{change_3h_pct:.2f}). Altcoin LONG işlemleri durduruldu!"
                }

            # 2. Ayı Piyasası: Fiyat EMA20 altında ve düşüyor
            if current_btc < ema20 and change_3h_pct < -0.8:
                return {
                    "status": "BEARISH",
                    "btc_price": current_btc,
                    "change_3h_pct": round(change_3h_pct, 2),
                    "block_longs": True,
                    "summary": f"📉 BTC satıcılı seyrediyor ({current_btc:.1f}$, EMA altı). Sadece yüksek hacimli veya SHORT fırsatları aranıyor."
                }

            # 3. Boğa Piyasası: Fiyat EMA20 üzerinde
            if current_btc >= ema20:
                block_shorts = (change_3h_pct >= 1.2)
                return {
                    "status": "BULLISH",
                    "btc_price": current_btc,
                    "change_3h_pct": round(change_3h_pct, 2),
                    "block_longs": False,
                    "block_shorts": block_shorts,
                    "summary": f"🟢 BTC yükseliş trendinde ({current_btc:.1f}$). {'Altcoin SHORT işlemleri donduruldu (BTC Rallisi).' if block_shorts else 'Altcoin LONG fırsatları için zemin uygun.'}"
                }

            return {
                "status": "NEUTRAL",
                "btc_price": current_btc,
                "change_3h_pct": round(change_3h_pct, 2),
                "block_longs": False,
                "summary": f"⚖️ BTC konsolide oluyor ({current_btc:.1f}$). Normal piyasa şartları."
            }

        except Exception as e:
            return {"status": "NEUTRAL", "summary": f"BTC analizi yapılamadı: {e}", "block_longs": False}

