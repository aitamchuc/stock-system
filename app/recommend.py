"""Sinh khuyến nghị giá mua/bán cho các mã CÓ BCTC QUÝ/NĂM MỚI công bố trong ngày.

Chạy trong pipeline hằng ngày, hoặc độc lập:
    python -m app.recommend            # chỉ mã có BCTC mới (within_days=3)
    python -m app.recommend --force    # ép chạy cho toàn bộ mã đã chấm điểm (để xem thử)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from sqlalchemy import func, select

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.bot import telegram
from app.db import init_db, session_scope
from app.engines import recommend as rec_engine
from app.models import DailyScore, Financial, OHLCV
from app import repo


def _build_context(session, symbol: str, ts: date) -> dict | None:
    sc = session.execute(
        select(DailyScore).where(DailyScore.symbol == symbol, DailyScore.ts == ts)
    ).scalar_one_or_none()
    if sc is None:
        return None
    close = session.execute(
        select(OHLCV.close).where(OHLCV.symbol == symbol, OHLCV.ts == ts)
    ).scalar_one_or_none()
    if not close:
        return None
    # Dùng giá thị trường trực tiếp nếu là phiên hôm nay (chính xác hơn giá EOD)
    price = float(close)
    if ts == date.today():
        try:
            from app.providers import get_provider
            lp = get_provider().latest_price(symbol)
            if lp and lp.get("price"):
                price = float(lp["price"])
        except Exception:
            pass
    fin = session.execute(
        select(Financial).where(Financial.symbol == symbol)
        .order_by(Financial.period.desc()).limit(1)
    ).scalar_one_or_none()
    r = sc.rationale or {}
    return {
        "symbol": symbol,
        "current_price": price,
        "support": r.get("support"),
        "resistance": r.get("resistance"),
        "final_score": sc.final_score,
        "signal": sc.signal,
        "pe": fin.pe if fin else None,
        "pb": fin.pb if fin else None,
        "why": r.get("why", ""),
        "main_risks": r.get("main_risks", []),
        "parts": r.get("parts", {}),
        "period": repo.latest_report_period(session, symbol, ts),
    }


def run_recommendations(session, ts: date, *, force: bool = False,
                        within_days: int = 3, send: bool = True) -> list[dict]:
    if force:
        symbols = [s for s in session.execute(
            select(DailyScore.symbol).where(DailyScore.ts == ts)).scalars().all()]
    else:
        symbols = repo.symbols_with_new_report(session, ts, within_days)

    results = []
    for sym in symbols:
        ctx = _build_context(session, sym, ts)
        if ctx is None:
            continue
        data = rec_engine.recommend(ctx)
        repo.upsert_recommendation(session, sym, ts, data)
        payload = {"symbol": sym, **data}
        results.append(payload)
        if send:
            telegram.send_message(telegram.format_recommendation(payload))
    return results


def run(force: bool = False) -> None:
    init_db()
    with session_scope() as s:
        ts = s.execute(select(func.max(DailyScore.ts))).scalar_one_or_none()
        if ts is None:
            print("Chưa có điểm số. Hãy chạy python -m app.pipeline trước.")
            return
        results = run_recommendations(s, ts, force=force)
    if not results:
        print(f"Không có mã nào có BCTC mới trong ngày {ts}. "
              f"Dùng --force để tạo khuyến nghị thử cho toàn bộ mã.")
    else:
        for r in results:
            print(f"{r['symbol']}: mua {r['buy_low']:,.0f}-{r['buy_high']:,.0f} | "
                  f"bán {r['target_price']:,.0f} | cắt lỗ {r['stop_loss']:,.0f} "
                  f"| {r['method']} | {r['conviction']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="Tạo khuyến nghị cho toàn bộ mã đã chấm điểm (bỏ điều kiện BCTC mới)")
    run(ap.parse_args().force)
