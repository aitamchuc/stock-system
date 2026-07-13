"""Hàm truy cập DB dùng chung (upsert idempotent, load dữ liệu cho engine)."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import settings

from app.models import (
    DailyPick,
    DailyScore,
    DataQualityLog,
    Financial,
    MoneyFlow,
    News,
    NewsImpact,
    NWPick,
    OHLCV,
    PennyPick,
    Recommendation,
    Symbol,
)


def _native(v):
    """Chuyển kiểu numpy → kiểu Python thuần (đệ quy vào dict/list).

    BẮT BUỘC trước khi ghi DB: psycopg2 KHÔNG biết adapt np.float64/np.int64 → nó render thành
    chuỗi 'np.float64(6.4)' và Postgres báo lỗi 'schema "np" does not exist'. SQLite thì bỏ qua
    được (np.float64 là lớp con của float) nên bug chỉ lộ ra trên Postgres/Supabase.
    """
    if isinstance(v, np.generic):          # np.float64, np.int64, np.bool_...
        return v.item()
    if isinstance(v, dict):
        return {k: _native(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_native(x) for x in v]
    return v


def _upsert(session: Session, model, rows: list[dict], pk_cols: list[str]) -> None:
    if not rows:
        return
    rows = [_native(r) for r in rows]
    dialect = session.bind.dialect.name
    ins = sqlite_insert if dialect == "sqlite" else pg_insert
    stmt = ins(model).values(rows)
    update_cols = {c.name: stmt.excluded[c.name]
                   for c in model.__table__.columns if c.name not in pk_cols}
    stmt = stmt.on_conflict_do_update(index_elements=pk_cols, set_=update_cols)
    session.execute(stmt)


def log_quality(session: Session, job: str, level: str, message: str,
                symbol: str | None = None, ts: date | None = None) -> None:
    session.add(DataQualityLog(job=job, symbol=symbol, ts=ts, level=level, message=message))


# ---------- Upserts ----------
def upsert_symbols(session: Session, items: list[dict]) -> None:
    _upsert(session, Symbol, items, ["symbol"])


def upsert_ohlcv(session: Session, symbol: str, df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    rows = [{"symbol": symbol, **{k: r[k] for k in
             ("ts", "open", "high", "low", "close", "volume", "value")}}
            for _, r in df.iterrows()]
    _upsert(session, OHLCV, rows, ["symbol", "ts"])
    return len(rows)


def upsert_money_flow(session: Session, symbol: str, df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    rows = [{"symbol": symbol, **{k: r[k] for k in
             ("ts", "foreign_buy_val", "foreign_sell_val", "foreign_net", "prop_net")}}
            for _, r in df.iterrows()]
    _upsert(session, MoneyFlow, rows, ["symbol", "ts"])
    return len(rows)


def upsert_financials(session: Session, items: list[dict]) -> int:
    valid_cols = {c.name for c in Financial.__table__.columns}
    rows = [{k: v for k, v in it.items() if k in valid_cols} for it in items]
    _upsert(session, Financial, rows, ["symbol", "period"])
    return len(rows)


def insert_news(session: Session, items: list[dict]) -> int:
    if not items:
        return 0
    session.add_all([News(**it) for it in items])
    return len(items)


def upsert_daily_score(session: Session, symbol: str, ts: date, data: dict) -> None:
    row = {"symbol": symbol, "ts": ts, "weights_version": settings.weights_version, **data}
    _upsert(session, DailyScore, [row], ["symbol", "ts"])


# ---------- Loads ----------
def load_ohlcv(session: Session, symbol: str, up_to: date | None = None) -> pd.DataFrame:
    q = select(OHLCV).where(OHLCV.symbol == symbol)
    if up_to:
        q = q.where(OHLCV.ts <= up_to)
    q = q.order_by(OHLCV.ts)
    rows = session.execute(q).scalars().all()
    return pd.DataFrame([{
        "ts": r.ts, "open": r.open, "high": r.high, "low": r.low,
        "close": r.close, "volume": r.volume, "value": r.value,
    } for r in rows])


def load_money_flow(session: Session, symbol: str, up_to: date | None = None) -> pd.DataFrame:
    q = select(MoneyFlow).where(MoneyFlow.symbol == symbol)
    if up_to:
        q = q.where(MoneyFlow.ts <= up_to)
    q = q.order_by(MoneyFlow.ts)
    rows = session.execute(q).scalars().all()
    return pd.DataFrame([{
        "ts": r.ts, "foreign_buy_val": r.foreign_buy_val,
        "foreign_sell_val": r.foreign_sell_val, "foreign_net": r.foreign_net,
        "prop_net": r.prop_net,
    } for r in rows])


def load_financials(session: Session, symbol: str) -> list[Financial]:
    return session.execute(
        select(Financial).where(Financial.symbol == symbol)
    ).scalars().all()


def load_recent_news(session: Session, symbol: str, limit: int = 10) -> list[News]:
    return session.execute(
        select(News).where(News.symbol == symbol)
        .order_by(News.published_at.desc()).limit(limit)
    ).scalars().all()


def active_symbols(session: Session) -> list[Symbol]:
    return session.execute(
        select(Symbol).where(Symbol.is_active.is_(True))
    ).scalars().all()


def symbols_with_new_report(session: Session, ts: date, within_days: int = 3) -> list[str]:
    """Mã có BCTC quý/năm công bố trong khoảng [ts-within_days, ts] (point-in-time)."""
    lo = ts - timedelta(days=within_days)
    rows = session.execute(
        select(Financial.symbol).where(
            Financial.publish_date.is_not(None),
            Financial.publish_date <= ts,
            Financial.publish_date >= lo,
        ).distinct()
    ).scalars().all()
    return list(rows)


def latest_report_period(session: Session, symbol: str, ts: date) -> str | None:
    row = session.execute(
        select(Financial.period).where(
            Financial.symbol == symbol,
            (Financial.publish_date.is_(None)) | (Financial.publish_date <= ts),
        ).order_by(Financial.period.desc()).limit(1)
    ).scalar_one_or_none()
    return row


def upsert_recommendation(session: Session, symbol: str, ts: date, data: dict) -> None:
    row = {"symbol": symbol, "ts": ts, **data}
    valid = {c.name for c in Recommendation.__table__.columns}
    _upsert(session, Recommendation, [{k: v for k, v in row.items() if k in valid}],
            ["symbol", "ts"])


def existing_news_urls(session: Session, urls: list[str]) -> set[str]:
    if not urls:
        return set()
    rows = session.execute(
        select(NewsImpact.url).where(NewsImpact.url.in_(urls))
    ).scalars().all()
    return set(rows)


def insert_news_impacts(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    valid = {c.name for c in NewsImpact.__table__.columns}
    session.add_all([NewsImpact(**_native({k: v for k, v in r.items() if k in valid}))
                     for r in rows])
    return len(rows)


def replace_nw_picks(session: Session, ts: date, rows: list[dict]) -> int:
    session.execute(delete(NWPick).where(NWPick.ts == ts))
    valid = {c.name for c in NWPick.__table__.columns}
    # rows có thể đã chứa 'ts' → gộp rồi ghi đè bằng ts truyền vào (tránh trùng keyword)
    session.add_all([
        NWPick(**_native({**{k: v for k, v in r.items() if k in valid}, "ts": ts}))
        for r in rows
    ])
    return len(rows)


def replace_daily_picks(session: Session, ts: date, rows: list[dict]) -> int:
    """Xóa danh sách chọn lọc cũ của ngày rồi ghi mới (để re-run không để lại mã cũ)."""
    session.execute(delete(DailyPick).where(DailyPick.ts == ts))
    valid = {c.name for c in DailyPick.__table__.columns}
    session.add_all([
        DailyPick(**_native({**{k: v for k, v in r.items() if k in valid}, "ts": ts}))
        for r in rows
    ])
    return len(rows)


def upsert_penny_pick(session: Session, symbol: str, ts: date, data: dict) -> None:
    row = {"symbol": symbol, "ts": ts, **data}
    valid = {c.name for c in PennyPick.__table__.columns}
    _upsert(session, PennyPick, [{k: v for k, v in row.items() if k in valid}],
            ["symbol", "ts"])
