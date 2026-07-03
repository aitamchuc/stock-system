"""Tổng hợp điểm tin tức/sự kiện.

Nếu có ANTHROPIC_API_KEY → dùng Claude tóm tắt + chấm sentiment.
Nếu không → fallback keyword-sentiment (chạy offline, đủ cho MVP/demo).
"""
from __future__ import annotations

from app import llm
from app.models import News

_POS = ["tăng trưởng", "kỷ lục", "lãi", "mua ròng", "trúng thầu", "cổ tức",
        "vượt kế hoạch", "khởi công", "ký kết", "mở rộng"]
_NEG = ["thua lỗ", "giảm", "bán ròng", "phạt", "điều tra", "cảnh báo",
        "hủy niêm yết", "nợ xấu", "chậm công bố", "phát hành thêm", "pha loãng"]

_EVENT_WEIGHT = {
    "dividend": +6, "buyback": +6, "insider": +4,
    "agm": 0, "issuance": -6, "other": 0,
}


def _keyword_sentiment(title: str) -> float:
    t = (title or "").lower()
    score = sum(1 for w in _POS if w in t) - sum(1 for w in _NEG if w in t)
    return max(-1.0, min(1.0, score / 2))


def score_single(title: str, event_type: str | None) -> tuple[float, str]:
    """Trả (sentiment[-1..1], summary). Dùng LLM (ChatGPT/Claude) nếu có key."""
    if llm.available():
        try:
            return _llm_score(title, event_type)
        except Exception as exc:  # pragma: no cover
            print(f"[news_nlp] LLM lỗi, fallback keyword: {exc}")
    return _keyword_sentiment(title), (title or "")[:180]


def _llm_score(title: str, event_type: str | None) -> tuple[float, str]:
    prompt = (
        "Bạn là chuyên gia phân tích tin tức chứng khoán VN. Với tiêu đề tin dưới đây, "
        "trả về đúng 2 dòng:\n"
        "SENTIMENT: <số thực -1..1>\n"
        "SUMMARY: <tóm tắt 1 câu tiếng Việt, khách quan>\n\n"
        f"Tiêu đề: {title}\nLoại sự kiện: {event_type}"
    )
    text = llm.chat(prompt, max_tokens=200)
    sent, summary = 0.0, title
    for line in text.splitlines():
        if line.upper().startswith("SENTIMENT:"):
            try:
                sent = max(-1.0, min(1.0, float(line.split(":", 1)[1].strip())))
            except ValueError:
                pass
        elif line.upper().startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip()
    return sent, summary


def aggregate(news_items: list[News]) -> dict:
    """Gộp các tin gần đây của 1 mã → điểm 0-100 + lý do."""
    if not news_items:
        return {"score": 50.0, "reasons": ["Không có tin tức đáng chú ý gần đây"]}

    sentiments = [n.sentiment for n in news_items if n.sentiment is not None]
    event_bonus = sum(_EVENT_WEIGHT.get(n.event_type or "other", 0) for n in news_items)
    base = 50 + (sum(sentiments) / len(sentiments) * 40 if sentiments else 0) + event_bonus
    score = max(0.0, min(100.0, base))

    reasons = []
    pos = [n for n in news_items if (n.sentiment or 0) > 0.2]
    neg = [n for n in news_items if (n.sentiment or 0) < -0.2]
    if pos:
        reasons.append(f"{len(pos)} tin tích cực gần đây")
    if neg:
        reasons.append(f"{len(neg)} tin tiêu cực/rủi ro")
    events = {n.event_type for n in news_items if n.event_type and n.event_type != "other"}
    if events:
        reasons.append("Sự kiện: " + ", ".join(sorted(events)))
    if not reasons:
        reasons.append("Tin tức trung tính")
    return {"score": round(score, 1), "reasons": reasons}
