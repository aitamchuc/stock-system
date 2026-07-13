"""Copy lịch sử giá từ DB local → DB cloud (Supabase) — KHÔNG tốn lệnh gọi API.

Vì sao cần: bộ quét toàn thị trường (nw_scan/penny) cần lịch sử giá để tính MA200/CMF/NW.
Nếu DB cloud chỉ có VN30, đa số mã bị bỏ qua âm thầm → kết quả sai (1 mã thay vì ~36).

    python scripts/seed_cloud_ohlcv.py --dest "postgresql://..." --min-liquidity 3e9
    python scripts/seed_cloud_ohlcv.py --dest "..." --status
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
from app.models import OHLCV, Symbol  # noqa: E402
from app import repo  # noqa: E402

CHUNK = 5000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True, help="DATABASE_URL của DB đích (Supabase)")
    ap.add_argument("--src", default="sqlite:///./stock.db", help="DB nguồn (mặc định local)")
    ap.add_argument("--min-liquidity", type=float, default=3e9,
                    help="Chỉ copy mã có GTGD TB 20 phiên >= ngưỡng (mặc định 3 tỷ)")
    ap.add_argument("--min-bars", type=int, default=300)
    ap.add_argument("--status", action="store_true", help="Chỉ xem tình trạng DB đích")
    args = ap.parse_args()

    src_eng = create_engine(_normalize_url(args.src), future=True)
    dst_eng = create_engine(_normalize_url(args.dest), future=True, pool_pre_ping=True)
    Base.metadata.create_all(bind=dst_eng)
    Src = sessionmaker(bind=src_eng)
    Dst = sessionmaker(bind=dst_eng)

    with Dst() as d:
        n_sym = d.execute(text("select count(distinct symbol) from ohlcv")).scalar()
        n_row = d.execute(text("select count(*) from ohlcv")).scalar()
        print(f"DB đích hiện có: {n_sym} mã | {n_row:,} dòng giá")
    if args.status:
        return

    # --- Chọn mã đủ thanh khoản & đủ lịch sử từ DB nguồn ---
    with Src() as s:
        rows = s.execute(
            select(OHLCV.symbol, func.count(), func.avg(OHLCV.value))
            .group_by(OHLCV.symbol).having(func.count() >= args.min_bars)
        ).all()
    picked = [r[0] for r in rows if (r[2] or 0) >= args.min_liquidity]
    print(f"Chọn {len(picked)} mã (>= {args.min_bars} nến, GTGD TB >= {args.min_liquidity/1e9:.0f} tỷ)")

    # --- Copy bảng symbols trước (ohlcv có khóa ngoại tới symbols) ---
    with Src() as s:
        syms = s.execute(select(Symbol).where(Symbol.symbol.in_(picked))).scalars().all()
        sym_rows = [{"symbol": x.symbol, "exchange": x.exchange, "company_name": x.company_name,
                     "industry": x.industry, "market_cap": x.market_cap,
                     "listed_shares": x.listed_shares, "is_active": x.is_active} for x in syms]
    with Dst() as d:
        repo.upsert_symbols(d, sym_rows)
        d.commit()
    print(f"Đã đồng bộ {len(sym_rows)} mã vào bảng symbols")

    # --- Copy OHLCV theo từng mã (bỏ qua mã đích đã đủ dữ liệu) ---
    with Dst() as d:
        have = {r[0]: r[1] for r in d.execute(
            select(OHLCV.symbol, func.count()).group_by(OHLCV.symbol)).all()}

    total = 0
    for i, sym in enumerate(picked, 1):
        if have.get(sym, 0) >= args.min_bars:
            continue
        with Src() as s:
            data = s.execute(select(OHLCV).where(OHLCV.symbol == sym)).scalars().all()
        rows_d = [{"symbol": r.symbol, "ts": r.ts, "open": r.open, "high": r.high,
                   "low": r.low, "close": r.close, "volume": r.volume, "value": r.value}
                  for r in data]
        with Dst() as d:
            for k in range(0, len(rows_d), CHUNK):
                repo.upsert_ohlcv_rows(d, rows_d[k:k + CHUNK])
            d.commit()
        total += len(rows_d)
        if i % 25 == 0 or i == len(picked):
            print(f"  ...{i}/{len(picked)} mã | {total:,} dòng đã copy")

    with Dst() as d:
        n_sym = d.execute(text("select count(distinct symbol) from ohlcv")).scalar()
        n_row = d.execute(text("select count(*) from ohlcv")).scalar()
    print(f"\n✅ Xong. DB đích: {n_sym} mã | {n_row:,} dòng giá")


if __name__ == "__main__":
    main()
