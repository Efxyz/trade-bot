"""
Trading Bot Configuration - Binance Futures (USDT.P)
VUR-KAÇ MİKRO SCALPING MODU (Hızlı Küçük Karlar Alıp Çıkma)
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CHARTS_DIR = DATA_DIR / "charts"
DB_PATH = DATA_DIR / "trading_bot.db"

DATA_DIR.mkdir(exist_ok=True)
CHARTS_DIR.mkdir(exist_ok=True)

# Binance Futures Settings
BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"
MIN_24H_VOLUME_USDT = 12_000_000  # Likit, anlık hacimli pariteler

# ========================================================
# FON YÖNETİMİ & KASA KALKANI (CAPITAL PROTECTION SHIELD)
# ========================================================
PORTFOLIO_EQUITY_USDT = 1000.0         # Başlangıç Fon Kasası ($1000 USDT)
MAX_CONCURRENT_TRADES = 2              # Aşırı işlem tuzağını önlemek için max 2 pozisyon (Sermaye koruması)
RISK_PER_TRADE_PCT = 2.0               # İşlem başına riske edilen maksimum kasa payı (%2.0 = $20 risk)
MAX_ALLOCATED_MARGIN_PER_TRADE = 350.0 # Bir işleme ayrılabilecek maksimum marjin ($1000 / 2)
POST_LOSS_COOLDOWN_MINUTES = 15        # Zararlı kapanış sonrası 15 dk karantina molası (İntikam işlemine son!)

# Gerçekçi Borsa Komisyon & Fiyat Kayması (Binance Futures)
BINANCE_TAKER_FEE_PCT = 0.05           # %0.05 Taker piyasa emri giriş komisyonu
BINANCE_ROUNDTRIP_FEE_PCT = 0.10       # %0.10 Toplam komisyon (Giriş %0.05 + Çıkış %0.05)
ESTIMATED_SLIPPAGE_PCT = 0.02          # %0.02 Tahmini kayma payı

# ========================================================
# MERDİVEN KÂR SİSTEMİ (STEP-LADDER PROFIT LOCKING)
# ========================================================
# Binance Futures Taker Komisyonu (%0.05 Giriş + %0.05 Çıkış = %0.10 raw price)
# Merdiven basamakları: Fiyat kâra geçtikçe stop kademeli olarak yukarı (Long) veya aşağı (Short) çekilir
ENABLE_LADDER_PROFIT = True

LADDER_STEPS = [
    # Basamak 1: Komisyon Korumalı Başabaş (BE+)
    # Fiyat +%0.40 kâra ulaştığında stop'u komisyonu kurtaracak seviyeye çek (+%0.15 raw)
    # Stop olsa dahi borsa komisyonu düşüldükten sonra Net kâr kalır!
    {"step": 1, "trigger_raw_pct": 0.40, "lock_raw_pct": 0.15, "name": "🪜 Basamak 1 (BE+)"},
    
    # Basamak 2: Çeyrek Kâr Kilidi
    # Fiyat +%0.75 kâra ulaştığında stop'u +%0.45 kâra çek (10x'te net +%3.5, 20x'te net +%7.0 marjin cepte)
    {"step": 2, "trigger_raw_pct": 0.75, "lock_raw_pct": 0.45, "name": "🪜 Basamak 2 (%0.45 Kilit)"},
    
    # Basamak 3: Yarım Kâr Kilidi
    # Fiyat +%1.15 kâra ulaştığında stop'u +%0.80 kâra çek (10x'te net +%7.0, 20x'te net +%14.0 marjin cepte)
    {"step": 3, "trigger_raw_pct": 1.15, "lock_raw_pct": 0.80, "name": "🪜 Basamak 3 (%0.80 Kilit)"},
    
    # Basamak 4: Hedefe Yakın Koruma
    # Fiyat +%1.55 kâra ulaştığında stop'u +%1.20 kâra çek (10x'te net +%11.0, 20x'te net +%22.0 marjin cepte)
    {"step": 4, "trigger_raw_pct": 1.55, "lock_raw_pct": 1.20, "name": "🪜 Basamak 4 (%1.20 Kilit)"},
]

# Dinamik Kanal (Runner / Trailing Channel): Zirvenin %0.25 gerisinden iz sürme mesafesi
LADDER_DYNAMIC_CHANNEL_PCT = 0.25

# Dinamik Kaldıraç (10x ve 20x)
LEVERAGE_STANDARD = 10  # 10x ile %1 fiyat hareketi = +%10 marjin karı
LEVERAGE_HIGH = 20      # 20x ile %1 fiyat hareketi = +%20 marjin karı

# ========================================================
# RİSK / ÖDÜL VE VOLATİLİTE AYARLARI (GÜRÜLTÜYE KARŞI KORUMA)
# ========================================================
TARGET_PROFIT_PCT = 1.60        # Fiyatta ortalama %1.40 - %2.00 kâr hedefi (10x'te +%16, 20x'te +%32 marjin)
MAX_SCALP_SL_PCT = 1.35         # Fiyatta maksimum %1.35 stop payı (Fitil ve gürültüye ezilmeme garantisi)
MIN_SCALP_SL_PCT = 0.95         # Minimum %0.95 stop (54 saniyede gürültüye stop olmama koruması)
MAX_SL_PCT_10X = 1.35           # 10x için max SL %1.35 (Marjin büyüklüğü küçültülerek risk $20'de sabitlenir)
MAX_SL_PCT_20X = 0.85           # 20x için max SL %0.85 (Sniper dar stop)
MIN_RR_RATIO = 1.4              # Minimum 1:1.4 Risk/Ödül oranı
MAX_HOLD_MINUTES = 45           # Hareketsiz pozisyonları 45 dakikada kapat (Parayı asla kitleme!)

# SMC & Confluence Kalite Eşiği (Sadece Kusursuz Grade A+ Kurulumlar)
MIN_CONFLUENCE_SCORE = 76       # 76 altı zayıf / ortalama sinyaller kesinlikle elenir (Eski: 68)

# Likidite ve Slippage / Spread Koruması (Jesse & Hummingbot Standartları)
MAX_ORDERBOOK_SPREAD_PCT = 0.12     # En iyi alış/satış makası %0.12'den genişse likidite tuzağı kabul edilir
MAX_ALLOWED_FUNDING_RATE = 0.0008    # Fonlama oranı %0.08'in üzerindeyse yön aleyhine işlem engellenir (Fonlama Tuzağı)

# RSI ve Yatay Piyasa (Chop) Güvenlik Sınırları
MAX_RSI_LONG = 68.0             # 68 üzeri RSI ile ASLA tepeden LONG alınmaz
MIN_RSI_LONG = 40.0             # 40 altı zayıf momentumda LONG alınmaz
MIN_RSI_SHORT = 34.0            # 34 altı RSI ile ASLA dipten SHORT girilmez
MAX_RSI_SHORT = 60.0            # 60 üzeri güçlü boğa momentumunda SHORT girilmez
MIN_4BAR_RANGE_PCT = 0.35       # Son 1 saatte dalgalanma %0.35'in altındaysa piyasa ölü kabul edilir
BTC_CHOP_MIN_RANGE_4H_PCT = 0.80 # BTC 4 saatlik hareket alanı <%0.80 ise piyasa donuktur, işlem açılmaz

# Tarama Aralığı (Aşırı İşlem ve Borsa Komisyonu Tuzağını Önleme)
SCAN_INTERVAL_SECONDS = 90  # Her 90 saniyede bir tarar (Eski 45s makineli tüfek moduna son)

# Zaman Dilimleri
PRIMARY_TIMEFRAME = "15m"   # 15 Dakikalık Mumlar
ENTRY_TIMEFRAME = "5m"      # 5 Dakikalık Giriş Teyidi
MACRO_TIMEFRAME = "1h"      # 1 Saatlik Trend Filtresi

# BTC Kalkanı
ENABLE_BTC_SHIELD = True
BTC_DROP_ALERT_PCT = 1.0

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ENABLE_TELEGRAM_COMMANDS = True
CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY", "")
