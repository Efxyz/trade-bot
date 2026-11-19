# 🤖 Binance Futures (USDT.P) Otonom Multi-Agent Quant Trade Bot & Canlı Terminal

**Binance Vadeli İşlemler (`USDT-M Perpetual / USDT.P`)** piyasası için geliştirilmiş; Smart Money Concepts (SMC), piyasa rejim tespiti, 10.000 yollu Monte Carlo stokastik simülasyonu, çoklu ajan münazara konseyi, ağırlıklı 2 kademeli DCA ve **Hibrit ATR Merdiven Kâr Kilidi** özelliklerini tek çatı altında birleştiren **6 katmanlı otonom algoritmik analiz, simülasyon ve canlı takip terminalidir**.

> [!NOTE]
> Sistem hem yerel masaüstü kontrol paneli olarak hem de **Railway** üzerinde 7/24 bulut terminali olarak çalışacak şekilde mimarilendirilmiştir. Sinyaller, kurumsal risk yönetimi ve gerçekleşen/olasılıksal net komisyon (`%0.05 Taker` giriş + `%0.05 Taker` çıkış = `%0.10` roundtrip) hesaplarıyla sanal olarak canlı piyasa fiyatlarında uçtan uca doğrulanır.

---

## 🎯 Ne İşe Yarar ve Neleri Çözer?

Klasik tek indikatörlü botların yaşadığı üç temel sorunu (testere piyasada erken stop avı, komisyon erimesi ve kazanan işlemin kârsız kapanması) çözmek üzere kurgulanmıştır:

1. **Tek Tip Parametre Yerine Piyasa Rejimi Adaptasyonu:** Yatay/testere (`CHOPPY`) ve güçlü akım (`TRENDING`) piyasalarını **Choppiness Index (CI)** ve **Kaufman Efficiency Ratio (KER)** ile otomatik ayırır; hedef R:R oranını, merdiven genişliğini ve mean-reversion stratejilerini rejime göre uyarlar.
2. **Sıfır Repainting & Lookahead Koruması:** Sinyal skorlaması yalnızca **kapanmış mumlar (`candles[:-1]`)** üzerinden hesaplanır; canlı WebSocket fiyatı sadece giriş anı doğrulaması ve milisaniyelik kâr/zarar takibi için kullanılır.
3. **Kazanan İşlemi Zararla Kapatmama Disiplini (Hibrit ATR Merdiven):** İşlem lehimize hızlıca döndüğünde **Basamak 1** sermaye kalkanı devreye girerek pozisyonun `%35`'ini nakit kâr olarak cebe alır ve kalan kısma nefes paylı BE+ kalkanı kurar; devam eden güçlü hareketlerde **Basamak 2–4** ve **Dinamik Kanal** volatiliteye (ATR) göre esneyerek büyük dalgaları taşır.

---

## 🧠 6 Katmanlı Multi-Agent Karar ve Takip Mimarisi

