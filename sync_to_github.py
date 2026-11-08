"""
Automatic GitHub Sync Engine for Antigravity & Railway CI/CD
Allows Antigravity to commit and push file changes directly to Efxyz/trade-bot
without needing git.exe or admin privileges.
"""
import os
import sys
import json
import base64
import urllib.request
import urllib.error
from pathlib import Path

REPO_OWNER = "Efxyz"
REPO_NAME = "trade-bot"
BRANCH = "main"

def get_token():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        # Check .env file
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GITHUB_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return token

def sync_file_to_github(rel_path: str, commit_msg: str = None) -> bool:
    token = get_token()
    if not token:
        print("❌ HATA: GITHUB_TOKEN bulunamadı! .env içine GITHUB_TOKEN=ghp_... ekleyin.")
        return False

    file_path = Path(__file__).parent / rel_path
    if not file_path.exists():
        print(f"❌ HATA: Dosya bulunamadı: {rel_path}")
        return False

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    content_b64 = base64.b64encode(file_bytes).decode("utf-8")
    norm_path = rel_path.replace("\\", "/")

    api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{norm_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Antigravity-AutoSync",
        "Content-Type": "application/json"
    }

    # 1. Mevcut dosyanın SHA hash'ini çek
    sha = None
    try:
        req = urllib.request.Request(api_url + f"?ref={BRANCH}", headers=headers, method="GET")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            sha = data.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            sha = None  # Dosya depoda henüz yok, yeni oluşturulacak
        else:
            print(f"⚠️ Dosya SHA sorgulama hatası ({e.code}): {e.read().decode('utf-8', errors='ignore')}")

    # 2. Dosyayı GitHub'a commit et (PUT)
    msg = commit_msg or f"Auto-sync: update {norm_path}"
    payload = {
        "message": msg,
        "content": content_b64,
        "branch": BRANCH
    }
    if sha:
        payload["sha"] = sha

    try:
        req = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="PUT"
        )
        with urllib.request.urlopen(req) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            commit_sha = res_data.get("commit", {}).get("sha", "")[:7]
            print(f"✅ Başarılı: {norm_path} GitHub'a yüklendi! Commit: {commit_sha}")
            return True
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        print(f"❌ GitHub API Hatası ({e.code}): {err_msg}")
        return False
    except Exception as ex:
        print(f"❌ Beklenmeyen hata: {ex}")
        return False

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "dashboard.py"
    msg = sys.argv[2] if len(sys.argv) > 2 else f"Update {target} with live TradingView BTC chart"
    print(f"🚀 GitHub Senkronizasyonu Başlatılıyor: {target} -> {REPO_OWNER}/{REPO_NAME} ({BRANCH})...")
    ok = sync_file_to_github(target, msg)
    if ok:
        print("⚡ Railway otomatik olarak yeni commit'i algılayıp birkaç saniye içinde canlıya alacak!")

