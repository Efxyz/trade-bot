"""
FAST Trading Bot Configuration - Binance Futures (USDT.P)
1 DAKİKALIK MİKRO SCALPING & SERİ İŞLEM MOTORU (YÜKSEK FREKANS)

Özellikler:
- Tamamen Bağımsız $1000 USDT Fon Kasası
- 1 Dakikalık (1m) Mumlarla Hızlı Giriş / Çıkış
- Ortalama 5-15 Dakika Pozisyonda Kalma Süresi
- Sık İşlem Sıklığı (Bol Bol İşlem)
- Hızlı Merdiven Kâr Kilidi (+%0.22'de BE+ Sigorta)
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CHARTS_DIR = DATA_DIR / "charts"
DB_PATH = DATA_DIR / "trading_bot.db"

# ========================================================
# FAST BOT FON YÖNETİMİ & KASA KALKANI (BAĞIMSIZ KASA)
# ========================================================
FAST_PORTFOLIO_EQUITY_USDT = 1000.0     # FAST Bot Başlangıç Kasası ($1000 USDT Bağımsız)
FAST_MAX_CONCURRENT_TRADES = 10         # Maksimum 10 eşzamanlı hızlı scalping pozisyonu
FAST_MAX_POSITIONS_PER_DIRECTION = 6    # Tek yöne max 6 LONG veya 6 SHORT (Toplam limit 10)
FAST_LEVERAGE = 10                      # Standart 10x Dinamik Kaldıraç
FAST_RISK_PER_TRADE_USDT = 15.0         # İşlem başına riske edilen miktar ($15 sabit risk)
FAST_ALLOCATED_MARGIN_PER_TRADE = 75.0  # Hızlı işlem başına marjin payı ($75)

# Borsa Komisyon & Kayma (Binance Vadeli Taker)
BINANCE_TAKER_FEE_PCT = 0.05
BINANCE_ROUNDTRIP_FEE_PCT = 0.10
ESTIMATED_SLIPPAGE_PCT = 0.02

# Telegram Bildirim Modu (Spam Önleme)
FAST_NOTIFY_INDIVIDUAL_TRADES = False       # Her işlem için tekil bildirim gönderme (Kapalı)
FAST_NOTIFY_HOURLY_REPORT = True           # Sadece her saat başı toplu PnL ve işlem raporu gönder

# ========================================================
# HIZLI MERDİVEN KÂR SİSTEMİ (FAST STEP-LADDER)
# ========================================================
# 1m hızlı mumlarda kârı anında korumak için sıkı basamaklar
FAST_LADDER_STEPS = [
    # Basamak 1: Fiyat +%0.22 kâra ulaştığında Stop'u +%0.08'e çek (Komisyonu çıkartır, işlemi garantiler)
    {"step": 1, "trigger_raw_pct": 0.22, "lock_raw_pct": 0.08, "name": "⚡ Hızlı BE+ (Komisyon Sigortası)"},
    
    # Basamak 2: Fiyat +%0.40 kâra ulaştığında Stop'u +%0.22'ye çek (10x'te +%2.2 marjin kârı cepte)
    {"step": 2, "trigger_raw_pct": 0.40, "lock_raw_pct": 0.22, "name": "⚡ Hızlı Kilit (+%2.2 Kâr)"},
    
    # Basamak 3: Fiyat +%0.60 kâra ulaştığında Stop'u +%0.45'e çek (10x'te +%4.5 marjin kârı cepte)
    {"step": 3, "trigger_raw_pct": 0.60, "lock_raw_pct": 0.45, "name": "⚡ Hızlı Kilit (+%4.5 Kâr)"}
]

# Dinamik Takip Kanalı
FAST_DYNAMIC_CHANNEL_PCT = 0.18

# ========================================================
# HIZLI SCALP RİSK / ÖDÜL VE ZAMAN PARAMETRELERİ
# ========================================================
FAST_PRIMARY_TIMEFRAME = "1m"           # 1 Dakikalık Ana İşlem Zaman Dilimi
FAST_CONFIRMATION_TIMEFRAME = "5m"      # 5 Dakikalık Mikro Trend Teyit Dilimi
FAST_SCAN_INTERVAL_SECONDS = 20         # 20 Saniyede Bir Hızlı Tarama (Seri Döngü)

FAST_TARGET_PROFIT_PCT = 0.65           # Hedef Kâr: Fiyatta +%0.65 (10x'te +%6.5 Marjin Kârı)
FAST_STOP_LOSS_PCT = 0.40               # Stop Loss: Fiyatta -%0.40 (10x'te -%4.0 Marjin Kaybı)
FAST_MIN_CONFLUENCE_SCORE = 65          # Hızlı Giriş Eşiği (65+ puan ile bol ve seri işlem fırsatı)
FAST_MIN_RR_RATIO = 1.4                 # Minimum 1:1.4 Risk/Ödül oranı
FAST_MAX_HOLD_MINUTES = 15              # Maksimum Pozisyon Süresi: 15 Dakika (Hareketsizse Çık!)

# Erken İptal (Hızlı Zarar Freni)
FAST_EARLY_INVALIDATION_ENABLED = True
FAST_EARLY_INVALIDATION_MINUTES = 4     # 4. dakikada negatifse (-%0.25) oyalanmadan çık
FAST_EARLY_INVALIDATION_LOSS_PCT = 0.25

# Günlük Devre Kesici & Karantina (FAST Kasa Kalkanı)
FAST_DAILY_MAX_DRAWDOWN_USDT = 35.0     # Günlük -$35 net zararda FAST taramayı o günlüğüne durdur
FAST_POST_LOSS_COOLDOWN_MINUTES = 5     # Zararlı paritede yalnızca 5 dk mola (hızlı devam)

# Freqtrade Side Guard (FAST Yön Kalkanı)
FAST_SIDE_GUARD_ENABLED = True
FAST_SIDE_MAX_CONSECUTIVE_LOSSES = 2    # Peş peşe 2 kayıpta o yön 30 dk dondurulur
FAST_SIDE_COOLDOWN_MINUTES = 30

# FAST Bot Taranacak Likit Pariteler Havuzu
FAST_COINS_UNIVERSE = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "1000PEPEUSDT",
    "WIFUSDT", "SUIUSDT", "NEARUSDT", "AVAXUSDT", "FETUSDT",
    "RENDERUSDT", "TAOUSDT", "TIAUSDT", "BNBUSDT", "XRPUSDT"
]

