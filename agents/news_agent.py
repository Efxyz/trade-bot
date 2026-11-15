"""
News & Fundamental Intelligence Agent & Haber Kararlandırma Konseyi
Gelişmiş Çok Kaynaklı Kripto Haber & Katalizör Araştırma Masası:
1. Kurumsal Haber Kaynakları: Cointelegraph, CoinDesk, Decrypt, The Block, CryptoSlate.
2. Sembole / Coine Özel Derin Araştırma (Coin-Specific News Deep-Dive) - İşlem öncesi canlı sorgu.
3. Haber Kararlandırma Konseyi (3 Uzman Masa):
   - 🏛️ Regülasyon & Hukuk Şefi (SEC, ETF, dava, yasaklama)
   - 🔐 Protokol & On-Chain Güvenlik Şefi (Hack, exploit, kilit açılımı, burn, ortaklık)
   - 🐋 Balina & Sosyal Hype Masası (X / Twitter trendleri, balina transferleri)
4. Yüzdelik Karar Verme (Position Size Multiplier):
   - Güçlü Boğa Katalizörü: +%25 Hacim (1.25x)
   - Nötr Akış: Standart Kasa (%100, 1.0x)
   - Şüpheli / FUD Baskısı: -%40 Defansif Kasa (0.60x)
   - Kara Kuğu / Hack / Dava: %100 VETO (0.0x - İşlem İptal!)
"""
import time
import requests
import xml.etree.ElementTree as ET
import urllib.parse
from typing import Dict, List, Optional, Tuple
from collections import deque
from datetime import datetime
from config import CRYPTOPANIC_API_KEY

LIVE_NEWS_FEED = deque(maxlen=35)

# Genişletilmiş Kripto Sembol - İsim Sözlüğü (Arama Hassasiyeti İçin)
SYMBOL_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "DOGE": "Dogecoin",
    "AVAX": "Avalanche", "XRP": "Ripple", "ADA": "Cardano", "BNB": "Binance Coin",
    "LINK": "Chainlink", "SUI": "Sui Network", "NEAR": "NEAR Protocol", "PEPE": "Pepe",
    "SHIB": "Shiba Inu", "APT": "Aptos", "INJ": "Injective", "TIA": "Celestia",
    "KAVA": "Kava", "AR": "Arweave", "SEI": "Sei Network", "WIF": "dogwifhat",
    "RENDER": "Render Token", "FET": "Fetch.ai", "LTC": "Litecoin", "BCH": "Bitcoin Cash",
    "ATOM": "Cosmos", "DOT": "Polkadot", "OP": "Optimism", "ARB": "Arbitrum",
    "FIL": "Filecoin", "STX": "Stacks", "RUNE": "THORChain", "IMX": "Immutable",
    "GRT": "The Graph", "FLOKI": "Floki", "BONK": "Bonk", "FTM": "Fantom"
}

# 🚨 Kara Kuğu & Kritik Ayı Anahtar Kelimeleri (Doğrudan VETO)
BLACK_SWAN_KEYWORDS = [
    "HACK", "EXPLOIT", "STOLEN", "DRAINED", "VULNERABILITY", "COMPROMISED",
    "SEC LAWSUIT", "SEC CHARGES", "SUBPOENA", "FRAUD", "INDICTMENT",
    "BAN", "BANNED", "DELIST", "DELISTING", "BANKRUPT", "INSOLVENCY",
    "SHUTDOWN", "RUG PULL", "SCAM", "SANCTION"
]

# 🚀 Güçlü Boğa Katalizörleri
BULLISH_CATALYST_KEYWORDS = [
    "ETF APPROV", "PARTNERSHIP", "LISTED ON", "LISTING", "MAINNET LAUNCH",
    "TOKEN BURN", "BUYBACK", "UPGRADE", "WHALE ACCUMULATION", "STRATEGIC INVESTMENT",
    "TREASURY ADOPTION", "ACQUISITION", "ALL-TIME HIGH", "ATH"
]

# 🩸 Genel Ayı & FUD Baskısı
BEARISH_KEYWORDS = [
    "DROP", "DUMP", "FALL", "CRASH", "BEARISH", "UNLOCK", "DILUTION",
    "OUTFLOW", "LIQUIDATION", "SELLING PRESSURE", "INVESTIGATION", "LAWSUIT",
    "FINE", "DOWNGRADE", "SLUMP"
]