```text
[Binance Futures REST + Milisaniyelik WebSocket Akışı]
                         │
                         ▼
  1. Tarama & Evren Seçimi (agents/scanner_agent.py)
     └─ Yüksek 24s hacimli ($12M+) likit USDT.P pariteleri + zehirli parite karantinası
                         │
                         ▼
  2. Çoklu-Vade SMC & Rejim Motoru (agents/ta_agent.py)
     ├─ 15m (Kısa) • 30m (Orta) • 1h (Uzun) eşzamanlı analiz
     ├─ CI + KER Rejim Tespiti (TRENDING / CHOPPY / TRANSITION)
     ├─ Kapalı Mum SMC: FVG, Order Block, Liquidity Sweep, SFP, Fib Golden Pocket
     └─ Kanal Doygunluk & VWAP Aşırı Uzama Kalkanı (Tepe Alım / Dip Satış Engeli)
                         │
                         ▼
  3. Kurumsal Risk & Mikroyapı Kalkanı (agents/risk_agent.py)
     ├─ 10x Standart / 20x Grade A+ Sniper kaldıraç seçimi
     ├─ Order Book Imbalance (Tahta Baskısı), Spread & Funding Rate kontrolü
     ├─ BTC Çöküş Kalkanı (BTC Market Shield) & Sembol/Yön bazlı limitler
     └─ Maksimum 8 eşzamanlı işlem • Tek yönde maks. 4 pozisyon • $200 baz marjin tavanı
                         │
                         ▼
  4. 10.000 Monte Carlo & Time Machine (agents/quant_simulation_agent.py)
     ├─ Kapanmış mumların ampirik log-getirileriyle 10.000 GBM + Jump-Diffusion yolu
     └─ Tarihsel kırılım rezonans testi (Empirical Replay)
                         │
                         ▼
  5. Münazara Konseyi & Haber Analizi (agents/ai_analyst_agent.py & news_agent.py)
     └─ Boğa, Ayı, Kuant Hakem ve Baş Yargıç oylaması + makro/haber duyarlılık teyidi
                         │
                         ▼
  6. Canlı WebSocket Takip, DCA & Hibrit ATR Merdiven (agents/tracker_agent.py)
     ├─ Bayat tick korumalı WebSocket fiyat takibi (max_age_sec = 5.0 sn)
     ├─ 2. Kademe Ağırlıklı DCA: (E1 + 0.5·E2) / 1.5 + R:R (>= 1.80) SL/TP1 kalibrasyonu
     ├─ Hibrit ATR Step-Ladder (%35 kısmi realizasyon + ATR bazlı Basamak 2-4 + Runner TP2)
     └─ EMA20 mum kapanış teyitli Akıllı Yapısal Erken Zarar Kes
```

---

## ⚙️ Öne Çıkan Çekirdek Özellikler

### 1. 📊 Çoklu-Vade SMC & Çift Sayımdan Arındırılmış Skorlama ([`agents/ta_agent.py`](agents/ta_agent.py))
- Aynı pariteyi eşzamanlı olarak **15 dakikalık (Vur-Kaç)**, **30 dakikalık (Dengeli Salınım)** ve **1 saatlik (Makro Trend)** vadelerde inceler; `ADX` ve kurulum kalitesine göre en verimli vadeyi seçer.
- **Korelasyon / Çoklu Sayım Temizliği:** Birbirini tekrarlayan indikatörlerin skoru suni şişirmesini önlemek için EMA+SuperTrend üst sınırı, ayrı tutulan LR-Channel yapısı ve birbirini dışlayan RSI/Divergence puanlaması kullanır.
- **Kanal Doygunluk Kalkanı:** Yükselen/düşen veya yatay kanalların en uç bölgelerinde kırılım gelmeden ters veya yorgun yönde işleme girilmesini otomatik engeller.

### 2. 🪜 Ağırlıklı DCA & Hibrit ATR Merdiven Kâr Kilidi ([`agents/tracker_agent.py`](agents/tracker_agent.py))
- **Doğru Ağırlıklı DCA Muhasebesi:** 2. kademe limit emir (%50 ek marjin) dolduğunda ortalama giriş fiyatı hacim ağırlıklı olarak `((E1 × 1.0) + (E2 × 0.5)) / 1.5` formülüyle güncellenir, marjin tavanı (`MAX_ALLOCATED_MARGIN_PER_TRADE × 1.5`) aşılırsa ek alım durdurulur ve `SL` / `TP1` mesafeleri asgari `1:1.80` R:R oranını koruyacak şekilde yeniden kalibre edilir.
- **Hibrit ATR Merdiven:**
  - **Basamak 1 (Hızlı Sermaye Kalkanı):** Küçük kârlarda gecikmeden tetiklenir; marjinin `%35`'ini nakit kâr olarak cebe alır ve kalan kısma komisyon korumalı nefes payı stopu yerleştirir.
  - **Basamak 2–4 & Dinamik Kanal:** Pozisyonun bulunduğu zaman diliminin kapanmış mum **ATR(14)** volatilitesine göre otomatik genişleyip daralır (`ATR_LADDER_MULT`).
- **Tam Parçalı Muhasebe (`reconcile_partial_pnl`):** Basamak 1 (`%35`) ve TP1 (`%50`) kısmi realize kârlarını başlangıç toplam marjini üzerinden birleştirerek nihai net yüzdesel ve dolar bazlı kârı sıfır sapmayla hesaplar.

