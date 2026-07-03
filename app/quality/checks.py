"""Kiểm tra chất lượng dữ liệu trước khi scoring. Trả danh sách mã 'sạch'."""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from app import repo


def check_symbol(session: Session, symbol: str, ts: date) -> tuple[bool, list[str]]:
    issues: list[str] = []
    df = repo.load_ohlcv(session, symbol, up_to=ts)

    if df.empty:
        issues.append("Không có dữ liệu giá")
        return False, issues
    if len(df) < 60:
        issues.append(f"Chỉ có {len(df)} phiên (<60) — không đủ cho phân tích kỹ thuật")
    if (df["close"] <= 0).any():
        issues.append("Có giá đóng cửa <= 0")
    if (df["volume"] < 0).any():
        issues.append("Có khối lượng âm")

    # Cảnh báo gap dữ liệu lớn (không chặn)
    df = df.sort_values("ts")
    gaps = pd.to_datetime(df["ts"]).diff().dt.days.fillna(1)
    if (gaps > 7).sum() > 0:
        issues.append("Có khoảng trống dữ liệu > 7 ngày")

    blocking = df.empty or len(df) < 60 or (df["close"] <= 0).any()
    return (not blocking), issues


def run_quality_checks(session: Session, symbols: list[str], ts: date) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for s in symbols:
        ok, issues = check_symbol(session, s, ts)
        result[s] = ok
        for msg in issues:
            level = "ERROR" if not ok else "WARN"
            repo.log_quality(session, "quality_check", level, msg, symbol=s, ts=ts)
    return result
