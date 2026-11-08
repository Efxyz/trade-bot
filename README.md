# 🚀 Binance Futures (USDT.P) 10x & 20x Multi-Agent Trade Bot & Canlı Dashboard

Bu sistem, **Binance Vadeli İşlemler (USDT-M Perpetual / USDT.P)** piyasasında çalışan çoklu yapay zeka ajanlı bir analiz, risk yönetim, sanal takip ve **canlı masaüstü kontrol paneli (Dashboard)** sistemidir.

---

## 🖥️ Canlı Web Dashboard (Kontrol Paneli)

Bilgisayarınızda anlık çalışan TradingView / Bloomberg Terminali benzeri koyu temalı web uygulaması:
* **Canlı Olası PnL (Unrealized PnL):** Açık sanal pozisyonların anlık fiyatlarla kar/zararını **her 2 saniyede bir canlı günceller**.
* **BTC Çöküş Kalkanı Barı:** Anlık Bitcoin fiyatını ve piyasa koruma durumunu canlı gösterir.
* **Geçmiş İşlemler & Gerçekleşen PnL:** Kapanan tüm işlemlerin net getirilerini listeler.
* **PNG Grafik Görüntüleyici:** Tablodaki "👁️ Grafik" butonuna basarak üretilen analiz grafiklerini tam boy inceler.
* **Hızlı Tarama Butonu:** Panelden tek tıkla anında piyasa taraması başlatabilirsiniz.

**Dashboard'u Açmak İçin:**
- Klasördeki [`open_dashboard.bat`](file:///c:/Users/isiks/OneDrive/Belgeler/antygravity/trade_bot/open_dashboard.bat) dosyasına çift tıklayın veya tarayıcınızda `http://127.0.0.1:5000` adresine gidin.

---

## ⚡ Temel Özellikler

1. **⚡ Dinamik Kaldıraç (10x vs 20x Sniper):**
   - Dar stoplu (<= %1.2 SL) ve yüksek kırılımlarda **20x Sniper (Grade A+)** önerir (Hedef: +%50 - +%100 kar).
   - Standart trendlerde güvenli **10x Kaldıraç** uygular.
2. **🛡️ BTC Market Shield (Çöküş Kalkanı):**
   - BTC ani düşüşe geçtiğinde tüm altcoin LONG sinyallerini otomatik durdurur.
3. **🔒 Break-Even (Sıfır Risk):**
   - TP1'e ulaşıldığında Stop-Loss seviyesini otomatik giriş fiyatına taşır.
4. **📱 Telegram İnteraktif Komutları:**
   - `@Effe_trade_bot` üzerinden `/tara`, `/durum`, `/aktif`, `/btc` komutları ile uzaktan yönetim.
5. **🎯 "Girseydim Ne Olurdu?" Simülatörü:**
   - 10x/20x kaldıraçlı gerçekleşen net PnL oranını hesaplayıp sonuç grafiği sunar.

---

## 🚀 Başlatma Komutları

* **7/24 Botu ve Dashboard'u Başlat:**
  Klasördeki [`start_scanner.bat`](file:///c:/Users/isiks/OneDrive/Belgeler/antygravity/trade_bot/start_scanner.bat) dosyasına çift tıklayın.
* **Sadece Dashboard'u Aç:**
  Klasördeki [`open_dashboard.bat`](file:///c:/Users/isiks/OneDrive/Belgeler/antygravity/trade_bot/open_dashboard.bat) dosyasına çift tıklayın.
