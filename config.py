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
MAX_CONCURRENT_TRADES = 5              # Patron Onayı: Maksimum 5 eşzamanlı pozisyon (Yüksek alfa kapasitesi)
MAX_POSITIONS_PER_DIRECTION = 3        # Tek Yöne Yığılma Kalkanı (Maksimum 3 LONG veya 3 SHORT)
RISK_PER_TRADE_PCT = 2.0               # İşlem başına riske edilen maksimum kasa payı (%2.0 = $20 risk)
MAX_ALLOCATED_MARGIN_PER_TRADE = 200.0 # Bir işleme ayrılabilecek taban maksimum marjin (%20 kuralı)
POST_LOSS_COOLDOWN_MINUTES = 15        # Zararlı kapanış sonrası 15 dk karantina molası (İntikam işlemine son!)

# Gerçekçi Borsa Komisyon & Fiyat Kayması (Binance Futures)
BINANCE_TAKER_FEE_PCT = 0.05           # %0.05 Taker piyasa emri giriş komisyonu
BINANCE_ROUNDTRIP_FEE_PCT = 0.10       # %0.10 Toplam komisyon (Giriş %0.05 + Çıkış %0.05)
ESTIMATED_SLIPPAGE_PCT = 0.02          # %0.02 Tahmini kayma payı

# ========================================================
# MERDİVEN KÂR SİSTEMİ (STEP-LADDER PROFIT LOCKING)
# ========================================================
# MERDİVEN KÂR SİSTEMİ (STEP-LADDER PROFIT LOCKING)
# ========================================================
# Binance Futures Taker Komisyonu (%0.05 Giriş + %0.05 Çıkış = %0.10 raw price)
# Merdiven basamakları: Fiyat kâra geçtikçe stop kademeli olarak kâra çekilir
# Kalibre Edilmiş Güvenli Aralıklar: Fiyata nefes payı tanır, mikro fitillerle erken boğulmayı önler.
ENABLE_LADDER_PROFIT = True

LADDER_STEPS = [
    # Basamak 1: Komisyon Korumalı Güvenli Kâr Kilidi (BE+)
    # Fiyat +%0.65 kâra ulaştığında stop'u +%0.25'e çek (10x'te net +%1.5 marjin cepte, %0.40 fitil payı)
    {"step": 1, "trigger_raw_pct": 0.65, "lock_raw_pct": 0.25, "name": "🪜 Basamak 1 (BE+ %0.25 Kilit)"},
    
    # Basamak 2: Çeyrek Kâr Kilidi
    # Fiyat +%1.00 kâra ulaştığında stop'u +%0.60 kâra çek (10x'te net +%5.0 marjin cepte)
    {"step": 2, "trigger_raw_pct": 1.00, "lock_raw_pct": 0.60, "name": "🪜 Basamak 2 (%0.60 Kilit)"},
    
    # Basamak 3: Yarım Kâr Kilidi
    # Fiyat +%1.45 kâra ulaştığında stop'u +%1.00 kâra çek (10x'te net +%9.0 marjin cepte)
    {"step": 3, "trigger_raw_pct": 1.45, "lock_raw_pct": 1.00, "name": "🪜 Basamak 3 (%1.00 Kilit)"},
    
    # Basamak 4: Hedefe Yakın Koruma
    # Fiyat +%1.85 kâra ulaştığında stop'u +%1.45 kâra çek (10x'te net +%13.5 marjin cepte)
    {"step": 4, "trigger_raw_pct": 1.85, "lock_raw_pct": 1.45, "name": "🪜 Basamak 4 (%1.45 Kilit)"},
]

# Dinamik Kanal (Runner / Trailing Channel): Zirvenin %0.30 gerisinden iz sürme mesafesi
LADDER_DYNAMIC_CHANNEL_PCT = 0.30

# Dinamik Kaldıraç (10x ve 20x)
LEVERAGE_STANDARD = 10  # 10x ile %1 fiyat hareketi = +%10 marjin karı
LEVERAGE_HIGH = 20      # 20x ile %1 fiyat hareketi = +%20 marjin karı

# ========================================================
# RİSK / ÖDÜL VE VOLATİLİTE AYARLARI (KESKİN NİŞANCI & GÜRÜLTÜ KORUMASI)
# ========================================================
TARGET_PROFIT_PCT = 2.00        # Fiyatta ortalama %2.00 kâr hedefi (10x'te +%20 marjin karı)
MAX_SCALP_SL_PCT = 1.15         # Fiyatta maksimum %1.15 stop payı (Kayıp frenleme kalkanı)
MIN_SCALP_SL_PCT = 0.85         # Minimum %0.85 stop (Gürültüye ezilmeme garantisi)
MAX_SL_PCT_10X = 1.15           # 10x için max SL %1.15 (Marjin büyüklüğü küçültülerek risk $20'de sabitlenir)
MAX_SL_PCT_20X = 1.00           # 20x Sniper için max SL %1.00 (Elit 85+ puanlı dar stoplu kurulumlar)
MIN_RR_RATIO = 1.8              # Minimum 1:1.8 Risk/Ödül oranı (Eski 1.4 barajı asimetrik getiri için yükseltildi)
MAX_HOLD_MINUTES = 90           # Hareketsiz pozisyonlara 90 dakika (6 mum) nefes payı tanı (Erken çıkış zararını önler)

# Dinamik Günlük Kota & Zirve Kâr Koruma Kalkanı (House-Money & Trailing Profit Lock)
DAILY_BASE_MAX_TRADES = 4              # Taban Keskin Nişancı Kotası: Zor/testere piyasada günde en fazla 4 işlem
PROFIT_STEP_FOR_BONUS_TRADES = 15.0     # Her +$15 net kârda kota genişlemesi
BONUS_TRADES_PER_STEP = 2              # Her +$15 kârda +2 ekstra işlem hakkı (Kârlı günde sınırsız avlanma)
DAILY_MAX_NEW_TRADES = 4               # Geriye dönük uyumluluk için alias
DAILY_MAX_DRAWDOWN_USDT = 50.0         # Günlük Acil Durum Sigortası (Circuit Breaker): -$50 kayıpta taramayı 24s dondur
DAILY_TRAILING_PROFIT_LOCK_ENABLED = True # Günlük Zirve Kâr Kilidi (Kazanılan kârı asla geri vermeme kalkanı)

# SMC & Confluence Kalite Eşiği (Sadece Kusursuz Grade A+ Kurulumlar - Keskin Nişancı Modu)
MIN_CONFLUENCE_SCORE = 82       # 82 altı ortalama sinyaller kesinlikle elenir (Eski: 76)

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
SCAN_INTERVAL_SECONDS = 30  # Yüksek Hassasiyetli Turbo Tarama: Her 30 saniyede bir kesintisiz tarar (3x Hız, Sıfır Fırsat Kaçırma)

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
