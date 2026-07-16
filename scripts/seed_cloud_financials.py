"""Copy BCTC từ DB local → DB cloud (Supabase) — KHÔNG tốn lệnh gọi API.

Vì sao cần: nạp BCTC qua vnstock mất ~4.5 giờ (3 lệnh gọi/mã, rate-limit 16/phút). Máy local
đã có sẵn 1200+ mã → chép thẳng lên cloud để bot/pipeline dùng được ngay mà không phải nạp lại.

    python scripts/seed_cloud_financials.py --dest "postgresql://..."
    python scripts/seed_cloud_financials.py --dest "..." --status
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import create_engine, func, select, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db import Base, _normalize_url  # noqa: E402
from app.models import Financial, OHLCV, Symbol  # noqa: E402
from app import repo  # noqa: E402

CHUNK = 40          # số mã mỗi lô ghi


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True, help="DATABASE_URL của DB đích (Supabase)")
    ap.add_argument("--src", default="sqlite:///./stock.db")
    ap.add_argument("--only-with-prices", action="store_true", default=True,
                    help="Chỉ copy BCTC của mã đã có giá ở DB đích (mặc định)")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    src_eng = create_engine(_normalize_url(args.src), future=True)
    dst_eng = create_engine(_normalize_url(args.dest), future=True, pool_pre_ping=True)
    Base.metadata.create_all(bind=dst_eng)
    Src = sessionmaker(bind=src_eng)
    Dst = sessionmaker(bind=dst_eng)

    with Dst() as d:
        n = d.execute(text("select count(distinct symbol) from financials")).scalar()
        rows = d.execute(text("select count(*) from financials")).scalar()
        print(f"DB đích hiện có BCTC: {n} mã | {rows:,} kỳ")
    if args.status:
        return

    with Src() as s:
        src_syms = set(s.execute(select(Financial.symbol).distinct()).scalars().all())
    with Dst() as d:
        have = set(d.execute(select(Financial.symbol).distinct()).scalars().all())
        # BCTC có khóa ngoại tới symbols → chỉ copy mã đã tồn tại ở đích
        dst_syms = set(d.execute(select(Symbol.symbol)).scalars().all())
        if args.only_with_prices:
            priced = set(d.execute(select(OHLCV.symbol).distinct()).scalars().all())
            dst_syms &= priced

    todo = sorted((src_syms & dst_syms) - have)
    print(f"Nguồn có {len(src_syms)} mã | đích đã có {len(have)} | sẽ copy {len(todo)} mã")
    if not todo:
        print("✅ Không có gì để copy.")
        return

    total = 0
    for i in range(0, len(todo), CHUNK):
        batch = todo[i:i + CHUNK]
        with Src() as s:
            recs = s.execute(select(Financial).where(Financial.symbol.in_(batch))).scalars().all()
        cols = [c.name for c in Financial.__table__.columns]
        rows = [{c: getattr(r, c) for c in cols} for r in recs]
        with Dst() as d:
            repo.upsert_financials(d, rows)
            d.commit()
        total += len(rows)
        print(f"  ...{min(i + CHUNK, len(todo))}/{len(todo)} mã | {total:,} kỳ BCTC")

    with Dst() as d:
        n = d.execute(text("select count(distinct symbol) from financials")).scalar()
    print(f"\n✅ Xong. DB đích giờ có BCTC: {n} mã")


if __name__ == "__main__":
    main()
