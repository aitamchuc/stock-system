"""Rule engine: quét daily_scores → sinh cảnh báo (dedupe theo symbol/ts/type)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Alert, DailyScore, OHLCV


def _already_sent(session: Session, symbol: str, ts: date, alert_type: str) -> bool:
    return session.execute(
        select(Alert).where(Alert.symbol == symbol, Alert.ts == ts,
                            Alert.alert_type == alert_type)
    ).first() is not None


def evaluate(session: Session, ts: date) -> list[dict]:
    """Trả list payload cảnh báo cần gửi."""
    scores = session.execute(
        select(DailyScore).where(DailyScore.ts == ts)
    ).scalars().all()

    alerts: list[dict] = []
    for sc in scores:
        ohlcv = session.execute(
            select(OHLCV).where(OHLCV.symbol == sc.symbol, OHLCV.ts == ts)
        ).scalar_one_or_none()
        price = ohlcv.close if ohlcv else None
        ind = (sc.rationale or {}).get("parts", {})

        triggered: list[str] = []
        if sc.final_score >= settings.alert_min_score:
            triggered.append("high_score")
        if sc.signal in ("very_positive", "positive") and sc.s_technical >= 70:
            triggered.append("breakout")
        if sc.s_moneyflow >= 70:
            triggered.append("foreign_inflow")
        if sc.signal in ("risk_warning", "distribution", "avoid"):
            triggered.append("risk")

        for atype in triggered:
            if _already_sent(session, sc.symbol, ts, atype):
                continue
            r = sc.rationale or {}
            payload = {
                "symbol": sc.symbol,
                "price": price,
                "final_score": sc.final_score,
                "signal": sc.signal,
                "alert_type": atype,
                "main_reason": (r.get("why") or ""),
                "support": r.get("support"),
                "resistance": r.get("resistance"),
                "main_risk": "; ".join((r.get("main_risks") or [])[:2]) or "Không có cảnh báo đặc biệt",
                "dashboard_url": f"{settings.dashboard_base_url}/stock/{sc.symbol}",
            }
            alerts.append(payload)
            session.add(Alert(symbol=sc.symbol, ts=ts, alert_type=atype, payload=payload))
    return alerts
