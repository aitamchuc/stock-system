"""Kiểm tra điểm dòng tiền khối ngoại sau khi chấm điểm."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.models import DailyScore, MoneyFlow  # noqa: E402

with session_scope() as s:
    ts = s.execute(select(func.max(DailyScore.ts))).scalar_one()
    print(f"Phiên: {ts}")
    print(f'{"Mã":<6}{"NgoạiRòng(tỷ)":>16}{"ĐiểmDòngTiền":>14}  Tổng')
    print("-" * 46)
    rows = s.execute(
        select(DailyScore).where(DailyScore.ts == ts).order_by(DailyScore.s_moneyflow.desc())
    ).scalars().all()
    for r in rows:
        mf = s.execute(select(MoneyFlow).where(
            MoneyFlow.symbol == r.symbol).order_by(MoneyFlow.ts.desc()).limit(1)).scalar_one_or_none()
        net = (mf.foreign_net / 1e9) if mf and mf.foreign_net is not None else None
        net_s = f"{net:+.1f}" if net is not None else "—"
        print(f"{r.symbol:<6}{net_s:>16}{r.s_moneyflow:>14.0f}{r.final_score:>7.0f}")
