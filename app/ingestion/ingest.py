"""Thu thập dữ liệu từ provider vào DB (idempotent, có retry)."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential

from app import repo
from app.engines import news_nlp
from app.providers import get_provider


def sync_symbols(session: Session) -> int:
    provider = get_provider()
    items = provider.list_symbols()
    repo.upsert_symbols(session, items)
    return len(items)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=20), reraise=True)
def _fetch_ohlcv(provider, symbol, start, end):
    return provider.ohlcv(symbol, start, end)


def ingest_prices(session: Session, symbol: str, lookback_days: int = 400,
                  end: date | None = None) -> int:
    provider = get_provider()
    end = end or date.today()
    start = end - timedelta(days=lookback_days)
    try:
        df = _fetch_ohlcv(provider, symbol, start.isoformat(), end.isoformat())
    except Exception as exc:
        repo.log_quality(session, "ingest_prices", "ERROR", f"lỗi tải giá: {exc}", symbol=symbol)
        return 0
    n = repo.upsert_ohlcv(session, symbol, df)
    if n == 0:
        repo.log_quality(session, "ingest_prices", "WARN", "không có dữ liệu giá", symbol=symbol)
    return n


def ingest_money_flow(session: Session, symbol: str, lookback_days: int = 60,
                      end: date | None = None) -> int:
    provider = get_provider()
    end = end or date.today()
    start = end - timedelta(days=lookback_days)
    df = provider.money_flow(symbol, start.isoformat(), end.isoformat())
    return repo.upsert_money_flow(session, symbol, df)


def ingest_financials(session: Session, symbol: str) -> int:
    provider = get_provider()
    items = provider.financials(symbol)
    return repo.upsert_financials(session, items)


def ingest_news(session: Session, symbol: str | None = None) -> int:
    provider = get_provider()
    items = provider.news(symbol)
    # Chấm sentiment + tóm tắt ngay khi nạp
    for it in items:
        sent, summary = news_nlp.score_single(it.get("title", ""), it.get("event_type"))
        it["sentiment"] = sent
        it["llm_summary"] = summary
    return repo.insert_news(session, items)