# 🟢 Genel Boğa & İvme
BULLISH_KEYWORDS = [
    "SURGE", "RALLY", "BREAKOUT", "BULLISH", "GAINS", "INFLOW",
    "REBOUND", "RECOVERY", "GROWTH", "EXPANDING", "BOUNCE"
]

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
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (TradeBot-NewsIntelligence/2.0)"
        })
        # Haber önbelleği: Sembol başına 10 dakika süreyle hafızada tutulur (Rate-limit ve hız kalkanı)
        self._coin_news_cache: Dict[str, Tuple[float, List[Dict]]] = {}
        self._last_general_fetch: float = 0.0

    def fetch_latest_market_news(self) -> List[Dict]:
        """
        Büyük kripto haber şirketlerinin (Cointelegraph, CoinDesk, Decrypt, The Block, CryptoSlate)
        RSS akışlarından en sıcak küresel piyasa haberlerini toplar.
        """
        now = time.time()
        if now - self._last_general_fetch < 60 and len(LIVE_NEWS_FEED) > 0:
            return list(LIVE_NEWS_FEED)
        self._last_general_fetch = now

        rss_feeds = [
            ("Cointelegraph", "https://cointelegraph.com/rss"),
            ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
            ("Decrypt", "https://decrypt.co/feed"),
            ("The Block", "https://www.theblock.co/rss.xml"),
            ("CryptoSlate", "https://cryptoslate.com/feed/")
        ]
        items = []
        for source_name, feed_url in rss_feeds:
            try:
                resp = self.session.get(feed_url, timeout=3.5)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    for item in root.findall(".//item")[:5]:
                        title = item.find("title").text if item.find("title") is not None else ""
                        pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                        link = item.find("link").text if item.find("link") is not None else ""
                        if title:
                            title_u = title.upper()
                            sentiment = "BULLISH" if any(w in title_u for w in BULLISH_KEYWORDS or BULLISH_CATALYST_KEYWORDS) else (
                                "BEARISH" if any(w in title_u for w in BEARISH_KEYWORDS or BLACK_SWAN_KEYWORDS) else "NEUTRAL"
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

    def fetch_coin_specific_news(self, symbol: str, lookback_hours: int = 24) -> List[Dict]:
        """
        İşleme girmeden önce ilgili coin hakkında derinlemesine hedef haber taraması yapar.
        Google News Finans RSS + Global Kripto Medyası çapraz taramasıyla son 24 saati analiz eder.
        """
        clean_symbol = symbol.replace("USDT", "").replace("USDC", "").replace(".P", "").upper()
        now = time.time()
        
        # 1. Önbellek kontrolü (10 dakika geçerli)
        if clean_symbol in self._coin_news_cache:
            cache_time, cached_articles = self._coin_news_cache[clean_symbol]
            if now - cache_time < 600:
                return cached_articles

        full_name = SYMBOL_NAMES.get(clean_symbol, clean_symbol)
        query = f"{clean_symbol} OR {full_name} crypto when:{lookback_hours}h"
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        
        articles = []
        try:
            resp = self.session.get(url, timeout=4.0)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item")[:12]:
                    title = item.find("title").text if item.find("title") is not None else ""
                    source = item.find("source").text if item.find("source") is not None else "Google News Finans"
                    link = item.find("link").text if item.find("link") is not None else ""
                    pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                    if title:
                        articles.append({
                            "title": title,
                            "source": source,
                            "link": link,
                            "date": pub_date
                        })
        except Exception:
            pass

        # Ayrıca genel havuzdaki haberlerden coin ile eşleşenleri ekle
        for n in list(LIVE_NEWS_FEED):
            t_u = n.get("title", "").upper()
            if clean_symbol in t_u or full_name.upper() in t_u:
                articles.append({
                    "title": n.get("title"),
                    "source": n.get("source"),
                    "link": n.get("link", ""),
                    "date": n.get("time", "")
                })

        self._coin_news_cache[clean_symbol] = (now, articles)
        return articles

    def investigate_coin_news(self, symbol: str, direction: str, funding_data: Optional[Dict] = None) -> Dict:
        """
        HABER KARARLANDIRMA KONSEYİ (NEWS INTELLIGENCE COUNCIL)
        İşleme girmeden önce coine özel haberleri ve katalizörleri masaya yatırır.
        3 Ajan Masasının (Regülasyon, Protokol Güvenliği, Balina/X Hype) ortak kararıyla:
        - Yüzdelik Kasa Çarpanı (pos_multiplier: 0.0x ile 1.25x)
        - Veto Kararı (is_vetoed: True/False)
        - Konsey Tartışma Raporu üretir.
        """
        clean_symbol = symbol.replace("USDT", "").replace("USDC", "").replace(".P", "").upper()
        full_name = SYMBOL_NAMES.get(clean_symbol, clean_symbol)
        articles = self.fetch_coin_specific_news(symbol)

        funding_rate = funding_data.get("lastFundingRate", 0.0) if funding_data else 0.0
        funding_pct = funding_rate * 100.0

        base_score = 50.0  # Nötr başlangıç
        black_swan_reasons = []
        bullish_reasons = []
        bearish_reasons = []

        for a in articles:
            t_upper = a["title"].upper()
            
            # 1. Kara Kuğu & Kritik Güvenlik Denetimi
            for kw in BLACK_SWAN_KEYWORDS:
                if kw in t_upper:
                    black_swan_reasons.append(f"{a['source']}: '{a['title']}' ({kw})")
                    base_score -= 35
                    break
            
            # 2. Güçlü Boğa Katalizörleri
            for kw in BULLISH_CATALYST_KEYWORDS:
                if kw in t_upper:
                    bullish_reasons.append(f"{a['source']}: '{a['title']}' ({kw})")
                    base_score += 20
                    break

            # 3. Genel Ayı / Düşüş
            for kw in BEARISH_KEYWORDS:
                if kw in t_upper:
                    bearish_reasons.append(f"{a['source']}: '{a['title']}'")
                    base_score -= 6
                    break

            # 4. Genel Boğa / İtiş
            for kw in BULLISH_KEYWORDS:
                if kw in t_upper:
                    base_score += 6
                    break

        news_score = max(0, min(100, int(base_score)))
        black_swan_detected = len(black_swan_reasons) > 0
        bullish_catalyst_detected = len(bullish_reasons) > 0

        # ========================================================
        # 🏛️ ÜÇLÜ HABER KARARLANDIRMA KONSEYİ TARTIŞMASI
        # ========================================================
        
        # Masa 1: Regülasyon & Hukuk Şefi
        if any("SEC" in r or "LAWSUIT" in r or "BAN" in r or "SANCTION" in r for r in black_swan_reasons + bearish_reasons):
            reg_verdict = f"⚠️ Yasal soruşturma, SEC davası veya regülasyon baskısı mevcut! {clean_symbol} riskli bölgede."
        elif any("ETF" in r for r in bullish_reasons):
            reg_verdict = f"🏛️ Kurumsal ETF ve onay rüzgarı lehimize esiyor. {clean_symbol} kurumsal radarında."
        else:
            reg_verdict = f"✅ Yasal, regülatif veya kurumsal cephede {clean_symbol} için majör bir tehdit tespit edilmedi."

        # Masa 2: Protokol & On-Chain Güvenlik Şefi
        if black_swan_detected:
            sec_verdict = f"🚨 KRİTİK GÜVENLİK ALARMI: Akıllı sözleşme açığı, hack veya tasfiye şüphesi! ({black_swan_reasons[0][:60]})"
        elif bullish_catalyst_detected:
            sec_verdict = f"⚡ Protokol seviyesinde güçlü güncelleme, yakım veya ekosistem ortaklığı doğrulandı! ({bullish_reasons[0][:60]})"
        else:
            sec_verdict = f"🛡️ {clean_symbol} protokolü ve on-chain durumu stabil, olağandışı kilit açılımı veya çöküş riski yok."

        # Masa 3: Balina & Sosyal Hype Masası (X / Twitter)
        if news_score >= 68:
            hype_verdict = f"📈 Sosyal medyada ve X üzerinde {clean_symbol} için güçlü boğa ivmesi, balina alımı ve FOMO hakim."
        elif news_score <= 32:
            hype_verdict = f"🩸 Kripto çevrelerinde ve X üzerinde {clean_symbol} aleyhine panik satışı ve FUD baskısı yayılıyor."
        elif funding_pct > 0.04 and direction == "LONG":
            hype_verdict = f"⚠️ Fonlama oranı yüksek (%{funding_pct:.3f}). Hype yapay spekülasyon veya long tuzağı olabilir."
        else:
            hype_verdict = f"⚖️ Sosyal hacim ve emir akışı dengeli. Organik piyasa ritmiyle hareket ediyor."

        council_debate = [
            f"🏛️ [Regülasyon Masası]: {reg_verdict}",
            f"🔐 [Protokol & Güvenlik]: {sec_verdict}",
            f"🐋 [Balina & X/Twitter Masası]: {hype_verdict}"
        ]

        # ========================================================
        # 🎯 KONSEY KARARI & YÜZDELİK POZİSYON BÜYÜKLÜĞÜ
        # ========================================================
        is_vetoed = False
        veto_reason = ""
        pos_multiplier = 1.0

        if direction == "LONG":
            if black_swan_detected or news_score < 30:
                is_vetoed = True
                pos_multiplier = 0.0
                veto_reason = f"🚨 Haber Konseyi Veto Etti (Skor: {news_score}/100): Kritik Ayı / Kara Kuğu Haberi Mevcut!"
                verdict = "🚨 KRİTİK KARA KUĞU VETOSU"
            elif news_score >= 75:
                pos_multiplier = 1.25 # Marjini %25 artır
                verdict = "GÜÇLÜ BOĞA KATALİZÖRÜ (+%25 Hacim)"
            elif news_score >= 60:
                pos_multiplier = 1.10 # Marjini %10 artır
                verdict = "POZİTİF HABER RÜZGARI (+%10 Hacim)"
            elif news_score < 45 or (funding_pct > 0.04):
                pos_multiplier = 0.60 # Marjini %40 kıs (Defansif)
                verdict = "ŞÜPHELİ AYI BASKISI (-%40 Defansif Kasa)"
            else:
                pos_multiplier = 1.00
                verdict = "ORGANİK TEKNİK AKIŞ / NÖTR"
        else: # SHORT
            if bullish_catalyst_detected and news_score > 70:
                is_vetoed = True
                pos_multiplier = 0.0
                veto_reason = f"🚨 Haber Konseyi Veto Etti (Skor: {news_score}/100): Güçlü Boğa Katalizörü Varken SHORT Yasaktır!"
                verdict = "🚨 BOĞA RALLİSİ VETOSU"
            elif black_swan_detected or news_score <= 30:
                pos_multiplier = 1.25 # Kötü haberde SHORT pozisyonu güçlendir
                verdict = "AYI ÇÖKÜŞ KATALİZÖRÜ (+%25 SHORT Hacmi)"
            elif news_score <= 45:
                pos_multiplier = 1.10
                verdict = "NEGATİF HABER DESTEĞİ (+%10 SHORT Hacmi)"
            elif news_score > 58:
                pos_multiplier = 0.60 # Boğa rüzgarında SHORT marjinini kıs
                verdict = "BOĞA BASKISI (-%40 Defansif Kasa)"
            else:
                pos_multiplier = 1.00
                verdict = "ORGANİK TEKNİK AKIŞ / NÖTR"

        # Geriye dönük uyumluluk alanları
        is_empty_move = (news_score < 45 and direction == "LONG" and funding_pct > 0.03)

        summary_title = articles[0]["title"] if articles else "Önemli bir haber akışı yok."
        if black_swan_detected:
            summary_title = f"⚠️ {black_swan_reasons[0]}"
        elif bullish_catalyst_detected:
            summary_title = f"🚀 {bullish_reasons[0]}"

        return {
            "symbol": symbol,
            "coin_name": full_name,
            "direction": direction,
            "news_score": news_score,
            "verdict": verdict,
            "is_vetoed": is_vetoed,
            "veto_reason": veto_reason,
            "pos_multiplier": pos_multiplier,
            "is_empty_move": is_empty_move,
            "funding_rate_pct": round(funding_pct, 4),
            "article_count": len(articles),
            "top_articles": articles[:4],
            "council_debate": council_debate,
            "summary": f"🏛️ Haber Konseyi ({news_score}/100): {verdict} | {summary_title[:75]}"
        }

    # Geriye dönük uyumluluk için alias
    def analyze_catalyst(self, symbol: str, direction: str, funding_data: Optional[Dict] = None) -> Dict:
        return self.investigate_coin_news(symbol, direction, funding_data)
