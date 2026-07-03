"""Backtest tín hiệu — chống look-ahead bias.

Chỉ dùng daily_scores (point-in-time) làm điểm vào lệnh, và giá TƯƠNG LAI có thật
để đo forward return. Trừ phí+slippage giả định. So sánh với benchmark (trung bình
toàn rổ như proxy VN-Index cho demo).
"""
from __future__ import annotations

from datetime import date

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DailyScore, OHLCV

FEE_SLIPPAGE = 0.003  # 0.3% mỗi vòng


def _forward_return(session: Session, symbol: str, entry_date: date, horizon: int) -> float | None:
    prices = session.execute(
        select(OHLCV.ts, OHLCV.close).where(OHLCV.symbol == symbol, OHLCV.ts >= entry_date)
        .order_by(OHLCV.ts)
    ).all()
    if len(prices) <= horizon:
        return None
    entry = prices[0][1]
    exit_ = prices[horizon][1]
    if not entry:
        return None
    return (exit_ - entry) / entry - FEE_SLIPPAGE


def run(session: Session, signal: str = "very_positive",
        horizons: tuple[int, ...] = (5, 20, 60)) -> dict:
    trades = session.execute(
        select(DailyScore.symbol, DailyScore.ts).where(DailyScore.signal == signal)
        .order_by(DailyScore.ts)
    ).all()

    result: dict = {"signal": signal, "n_signals": len(trades), "horizons": {}}
    for h in horizons:
        rets, bench = [], []
        for symbol, ts in trades:
            r = _forward_return(session, symbol, ts, h)
            if r is None:
                continue
            rets.append(r)
            b = _benchmark_return(session, ts, h)
            if b is not None:
                bench.append(b)
        if not rets:
            result["horizons"][h] = {"n": 0}
            continue
        arr = np.array(rets)
        result["horizons"][h] = {
            "n": len(arr),
            "win_rate": round(float((arr > 0).mean()), 3),
            "avg_return": round(float(arr.mean()), 4),
            "median_return": round(float(np.median(arr)), 4),
            "max_drawdown": round(float(arr.min()), 4),
            "sharpe_like": round(float(arr.mean() / (arr.std() + 1e-9)), 3),
            "benchmark_avg": round(float(np.mean(bench)), 4) if bench else None,
            "alpha": round(float(arr.mean() - np.mean(bench)), 4) if bench else None,
        }
    return result


def _benchmark_return(session: Session, entry_date: date, horizon: int) -> float | None:
    """Proxy benchmark: trung bình forward return toàn rổ tại entry_date."""
    symbols = session.execute(
        select(OHLCV.symbol).where(OHLCV.ts == entry_date).distinct()
    ).scalars().all()
    rets = []
    for s in symbols:
        r = _forward_return(session, s, entry_date, horizon)
        if r is not None:
            rets.append(r + FEE_SLIPPAGE)  # benchmark không trừ phí giao dịch cá nhân
    return float(np.mean(rets)) if rets else None
