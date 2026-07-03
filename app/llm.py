"""Lớp trừu tượng gọi LLM — hỗ trợ OpenAI (ChatGPT) và Anthropic (Claude).

Chọn nhà cung cấp:
  - settings.llm_provider ép cứng ("openai" | "anthropic"), hoặc
  - tự nhận diện: có OPENAI_API_KEY → openai; else có ANTHROPIC_API_KEY → anthropic; else none.
"""
from __future__ import annotations

from app.config import settings


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
        resp = client.chat.completions.create(
            model=settings.openai_model, messages=messages,
            max_tokens=max_tokens, temperature=temperature,
        )
        return resp.choices[0].message.content or ""

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
