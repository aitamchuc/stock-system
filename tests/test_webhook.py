"""Test webhook Telegram: bảo mật, khử trùng, trả 200 ngay.

Endpoint này CÔNG KHAI trên internet → sai sót bảo mật nghĩa là bất kỳ ai cũng điều khiển
được bot (tốn tiền LLM, spam tin nhắn).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///./test_stock.db"
os.environ["DATA_SOURCE"] = "demo"
os.environ["TELEGRAM_WEBHOOK_SECRET"] = "test-secret-123"

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.bot import webhook  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

SECRET = "test-secret-123"


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    settings.telegram_webhook_secret = SECRET
    webhook._seen.clear()
    webhook._seen_set.clear()
    # chặn mọi lần gửi Telegram thật; ghi lại lời gọi để kiểm chứng
    calls = []
    monkeypatch.setattr(webhook, "_process", lambda text, chat: calls.append((text, chat)))
    yield calls


def _update(uid: int, text: str = "/FPT") -> dict:
    return {"update_id": uid,
            "message": {"text": text, "chat": {"id": 999}}}


def test_rejects_without_secret():
    c = TestClient(app)
    r = c.post("/telegram/webhook", json=_update(1))
    assert r.status_code == 403


def test_rejects_wrong_secret():
    c = TestClient(app)
    r = c.post("/telegram/webhook", json=_update(2),
               headers={"X-Telegram-Bot-Api-Secret-Token": "sai-bet"})
    assert r.status_code == 403


def test_accepts_correct_secret_and_queues_work(_setup):
    c = TestClient(app)
    r = c.post("/telegram/webhook", json=_update(3),
               headers={"X-Telegram-Bot-Api-Secret-Token": SECRET})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert _setup == [("/FPT", 999)]           # đã đẩy sang xử lý nền


def test_deduplicates_repeated_update_id(_setup):
    c = TestClient(app)
    h = {"X-Telegram-Bot-Api-Secret-Token": SECRET}
    for _ in range(3):
        c.post("/telegram/webhook", json=_update(7), headers=h)
    assert len(_setup) == 1, "update trùng bị xử lý nhiều lần → tốn tiền LLM gấp bội"


def test_ignores_non_text_updates(_setup):
    c = TestClient(app)
    r = c.post("/telegram/webhook",
               json={"update_id": 9, "message": {"chat": {"id": 999}}},   # sticker/ảnh
               headers={"X-Telegram-Bot-Api-Secret-Token": SECRET})
    assert r.status_code == 200 and _setup == []


def test_503_when_secret_not_configured():
    settings.telegram_webhook_secret = ""
    c = TestClient(app)
    r = c.post("/telegram/webhook", json=_update(11))
    assert r.status_code == 503                # không cho chạy hớ hênh khi chưa cấu hình
    settings.telegram_webhook_secret = SECRET


def test_dedupe_memory_is_bounded():
    """Không được rò rỉ bộ nhớ: service free chỉ có 512MB."""
    webhook._seen.clear()
    webhook._seen_set.clear()
    for i in range(1500):
        webhook._already_handled(i)
    assert len(webhook._seen) <= webhook._seen.maxlen
    assert len(webhook._seen_set) <= webhook._seen.maxlen
