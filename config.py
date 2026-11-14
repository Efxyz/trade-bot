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
# Kalibre Edilmiş Geniş Aralıklar: Kazançları erken boğmaz, mikro fitillerde en az +$5-$12 net kârı kilitler.
ENABLE_LADDER_PROFIT = True

LADDER_STEPS = [
    # Basamak 1: Freqtrade Dual-Tier Mikro BE+ Kalkanı (+%0.35 Ham / +%3.5 Marjin)
    # Fiyat +%0.35 kâra ulaştığında stop'u +%0.10'a çek (komisyonu çıkarır ve ASLA eksiye düşürmez)
    {"step": 1, "trigger_raw_pct": 0.35, "lock_raw_pct": 0.10, "name": "🛡️ Basamak 1 (BE+ %0.10 Sigorta)"},

    # Basamak 2: Komisyon Korumalı Sağlıklı Kâr Kilidi (%0.30 Kilit)
    # Fiyat +%0.65 kâra ulaştığında stop'u +%0.30'a çek (10x'te net +%3.0 marjin cepte, erken boğulmayı önler)
    {"step": 2, "trigger_raw_pct": 0.65, "lock_raw_pct": 0.30, "name": "🪜 Basamak 2 (%0.30 Kilit)"},

    # Basamak 3: Çeyrek Kâr Kilidi
    # Fiyat +%1.10 kâra ulaştığında stop'u +%0.70 kâra çek (10x'te net +%7.0 marjin cepte, +$11-$14)
    {"step": 3, "trigger_raw_pct": 1.10, "lock_raw_pct": 0.70, "name": "🪜 Basamak 3 (%0.70 Kilit)"},

    # Basamak 4: Hedefe Yakın Koruma
    # Fiyat +%1.60 kâra ulaştığında stop'u +%1.25 kâra çek (10x'te net +%12.5 marjin cepte, +$18-$22)
    {"step": 4, "trigger_raw_pct": 1.60, "lock_raw_pct": 1.25, "name": "🪜 Basamak 4 (%1.25 Kilit)"},
]

# Dinamik Kanal (Runner / Trailing Channel): Zirvenin %0.30 gerisinden iz sürme mesafesi
LADDER_DYNAMIC_CHANNEL_PCT = 0.30

# Zehirli Parite Kara Listesi (Toxic Asset Quarantine)
# Geçmiş 30 ve 90 günlük testlerde kasayı en çok eriten, kronik stop-hunt ve testere pariteleri
EXCLUDED_SYMBOLS_BLACKLIST = ["LINKUSDT", "ARBUSDT", "INJUSDT", "APTUSDT"]

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
MAX_SL_PCT_20X = 1.20           # 20x Sniper için max SL %1.20 (15m ATR dalgalanmasına uygun elit 85+ puanlı kurulumlar)
MIN_RR_RATIO = 1.8              # Minimum 1:1.8 Risk/Ödül oranı (Eski 1.4 barajı asimetrik getiri için yükseltildi)
MAX_HOLD_MINUTES = 90           # Hareketsiz pozisyonlara 90 dakika (6 mum) nefes payı tanı (Erken çıkış zararını önler)

# Erken Zarar Kes Kalkanı (Early Invalidation Shield - Hızlı Zarar Freni)
EARLY_INVALIDATION_ENABLED = True      # Toparlanamayan negatif pozisyonları -$20 beklemeden erken kes
EARLY_INVALIDATION_MINUTES = 20        # Hızlı kontrol süresi (dakika) - 20 dk (15m mum kapanışı + 5m teyit)
EARLY_INVALIDATION_LOSS_PCT = 0.35     # Fiyat %-0.35 altındaysa erken çıkış tetiklenir (Kaybı -$5-$7'de keser)
MAX_VWAP_DISTANCE_PCT = 1.30           # 15m VWAP'tan %1.30'dan fazla uzaktaki fiyatlarda aşırı uzama filtresi (Mean-Reversion Kalkanı)
SMC_PREMIUM_DISCOUNT_FILTER = True     # SMC Premium/Discount Kalkanı (Dipten Short / Tepeden Long Engeli)

