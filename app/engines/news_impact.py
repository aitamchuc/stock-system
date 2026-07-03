"""AI phân tích ảnh hưởng của tin tức kinh tế tới giá cổ phiếu (theo lô, tiết kiệm chi phí).

Với mỗi bài (tiêu đề + tóm tắt), LLM đánh giá:
  - relevant: có liên quan thị trường chứng khoán VN không
  - scope: macro (vĩ mô) | sector (ngành) | company (doanh nghiệp cụ thể)
  - impact_level: cao | trung bình | thấp
  - direction: tích cực | tiêu cực | trung tính  (với giá cổ phiếu liên quan)
  - affected_symbols: mã trong danh mục theo dõi bị ảnh hưởng (nếu có)
  - sectors: ngành bị ảnh hưởng
  - analysis: 1-2 câu giải thích ảnh hưởng tới giá

Không có LLM → fallback keyword: chỉ gắn relevant + direction thô, impact "thấp".
"""
from __future__ import annotations

import json

from app import llm

_SYSTEM = (
    "Bạn là chuyên gia phân tích tác động tin tức tới thị trường chứng khoán Việt Nam. "
    "Đánh giá KHÁCH QUAN, thận trọng, KHÔNG cam kết lợi nhuận, KHÔNG bịa. Chỉ dựa trên nội dung "
    "tiêu đề/tóm tắt được cung cấp. Nếu tin không liên quan TTCK VN, đánh dấu relevant=false."
)

_POS = ["tăng trưởng", "kỷ lục", "lãi lớn", "hồi phục", "nới lỏng", "giảm lãi suất",
        "gói kích thích", "thặng dư", "trúng thầu", "khởi công", "fdi", "nâng hạng"]
_NEG = ["suy thoái", "lạm phát", "tăng lãi suất", "thua lỗ", "vỡ nợ", "trừng phạt",
        "điều tra", "bắt", "phạt", "căng thẳng", "chiến tranh", "bán tháo", "sụt giảm"]


def synthesize(notable: list[dict], watchlist: list[str]) -> str | None:
    """Tầng 2: phân tích SÂU — tổng hợp các tin đáng chú ý thành bản tin cho NĐT.

    notable: list dict {title, impact_level, direction, affected_symbols, sectors, analysis, source}.
    Trả về text bản tin (tiếng Việt) hoặc None nếu không có LLM/lỗi.
    """
    if not notable or not llm.available():
        return None
    from app.engines.recommend import advisor_system   # tái dùng persona "Cố vấn Đầu tư AI"

    items = [{
        "title": a.get("title"), "impact": a.get("impact_level"),
        "direction": a.get("direction"), "symbols": a.get("affected_symbols"),
        "sectors": a.get("sectors"), "analysis": a.get("analysis"),
    } for a in notable[:15]]
    prompt = (
        "Dưới đây là các tin kinh tế đáng chú ý vừa quét (đã sơ bộ phân loại). Với vai trò cố vấn "
        "đầu tư, hãy PHÂN TÍCH SÂU và tổng hợp thành BẢN TIN ngắn gọn, sắc bén cho nhà đầu tư đang "
        f"theo dõi danh mục VN30: {', '.join(watchlist)}.\n\n"
        "Cấu trúc bản tin (tiếng Việt, súc tích, có emoji đầu mục, KHÔNG cam kết lợi nhuận, "
        "KHÔNG bịa ngoài dữ liệu được cấp, giữ TỔNG độ dài dưới ~1400 ký tự):\n"
        "🌐 <b>Bối cảnh &amp; tâm lý thị trường</b>: 1-2 câu.\n"
        "🔑 <b>Chủ đề chính</b>: gộp tin liên quan thành 2-4 nhóm, nêu ý nghĩa.\n"
        "🎯 <b>Tác động cụ thể</b>: mã/ngành bị ảnh hưởng, chiều (tích cực/tiêu cực), mức độ, "
        "khung thời gian (ngắn/trung hạn). CHỈ nêu mã khi tin nói trực tiếp về mã đó.\n"
        "⚠️ <b>Rủi ro &amp; điều cần theo dõi</b>.\n"
        "Dùng thẻ HTML <b> cho tiêu đề mục, KHÔNG dùng Markdown.\n\n"
        f"TIN TỨC:\n{json.dumps(items, ensure_ascii=False)}"
    )
    try:
        return llm.chat(prompt, max_tokens=1000, system=advisor_system()).strip()
    except Exception as exc:  # pragma: no cover
        print(f"[news_impact] synthesize lỗi: {exc}")
        return None


