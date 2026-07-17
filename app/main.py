"""FastAPI app: REST API + dashboard (Jinja2). Chạy: `uvicorn app.main:app --reload`."""
from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.backtest import engine as backtest_engine
from app.db import get_db, init_db
from app.engines.scoring import SIGNAL_LABELS
from app.models import (
    DailyPick,
    DailyScore,
    DataQualityLog,
    Financial,
    MoneyFlow,
    News,
    NewsImpact,
    OHLCV,
    PennyPick,
    Recommendation,
    Symbol,
)
from app.schemas import DISCLAIMER, RankingItem, RankingResponse

app = FastAPI(title="VN Stock Ranking & Alert API", version="1.0.0")

# Bot Telegram chạy 24/7 qua webhook (không cần tiến trình long-polling → dùng được gói free)
from app.bot.webhook import router as telegram_router  # noqa: E402

app.include_router(telegram_router)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.cache = None  # tránh lỗi LRUCache của Jinja trên Python 3.14


@app.on_event("startup")
def _startup() -> None:
    # KHÔNG để lỗi DB làm sập cả web service (nếu không, sai DATABASE_URL → crash-loop →
    # bot webhook + dashboard + health đều chết, không chẩn đoán được). Chạy tiếp, thử lại sau.
    try:
        init_db()
        print("[startup] init_db OK")
    except Exception as exc:
        print(f"[startup] ⚠️ init_db lỗi (service vẫn chạy, sẽ thử lại mỗi request): {str(exc)[:120]}")


@app.middleware("http")
async def _ensure_db(request: Request, call_next):
    """Nếu init_db lúc khởi động thất bại (vd DB tạm lỗi), tạo bảng ở request đầu chạm DB."""
    if not getattr(app.state, "db_ready", False):
        try:
            init_db()
            app.state.db_ready = True
        except Exception:
            pass
    return await call_next(request)


def _latest_ts(db: Session):
    return db.execute(select(func.max(DailyScore.ts))).scalar_one_or_none()