# Freqtrade Side-Specific Stoploss Guard (Yön Bazlı Seri Zarar Kalkanı)
# Bir yönde (özellikle SHORT) peş peşe zarar geldiğinde o yönü dondurur, diğer yön (LONG) kesintisiz devam eder
SIDE_STOPLOSS_GUARD_ENABLED = True
SIDE_STOPLOSS_MAX_CONSECUTIVE_LOSSES = 2   # Peş peşe 2 zarar eden yön kilitlenir
SIDE_STOPLOSS_COOLDOWN_MINUTES = 120       # Kilitlenen yön 120 dakika boyunca yeni işleme kapatılır

# Dinamik Günlük Kota & Zirve Kâr Koruma Kalkanı (House-Money & Trailing Profit Lock)
DAILY_BASE_MAX_TRADES = 4              # Taban Keskin Nişancı Kotası: Zor/testere piyasada günde en fazla 4 işlem
PROFIT_STEP_FOR_BONUS_TRADES = 15.0     # Her +$15 net kârda kota genişlemesi
BONUS_TRADES_PER_STEP = 2              # Her +$15 kârda +2 ekstra işlem hakkı (Kârlı günde sınırsız avlanma)
DAILY_MAX_NEW_TRADES = 4               # Geriye dönük uyumluluk için alias
ENABLE_CIRCUIT_BREAKER = True           # Güvenlik Kalkanı: Günlük -$50 kayıpta taramayı 24s dondur
DAILY_MAX_DRAWDOWN_USDT = 50.0         # Günlük Acil Durum Sigortası (Circuit Breaker): -$50 kayıpta taramayı 24s dondur
DAILY_TRAILING_PROFIT_LOCK_ENABLED = True # Günlük Zirve Kâr Kilidi (Kazanılan kârı asla geri vermeme kalkanı)

# SMC & Confluence Kalite Eşiği (Dengeli Kurumsal SMC Kalibrasyonu - 14 Kasım Canlı Saha Ayarı)
MIN_CONFLUENCE_SCORE = 68            # 68+ Grade A fırsatlar için optimize edildi (Eski: 72/82)
MIN_CONFLUENCE_SCORE_SHORT = 70      # Short Kalite Eşiği: 70+ (Eski: 74/84)

# Likidite ve Slippage / Spread Koruması (Jesse & Hummingbot Standartları)
MAX_ORDERBOOK_SPREAD_PCT = 0.12     # En iyi alış/satış makası %0.12'den genişse likidite tuzağı kabul edilir
MAX_ALLOWED_FUNDING_RATE = 0.0008    # Fonlama oranı %0.08'in üzerindeyse yön aleyhine işlem engellenir (Fonlama Tuzağı)

# RSI ve Yatay Piyasa (Chop) Güvenlik Sınırları
MAX_RSI_LONG = 68.0             # 68 üzeri RSI ile ASLA tepeden LONG alınmaz
MIN_RSI_LONG = 40.0             # 40 altı zayıf momentumda LONG alınmaz
MIN_RSI_SHORT = 34.0            # 34 altı RSI ile ASLA dipten SHORT girilmez
MAX_RSI_SHORT = 60.0            # 60 üzeri güçlü boğa momentumunda SHORT girilmez
MIN_4BAR_RANGE_PCT = 0.35       # Son 1 saatte dalgalanma %0.35'in altındaysa piyasa ölü kabul edilir
BTC_CHOP_MIN_RANGE_4H_PCT = 0.70 # BTC 4 saatlik hareket alanı <%0.70 ise piyasa donuktur (Eski: 0.75 / 1.20)

# Tarama Aralığı (15m Mumlar İçin Optimize Edilmiş Kurumsal Ritim - Daha Yavaş & Sakin)
SCAN_INTERVAL_SECONDS = 180  # 15m SMC için her 180 saniyede bir (3 dk) sakin ve derin kurumsal tarama

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
