"""Smoke test: pipeline chạy end-to-end trên demo data + backtest có kết quả.

Dùng DB riêng (test_stock.db) và ép nguồn demo TRƯỚC khi import app, để không đụng vào
stock.db thật của người dùng và không phụ thuộc mạng.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["DATABASE_URL"] = "sqlite:///./test_stock.db"
os.environ["DATA_SOURCE"] = "demo"

from app.db import init_db, session_scope
from app.pipeline import run_daily
from app.backtest import engine as bt
from app.engines import ta_engine, fundamental
from app.providers.demo_provider import DemoProvider


def test_demo_provider_shapes():
    p = DemoProvider()
    df = p.ohlcv("FPT", "2024-01-01", "2025-06-30")
    assert not df.empty and {"ts", "open", "close", "volume"} <= set(df.columns)
    assert len(p.financials("FPT")) >= 4


def test_ta_engine_scores():
    p = DemoProvider()
    df = p.ohlcv("HPG", "2023-06-01", "2025-06-30")
    res = ta_engine.analyze(df)
    assert 0 <= res["score"] <= 100
    assert res["support"] and res["resistance"]


def test_full_pipeline_and_backtest():
    init_db()
    summary = run_daily(ingest_data=True)
    assert summary["scored"] > 0
    with session_scope() as s:
        result = bt.run(s, signal="very_positive")
    assert "horizons" in result


if __name__ == "__main__":
    test_demo_provider_shapes()
    test_ta_engine_scores()
    test_full_pipeline_and_backtest()
    print("OK - tất cả smoke test pass")
