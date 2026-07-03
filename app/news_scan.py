"""Quét tin tức kinh tế (VN + thế giới), AI phân tích ảnh hưởng giá cổ phiếu, gửi Telegram.

Chạy 2 lần/ngày (9h & 14h) qua Task Scheduler, hoặc thủ công:
    python -m app.news_scan
    python -m app.news_scan --no-telegram

⚠️ Phân tích tham khảo, không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.bot import telegram
from app.config import settings
from app.db import init_db, session_scope
from app.engines import news_impact
from app import repo


def _run_label() -> str:
    h = datetime.now().hour
    session = "phiên sáng" if h < 12 else "phiên chiều"
    return f"{session} {datetime.now():%d/%m %H:%M}"


def scan(*, send: bool = True) -> dict:
    from app.news_sources import fetch_all

    articles = fetch_all()
    urls = [a["url"] for a in articles]

    with session_scope() as s:
        seen = repo.existing_news_urls(s, urls)
        watchlist = [x.symbol for x in repo.active_symbols(s)]
    new = [a for a in articles if a["url"] not in seen][: settings.news_scan_limit]
    print(f"[news] {len(articles)} bài lấy về, {len(new)} bài mới → phân tích...")
    if not new:
        return {"fetched": len(articles), "new": 0, "notable": 0}

    # Phân tích theo lô để tiết kiệm chi phí LLM
    analyzed: list[dict] = []
    bs = settings.news_batch_size
    for i in range(0, len(new), bs):
        batch = new[i:i + bs]
        res = news_impact.analyze_batch(batch, watchlist)
        for a, r in zip(batch, res):
            analyzed.append({**a, **r})

    # Lưu DB
    with session_scope() as s:
        repo.insert_news_impacts(s, [{
            "url": a["url"], "published_at": a.get("published"), "source": a["source"],
            "region": a.get("region"), "title": a["title"],
            "relevant": a["relevant"], "scope": a.get("scope"),
            "impact_level": a.get("impact_level"), "direction": a.get("direction"),
            "affected_symbols": a.get("affected_symbols", []), "sectors": a.get("sectors", []),
            "analysis": a.get("analysis"),
        } for a in analyzed])

    # Chọn tin đáng chú ý: liên quan + ảnh hưởng cao/trung bình
    notable = [a for a in analyzed
               if a.get("relevant") and a.get("impact_level") in ("cao", "trung bình")]
    # Ưu tiên impact cao và có mã cụ thể lên đầu
    notable.sort(key=lambda a: (a.get("impact_level") == "cao",
                                bool(a.get("affected_symbols"))), reverse=True)

    # Tầng 2: AI phân tích SÂU, tổng hợp thành bản tin trước khi gửi
    with session_scope() as s:
        watchlist = [x.symbol for x in repo.active_symbols(s)]
    brief = news_impact.synthesize(notable, watchlist) if notable else None

    if send and notable:
        if brief:
            telegram.send_message(telegram.format_news_brief(brief, notable, _run_label()))
        else:  # không có LLM → gửi danh sách rút gọn
            telegram.send_message(telegram.format_news_digest(notable[:12], _run_label()))

    return {"fetched": len(articles), "new": len(new),
            "notable": len(notable), "deep_brief": bool(brief)}


def run(send: bool = True) -> None:
    init_db()
    summary = scan(send=send)
    print(f"[news] Xong: {summary}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-telegram", action="store_true")
    run(send=not ap.parse_args().no_telegram)
