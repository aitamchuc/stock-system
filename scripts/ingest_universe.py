"""Nạp lịch sử giá cho TOÀN BỘ mã niêm yết — chạy tiếp được (resumable).

Rate-limit vnstock (guest) là ~18 lệnh/phút → ~1527 mã mất ~85 phút. Script tự dừng khi hết
ngân sách thời gian, lần chạy sau tự bỏ qua mã đã đủ dữ liệu.

    python scripts/ingest_universe.py --minutes 9
    python scripts/ingest_universe.py --minutes 9 --status   # chỉ xem tiến độ

Mã mới nạp được đánh dấu is_active=False để KHÔNG lọt vào pipeline chấm điểm hằng ngày
(watchlist VN30 vẫn giữ is_active=True).
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
from app.models import OHLCV, Symbol  # noqa: E402
from app.providers import get_provider  # noqa: E402
from app import repo  # noqa: E402

MIN_BARS = 300          # đủ cho MA200 + NW + forward return


def _bar_counts(session) -> dict[str, int]:
    rows = session.execute(
        select(OHLCV.symbol, func.count()).group_by(OHLCV.symbol)
    ).all()
    return {s: n for s, n in rows}


def _register_universe(session, listed: list[dict]) -> int:
    """Ghi các mã mới vào bảng symbols với is_active=False (không đụng watchlist đang active)."""
    existing = {s.symbol for s in session.execute(select(Symbol)).scalars().all()}
    new = [{"symbol": d["symbol"], "exchange": d.get("exchange") or "?", "is_active": False}
           for d in listed if d["symbol"] not in existing]
    if new:
        repo.upsert_symbols(session, new)
    return len(new)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=9.0, help="Ngân sách thời gian (phút)")
    ap.add_argument("--status", action="store_true", help="Chỉ in tiến độ rồi thoát")
    args = ap.parse_args()

    if settings.data_source != "vnstock":
        print("❌ Cần DATA_SOURCE=vnstock (tránh ghi dữ liệu demo đè lên giá thật).")
        return

    init_db()
    provider = get_provider()

    with session_scope() as s:
        listed = provider.all_listed_symbols()
        if not listed:
            print("❌ Không lấy được danh sách mã (API vnstock lỗi?).")
            return
        added = _register_universe(s, listed)
        counts = _bar_counts(s)

    universe = [d["symbol"] for d in listed]
    done = [x for x in universe if counts.get(x, 0) >= MIN_BARS]
    todo = [x for x in universe if counts.get(x, 0) < MIN_BARS]
    print(f"Tổng {len(universe)} mã | đã đủ dữ liệu: {len(done)} | còn lại: {len(todo)}"
          f" | mã mới ghi vào symbols: {added}")
    if args.status or not todo:
        if not todo:
            print("✅ Đã nạp xong toàn bộ.")
        return

    deadline = time.monotonic() + args.minutes * 60
    ok = fail = 0
    for sym in todo:
        if time.monotonic() >= deadline:
            break
        try:
            with session_scope() as s:
                n = ingest.ingest_prices(s, sym)
            if n > 0:
                ok += 1
            else:
                fail += 1
        except Exception as exc:
            fail += 1
            print(f"  {sym}: lỗi {str(exc)[:60]}")

    remaining = len(todo) - ok - fail
    print(f"Lượt này: nạp OK {ok}, lỗi/rỗng {fail} | ước còn ~{remaining} mã "
          f"(~{remaining / 18:.0f} phút nữa)")
    if remaining > 0:
        print("→ Chạy lại lệnh này để tiếp tục.")


if __name__ == "__main__":
    main()
