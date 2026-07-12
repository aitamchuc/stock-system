"""Test port SFI: các chỉ báo tính đúng và NHÂN QUẢ (không nhìn trước tương lai)."""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///./test_stock.db"
os.environ["DATA_SOURCE"] = "demo"

from app.engines import sfi  # noqa: E402


def _df(n=250, seed=7):
    rng = np.random.default_rng(seed)
    close = 20000 * np.cumprod(1 + rng.normal(0.0005, 0.015, n))
    high = close * (1 + abs(rng.normal(0, 0.006, n)))
    low = close * (1 - abs(rng.normal(0, 0.006, n)))
    return pd.DataFrame({"ts": range(n), "high": high, "low": low, "close": close,
                         "volume": rng.integers(1e5, 1e6, n)})


def test_wma_matches_definition():
    s = pd.Series([1.0, 2, 3, 4, 5])
    w = sfi.wma(s, 3)
    # WMA(3) tại i=2: (1*1 + 2*2 + 3*3)/6 = 14/6
    assert abs(w.iloc[2] - 14 / 6) < 1e-9
    assert np.isnan(w.iloc[1])          # chưa đủ cửa sổ


def test_rsi_bounds():
    r = sfi.rsi(_df()["close"])
    r = r.dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_oracle_score_range():
    o = sfi.oracle_score(_df())
    assert o.min() >= 0 and o.max() <= 6


def test_ut_bot_and_kalman_finite():
    df = _df()
    ub = sfi.ut_bot(df).dropna()
    km = sfi.kalman(df["close"]).dropna()
    assert len(ub) > 200 and np.isfinite(ub).all()
    assert len(km) > 200 and np.isfinite(km).all()
    # Kalman bám giá, không lệch quá xa
    assert (abs(km - df["close"]) / df["close"]).mean() < 0.1


def test_causality_no_lookahead():
    """Cắt bớt dữ liệu tương lai KHÔNG được làm đổi giá trị chỉ báo ở quá khứ."""
    df = _df(300)
    full = sfi.compute(df)
    cut = sfi.compute(df.iloc[:250].copy())
    k = 240                                   # kiểm tra tại nến 240
    for col in ("smart_trail", "ut_stop", "kalman", "oracle"):
        a, b = full[col].iloc[k], cut[col].iloc[k]
        assert (np.isnan(a) and np.isnan(b)) or abs(a - b) < 1e-6, f"{col} nhìn trước tương lai!"


def test_compute_signal_columns():
    r = sfi.compute(_df())
    for c in ("st_rising", "ut_long", "kalman_up", "oracle_bull", "all_bull",
              "oracle_bull_cross"):
        assert c in r.columns
    # tín hiệu sự kiện phải là tập con của trạng thái
    assert (r["oracle_bull_cross"] & ~r["oracle_bull"]).sum() == 0


if __name__ == "__main__":
    test_wma_matches_definition()
    test_rsi_bounds()
    test_oracle_score_range()
    test_ut_bot_and_kalman_finite()
    test_causality_no_lookahead()
    test_compute_signal_columns()
    print("OK")
