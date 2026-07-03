"""Nguồn tin RSS (báo kinh tế VN + thế giới). Chỉ dùng RSS công khai (hợp pháp, ổn định).

Trả về bài viết đã chuẩn hóa: {title, summary, url, source, published, region}.
"""
from __future__ import annotations

import html
import re
from datetime import datetime

import feedparser

# region: "VN" | "World"
FEEDS = [
    ("VnExpress - Kinh doanh", "https://vnexpress.net/rss/kinh-doanh.rss", "VN"),
    ("VnExpress - Chứng khoán", "https://vnexpress.net/rss/kinh-doanh/chung-khoan.rss", "VN"),
    ("CafeF - Chứng khoán", "https://cafef.vn/thi-truong-chung-khoan.rss", "VN"),
    ("CafeF - Doanh nghiệp", "https://cafef.vn/doanh-nghiep.rss", "VN"),
    ("CafeF - Vĩ mô", "https://cafef.vn/vi-mo-dau-tu.rss", "VN"),
    ("VietnamNet - Kinh doanh", "https://vietnamnet.vn/rss/kinh-doanh.rss", "VN"),
    ("World - Kinh tế toàn cầu",
     "https://news.google.com/rss/search?q=global+economy+stock+markets+when:1d&hl=en-US&gl=US&ceid=US:en", "World"),
    ("World - Fed & lãi suất",
     "https://news.google.com/rss/search?q=federal+reserve+interest+rates+inflation+when:1d&hl=en-US&gl=US&ceid=US:en", "World"),
]

_TAG = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return html.unescape(_TAG.sub("", text or "")).strip()


def _published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime(*t[:6])
            except Exception:
                pass
    return None


def fetch_all(limit_per_feed: int = 30) -> list[dict]:
    """Lấy bài từ tất cả feed. Bỏ qua feed lỗi. Sắp xếp mới → cũ, khử trùng theo URL."""
    seen: set[str] = set()
    out: list[dict] = []
    for source, url, region in FEEDS:
        try:
            d = feedparser.parse(url)
        except Exception as exc:  # pragma: no cover
            print(f"[news] feed lỗi {source}: {exc}")
            continue
        for e in d.entries[:limit_per_feed]:
            link = e.get("link")
            if not link or link in seen:
                continue
            seen.add(link)
            out.append({
                "title": _clean(e.get("title", "")),
                "summary": _clean(e.get("summary", ""))[:400],
                "url": link,
                "source": source,
                "region": region,
                "published": _published(e),
            })
    out.sort(key=lambda a: a["published"] or datetime.min, reverse=True)
    return out
