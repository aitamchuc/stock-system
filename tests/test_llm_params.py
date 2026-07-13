"""Test lớp LLM gửi ĐÚNG tham số cho từng loại model (không gọi mạng — dùng client giả).

Bug thật đã gặp với gpt-5:
  • gửi 'max_tokens'  → 400 Unsupported parameter
  • gửi 'temperature' → 400 Only default (1) is supported
  • ngân sách quá thấp → token suy luận đốt hết → trả về CHUỖI RỖNG
"""
import os
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///./test_stock.db"
os.environ["DATA_SOURCE"] = "demo"

from app import llm  # noqa: E402


def test_detect_reasoning_models():
    for m in ("gpt-5", "gpt-5-mini", "gpt-5-pro", "o1", "o3-mini", "o4-mini"):
        assert llm.is_reasoning_model(m), m
    for m in ("gpt-4o-mini", "gpt-4o", "gpt-4.1", "claude-sonnet-5"):
        assert not llm.is_reasoning_model(m), m


def test_reasoning_budget_has_headroom():
    # phải cấp thêm ngân sách cho token suy luận, nếu không model trả về rỗng
    assert llm._reasoning_budget(600) >= 3000
    assert llm._reasoning_budget(2000) > 2000


def _fake_openai(captured):
    """Client giả ghi lại kwargs gửi lên OpenAI."""
    class Completions:
        def create(self, **kw):
            captured.update(kw)
            msg = types.SimpleNamespace(content="ok")
            choice = types.SimpleNamespace(message=msg, finish_reason="stop")
            return types.SimpleNamespace(choices=[choice])

    class Chat:
        completions = Completions()

    class Client:
        def __init__(self, api_key=None):
            self.chat = Chat()

    return types.SimpleNamespace(OpenAI=Client)


def _run(monkeypatch, model):
    captured: dict = {}
    monkeypatch.setitem(sys.modules, "openai", _fake_openai(captured))
    monkeypatch.setattr(llm.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(llm.settings, "openai_model", model)
    monkeypatch.setattr(llm.settings, "llm_provider", "openai")
    monkeypatch.setattr(llm.settings, "openai_reasoning_effort", "medium")
    out = llm.chat("hi", max_tokens=600, temperature=0.3)
    return out, captured


def test_reasoning_model_params(monkeypatch):
    out, kw = _run(monkeypatch, "gpt-5")
    assert out == "ok"
    assert "max_tokens" not in kw, "gpt-5 sẽ báo lỗi 400 nếu gửi max_tokens"
    assert "temperature" not in kw, "gpt-5 chỉ nhận temperature mặc định"
    assert kw["max_completion_tokens"] >= 3000, "thiếu headroom → trả về rỗng"
    assert kw["reasoning_effort"] == "medium"


def test_classic_model_params(monkeypatch):
    out, kw = _run(monkeypatch, "gpt-4o-mini")
    assert out == "ok"
    assert kw["max_tokens"] == 600
    assert kw["temperature"] == 0.3
    assert "max_completion_tokens" not in kw
    assert "reasoning_effort" not in kw


if __name__ == "__main__":
    test_detect_reasoning_models()
    test_reasoning_budget_has_headroom()
    print("OK (chạy pytest để test đủ)")
