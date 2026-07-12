"""Nạp BCTC (KQKD + cân đối + lưu chuyển tiền) cho toàn thị trường — resumable.

~1480 mã × 3 lệnh gọi ÷ 16 lệnh/phút ≈ 4,5–5 giờ. Script tự dừng khi hết ngân sách thời gian;
lần chạy sau tự bỏ qua mã đã có BCTC.

    python scripts/ingest_financials.py --minutes 300
    python scripts/ingest_financials.py --status        # chỉ xem tiến độ

Chỉ nạp cho mã có >=300 nến giá (đủ để backtest yếu tố cơ bản). Mã trả rỗng được đánh dấu vào
data_quality_log để lần sau không thử lại vô ích.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import func, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import init_db, session_scope  # noqa: E402
from app.ingestion import ingest  # noqa: E402
from app.models import DataQualityLog, Financial, OHLCV  # noqa: E402

MIN_BARS = 300
NO_DATA_JOB = "fin_no_data"     # đánh dấu mã đã thử nhưng không có BCTC


def _symbols_with_bars(session) -> set[str]:
    rows = session.execute(
        select(OHLCV.symbol).group_by(OHLCV.symbol).having(func.count() >= MIN_BARS)
    ).scalars().all()
    return set(rows)


def _have_financials(session) -> set[str]:
    return set(session.execute(select(Financial.symbol).distinct()).scalars().all())


def _attempted_empty(session) -> set[str]:
    return set(session.execute(
        select(DataQualityLog.symbol).where(DataQualityLog.job == NO_DATA_JOB).distinct()
    ).scalars().all())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=300.0)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if settings.data_source != "vnstock":
        print("❌ Cần DATA_SOURCE=vnstock.")
        return

    init_db()
    with session_scope() as s:
        universe = _symbols_with_bars(s)
        done = _have_financials(s)
        empty = _attempted_empty(s)
    todo = sorted(universe - done - empty)
    print(f"Mã đủ nến: {len(universe)} | đã có BCTC: {len(done)} | "
          f"rỗng (bỏ qua): {len(empty)} | còn lại: {len(todo)}")
    if args.status or not todo:
        if not todo:
            print("✅ Đã nạp xong BCTC toàn bộ.")
        return
    print(f"Ước thời gian còn lại: ~{len(todo) * 3 / 16:.0f} phút (~{len(todo) * 3 / 16 / 60:.1f} giờ)")

    deadline = time.monotonic() + args.minutes * 60
    ok = empty_n = 0
    for sym in todo:
        if time.monotonic() >= deadline:
            break
        try:
            with session_scope() as s:
                n = ingest.ingest_financials(s, sym)
                if n > 0:
                    ok += 1
                else:
                    empty_n += 1
                    s.add(DataQualityLog(job=NO_DATA_JOB, symbol=sym, level="INFO",
                                         message="BCTC rỗng"))
        except Exception as exc:
            print(f"  {sym}: lỗi {str(exc)[:60]}")
    print(f"Lượt này: có BCTC {ok}, rỗng {empty_n}. Chạy lại lệnh để tiếp tục.")


if __name__ == "__main__":
    main()
