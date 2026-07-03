"""Test phân tích ảnh hưởng tin tức (fallback không cần LLM/mạng)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///./test_stock.db"
os.environ["DATA_SOURCE"] = "demo"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = ""

from app.engines import news_impact  # noqa: E402


def test_fallback_direction():
    arts = [
        {"title": "Doanh nghiệp báo lãi kỷ lục, tăng trưởng mạnh", "summary": ""},
        {"title": "Lo ngại suy thoái và lạm phát, thị trường bán tháo", "summary": ""},
    ]
    res = news_impact.analyze_batch(arts, watchlist=["FPT", "HPG"])
    assert len(res) == 2
    assert res[0]["direction"] == "tích cực"
    assert res[1]["direction"] == "tiêu cực"
    # fallback luôn hợp lệ cấu trúc
    for r in res:
        assert set(["relevant", "impact_level", "direction", "affected_symbols"]) <= set(r)


def test_clean_html():
    from app.news_sources import _clean
    assert _clean("Giá <b>tăng</b> &amp; mạnh") == "Giá tăng & mạnh"


if __name__ == "__main__":
    test_fallback_direction()
    test_clean_html()
    print("OK")
