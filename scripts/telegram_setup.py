"""Trợ giúp cấu hình Telegram: xác thực token, tìm chat_id, gửi tin test.

Cách dùng:
  1. Chat với @BotFather trên Telegram -> /newbot -> lấy TOKEN.
  2. Mở bot vừa tạo, bấm Start và gửi 1 tin bất kỳ (vd "hello").
  3. Chạy:
        python scripts/telegram_setup.py --token 123456:ABC...
     Script sẽ in chat_id và gửi 1 tin test. Sau đó dán vào .env:
        TELEGRAM_TOKEN=...
        TELEGRAM_CHAT_ID=...

  (Nếu đã đặt token trong .env thì chạy không cần --token.)
"""
import argparse
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


def call(token: str, method: str, **params):
    r = httpx.get(API.format(token=token, method=method), params=params, timeout=15)
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=settings.telegram_token,
                    help="Bot token (mặc định lấy từ .env)")
    ap.add_argument("--chat-id", default="", help="Gửi test tới chat_id cụ thể (tùy chọn)")
    args = ap.parse_args()

    token = args.token.strip()
    if not token:
        print("❌ Chưa có token. Truyền --token hoặc đặt TELEGRAM_TOKEN trong .env.")
        return

    # 1) Xác thực token
    me = call(token, "getMe")
    if not me.get("ok"):
        print(f"❌ Token không hợp lệ: {me}")
        return
    print(f"✅ Bot: @{me['result']['username']} ({me['result']['first_name']})")

    # 2) Tìm chat_id từ tin nhắn gần nhất
    chat_id = args.chat_id.strip()
    if not chat_id:
        updates = call(token, "getUpdates")
        chats = {}
        for u in updates.get("result", []):
            msg = u.get("message") or u.get("channel_post") or {}
            chat = msg.get("chat") or {}
            if chat.get("id"):
                chats[chat["id"]] = chat.get("title") or chat.get("username") or chat.get("first_name")
        if not chats:
            print("⚠️  Chưa thấy tin nhắn nào. Hãy MỞ BOT, bấm Start và gửi 1 tin, rồi chạy lại.")
            return
        print("📇 Các chat phát hiện được:")
        for cid, name in chats.items():
            print(f"   chat_id={cid}  ({name})")
        chat_id = str(list(chats)[-1])

    # 3) Gửi tin test
    print(f"📤 Gửi tin test tới chat_id={chat_id} ...")
    res = httpx.post(
        API.format(token=token, method="sendMessage"),
        json={"chat_id": chat_id,
              "text": "✅ <b>Kết nối Telegram thành công!</b>\nHệ thống cảnh báo cổ phiếu đã sẵn sàng.\n<i>Thông tin tham khảo, không phải khuyến nghị đầu tư.</i>",
              "parse_mode": "HTML"},
        timeout=15,
    ).json()
    if res.get("ok"):
        print("🎉 Đã gửi! Kiểm tra Telegram của bạn.")
        print(f"\n👉 Thêm vào .env:\n   TELEGRAM_TOKEN={token}\n   TELEGRAM_CHAT_ID={chat_id}")
    else:
        print(f"❌ Gửi lỗi: {res}")


if __name__ == "__main__":
    main()
