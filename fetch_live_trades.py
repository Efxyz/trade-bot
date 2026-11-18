"""
Canlı Railway Sunucusundan Anlık İşlem & Shadow Ablasyon Denetim İstemcisi
Kullanım: python fetch_live_trades.py [saat=36]
Gereksinim: .env dosyasında RAILWAY_URL=https://...up.railway.app (ve varsa ADMIN_PIN=...)
"""
import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path


def load_env_vars():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    load_env_vars()
    base_url = os.environ.get("RAILWAY_URL", "").strip().rstrip("/")
    pin = os.environ.get("ADMIN_PIN", "1923").strip()
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 36

    if not base_url:
        print("HATA: .env içinde RAILWAY_URL tanımlı değil! Örnek: RAILWAY_URL=https://proje.up.railway.app")
        sys.exit(1)

    url = f"{base_url}/api/audit/live?hours={hours}"
    req = urllib.request.Request(url, headers={"X-Admin-Pin": pin, "User-Agent": "TradeBot-LiveAudit"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP HATA ({e.code}): {e.read().decode('utf-8', errors='ignore')}")
        sys.exit(1)
    except Exception as e:
        print(f"BAĞLANTI HATASI: {e}")
        sys.exit(1)

    print(f"=== CANLI RAILWAY DENETİM ({data.get('server_utc')} UTC | Son {data.get('hours')} saat) ===")
    eq = data.get("equities", {})
    print(f"Kasalar -> Standart: ${eq.get('standard')} | FAST: ${eq.get('fast')} | SÜPER FAST: ${eq.get('super_fast')}")

    for bot_key in ["standard", "fast", "super_fast"]:
        rows = data.get("bots", {}).get(bot_key, [])
        print(f"\n--- {bot_key.upper()} ({len(rows) if isinstance(rows, list) else 0} kayıt) ---")
        if isinstance(rows, list):
            for r in rows:
                margin = float(r.get("allocated_margin_usdt") or 0.0)
                pnl_pct = float(r.get("simulated_pnl_pct") or 0.0)
                pnl_usd = round(margin * (pnl_pct / 100.0), 2)
                print(
                    f"#{r['id']} [{r['created_at']}] {r['symbol']} {r['direction']} {r.get('leverage')}x "
                    f"| {r['status']} | Giriş:{r.get('actual_entry_price')} Çıkış:{r.get('exit_price')} "
                    f"| PnL: {pnl_pct:+.2f}% (${pnl_usd:+.2f})"
                )

    ablation = data.get("shadow_ablation", [])
    if ablation:
        print("\n--- SHADOW ABLASYON ÖZETİ ---")
        for a in ablation:
            print(a)


if __name__ == "__main__":
    main()
