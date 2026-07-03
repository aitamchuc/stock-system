"""Backfill điểm số theo lịch sử để backtest có dữ liệu.

Ingest 1 lần (nạp toàn bộ OHLCV lịch sử), sau đó chấm điểm point-in-time cho từng
phiên trong quá khứ (mỗi phiên chỉ dùng dữ liệu <= phiên đó). Nhờ vậy backtest có
nhiều tín hiệu + có giá tương lai thật để đo hiệu quả.

    python scripts/backfill.py --days 180
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import init_db, session_scope  # noqa: E402
from app.ingestion import ingest  # noqa: E402
from app.models import OHLCV  # noqa: E402
from app.pipeline import score_symbol  # noqa: E402
from app.quality.checks import check_symbol  # noqa: E402
from app import repo  # noqa: E402


def main(days: int) -> None:
    init_db()
    with session_scope() as s:
        ingest.sync_symbols(s)
        symbols = [x.symbol for x in repo.active_symbols(s)]

    print(f"[backfill] Ingest dữ liệu lịch sử cho {len(symbols)} mã...")
    for sym in symbols:
        with session_scope() as s:
            ingest.ingest_prices(s, sym, lookback_days=days + 260)
            ingest.ingest_money_flow(s, sym, lookback_days=days + 30)
            ingest.ingest_financials(s, sym)
            ingest.ingest_news(s, sym)

    # Lấy danh sách phiên giao dịch (trừ vài phiên cuối để còn giá tương lai đo return)
    with session_scope() as s:
        all_dates = s.execute(
            select(OHLCV.ts).distinct().order_by(OHLCV.ts)
        ).scalars().all()
    trade_dates = all_dates[-days:-5] if len(all_dates) > days else all_dates[:-5]

    print(f"[backfill] Chấm điểm point-in-time cho {len(trade_dates)} phiên...")
    total = 0
    for i, ts in enumerate(trade_dates):
        with session_scope() as s:
            for sym in symbols:
                ok, _ = check_symbol(s, sym, ts)
                if ok and score_symbol(s, sym, ts):
                    total += 1
        if i % 20 == 0:
            print(f"  ...{ts} ({i+1}/{len(trade_dates)})")
    print(f"[backfill] Xong: {total} bản ghi điểm. Giờ chạy backtest qua /api/backtest.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180, help="Số phiên lịch sử để backfill")
    main(ap.parse_args().days)
