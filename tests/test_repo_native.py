"""Test chống lỗi 'schema np does not exist' — kiểu numpy KHÔNG được lọt xuống DB.

Bug thật: psycopg2 không adapt được np.float64 → render thành 'np.float64(6.4)' → Postgres
báo lỗi schema "np". SQLite bỏ qua được (np.float64 là lớp con của float) nên bug chỉ lộ trên
Supabase/Postgres. Test này kiểm tra ở tầng dữ liệu nên bắt được bug bất kể DB nào.
"""
import os
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///./test_stock.db"
os.environ["DATA_SOURCE"] = "demo"

from app.engines import penny_scanner  # noqa: E402
from app.repo import _native  # noqa: E402


def _has_numpy(v) -> bool:
    if isinstance(v, np.generic):
        return True
    if isinstance(v, dict):
        return any(_has_numpy(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return any(_has_numpy(x) for x in v)
    return False


def test_native_strips_numpy_scalars():
    row = {
        "a": np.float64(1.5), "b": np.int64(3), "c": np.bool_(True),
        "d": {"nested": np.float32(2.5)}, "e": [np.float64(1.0), "x", 2],
        "f": "giữ nguyên", "g": None,
    }
    out = _native(row)
    assert not _has_numpy(out), "còn sót kiểu numpy sau khi _native()"
    assert out["a"] == 1.5 and isinstance(out["a"], float)
    assert out["b"] == 3 and isinstance(out["b"], int)
    assert out["c"] is True
    assert out["e"][0] == 1.0 and out["f"] == "giữ nguyên" and out["g"] is None


def test_penny_analyze_row_is_db_safe_after_native():
    """penny_scanner.analyze() trả về np.float64 (đây chính là nguồn gây lỗi trên Postgres)."""
    n = 80
    rng = np.random.default_rng(3)
    close = 5000 * np.cumprod(1 + rng.normal(0.001, 0.02, n))
    df = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n).date,
        "high": close * 1.02, "low": close * 0.98, "close": close,
        "volume": rng.integers(1e5, 2e6, n),
    })
    res = penny_scanner.analyze(df, {"value": 8e9, "foreign_net": 1e8})
    st = res["stats"]
    row = {
        "upside_score": res["upside_score"], "risk_score": res["risk_score"],
        "return_1m_pct": st.get("return_1m_pct"), "atr_pct": st.get("atr_pct"),
        "volume_zscore": st.get("volume_zscore"),
        "signals": res["signals"], "warnings": res["warnings"],
    }
    # Sau khi qua _native (repo áp dụng trước mọi lần ghi DB) → không còn numpy
    assert not _has_numpy(_native(row)), "numpy lọt xuống DB → sẽ sập trên Postgres"


if __name__ == "__main__":
    test_native_strips_numpy_scalars()
    test_penny_analyze_row_is_db_safe_after_native()
    print("OK")
