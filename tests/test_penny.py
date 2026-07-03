"""Test bộ quét penny: lọc thanh khoản + chấm điểm tiềm năng/rủi ro."""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///./test_stock.db"
os.environ["DATA_SOURCE"] = "demo"

from app.engines import penny_scanner  # noqa: E402


def test_screen_liquidity_and_price():
    snap = {
        "AAA": {"price": 5000, "volume": 2_000_000, "value": 0, "foreign_net": 100},   # 10 tỷ → penny ok
        "BBB": {"price": 5000, "volume": 100, "value": 0, "foreign_net": 0},            # ~0.5tr → loại (thanh khoản)
        "CCC": {"price": 50_000, "volume": 1_000_000, "value": 0, "foreign_net": 0},    # giá cao → loại
    }
    cands = penny_scanner.screen(snap, price_max=10_000, min_liquidity=1e9)
    syms = [c["symbol"] for c in cands]
    assert "AAA" in syms and "BBB" not in syms and "CCC" not in syms


def _fake_ohlcv(base: float, n: int = 80, spike: bool = False) -> pd.DataFrame:
    rows = []
    d = date.today() - timedelta(days=n)
    price = base
    for i in range(n):
        price *= 1.01 if i > n - 5 else 1.0
        v = 5_000_000 if (spike and i == n - 1) else 1_000_000
        rows.append({"ts": d, "open": price, "high": price * 1.02,
                     "low": price * 0.98, "close": price, "volume": v})
        d += timedelta(days=1)
    return pd.DataFrame(rows)


def test_analyze_scores_bounds():
    df = _fake_ohlcv(5000, spike=True)
    r = penny_scanner.analyze(df, {"value": 8e9, "foreign_net": 50})
    assert 0 <= r["upside_score"] <= 100
    assert 0 <= r["risk_score"] <= 100
    assert r["warnings"]                       # luôn có cảnh báo rủi ro
    assert "đầu cơ" in r["warnings"][0].lower() or "rủi ro" in r["warnings"][0].lower()


def test_analyze_insufficient_history():
    df = _fake_ohlcv(5000, n=20)
    r = penny_scanner.analyze(df, {"value": 8e9})
    assert r["upside_score"] == 0 and r["risk_score"] == 100


if __name__ == "__main__":
    test_screen_liquidity_and_price()
    test_analyze_scores_bounds()
    test_analyze_insufficient_history()
    print("OK")
