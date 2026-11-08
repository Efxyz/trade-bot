# Binance Vadeli İşlemler Çoklu-Ajan Trade Bot Dockerfile
FROM python:3.11-slim

# Sistem kütüphaneleri (Matplotlib ve ağ soketleri için)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    libfreetype6-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Bağımlılıkları yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Proje dosyalarını kopyala
COPY . .

# Kalıcı veritabanı ve grafik klasörleri
RUN mkdir -p data/charts

EXPOSE 5000

ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

# Bot Terminali ve Arka Plan Ajanlarını Başlat
CMD ["python", "dashboard.py"]