# ---------------- REST API ----------------
@app.get("/api/health")
def health():
    # Chỉ báo cấu hình (boolean, KHÔNG lộ giá trị bí mật) — để chẩn đoán deploy từ xa.
    from app.config import settings as _s
    return {
        "status": "ok",
        "config": {
            "webhook_secret_set": bool(_s.telegram_webhook_secret),
            "telegram_configured": bool(_s.telegram_token and _s.telegram_chat_id),
            "openai_set": bool(_s.openai_api_key),
            "model": _s.openai_model,
            "db": "postgres" if "postgres" in _s.database_url else "sqlite/other",
        },
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/live")
def live(symbols: str | None = None, db: Session = Depends(get_db)):
    """Giá thị trường trực tiếp (gần thời gian thực) cho watchlist hoặc danh sách mã truyền vào."""
    from app.providers import get_provider

    if symbols:
        syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        syms = [s.symbol for s in db.execute(
            select(Symbol).where(Symbol.is_active.is_(True))).scalars().all()]
    try:
        data = get_provider().live_prices(syms)
    except Exception as exc:
        return {"error": str(exc), "prices": {}}
    return {"disclaimer": DISCLAIMER, "count": len(data), "prices": data}


@app.get("/api/ranking", response_model=RankingResponse)
def ranking(
    signal: str | None = None,
    industry: str | None = None,
    exchange: str | None = None,
    min_score: float = 0,
    min_liquidity: float = 0,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
):
    ts = _latest_ts(db)
    if ts is None:
        return RankingResponse(as_of=None, count=0, items=[])

    q = (
        select(DailyScore, Symbol, OHLCV)
        .join(Symbol, Symbol.symbol == DailyScore.symbol)
        .join(OHLCV, (OHLCV.symbol == DailyScore.symbol) & (OHLCV.ts == DailyScore.ts))
        .where(DailyScore.ts == ts, DailyScore.final_score >= min_score)
    )
    if signal:
        q = q.where(DailyScore.signal == signal)
    if industry:
        q = q.where(Symbol.industry == industry)
    if exchange:
        q = q.where(Symbol.exchange == exchange)
    q = q.order_by(DailyScore.final_score.desc()).limit(limit)

    items = []
    for sc, sym, oh in db.execute(q).all():
        liq = oh.value or 0
        if liq < min_liquidity:
            continue
        items.append(RankingItem(
            symbol=sc.symbol, exchange=sym.exchange, industry=sym.industry,
            company_name=sym.company_name, close=oh.close, liquidity=liq,
            final_score=sc.final_score, signal=sc.signal,
            signal_label=SIGNAL_LABELS.get(sc.signal, sc.signal),
        ))
    return RankingResponse(as_of=ts, count=len(items), items=items)


@app.get("/api/stock/{symbol}")
def stock_detail(symbol: str, db: Session = Depends(get_db)):
    symbol = symbol.upper()
    sym = db.get(Symbol, symbol)
    if sym is None:
        return JSONResponse({"error": "symbol not found"}, status_code=404)

    ts = _latest_ts(db)
    score = db.execute(
        select(DailyScore).where(DailyScore.symbol == symbol, DailyScore.ts == ts)
    ).scalar_one_or_none()

    prices = db.execute(
        select(OHLCV).where(OHLCV.symbol == symbol).order_by(OHLCV.ts.desc()).limit(120)
    ).scalars().all()
    fins = db.execute(
        select(Financial).where(Financial.symbol == symbol).order_by(Financial.period)
    ).scalars().all()
    news = db.execute(
        select(News).where(News.symbol == symbol).order_by(News.published_at.desc()).limit(10)
    ).scalars().all()
    flows = db.execute(
        select(MoneyFlow).where(MoneyFlow.symbol == symbol).order_by(MoneyFlow.ts.desc()).limit(20)
    ).scalars().all()
    rec = db.execute(
        select(Recommendation).where(Recommendation.symbol == symbol)
        .order_by(Recommendation.ts.desc()).limit(1)
    ).scalar_one_or_none()
    try:
        from app.providers import get_provider
        live_price = get_provider().latest_price(symbol)
    except Exception:
        live_price = None

    return {
        "disclaimer": DISCLAIMER,
        "symbol": symbol,
        "live": live_price,
        "recommendation": None if not rec else {
            "as_of": str(rec.ts), "report_period": rec.report_period,
            "current_price": rec.current_price,
            "buy_low": rec.buy_low, "buy_high": rec.buy_high,
            "target_price": rec.target_price, "stop_loss": rec.stop_loss,
            "fair_value": rec.fair_value, "expected_return": rec.expected_return,
            "risk_reward": rec.risk_reward, "conviction": rec.conviction,
            "method": rec.method, "thesis": rec.thesis,
        },
        "company_name": sym.company_name,
        "exchange": sym.exchange,
        "industry": sym.industry,
        "score": None if not score else {
            "as_of": str(score.ts),
            "final_score": score.final_score,
            "signal": score.signal,
            "signal_label": SIGNAL_LABELS.get(score.signal, score.signal),
            "parts": {
                "fundamental": score.s_fundamental, "growth": score.s_growth,
                "health": score.s_health, "valuation": score.s_valuation,
                "technical": score.s_technical, "moneyflow": score.s_moneyflow,
                "news": score.s_news, "risk": score.s_risk,
            },
            "rationale": score.rationale,
        },
        "prices": [{"ts": str(p.ts), "open": p.open, "high": p.high, "low": p.low,
                    "close": p.close, "volume": p.volume} for p in reversed(prices)],
        "financials": [{"period": f.period, "revenue": f.revenue, "net_income": f.net_income,
                        "roe": f.roe, "roa": f.roa, "net_margin": f.net_margin,
                        "pe": f.pe, "pb": f.pb} for f in fins],
        "money_flow": [{"ts": str(m.ts), "foreign_net": m.foreign_net, "prop_net": m.prop_net}
                       for m in reversed(flows)],
        "news": [{"published_at": str(n.published_at), "title": n.title, "url": n.url,
                  "sentiment": n.sentiment, "event_type": n.event_type} for n in news],
    }


@app.get("/api/recommendations")
def recommendations(db: Session = Depends(get_db)):
    ts = db.execute(select(func.max(Recommendation.ts))).scalar_one_or_none()
    if ts is None:
        return {"as_of": None, "disclaimer": DISCLAIMER, "items": []}
    rows = db.execute(
        select(Recommendation).where(Recommendation.ts == ts)
        .order_by(Recommendation.expected_return.desc())
    ).scalars().all()
    return {
        "as_of": str(ts),
        "disclaimer": DISCLAIMER,
        "items": [{
            "symbol": r.symbol, "report_period": r.report_period,
            "current_price": r.current_price, "buy_low": r.buy_low, "buy_high": r.buy_high,
            "target_price": r.target_price, "stop_loss": r.stop_loss,
            "expected_return": r.expected_return, "risk_reward": r.risk_reward,
            "conviction": r.conviction, "method": r.method, "thesis": r.thesis,
        } for r in rows],
    }


@app.get("/api/picks")
def daily_picks(db: Session = Depends(get_db)):
    """Cổ phiếu NÊN ĐẦU TƯ do AI chọn lọc (phiên mới nhất)."""
    ts = db.execute(select(func.max(DailyPick.ts))).scalar_one_or_none()
    if ts is None:
        return {"as_of": None, "disclaimer": DISCLAIMER, "items": []}
    rows = db.execute(
        select(DailyPick).where(DailyPick.ts == ts)
        .order_by(DailyPick.final_score.desc())
    ).scalars().all()
    return {
        "as_of": str(ts), "disclaimer": DISCLAIMER, "count": len(rows),
        "items": [{
            "symbol": r.symbol, "action": r.action, "conviction": r.conviction,
            "final_score": r.final_score, "thesis": r.thesis,
            "buy_low": r.buy_low, "buy_high": r.buy_high,
            "target_price": r.target_price, "stop_loss": r.stop_loss, "method": r.method,
        } for r in rows],
    }


@app.get("/api/news")
def news_impact_feed(only_notable: bool = True, limit: int = 40, db: Session = Depends(get_db)):
    """Tin tức đã phân tích ảnh hưởng (AI). only_notable=true chỉ lấy tin ảnh hưởng cao/trung bình."""
    q = select(NewsImpact).order_by(NewsImpact.id.desc()).limit(limit)
    if only_notable:
        q = select(NewsImpact).where(
            NewsImpact.relevant.is_(True),
            NewsImpact.impact_level.in_(["cao", "trung bình"]),
        ).order_by(NewsImpact.id.desc()).limit(limit)
    rows = db.execute(q).scalars().all()
    return {
        "disclaimer": DISCLAIMER,
        "count": len(rows),
        "items": [{
            "title": r.title, "url": r.url, "source": r.source, "region": r.region,
            "published_at": str(r.published_at) if r.published_at else None,
            "scope": r.scope, "impact_level": r.impact_level, "direction": r.direction,
            "affected_symbols": r.affected_symbols, "sectors": r.sectors,
            "analysis": r.analysis,
        } for r in rows],
    }


@app.get("/api/penny")
def penny(db: Session = Depends(get_db)):
    """Ứng viên cổ phiếu penny tiềm năng (ĐẦU CƠ RỦI RO RẤT CAO)."""
    ts = db.execute(select(func.max(PennyPick.ts))).scalar_one_or_none()
    if ts is None:
        return {"as_of": None, "disclaimer": DISCLAIMER, "items": []}
    rows = db.execute(
        select(PennyPick).where(PennyPick.ts == ts)
        .order_by(PennyPick.upside_score.desc())
    ).scalars().all()
    return {
        "as_of": str(ts),
        "warning": "Cổ phiếu penny đầu cơ RỦI RO RẤT CAO — có thể bị làm giá/kéo xả và mất phần lớn vốn. "
                   "Đây KHÔNG phải khuyến nghị mua.",
        "disclaimer": DISCLAIMER,
        "items": [{
            "symbol": r.symbol, "exchange": r.exchange, "price": r.price,
            "liquidity": r.liquidity, "upside_score": r.upside_score, "risk_score": r.risk_score,
            "return_1m_pct": r.return_1m_pct, "atr_pct": r.atr_pct,
            "volume_zscore": r.volume_zscore, "foreign_net": r.foreign_net,
            "signals": r.signals, "warnings": r.warnings,
        } for r in rows],
    }


@app.get("/api/backtest")
def backtest(signal: str = "very_positive", db: Session = Depends(get_db)):
    return backtest_engine.run(db, signal=signal)


@app.get("/api/quality-log")
def quality_log(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.execute(
        select(DataQualityLog).order_by(DataQualityLog.created_at.desc()).limit(limit)
    ).scalars().all()
    return [{"job": r.job, "symbol": r.symbol, "ts": str(r.ts) if r.ts else None,
             "level": r.level, "message": r.message,
             "created_at": str(r.created_at)} for r in rows]


# ---------------- Dashboard ----------------
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    resp = ranking(limit=100, db=db)
    return templates.TemplateResponse(request, "dashboard.html", {
        "items": resp.items, "as_of": resp.as_of,
        "disclaimer": DISCLAIMER, "signal_labels": SIGNAL_LABELS,
    })


@app.get("/stock/{symbol}", response_class=HTMLResponse)
def stock_page(request: Request, symbol: str, db: Session = Depends(get_db)):
    data = stock_detail(symbol, db)
    if isinstance(data, JSONResponse):
        return HTMLResponse("<h1>Không tìm thấy mã</h1>", status_code=404)
    return templates.TemplateResponse(request, "stock.html", {"d": data})
