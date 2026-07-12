"""Test Nadaraya-Watson Envelope: dải hợp lệ + logic tín hiệu đúng định nghĩa."""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///./test_stock.db"
os.environ["DATA_SOURCE"] = "demo"

from app.engines import nw_envelope as nw  # noqa: E402


def _wave(n=300, period=40, amp=0.1, base=20000.0):
    t = np.arange(n)
    return pd.Series(base * (1 + amp * np.sin(2 * np.pi * t / period)))


def test_bands_order_and_shape():
    res = nw.compute(_wave())
    assert res is not None and len(res) == 300
    ok = res["upper"].notna()
    assert (res.loc[ok, "lower"] < res.loc[ok, "out"]).all()
    assert (res.loc[ok, "out"] < res.loc[ok, "upper"]).all()


def test_signal_logic_matches_definition():
    res = nw.compute(_wave()).dropna()
    lower, upper = res["lower"], res["upper"]
    exp_buy = (lower > lower.shift(1)) & (lower.shift(1) <= lower.shift(2))
    exp_sell = (upper < upper.shift(1)) & (upper.shift(1) >= upper.shift(2))
    # bỏ 2 hàng đầu (shift chưa đủ)
    assert res["buy"].iloc[2:].equals(exp_buy.iloc[2:].fillna(False))
    assert res["sell"].iloc[2:].equals(exp_sell.iloc[2:].fillna(False))


def test_signals_fire_on_oscillating_series():
    res = nw.compute(_wave())
    assert res["buy"].sum() > 0 and res["sell"].sum() > 0


def test_insufficient_history_returns_none():
    assert nw.compute(pd.Series([1.0] * 10)) is None


def test_latest_signal_shape():
    df = pd.DataFrame({"ts": range(300), "close": _wave()})
    r = nw.latest_signal(df)
    assert r is not None
    assert set(["signal", "upper", "lower", "mid", "price", "position"]) <= set(r)
    assert r["lower"] < r["upper"]


if __name__ == "__main__":
    test_bands_order_and_shape()
    test_signal_logic_matches_definition()
    test_signals_fire_on_oscillating_series()
    test_insufficient_history_returns_none()
    test_latest_signal_shape()
    print("OK")
