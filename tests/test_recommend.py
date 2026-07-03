"""Test engine khuyến nghị: mức giá hợp lệ (cắt lỗ < mua < bán)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///./test_stock.db"
os.environ["DATA_SOURCE"] = "demo"

from app.engines import recommend as rec  # noqa: E402


def test_compute_levels_ordering():
    lv = rec.compute_levels(current=100_000, support=90_000, resistance=120_000, final_score=80)
    assert lv["stop_loss"] < lv["buy_low"] <= lv["buy_high"] < lv["target_price"]
    assert lv["risk_reward"] and lv["risk_reward"] > 0


def test_compute_levels_missing_sr():
    # Thiếu hỗ trợ/kháng cự -> vẫn cho mức hợp lệ (fallback ±)
    lv = rec.compute_levels(current=50_000, support=None, resistance=None, final_score=50)
    assert lv["stop_loss"] < lv["buy_low"] <= lv["buy_high"] < lv["target_price"]


def test_recommend_rule_fallback():
    ctx = {
        "symbol": "TST", "current_price": 30_000, "support": 27_000, "resistance": 36_000,
        "final_score": 72, "signal": "positive", "pe": 10.0, "pb": 1.5,
        "why": "Điểm cơ bản cao", "main_risks": ["Thanh khoản thấp"], "period": "2025Q1",
    }
    out = rec.recommend(ctx)  # không có API key -> method rule
    assert out["method"] in ("rule", "llm")
    assert out["stop_loss"] < out["buy_low"] <= out["buy_high"] < out["target_price"]
    assert out["thesis"]
    assert out["fair_value"] is not None      # có pe -> có giá hợp lý tham chiếu


if __name__ == "__main__":
    test_compute_levels_ordering()
    test_compute_levels_missing_sr()
    test_recommend_rule_fallback()
    print("OK")
