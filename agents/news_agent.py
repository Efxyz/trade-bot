"""
News & Sentiment Agent
Reads crypto news and evaluates whether a price move is driven by real fundamental catalysts
or is an empty speculative pump / liquidation hunt trap.
Maintains a live news feed for the Office News Desk.
"""
import requests
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
from collections import deque
from datetime import datetime
from config import CRYPTOPANIC_API_KEY

LIVE_NEWS_FEED = deque(maxlen=25)

def get_live_news_feed() -> List[Dict]:
    try:
        from core.database import get_news_feed_db
        db_news = get_news_feed_db(limit=25)
        if db_news:
            return db_news
    except Exception:
        pass
    return list(LIVE_NEWS_FEED)

class NewsAgent:
    def __init__(self, api_key: str = CRYPTOPANIC_API_KEY):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "TradeBotNews/1.0"})

    def fetch_latest_market_news(self) -> List[Dict]:
        """Cointelegraph & CoinDesk RSS akışlarından son piyasa haberlerini toplar."""
        rss_feeds = [
            ("Cointelegraph", "https://cointelegraph.com/rss"),
            ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/")
        ]
        items = []
        for source_name, feed_url in rss_feeds:
            try:
                resp = self.session.get(feed_url, timeout=4)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    for item in root.findall(".//item")[:5]:
                        title = item.find("title").text if item.find("title") is not None else ""
                        pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                        link = item.find("link").text if item.find("link") is not None else ""
                        if title:
                            # Sentiment tag
                            title_u = title.upper()
                            sentiment = "BULLISH" if any(w in title_u for w in ["SURGE", "RALLY", "JUMP", "HIGH", "BULL", "GAIN", "ETF", "APPROVE"]) else (
                                "BEARISH" if any(w in title_u for w in ["DROP", "DUMP", "FALL", "CRASH", "SEC", "HACK", "BAN", "LOSS"]) else "NEUTRAL"
                            )
                            time_str = datetime.now().strftime("%H:%M")
                            entry = {
                                "source": source_name,
                                "title": title,
                                "time": time_str,
                                "sentiment": sentiment,
                                "link": link
                            }
                            items.append(entry)
                            if entry not in LIVE_NEWS_FEED:
                                LIVE_NEWS_FEED.appendleft(entry)
                            try:
                                from core.database import save_news_item_db
                                save_news_item_db(source_name, title, time_str, sentiment, link)
                            except Exception:
                                pass
            except Exception:
                continue
        return items

    def get_cryptopanic_news(self, currency: str) -> List[Dict]:
        if not self.api_key:
            return []
        url = "https://cryptopanic.com/api/v1/posts/"
        params = {
            "auth_token": self.api_key,
            "currencies": currency.upper(),
            "kind": "news",
            "filter": "important",
            "public": "true"
        }
        try:
            resp = self.session.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("results", [])[:5]:
                    results.append({
                        "title": item.get("title", ""),
                        "published_at": item.get("published_at", ""),
                        "url": item.get("url", ""),
                        "domain": item.get("domain", "")
                    })
                return results
        except Exception:
            pass
        return []

    def analyze_catalyst(self, symbol: str, direction: str, funding_data: Optional[Dict] = None) -> Dict:
        base_coin = symbol.replace("USDT", "")
        news_items = self.get_cryptopanic_news(base_coin)
        funding_rate = funding_data.get("lastFundingRate", 0.0) if funding_data else 0.0
        has_news = len(news_items) > 0
        news_titles = [item["title"] for item in news_items]

        if not has_news:
            if direction == "LONG" and funding_rate > 0.0004:
                verdict = "DİKKAT: SPEKÜLATİF ŞİŞME"
                is_empty_move = True
                summary = "Haber akışı yok. Yüksek fonlama oranı tuzak riski taşıyor."
            else:
                verdict = "TEKNİK FİYAT HAREKETİ"
                is_empty_move = False
                summary = "Haber akışı sakin. Hareket organik teknik akış kaynaklı."
        else:
            verdict = "HABER DESTEKLİ KATALİZÖR"
            is_empty_move = False
            summary = news_titles[0]

        return {
            "symbol": symbol,
            "verdict": verdict,
            "is_empty_move": is_empty_move,
            "funding_rate_pct": round(funding_rate * 100, 4),
            "summary": summary
        }
