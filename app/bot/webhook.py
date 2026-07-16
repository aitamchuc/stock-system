"""Telegram webhook — cho bot chạy 24/7 trên Render gói FREE mà không cần tiến trình long-polling.

Vì sao webhook thay vì long-polling:
  • Render gói free KHÔNG có Background Worker (chỉ gói trả phí) → không chạy listener 24/7 được.
  • Web service free thì ngủ khi rảnh, nhưng TỰ THỨC khi có HTTP request → Telegram đẩy tin
    vào đây là service thức dậy xử lý. Miễn phí, không cần máy bạn bật.

Ba điểm bắt buộc phải xử lý đúng:
  1. BẢO MẬT: endpoint công khai → phải kiểm tra header bí mật, nếu không ai cũng POST giả
     lệnh vào bot được (tốn tiền LLM + spam).
  2. TRẢ 200 NGAY: phân tích mất 10-30s; Telegram timeout ~60s và sẽ GỬI LẠI nếu chậm →
     xử lý nền, trả 200 tức thì.
  3. KHỬ TRÙNG: Telegram có thể gửi lại cùng update_id (vd lúc service cold-start) → nhớ
     update_id đã xử lý để không phân tích/tính tiền LLM hai lần.
"""
from __future__ import annotations

from collections import deque

from fastapi import APIRouter, BackgroundTasks, Header, Request
from fastapi.responses import JSONResponse

from app.bot import telegram
from app.config import settings

router = APIRouter()

# Khử trùng update_id đã xử lý (bounded — không rò rỉ bộ nhớ)
_seen: deque[int] = deque(maxlen=500)
_seen_set: set[int] = set()


def _already_handled(update_id: int) -> bool:
    if update_id in _seen_set:
        return True
    if len(_seen) == _seen.maxlen:
        _seen_set.discard(_seen[0])
    _seen.append(update_id)
    _seen_set.add(update_id)
    return False


def _process(text: str, chat_id: int) -> None:
    """Chạy nền: phân tích rồi gửi trả lời."""
    from app.bot import listener

    try:
        if listener._is_analyze_request(text):
            telegram.send_message("⏳ Đang phân tích... (nạp dữ liệu + BCTC + AI, ~10-30 giây)",
                                  chat_id=str(chat_id))
        telegram.send_message(listener.handle(text), chat_id=str(chat_id))
    except Exception as exc:  # pragma: no cover
        print(f"[webhook] lỗi xử lý {text!r}: {exc}")
        telegram.send_message(f"❌ Lỗi khi xử lý: {str(exc)[:200]}", chat_id=str(chat_id))


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    background: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    # 1) Bảo mật — từ chối nếu không đúng bí mật
    if not settings.telegram_webhook_secret:
        return JSONResponse({"error": "webhook chưa cấu hình TELEGRAM_WEBHOOK_SECRET"},
                            status_code=503)
    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        return JSONResponse({"error": "unauthorized"}, status_code=403)

    update = await request.json()
    update_id = update.get("update_id")
    msg = update.get("message") or update.get("edited_message") or {}
    text = msg.get("text")
    chat_id = (msg.get("chat") or {}).get("id")

    if not text or not chat_id:
        return {"ok": True}                       # bỏ qua ảnh/sticker/... nhưng vẫn báo nhận
    if update_id is not None and _already_handled(update_id):
        print(f"[webhook] bỏ qua update trùng {update_id}")
        return {"ok": True}

    # 2) Trả 200 NGAY, xử lý nền (tránh Telegram timeout → gửi lại → phân tích 2 lần)
    background.add_task(_process, text, chat_id)
    return {"ok": True}
