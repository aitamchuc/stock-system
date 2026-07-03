"""Kiểm tra P/E, P/B và điểm định giá sau khi chấm điểm."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.models import DailyScore, Financial, OHLCV  # noqa: E402

with session_scope() as s:
    ts = s.execute(select(func.max(DailyScore.ts))).scalar_one()
    print(f"Phiên: {ts}")
    print(f'{"Mã":<6}{"Giá":>10}{"P/E":>8}{"P/B":>7}{"DinhGia":>9}{"Tổng":>7}')
    print("-" * 47)
    rows = s.execute(
        select(DailyScore).where(DailyScore.ts == ts).order_by(DailyScore.s_valuation.desc())
    ).scalars().all()
    for r in rows:
        close = s.execute(select(OHLCV.close).where(
            OHLCV.symbol == r.symbol, OHLCV.ts == ts)).scalar_one()
        fin = s.execute(select(Financial).where(Financial.symbol == r.symbol)
                        .order_by(Financial.period.desc()).limit(1)).scalar_one_or_none()
        pe = f"{fin.pe:.1f}" if fin and fin.pe else "—"
        pb = f"{fin.pb:.2f}" if fin and fin.pb else "—"
        print(f"{r.symbol:<6}{close:>10,.0f}{pe:>8}{pb:>7}{r.s_valuation:>9.0f}{r.final_score:>7.0f}")
