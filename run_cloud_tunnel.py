"""
Cloudflare Quick Tunnel - Telefon ve Mobil Cihazlardan Anında 7/24 Erişim
Bu script, bilgisayarınızda çalışan Trade Bot Terminalini (http://127.0.0.1:5000)
dünyanın her yerinden telefonunuzla izleyebileceğiniz güvenli, ücretsiz ve şifreli
bir HTTPS bağlantısına (örneğin: https://xyz.trycloudflare.com) dönüştürür.
"""
import os
import sys
import time
import subprocess
import urllib.request
from pathlib import Path

CLOUDFLARED_DIR = Path(__file__).resolve().parent / "data" / "tools"
CLOUDFLARED_DIR.mkdir(parents=True, exist_ok=True)
EXE_NAME = "cloudflared.exe" if os.name == "nt" else "cloudflared"
EXE_PATH = CLOUDFLARED_DIR / EXE_NAME
DOWNLOAD_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

def download_cloudflared_if_needed():
    """Cloudflared binary dosyasını indirir (Hesap veya kurulum gerektirmez)."""
    if EXE_PATH.exists():
        return True

    print("🌐 [Cloudflare Tunnel] Güvenli tünel istemcisi hazırlanıyor...")
    print(f"📥 İndiriliyor: {DOWNLOAD_URL}")
    try:
        urllib.request.urlretrieve(DOWNLOAD_URL, EXE_PATH)
        print("✅ Cloudflared başarıyla indirildi!\n")
        return True
    except Exception as e:
        print(f"⚠️ İndirme hatası: {e}")
        print("Alternatif: https://github.com/cloudflare/cloudflared/releases adresinden cloudflared-windows-amd64.exe indirip data/tools/ içine koyabilirsiniz.")
        return False

def start_tunnel(local_port=5000):
    """5000 portunu güvenli dünya linkine bağlar."""
    if not download_cloudflared_if_needed():
        return

    print("=" * 65)
    print("🚀 [BULUT BAĞLANTISI] Mobil & İnternet Tüneli Başlatılıyor...")
    print(f"Hedef Port: http://127.0.0.1:{local_port}")
    print("Aşağıda 'https://...trycloudflare.com' şeklinde bir link belirecek.")
    print("O linki telefonunuzun tarayıcısından açıp ana ekranınıza ekleyebilirsiniz!")
    print("=" * 65 + "\n")

    cmd = [str(EXE_PATH), "tunnel", "--url", f"http://127.0.0.1:{local_port}"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            if "trycloudflare.com" in line:
                for part in line.split():
                    if "trycloudflare.com" in part:
                        print("\n" + "⭐" * 60)
                        print(f"📱 TELEFONUNUZDAN GİREBİLECEĞİNİZ CANLI LİNK:")
                        print(f"👉 {part.strip()}")
                        print("⭐" * 60 + "\n")
    except KeyboardInterrupt:
        print("\n🛑 Tünel kapatıldı.")

if __name__ == "__main__":
    start_tunnel(5000)

