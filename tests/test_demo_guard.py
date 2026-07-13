"""Test chốt an toàn: nguồn 'demo' KHÔNG được ghi đè giá THẬT đã có trong DB.

Sự cố có thật: DemoProvider sinh giá synthetic (20k–100k) và nhiều mã thật nằm trong danh sách
demo (BSR, FPT, HPG...). Chỉ cần lỡ chạy một lệnh với DATA_SOURCE=demo trên DB thật là giá giả
ghi đè giá thật → BSR hiện 85.120 thay vì 25.750, mọi chỉ báo/cảnh báo đều sai.
"""
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///./test_demo_guard.db"
os.environ["DATA_SOURCE"] = "vnstock"          # bắt đầu ở chế độ THẬT
import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import init_db, session_scope  # noqa: E402
from app.models import OHLCV  # noqa: E402
from app import repo  # noqa: E402


@pytest.fixture(autouse=True)
def _guard_on():
    """settings là singleton dùng chung giữa các test module → phải set/khôi phục trong từng test,
    nếu không các test sẽ ghi đè cờ của nhau."""
    src, allow = settings.data_source, settings.allow_demo_overwrite
    settings.allow_demo_overwrite = False       # test này kiểm CHÍNH chốt an toàn → tắt cửa thoát
    yield
    settings.data_source, settings.allow_demo_overwrite = src, allow


def _df(close: float, n: int = 5) -> pd.DataFrame:
    return pd.DataFrame({
        "ts": pd.date_range("2026-07-01", periods=n).date,
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": 1_000_000, "value": close * 1_000_000,
    })


def test_demo_cannot_overwrite_real_prices():
    init_db()
    with session_scope() as s:
        repo.upsert_symbols(s, [{"symbol": "BSR", "exchange": "UPCOM"}])
        # 1) Ghi giá THẬT (nguồn vnstock)
        settings.data_source = "vnstock"
        repo.upsert_ohlcv(s, "BSR", _df(25_750))

    with session_scope() as s:
        real = s.execute(
            OHLCV.__table__.select().where(OHLCV.symbol == "BSR")).fetchall()
        assert real and all(abs(r.close - 25_750) < 1 for r in real)

    # 2) Nguồn DEMO cố ghi đè giá synthetic → PHẢI BỊ CHẶN
    with session_scope() as s:
        settings.data_source = "demo"
        n = repo.upsert_ohlcv(s, "BSR", _df(85_120))
        assert n == 0, "demo đã ghi đè được giá thật!"

    with session_scope() as s:
        rows = s.execute(OHLCV.__table__.select().where(OHLCV.symbol == "BSR")).fetchall()
        assert all(abs(r.close - 25_750) < 1 for r in rows), "giá thật đã bị giá demo ghi đè!"

    settings.data_source = "vnstock"            # trả lại trạng thái


def test_demo_can_write_when_no_existing_data():
    """Demo vẫn ghi được bình thường khi DB chưa có dữ liệu cho mã đó (dùng để phát triển)."""
    with session_scope() as s:
        repo.upsert_symbols(s, [{"symbol": "NEWSYM", "exchange": "HOSE"}])
        settings.data_source = "demo"
        n = repo.upsert_ohlcv(s, "NEWSYM", _df(30_000))
        assert n > 0
    settings.data_source = "vnstock"


if __name__ == "__main__":
    test_demo_cannot_overwrite_real_prices()
    test_demo_can_write_when_no_existing_data()
    print("OK")
