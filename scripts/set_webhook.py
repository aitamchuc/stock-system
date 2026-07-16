"""Đăng ký / gỡ / kiểm tra Telegram webhook.

    python scripts/set_webhook.py --url https://stock-dashboard.onrender.com
    python scripts/set_webhook.py --status        # xem webhook hiện tại
    python scripts/set_webhook.py --delete        # gỡ (quay lại dùng long-polling)

Tự sinh TELEGRAM_WEBHOOK_SECRET nếu chưa có — nhớ đặt cùng giá trị đó vào Render/.env,
nếu không endpoint sẽ từ chối mọi tin (403).
"""
import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402

from app.config import settings  # noqa: E402

API = "https://api.telegram.org/bot{token}/{method}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="URL gốc của web service (vd https://xxx.onrender.com)")
    ap.add_argument("--secret", default=settings.telegram_webhook_secret)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--delete", action="store_true")
    args = ap.parse_args()

    token = settings.telegram_token
    if not token:
        print("❌ Thiếu TELEGRAM_TOKEN trong .env")
        return

    if args.status:
        r = httpx.get(API.format(token=token, method="getWebhookInfo"), timeout=15).json()
        info = r.get("result", {})
        print("URL hiện tại:", info.get("url") or "(chưa đặt — bot đang dùng long-polling)")
        print("Tin chờ xử lý:", info.get("pending_update_count"))
        if info.get("last_error_message"):
            print("⚠️ Lỗi gần nhất:", info["last_error_message"])
        return

    if args.delete:
        r = httpx.get(API.format(token=token, method="deleteWebhook"), timeout=15).json()
        print("Đã gỡ webhook." if r.get("ok") else f"Lỗi: {r}")
        return

    if not args.url:
        print("❌ Cần --url (vd --url https://stock-dashboard.onrender.com)")
        return

    secret = args.secret or secrets.token_urlsafe(32)
    hook = args.url.rstrip("/") + "/telegram/webhook"
    r = httpx.post(API.format(token=token, method="setWebhook"), json={
        "url": hook,
        "secret_token": secret,
        "allowed_updates": ["message"],
        "drop_pending_updates": True,
    }, timeout=20).json()

    if not r.get("ok"):
        print(f"❌ Lỗi: {r}")
        return
    print(f"✅ Đã đăng ký webhook: {hook}")
    if not args.secret:
        print("\n🔑 ĐÃ SINH SECRET MỚI — đặt biến này vào Render (và .env nếu chạy local):")
        print(f"   TELEGRAM_WEBHOOK_SECRET={secret}")
        print("   (Không đặt đúng giá trị này thì endpoint sẽ từ chối mọi tin nhắn — lỗi 403.)")


if __name__ == "__main__":
    main()
