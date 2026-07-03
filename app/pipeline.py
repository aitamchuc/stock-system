"""Orchestrator pipeline hằng ngày. Chạy trực tiếp: `python -m app.pipeline`.

Các bước: ingest → validate → enrich(TA/FA/MF/News) → score → snapshot → alert → telegram.
Không cần Celery/Redis để chạy — phù hợp phát triển & cron đơn giản.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

# Windows console mặc định cp1252 -> đảm bảo in được emoji/tiếng Việt.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import select

from app.alerting import rules
from app.bot import telegram
from app.config import settings
from app.db import init_db, session_scope
from app.engines import fundamental, moneyflow, news_nlp, scoring, ta_engine
from app.ingestion import ingest
from app.models import OHLCV
from app.quality.checks import run_quality_checks
from app import repo


def score_symbol(session, symbol: str, ts: date) -> bool:
    ohlcv = repo.load_ohlcv(session, symbol, up_to=ts)
    if ohlcv.empty:
        return False

    ta = ta_engine.analyze(ohlcv)
    fins = repo.load_financials(session, symbol)
    last_close = float(ohlcv.sort_values("ts")["close"].iloc[-1])
    fa = fundamental.analyze(fins, as_of=ts, price=last_close)
    # Lưu P/E, P/B hiện tại vào kỳ BCTC gần nhất để dashboard hiển thị (giá đổi theo ngày)
    if fins and (fa.get("pe") is not None or fa.get("pb") is not None):
        latest_fin = max(fins, key=lambda f: f.period)
        latest_fin.pe, latest_fin.pb = fa.get("pe"), fa.get("pb")
    mf_df = repo.load_money_flow(session, symbol, up_to=ts)
    mf = moneyflow.analyze(mf_df, ohlcv)
    news_items = repo.load_recent_news(session, symbol, limit=10)
    news = news_nlp.aggregate(news_items)

    liquidity = float(ohlcv.sort_values("ts")["value"].tail(20).mean() or 0)
    result = scoring.combine(
        ta=ta, fa=fa, mf=mf, news=news,
        liquidity_value=liquidity, weights=settings.weights,
    )
    repo.upsert_daily_score(session, symbol, ts, result)
    return True


def run_daily(ingest_data: bool = True, trade_date: date | None = None) -> dict:
    init_db()
    summary = {"ingested": 0, "scored": 0, "alerts": 0, "skipped": 0}

    # Làm mới snapshot khối ngoại (nếu dùng vnstock)
    try:
        from app.providers.vnstock_provider import reset_board_cache
        reset_board_cache()
    except Exception:
        pass

    with session_scope() as session:
        # 0. Đảm bảo có danh mục mã
        ingest.sync_symbols(session)
        symbols = [s.symbol for s in repo.active_symbols(session)]

    # 1. Ingest (mỗi mã 1 transaction để lỗi 1 mã không kéo sập cả rổ)
    if ingest_data:
        for sym in symbols:
            with session_scope() as session:
                ingest.ingest_prices(session, sym)
                ingest.ingest_money_flow(session, sym)
                ingest.ingest_financials(session, sym)
                ingest.ingest_news(session, sym)
                summary["ingested"] += 1

    # Xác định trade_date = phiên mới nhất có trong DB
    with session_scope() as session:
        if trade_date is None:
            trade_date = session.execute(
                select(OHLCV.ts).order_by(OHLCV.ts.desc()).limit(1)
            ).scalar_one_or_none()
        if trade_date is None:
            print("[pipeline] Không có dữ liệu giá — dừng.")
            return summary

        # 2. Quality check
        quality = run_quality_checks(session, symbols, trade_date)

        # 3+4. Enrich + score từng mã sạch
        for sym in symbols:
            if not quality.get(sym, False):
                summary["skipped"] += 1
                continue
            if score_symbol(session, sym, trade_date):
                summary["scored"] += 1

    # 5. Đánh giá cảnh báo (luôn LƯU DB cho dashboard; chỉ gửi Telegram nếu bật cờ)
    with session_scope() as session:
        alerts = rules.evaluate(session, trade_date)
    if settings.push_individual_alerts:
        telegram.send_many(alerts)
    summary["alerts"] = len(alerts)

    # 6. Khuyến nghị giá cho mã có BCTC mới (lưu DB; không spam Telegram ở đây)
    from app.recommend import run_recommendations
    with session_scope() as session:
        recs = run_recommendations(session, trade_date, within_days=3, send=False)
    summary["recommendations"] = len(recs)

    # 7. AI CHỌN LỌC cổ phiếu NÊN ĐẦU TƯ → đây là nội dung DUY NHẤT gửi Telegram
    from app.curate import curate
    with session_scope() as session:
        picks = curate(session, trade_date, send=True)
    summary["picks"] = len(picks)
    summary["trade_date"] = str(trade_date)

    print(f"[pipeline] Hoàn tất {trade_date}: {summary}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chạy pipeline chấm điểm hằng ngày")
    parser.add_argument("--no-ingest", action="store_true", help="Bỏ qua bước thu thập dữ liệu")
    args = parser.parse_args()
    run_daily(ingest_data=not args.no_ingest)