def _fallback(article: dict) -> dict:
    t = (article.get("title", "") + " " + article.get("summary", "")).lower()
    pos = sum(1 for w in _POS if w in t)
    neg = sum(1 for w in _NEG if w in t)
    direction = "tích cực" if pos > neg else "tiêu cực" if neg > pos else "trung tính"
    return {
        "relevant": True, "scope": "macro", "impact_level": "thấp",
        "direction": direction, "affected_symbols": [], "sectors": [],
        "analysis": "(Phân tích tự động theo từ khóa — chưa bật LLM.)",
    }


def analyze_batch(articles: list[dict], watchlist: list[str]) -> list[dict]:
    """Phân tích 1 lô bài. Trả list dict cùng thứ tự articles."""
    if not articles:
        return []
    if not llm.available():
        return [_fallback(a) for a in articles]

    items = [{"i": i, "title": a["title"], "summary": a.get("summary", ""),
              "region": a.get("region")} for i, a in enumerate(articles)]
    prompt = (
        f"Danh mục cổ phiếu đang theo dõi: {', '.join(watchlist)}.\n"
        "QUY TẮC affected_symbols: CHỈ thêm một mã khi bài viết nói TRỰC TIẾP về chính doanh nghiệp "
        "đó (đúng mã/đúng công ty). KHÔNG suy diễn theo 'hệ sinh thái', người liên quan, hay mã gần "
        "giống. Nếu chỉ ảnh hưởng ngành/vĩ mô, để affected_symbols rỗng và dùng sectors.\n\n"
        "Phân tích từng bài dưới đây. Trả về DUY NHẤT một JSON array, mỗi phần tử:\n"
        '{"i":số thứ tự, "relevant":true/false, "scope":"macro|sector|company", '
        '"impact_level":"cao|trung bình|thấp", "direction":"tích cực|tiêu cực|trung tính", '
        '"affected_symbols":["MÃ",...], "sectors":["ngành",...], '
        '"analysis":"1-2 câu tiếng Việt: ảnh hưởng tới giá cổ phiếu/ngành liên quan như thế nào"}\n\n'
        f"BÀI VIẾT:\n{json.dumps(items, ensure_ascii=False)}"
    )
    try:
        text = llm.chat(prompt, max_tokens=2000, system=_SYSTEM)
        s, e = text.find("["), text.rfind("]")
        data = json.loads(text[s:e + 1]) if s >= 0 and e >= 0 else []
    except Exception as exc:  # pragma: no cover
        print(f"[news_impact] LLM lỗi, fallback: {exc}")
        return [_fallback(a) for a in articles]

    by_i = {int(d.get("i", -1)): d for d in data if isinstance(d, dict)}
    out = []
    for i, a in enumerate(articles):
        d = by_i.get(i)
        if not d:
            out.append(_fallback(a))
            continue
        wl = set(watchlist)
        out.append({
            "relevant": bool(d.get("relevant", False)),
            "scope": d.get("scope"),
            "impact_level": d.get("impact_level"),
            "direction": d.get("direction"),
            "affected_symbols": [s for s in (d.get("affected_symbols") or []) if s in wl],
            "sectors": d.get("sectors") or [],
            "analysis": (d.get("analysis") or "")[:500],
        })
    return out
