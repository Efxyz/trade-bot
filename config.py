"""
Trading Bot Configuration - Binance Futures (USDT.P)
VUR-KAÇ MİKRO SCALPING MODU (Hızlı Küçük Karlar Alıp Çıkma)
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Windows'ta çıktı bir boruya/dosyaya yönlendirildiğinde (cp1254) emoji içeren print'ler çökmesin
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
# TRADEBOT_DATA_DIR: testler ve izole çalıştırmalar için veri klasörünü değiştirir
DATA_DIR = Path(os.getenv("TRADEBOT_DATA_DIR") or (BASE_DIR / "data"))
CHARTS_DIR = DATA_DIR / "charts"
DB_PATH = DATA_DIR / "trading_bot.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CHARTS_DIR.mkdir(exist_ok=True)

# Binance Futures Settings
BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"
MIN_24H_VOLUME_USDT = 12_000_000  # Likit, anlık hacimli pariteler

# ========================================================
# FON YÖNETİMİ & KASA KALKANI (CAPITAL PROTECTION SHIELD)
# ========================================================
PORTFOLIO_EQUITY_USDT = 1000.0         # Başlangıç Fon Kasası ($1000 USDT)
MAX_CONCURRENT_TRADES = 8              # 3-Vadeli Tek Panel: Kısa (15m), Orta (30m) ve Uzun (1h) için dengeli slot kapasitesi
MAX_POSITIONS_PER_DIRECTION = 4        # Tek Yöne Yığılma Kalkanı (Maksimum 4 LONG veya 4 SHORT)
RISK_PER_TRADE_PCT = 1.5               # İşlem başına riske edilen maksimum komisyon dahil kasa payı (%1.5 = $15 risk)
MAX_ALLOCATED_MARGIN_PER_TRADE = 200.0 # Bir işleme ayrılabilecek taban maksimum marjin (%20 kuralı)
POST_LOSS_COOLDOWN_MINUTES = 15        # Zararlı kapanış sonrası 15 dk karantina molası (İntikam işlemine son!)
ENABLE_LOSING_DCA = False              # Zarardaki işleme +50% ek marjin eklemeyi kapat (Adverse Selection koruması)

# ========================================================
# ÇOKLU-MOTOR YÖNETİMİ & 3-VADELİ TEK TERMİNAL MODU
# ========================================================
ENABLE_FAST_ENGINE = False             # FAST (1m) Motoru Geçici Olarak Durduruldu (Kodlar Korunur)
ENABLE_SUPER_FAST_ENGINE = False       # SÜPER FAST (1s) Motoru Geçici Olarak Durduruldu (Kodlar Korunur)

# 3-Zaman Dilimli Çoklu-Vade (Triple-Horizon) Yapılandırması
TIMEFRAME_SHORT = "15m"                # ⚡ Kısa Vade: 15 Dakikalık Mikro Dalgalar & Hızlı TP1
TIMEFRAME_MEDIUM = "30m"               # 🎯 Orta Vade: 30 Dakikalık Likidite Süpürmeleri & Salınımlar
TIMEFRAME_LONG = "1h"                  # 👑 Uzun Vade: 1 Saatlik Kurumsal Makro Trend & Runner TP2

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
    # Basamak 1: %35 Kısmi Kâr Cebe + Nefes Alan BE+ Kalkanı (+%0.50 Ham / -%0.10 Nefes Payı Stop)
    # Fiyat +%0.50 kâra ulaştığında pozisyonun %35'i nakit kâr alınır, kalan %65'in stopu girişin -%0.10 gerisine çekilir (gerçek net kâr >= +0.10% garantili!)
    {"step": 1, "trigger_raw_pct": 0.50, "lock_raw_pct": -0.10, "name": "🛡️ Basamak 1 (%35 Kâr Cebe + Nefes Payı BE+)"},

    # Basamak 2: Komisyon Korumalı Sağlıklı Kâr Kilidi (%0.35 Kilit)
    # Fiyat +%0.75 kâra ulaştığında stop'u +%0.35'e çek (erken boğulmayı önler, güçlü net kâr kilitler)
    {"step": 2, "trigger_raw_pct": 0.75, "lock_raw_pct": 0.35, "name": "🪜 Basamak 2 (+%0.35 Kâr Kilidi)"},

    # Basamak 3: Çeyrek Kâr Kilidi
    # Fiyat +%1.15 kâra ulaştığında stop'u +%0.75 kâra çek
    {"step": 3, "trigger_raw_pct": 1.15, "lock_raw_pct": 0.75, "name": "🪜 Basamak 3 (+%0.75 Kâr Kilidi)"},

    # Basamak 4: Hedefe Yakın Koruma
    # Fiyat +%1.60 kâra ulaştığında stop'u +%1.25 kâra çek
    {"step": 4, "trigger_raw_pct": 1.60, "lock_raw_pct": 1.25, "name": "🪜 Basamak 4 (+%1.25 Kâr Kilidi)"},
]

# Dinamik Kanal (Runner / Trailing Channel): Zirvenin %0.30 gerisinden iz sürme mesafesi
LADDER_DYNAMIC_CHANNEL_PCT = 0.30

# Zehirli Parite Kara Listesi (Toxic Asset Quarantine)
# Geçmiş 30 ve 90 günlük testlerde kasayı en çok eriten, kronik stop-hunt ve testere pariteleri
EXCLUDED_SYMBOLS_BLACKLIST = ["LINKUSDT", "ARBUSDT", "INJUSDT", "APTUSDT"]

# Dinamik Kaldıraç (Yüksek 20x kaldıracın komisyon ve SL aşındırması nedeniyle tüm işlemler 10x'e sabitlendi)
LEVERAGE_STANDARD = 10  # 10x ile %1 fiyat hareketi = +%10 marjin karı
LEVERAGE_HIGH = 10      # 20x devre dışı -> Tüm işlemler 10x (%67.5 canlı WR)

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
MAX_VWAP_DISTANCE_PCT = 3.20           # 15m VWAP'tan %3.20'den fazla uzaktaki fiyatlarda aşırı uzama filtresi (Mean-Reversion Kalkanı)
SMC_PREMIUM_DISCOUNT_FILTER = True     # SMC Premium/Discount Kalkanı (Dipten Short / Tepeden Long Engeli)

# Freqtrade Side-Specific Stoploss Guard (Yön Bazlı Seri Zarar Kalkanı)
# Bir yönde (özellikle SHORT) peş peşe zarar geldiğinde o yönü dondurur, diğer yön (LONG) kesintisiz devam eder
SIDE_STOPLOSS_GUARD_ENABLED = True
SIDE_STOPLOSS_MAX_CONSECUTIVE_LOSSES = 2   # Peş peşe 2 zarar eden yön kilitlenir
SIDE_STOPLOSS_COOLDOWN_MINUTES = 45        # Kilitlenen yön 45 dakika boyunca yeni işleme kapatılır (Eski: 120 dk)

# ========================================================
# VADEYE / ZAMAN DİLİMİNE ÖZEL GÜNLÜK İŞLEM KOTALARI
# (Timeline-Specific Independent Daily Quotas & House-Money Bonus)
# ========================================================
# Her zaman diliminin bağımsız günlük kotası vardır.
# Bir vadenin (örneğin 15m) kotası dolduğunda diğer vadeler (30m ve 1h) fırsat aramaya kesintisiz devam eder!
DAILY_MAX_TRADES_15M = 6              # ⚡ 15m (Kısa Vade): Günde azami 6 işlem (Keskin Nişancı Kotası)
DAILY_MAX_TRADES_30M = 5              # 🎯 30m (Orta Vade): Günde azami 5 işlem
DAILY_MAX_TRADES_1H = 4               # 👑 1h (Uzun Vade): Günde azami 4 işlem

DAILY_BASE_MAX_TRADES = 15            # Toplam tavan referansı (6 + 5 + 4)
DAILY_MAX_NEW_TRADES = 15             # Geriye dönük uyumluluk aliası
PROFIT_STEP_FOR_BONUS_TRADES = 15.0   # Her +$15 net kârda her vadeye +1 ekstra kota slotu eklenir
BONUS_TRADES_PER_STEP = 1             # Her kâr adımında her vade kotasına ilave hak
ENABLE_CIRCUIT_BREAKER = True         # Güvenlik Kalkanı: Günlük -$35 kayıpta taramayı 24s dondur
DAILY_MAX_DRAWDOWN_USDT = 35.0       # Günlük Acil Durum Sigortası (Circuit Breaker): -$35 kayıpta taramayı dondur
DAILY_TRAILING_PROFIT_LOCK_ENABLED = True # Günlük Zirve Kâr Kilidi (Kazanılan kârı asla geri vermeme kalkanı)

# SMC & Confluence Kalite Eşiği (Yüksek Seçicilik Kalibrasyonu - Kota Korumalı)
MIN_CONFLUENCE_SCORE = 68            # Yalnızca A+ 68+ puanlı kurulumlar kabul edilir
MIN_CONFLUENCE_SCORE_SHORT = 70      # Short Kalite Eşiği: 70+

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

# Tarama Aralığı (3-Vadeli Hızlı ve Dengeli Tarama)
SCAN_INTERVAL_SECONDS = 90  # FAST & SÜPER FAST kapalı olduğu için 90 saniyede bir dinamik tarama

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

# ========================================================
# DEEPSEEK-R1 QUANT YÜKSELTMESİ: REPAINT, ATR MERDİVEN & REJİM
# ========================================================
# Kapanmamış mum (candles[-1]) kaynaklı lookahead/repainting hatalarını önle
USE_CLOSED_CANDLES_FOR_SCORING = True

# Volatiliteye (ATR) Normalize Dinamik Merdiven Kâr Sistemi
ATR_LADDER_ENABLED = True
ATR_PERIOD = 14
ATR_LADDER_MULT = {
    1: {"trigger": 1.15, "lock_distance": 0.45},
    2: {"trigger": 1.75, "lock_distance": 0.55},
    3: {"trigger": 2.40, "lock_distance": 0.70},
    4: {"trigger": 3.10, "lock_distance": 0.90},
}

# Piyasa Rejim Tespiti (Choppiness Index & Kaufman Efficiency Ratio)
REGIME_CHOP_PERIOD = 14
REGIME_KER_PERIOD = 20
REGIME_CI_TREND = 38.2
REGIME_CI_CHOP = 61.8
REGIME_KER_TREND = 0.50
REGIME_KER_CHOP = 0.25

REGIME_POLICY = {
    "TRENDING":   {"min_rr": 1.65, "ladder_mult": 1.35, "hold_mult": 1.4, "mean_reversion": False},
    "CHOPPY":     {"min_rr": 2.10, "ladder_mult": 0.75, "hold_mult": 0.65, "mean_reversion": True},
    "TRANSITION": {"min_rr": 1.80, "ladder_mult": 1.00, "hold_mult": 1.0, "mean_reversion": True},
}

# Günlük Oransal Zirve Kâr Kilidi
DAILY_TRAILING_PROFIT_RATIO = 0.55
DAILY_TRAILING_PROFIT_MIN_USDT = 25.0

# Gerçek Emir Modu İçin Post-Only (GTX) Maker Komisyon Yapılandırması
ENABLE_MAKER_POST_ONLY = False         # Sanal simülasyonda muhafazakâr Taker (%0.10) korunur; canlı emirde GTX (%0.04) açılır
MAKER_FEE_PCT = 0.02                   # %0.02 Binance Futures Maker komisyonu
MAKER_ROUNDTRIP_FEE_PCT = 0.04         # Giriş + TP Maker toplam %0.04 komisyon

# ========================================================
# STRATEJİ ANAHTARLARI (Backtest ile doğrulanarak belirlenir: python -m backtest.run --variants ...)
# ========================================================
ENABLE_PAIR_TRADING = False              # Stat-arb pair: bacak başına ayrı stop hedge'i bozuyor; canlıda net ~0 (yalnızca komisyon)
ENABLE_MC_GATE = True                    # Monte Carlo veto kapısı
ENABLE_QUALITY_GATE = True               # Turnuva kalite barajı (MC + komite + R:R + not)
QUALITY_GATE_THRESHOLD = 68.0
LADDER_STEP1_PARTIAL_PCT = 0.35         # Basamak 1'de realize edilen pozisyon oranı (0 = kısmi satış yok)
ENABLE_MOMENTUM_STAGNATION_EXIT = True   # İlk 2 mumda yön teyidi yoksa küçük zararla çıkış
SCORING_DEDUP = False                    # True: iki yöne birden puan veren faktörler (hacim, RSI 48-52) nötrlenir
USE_REGIME_MIN_RR = False                # True: rejim politikasındaki min R:R (TRENDING 1.65) gerçekten uygulanır

# Strateji sürüm etiketi: her yeni işleme yazılır; istatistikler sürüm bazında ayrıştırılabilir
STRATEGY_VERSION = "v2.0-overhaul"

# Pozisyon takip döngüsü (ana taramadan bağımsız thread): WebSocket fiyatlarıyla saniyelik SL/TP kontrolü
TRACKER_INTERVAL_SECONDS = 2.0

# ========================================================
# ÖZ-KALİBRASYON (SELF-TUNING) KİLİDİ
# ========================================================
# Küçük örneklemlerle (5-15 işlem) parametre değiştirmek aşırı uyuma (overfitting) yol açar.
# False iken: adaptive_hyperparams.json yok sayılır, yalnızca bu dosyadaki sabitler kullanılır,
# otonom döngü yalnızca rapor üretir (diske yazmaz).
SELF_TUNING_ENABLED = os.getenv("SELF_TUNING_ENABLED", "false").lower() == "true"
SELF_TUNING_MIN_TRADES = 150            # Açıksa bile en az bu kadar kapalı işlem olmadan parametre değiştirilmez
