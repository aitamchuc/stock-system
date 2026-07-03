"""Test AI chọn lọc (fallback quy tắc, không cần LLM/mạng)."""
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///./test_stock.db"
os.environ["DATA_SOURCE"] = "demo"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = ""

from app.db import init_db, session_scope  # noqa: E402
from app.models import DailyScore, OHLCV  # noqa: E402
from app import curate  # noqa: E402


def test_curate_rule_selects_positive():
    init_db()
    ts = date(2025, 1, 6)
    with session_scope() as s:
        s.merge(OHLCV(symbol="AAA", ts=ts, open=10000, high=10500, low=9800,
                      close=10000, volume=1_000_000, value=1e10))
        s.merge(DailyScore(symbol="AAA", ts=ts, final_score=80, signal="very_positive",
                           s_risk=80, rationale={"parts": {"fundamental": 90, "risk": 80},
                                                 "support": 9500, "resistance": 12000,
                                                 "why": "Nền tảng tốt", "main_risks": []}))
        s.merge(DailyScore(symbol="BBB", ts=ts, final_score=50, signal="neutral",
                           rationale={"parts": {}}))
    with session_scope() as s:
        picks = curate.curate(s, ts, send=False)
    syms = [p["symbol"] for p in picks]
    assert "AAA" in syms          # very_positive → Mua tích lũy
    assert "BBB" not in syms       # neutral, dưới ngưỡng → loại
    p = next(x for x in picks if x["symbol"] == "AAA")
    assert p["buy_low"] and p["target_price"] and p["stop_loss"]


if __name__ == "__main__":
    test_curate_rule_selects_positive()
    print("OK")