### 3. 🛡️ Sermaye Koruma & Otonom Kalibrasyon Kalkanları ([`core/database.py`](core/database.py), [`core/self_tuning_engine.py`](core/self_tuning_engine.py))
- **Sembol + Yön Bazlı Soğuma Molası:** Bir paritede zararlı kapanış olduğunda tüm sistemi dondurmak yerine yalnızca o sembolün o yönünü **15 dakika** karantinaya alır.
- **Side-Specific Stoploss Guard:** Aynı yönde ardışık 2 stop oluşursa o yönü **45 dakika** kilitlerken karşı yön fırsatlarını açık tutar.
- **Oransal Günlük Zirve Kâr Kilidi:** Gün içi net gerçekleşen kâr `$25+` üzerine çıktığında zirvenin `%55`'ini taban kilidi olarak korur.
- **Otonom Öz-Kalibrasyon (`Self-Tuning`):** Kapalı işlem istatistiklerine (Win Rate, Profit Factor, Expectancy) bakarak puan barajlarını dinamik ayarlar ve geçmiş performansı sürekli izler.

### 4. 🖥️ Canlı Web Terminali, 3D Ajan Ofisi & Telegram Yönetimi
- **Web Dashboard ([`dashboard.py`](dashboard.py)):** Dark-mode profesyonel arayüz; canlı Unrealized/Realized PnL tablosu, BTC Çöküş Kalkanı göstergesi, **3D Sims Ajan Ofisi & Münazara Odası**, tek tıkla manuel tarama ve kurumsal PNG grafik inceleme penceresi ([`agents/chart_agent.py`](agents/chart_agent.py)).
- **Telegram İnteraktif Bot ([`agents/telegram_command_agent.py`](agents/telegram_command_agent.py) & [`agents/notifier_agent.py`](agents/notifier_agent.py)):** `/tara`, `/durum`, `/aktif`, `/btc` komutları ile uzaktan kontrol, anlık giriş/çıkış bildirimleri ve her gece **23:59**'da günlük performans özet raporu.

---

## 📂 Proje Klasör Yapısı

```text
trade_bot/
├── main.py                          # Ana orkestratör döngüsü & dashboard/telegram entegrasyonu
├── config.py                        # Strateji, risk, ATR merdiven, rejim ve koruma sabitleri
├── dashboard.py                     # Flask tabanlı canlı Web Terminali & 3D Ajan Ofisi arayüzü
├── templates/office.html            # Web terminali arayüz şablonu
├── backtest/                        # Canlı strateji koduyla çalışan olay güdümlü backtest motoru
├── tests/                           # pytest birim + entegrasyon testleri (izole geçici DB)
├── requirements.txt                 # Python bağımlılıkları
├── Dockerfile / Procfile            # Railway & Docker konteyner dağıtım yapılandırmaları
├── start_scanner.bat                # Yerel 7/24 bot + dashboard başlatıcı
├── open_dashboard.bat               # Sadece yerel kontrol paneli başlatıcı
├── core/
│   ├── binance_client.py            # Binance Futures REST API istemcisi (60s kline/book önbellekli)
│   ├── binance_streamer.py          # Milisaniyelik WebSocket fiyat akışı & bayat veri koruması
│   ├── database.py                  # SQLite işlem defteri, kısmi kâr mutabakatı & günlük kilitler
│   ├── database_legacy.py           # Kapatılmış FAST/SÜPER FAST motorlarının DB katmanı (geçmiş istatistikler)
│   ├── timeutil.py                  # Tek zaman kaynağı: tüm DB damgaları UTC; backtest için simüle saat
│   ├── accounting.py                # Fonlama (funding) maliyeti ve saf muhasebe yardımcıları
│   ├── advanced_indicators.py       # FVG, OB, Sweep, SFP, TTM Squeeze, VWAP, LR-Channel motoru
│   ├── quant_knowledge_base.py      # Kurumsal quant bilgi tabanı yardımcıları
│   ├── self_tuning_engine.py        # Win Rate / Expectancy bazlı otonom baraj kalibrasyonu
│   └── reflection.py                # İşlem sonrası yansıma & ders çıkarma motoru
└── agents/
    ├── scanner_agent.py             # Likit USDT.P parite tarayıcısı
    ├── ta_agent.py                  # Çoklu-vade (15m/30m/1h) SMC + Rejim analiz ajanı
    ├── risk_agent.py                # Kasa, kaldıraç, OBI tahta baskısı & portföy risk ajanı
    ├── quant_simulation_agent.py    # 10.000 Monte Carlo GBM & Empirical Replay ajanı
    ├── ai_analyst_agent.py          # Adversarial Boğa/Ayı/Hakem münazara komitesi
    ├── news_agent.py                # Kripto/makro haber duyarlılık ajanı
    ├── tracker_agent.py             # Canlı pozisyon takip, DCA & Hibrit ATR Merdiven motoru
    ├── chart_agent.py               # Kurumsal analiz PNG grafik üreticisi
    ├── notifier_agent.py            # Telegram sinyal, kapatma & 23:59 gün sonu rapor ajanı
    └── telegram_command_agent.py    # İnteraktif Telegram komut dinleyicisi
```

