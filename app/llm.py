"""Lớp trừu tượng gọi LLM — hỗ trợ OpenAI (ChatGPT) và Anthropic (Claude).

Chọn nhà cung cấp:
  - settings.llm_provider ép cứng ("openai" | "anthropic"), hoặc
  - tự nhận diện: có OPENAI_API_KEY → openai; else có ANTHROPIC_API_KEY → anthropic; else none.
"""
from __future__ import annotations

import re

from app.config import settings

# Model SUY LUẬN của OpenAI (gpt-5*, o1/o3/o4...) có API khác model thường:
#   • dùng 'max_completion_tokens' (gửi 'max_tokens' → lỗi 400)
#   • KHÔNG nhận 'temperature' khác 1
#   • token SUY LUẬN tính chung vào ngân sách output → phải cấp headroom, nếu không model
#     đốt hết ngân sách vào suy luận và trả về CHUỖI RỖNG (đã kiểm chứng: 512/600 token)
_REASONING_RE = re.compile(r"^(gpt-5|o\d)", re.IGNORECASE)


def is_reasoning_model(model: str) -> bool:
    return bool(_REASONING_RE.match(model or ""))


def _reasoning_budget(max_tokens: int) -> int:
    """Ngân sách token cho model suy luận = output mong muốn + headroom cho phần suy luận."""
    return max(max_tokens * 4, max_tokens + 3000)


def provider() -> str:
    if settings.llm_provider:
        return settings.llm_provider.lower()
    if settings.openai_api_key:
        return "openai"
    if settings.anthropic_api_key:
        return "anthropic"
    return "none"


def available() -> bool:
    return provider() in ("openai", "anthropic")


def model_name() -> str:
    return settings.openai_model if provider() == "openai" else settings.llm_model


def chat(prompt: str, *, max_tokens: int = 600, system: str | None = None,
         temperature: float = 0.3) -> str:
    """Gửi 1 prompt, trả về text. Ném lỗi nếu chưa cấu hình LLM."""
    p = provider()
    if p == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        model = settings.openai_model
        kwargs: dict = {"model": model, "messages": messages}
        if is_reasoning_model(model):
            kwargs["max_completion_tokens"] = _reasoning_budget(max_tokens)
            if settings.openai_reasoning_effort:
                kwargs["reasoning_effort"] = settings.openai_reasoning_effort
            # cố tình KHÔNG gửi temperature — model suy luận chỉ nhận mặc định
        else:
            kwargs["max_tokens"] = max_tokens
            kwargs["temperature"] = temperature

        resp = client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content or ""
        if not text:
            # Thường do ngân sách bị suy luận đốt hết → báo rõ thay vì im lặng fallback
            fr = resp.choices[0].finish_reason
            print(f"[llm] {model} trả về RỖNG (finish_reason={fr}) — "
                  f"có thể thiếu max_completion_tokens cho phần suy luận.")
        return text

    if p == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        kwargs = {
            "model": settings.llm_model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        msg = client.messages.create(**kwargs)
        return msg.content[0].text

    raise RuntimeError("Chưa cấu hình LLM (thiếu OPENAI_API_KEY / ANTHROPIC_API_KEY).")
