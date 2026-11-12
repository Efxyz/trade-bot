"""
SÜPER FAST Trading Bot Configuration - Binance Futures (USDT.P)
SANİYELİK MİKRO-TICK SCALPING & ULTRA YÜKSEK FREKANSLI (HFT) İŞLEM MOTORU

Özellikler:
- Tamamen Bağımsız $1000 USDT Fon Kasası
- Saniyelik Mumlar & Sub-Second WebSocket Tick Akışı
- Toplam 20 Eşzamanlı İşlem Sınırı
- Ortalama 1-5 Dakika Pozisyonda Kalma Süresi (Mikro Vur-Kaç)
- Ultra Hızlı Kâr Kilidi (+%0.15'te BE+ Sigorta)
- Saatlik Telegram Özet Raporu
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CHARTS_DIR = DATA_DIR / "charts"
DB_PATH = DATA_DIR / "trading_bot.db"

# ========================================================
# SÜPER FAST FON YÖNETİMİ & KASA KALKANI (BAĞIMSIZ KASA)
# ========================================================
SUPER_FAST_PORTFOLIO_EQUITY_USDT = 1000.0   # Süper FAST Bot Başlangıç Kasası ($1000 USDT Bağımsız)
SUPER_FAST_MAX_CONCURRENT_TRADES = 20        # Maksimum 20 eşzamanlı saniyelik scalping pozisyonu
SUPER_FAST_MAX_POSITIONS_PER_DIRECTION = 12  # Tek yöne max 12 LONG veya 12 SHORT (20 kapasite dengeli)
SUPER_FAST_LEVERAGE = 10                    # Standart 10x Dinamik Kaldıraç
SUPER_FAST_RISK_PER_TRADE_USDT = 7.5        # İşlem başına riske edilen miktar ($7.5 dar risk)
SUPER_FAST_ALLOCATED_MARGIN_PER_TRADE = 35.0 # Saniyelik işlem başına marjin payı (20 işlem x $35 = $700 marjin)

# Borsa Komisyon & Kayma (Binance Vadeli Taker)
BINANCE_TAKER_FEE_PCT = 0.05
BINANCE_ROUNDTRIP_FEE_PCT = 0.10
ESTIMATED_SLIPPAGE_PCT = 0.02

# Telegram Bildirim Ayarları (Spam Önleme)
SUPER_FAST_NOTIFY_INDIVIDUAL_TRADES = False  # Her işlem için tekil bildirim gönderme (Kapalı)
SUPER_FAST_NOTIFY_HOURLY_REPORT = True      # Sadece her saat başı toplu PnL ve işlem raporu gönder

# ========================================================
# ========================================================
# ULTRA HIZLI MERDİVEN KÂR SİSTEMİ (MICRO STEP-LADDER - KOMİSYON KORUMALI)
# ========================================================
# Binance vadeli roundtrip taker komisyonu (%0.10 ham / %1.0 marjin).
# BE+ kilidi %0.14 ham kârı sabitleyerek komisyon sonrası NET +%0.40 KÂR garantiler.
SUPER_FAST_LADDER_STEPS = [
    # Basamak 1: Fiyat +%0.22 kâra ulaştığında Stop'u +%0.14'e çek (Komisyonu net aşar, kârı kilitler)
    {"step": 1, "trigger_raw_pct": 0.22, "lock_raw_pct": 0.14, "name": "⚡⚡ Saniyelik BE+ (Komisyon Korumalı)"},
    
    # Basamak 2: Fiyat +%0.35 kâra ulaştığında Stop'u +%0.22'ye çek (10x'te net +%1.2 kâr cepte)
    {"step": 2, "trigger_raw_pct": 0.35, "lock_raw_pct": 0.22, "name": "⚡⚡ Saniyelik Kilit (+%1.2 Kâr)"},
    
    # Basamak 3: Fiyat +%0.50 kâra ulaştığında Stop'u +%0.35'e çek (10x'te net +%2.5 kâr cepte)
    {"step": 3, "trigger_raw_pct": 0.50, "lock_raw_pct": 0.35, "name": "⚡⚡ Saniyelik Kilit (+%2.5 Kâr)"}
]

# Dinamik Takip Kanalı
SUPER_FAST_DYNAMIC_CHANNEL_PCT = 0.12

# ========================================================
# SANİYELİK SCALP RİSK / ÖDÜL VE ZAMAN PARAMETRELERİ
# ========================================================
SUPER_FAST_PRIMARY_TIMEFRAME = "1s"          # Saniyelik / Tick Akışı Ana İşlem Dilimi
SUPER_FAST_CONFIRMATION_TIMEFRAME = "1m"     # 1 Dakikalık Mikro Trend Teyit Dilimi
SUPER_FAST_SCAN_INTERVAL_SECONDS = 8         # 8 Saniyede Bir Hızlı Tarama Döngüsü (Tam Limit Ayarında)

SUPER_FAST_TARGET_PROFIT_PCT = 0.50          # Hedef Kâr: Fiyatta +%0.50 (10x'te +%5.0 Marjin Kârı)
SUPER_FAST_STOP_LOSS_PCT = 0.25              # Stop Loss: Fiyatta -%0.25 (10x'te -%2.5 Marjin Kaybı)
SUPER_FAST_MAX_HOLD_MINUTES = 6              # 6 Dakika içinde kâra gitmeyen mikro scalpten çık (Hızlı Rotasyon)

# Erken Geçersizlik (Early Invalidation)
SUPER_FAST_EARLY_INVALIDATION_ENABLED = True
SUPER_FAST_EARLY_INVALIDATION_MINUTES = 2    # 2 dakika içinde tersine -%0.16 giderse erken kes
SUPER_FAST_EARLY_INVALIDATION_LOSS_PCT = 0.16

# Güvenlik Kalkanı
SUPER_FAST_CIRCUIT_BREAKER_ENABLED = False  # Patron Talimatı: Devre kesici kapatıldı (Bugün işlemler izleniyor)
SUPER_FAST_DAILY_MAX_DRAWDOWN_USDT = 40.0    # Günlük $40 kümülatif zararda yeni mikro işlemleri durdur
SUPER_FAST_POST_LOSS_COOLDOWN_MINUTES = 12   # Zararlı kapanan pariteye 12 dakika dinlenme (intikam işlemine son)
SUPER_FAST_BLOCK_DEAD_CHOP = False           # Saniyelik scalping için piyasa dondurması kapalı (LONG koruması aktif kalır)
SUPER_FAST_SIDE_GUARD_ENABLED = True
SUPER_FAST_SIDE_MAX_CONSECUTIVE_LOSSES = 3   # Bir yönde 3 ardışık zararda o yönü 20 dakika dondur
SUPER_FAST_SIDE_COOLDOWN_MINUTES = 20

# Taranacak Likit Pariteler Havuzu (En Hızlı ve Likit 15 Parite - Tam Limit Uyumlu)
SUPER_FAST_COINS_UNIVERSE = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "1000PEPEUSDT",
    "WIFUSDT", "SUIUSDT", "NEARUSDT", "AVAXUSDT", "FETUSDT",
    "RENDERUSDT", "TAOUSDT", "TIAUSDT", "BNBUSDT", "XRPUSDT"
]