*(Not: Eski deneysel `fast_*` / `super_fast_*` motorları kaldırıldı; yalnızca geçmiş istatistikleri için DB katmanı `core/database_legacy.py` içinde korunuyor.)*

---

## 🚀 Kurulum ve Çalıştırma

### 1. Ortam Değişkenleri (`.env` / Railway Variables)
Proje kökünde [`.env.example`](.env.example) dosyasını baz alarak `.env` oluşturun:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
GEMINI_API_KEY=optional_ai_key
CRYPTOPANIC_API_KEY=optional_api_key
ADMIN_PIN=en-az-6-karakterlik-gizli-pin
SELF_TUNING_ENABLED=false
```
- **`ADMIN_PIN` zorunludur:** Varsayılan PIN yoktur. Tanımsız veya zayıfsa (6 karakterden kısa, `6004` vb.) pozisyon kapatma, tarama, AI ve kalibrasyon butonları devre dışı kalır. IP başına 5 hatalı denemede 15 dk kilit uygulanır.
- **`SELF_TUNING_ENABLED`:** Varsayılan `false`. Küçük örneklemle otomatik parametre değiştirme aşırı uyuma yol açtığı için kapalıdır; açılsa bile en az 150 kapalı işlem gerekir.

### 2. Yerel Çalıştırma (Windows)
- **Bot + Canlı Dashboard'u Birlikte Başlatmak İçin:** `start_scanner.bat` dosyasına çift tıklayın (veya `python main.py` çalıştırın).
- **Sadece Web Dashboard'u Açmak İçin:** `open_dashboard.bat` dosyasına çift tıklayın ve tarayıcınızdan `http://127.0.0.1:5000` adresine gidin.

### 3. Manuel Python Kurulumu
```bash
pip install -r requirements.txt
python main.py
```

### 4. Testler
```bash
pip install pytest
python -m pytest -q
```
Testler geçici bir veri klasörü (`TRADEBOT_DATA_DIR`) kullanır; gerçek veritabanına dokunmaz.

---

## 🔬 Backtest (Strateji Doğrulama)
Backtest motoru canlı botun **kendi** sinyal, risk ve takip kodunu simüle saatle çalıştırır. Çıkışlar 1 dakikalık mumların tick'leriyle (fitil temasları dahil, muhafazakâr sıralama) gerçek `CounterfactualTrackerAgent` tarafından yönetilir; komisyon, kayma ve fonlama dahildir.
```bash
python -m backtest.run --days 30                              # mevcut strateji
python -m backtest.run --days 30 --variants baseline,no_mc,wide_ladder
python -m backtest.run --days 45 --symbols BTCUSDT,ETHUSDT,SOLUSDT
```
Varyantlar `backtest/run.py` içindeki `VARIANTS` sözlüğünde tanımlıdır; her biri bir filtreyi veya çıkış kuralını değiştirerek katkısını ölçer. Haber, OI/basis/emir defteri ve Gemini AI filtreleri geçmiş veriyle yeniden üretilemediği için backtest'te atlanır.

**Kural:** Strateji parametresi değiştirmeden önce backtest'te en az birkaç yüz işlemlik örneklemle ve farklı dönemlerde tutarlı iyileşme görülmelidir.

## ⚠️ Yasal Uyarı
Bu yazılım araştırma, simülasyon ve algoritmik strateji doğrulama amacıyla geliştirilmiştir. Kripto para vadeli işlemleri yüksek kaldıraç nedeniyle yüksek risk içerir; yatırım tavsiyesi değildir.
