"""In nhanh bảng xếp hạng phiên mới nhất từ DB (tiện kiểm tra dữ liệu thật)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.models import DailyScore, OHLCV  # noqa: E402

with session_scope() as s:
    ts = s.execute(select(func.max(DailyScore.ts))).scalar_one()
    print("Phiên:", ts)
    rows = s.execute(
        select(DailyScore).where(DailyScore.ts == ts)
        .order_by(DailyScore.final_score.desc())
    ).scalars().all()
    header = f'{"Mã":<6}{"Giá":>11}{"Tổng":>6}{"CoBan":>7}{"KyThuat":>8}{"SucKhoe":>8}{"DinhGia":>8}  Tín hiệu'
    print(header)
    print("-" * len(header))
    for r in rows:
        px = s.execute(
            select(OHLCV.close).where(OHLCV.symbol == r.symbol, OHLCV.ts == ts)
        ).scalar_one()
        print(f'{r.symbol:<6}{px:>11,.0f}{r.final_score:>6.0f}'
              f'{r.s_fundamental:>7.0f}{r.s_technical:>8.0f}'
              f'{r.s_health:>8.0f}{r.s_valuation:>8.0f}  {r.signal}')
