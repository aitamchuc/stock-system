"""ORM models — ánh xạ schema đã thiết kế.

Nguyên tắc quan trọng: `daily_scores` là APPEND-ONLY theo (symbol, ts) để đảm bảo
point-in-time, tránh look-ahead bias khi backtest.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# BigInteger không tự tăng trên SQLite (chỉ INTEGER PRIMARY KEY mới auto-increment).
# Dùng variant để SQLite dùng INTEGER, Postgres dùng BIGINT.
AutoPK = BigInteger().with_variant(Integer, "sqlite")


class Symbol(Base):
    __tablename__ = "symbols"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(8))            # HOSE|HNX|UPCOM
    company_name: Mapped[str | None] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(128))
    market_cap: Mapped[float | None] = mapped_column(Float)
    listed_shares: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class OHLCV(Base):
    __tablename__ = "ohlcv"

    symbol: Mapped[str] = mapped_column(String(16), ForeignKey("symbols.symbol"), primary_key=True)
    ts: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(BigInteger)
    value: Mapped[float | None] = mapped_column(Float)          # giá trị GD ~ thanh khoản


class MoneyFlow(Base):
    __tablename__ = "money_flow"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    ts: Mapped[date] = mapped_column(Date, primary_key=True)
    foreign_buy_val: Mapped[float | None] = mapped_column(Float)
    foreign_sell_val: Mapped[float | None] = mapped_column(Float)
    foreign_net: Mapped[float | None] = mapped_column(Float)
    prop_net: Mapped[float | None] = mapped_column(Float)       # tự doanh ròng


class Financial(Base):
    __tablename__ = "financials"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    period: Mapped[str] = mapped_column(String(8), primary_key=True)  # '2025Q1' | '2024'
    revenue: Mapped[float | None] = mapped_column(Float)
    gross_profit: Mapped[float | None] = mapped_column(Float)
    net_income: Mapped[float | None] = mapped_column(Float)
    gross_margin: Mapped[float | None] = mapped_column(Float)
    net_margin: Mapped[float | None] = mapped_column(Float)
    roe: Mapped[float | None] = mapped_column(Float)
    roa: Mapped[float | None] = mapped_column(Float)
    total_debt: Mapped[float | None] = mapped_column(Float)
    equity: Mapped[float | None] = mapped_column(Float)
    share_capital: Mapped[float | None] = mapped_column(Float)   # vốn góp (paid-in) → số cp = /10000
    cash: Mapped[float | None] = mapped_column(Float)
    cfo: Mapped[float | None] = mapped_column(Float)            # dòng tiền kinh doanh
    fcf: Mapped[float | None] = mapped_column(Float)
    inventory: Mapped[float | None] = mapped_column(Float)
    receivables: Mapped[float | None] = mapped_column(Float)
    payables: Mapped[float | None] = mapped_column(Float)
    eps: Mapped[float | None] = mapped_column(Float)
    pe: Mapped[float | None] = mapped_column(Float)
    pb: Mapped[float | None] = mapped_column(Float)
    ev_ebitda: Mapped[float | None] = mapped_column(Float)
    publish_date: Mapped[date | None] = mapped_column(Date)     # QUAN TRỌNG cho point-in-time


class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(AutoPK, primary_key=True, autoincrement=True)
    symbol: Mapped[str | None] = mapped_column(String(16), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    sentiment: Mapped[float | None] = mapped_column(Float)      # -1..1
    event_type: Mapped[str | None] = mapped_column(String(32))  # dividend|issuance|agm|buyback|insider|other
    llm_summary: Mapped[str | None] = mapped_column(Text)


class DailyScore(Base):
    __tablename__ = "daily_scores"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    ts: Mapped[date] = mapped_column(Date, primary_key=True)
    s_fundamental: Mapped[float] = mapped_column(Float, default=0)
    s_growth: Mapped[float] = mapped_column(Float, default=0)
    s_health: Mapped[float] = mapped_column(Float, default=0)
    s_valuation: Mapped[float] = mapped_column(Float, default=0)
    s_technical: Mapped[float] = mapped_column(Float, default=0)
    s_moneyflow: Mapped[float] = mapped_column(Float, default=0)
    s_news: Mapped[float] = mapped_column(Float, default=0)
    s_risk: Mapped[float] = mapped_column(Float, default=0)
    final_score: Mapped[float] = mapped_column(Float, default=0)
    signal: Mapped[str] = mapped_column(String(32), default="neutral")
    rationale: Mapped[dict] = mapped_column(JSON, default=dict)
    weights_version: Mapped[str] = mapped_column(String(16), default="v1")


class Recommendation(Base):
    """Khuyến nghị giá mua/bán do AI agent tạo cho mã có BCTC mới (append-only theo ngày).

    ⚠️ Chỉ tham khảo — KHÔNG phải khuyến nghị đầu tư, KHÔNG cam kết lợi nhuận.
    """
    __tablename__ = "recommendations"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    ts: Mapped[date] = mapped_column(Date, primary_key=True)
    report_period: Mapped[str | None] = mapped_column(String(8))   # kỳ BCTC kích hoạt
    current_price: Mapped[float | None] = mapped_column(Float)
    buy_low: Mapped[float | None] = mapped_column(Float)
    buy_high: Mapped[float | None] = mapped_column(Float)
    target_price: Mapped[float | None] = mapped_column(Float)       # giá bán/chốt lời
    stop_loss: Mapped[float | None] = mapped_column(Float)
    fair_value: Mapped[float | None] = mapped_column(Float)
    expected_return: Mapped[float | None] = mapped_column(Float)    # (target/buy_mid - 1)
    risk_reward: Mapped[float | None] = mapped_column(Float)
    conviction: Mapped[str | None] = mapped_column(String(16))      # cao|trung bình|thấp
    method: Mapped[str | None] = mapped_column(String(8))           # llm|rule
    thesis: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class NewsImpact(Base):
    """Bài báo kinh tế + phân tích AI về mức độ/chiều ảnh hưởng tới giá cổ phiếu.

    ⚠️ Phân tích tham khảo, không phải khuyến nghị đầu tư.
    """
    __tablename__ = "news_impact"

    id: Mapped[int] = mapped_column(AutoPK, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str | None] = mapped_column(String(64))
    region: Mapped[str | None] = mapped_column(String(8))          # VN | World
    title: Mapped[str | None] = mapped_column(Text)
    relevant: Mapped[bool] = mapped_column(Boolean, default=False)  # có liên quan TTCK VN không
    scope: Mapped[str | None] = mapped_column(String(16))          # macro | sector | company
    impact_level: Mapped[str | None] = mapped_column(String(16))   # cao | trung bình | thấp
    direction: Mapped[str | None] = mapped_column(String(16))      # tích cực | tiêu cực | trung tính
    affected_symbols: Mapped[dict] = mapped_column(JSON, default=list)
    sectors: Mapped[dict] = mapped_column(JSON, default=list)
    analysis: Mapped[str | None] = mapped_column(Text)             # AI giải thích ảnh hưởng
    scanned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PennyPick(Base):
    """Ứng viên cổ phiếu penny tiềm năng (đầu cơ, rủi ro rất cao). Append-only theo ngày.

    ⚠️ Chỉ để nghiên cứu — KHÔNG phải khuyến nghị mua, KHÔNG hứa hẹn tăng giá.
    """
    __tablename__ = "penny_picks"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    ts: Mapped[date] = mapped_column(Date, primary_key=True)
    exchange: Mapped[str | None] = mapped_column(String(8))
    price: Mapped[float | None] = mapped_column(Float)
    liquidity: Mapped[float | None] = mapped_column(Float)
    upside_score: Mapped[float] = mapped_column(Float, default=0)     # tiềm năng 0-100
    risk_score: Mapped[float] = mapped_column(Float, default=0)       # rủi ro 0-100 (cao=rủi ro lớn)
    return_1m_pct: Mapped[float | None] = mapped_column(Float)
    atr_pct: Mapped[float | None] = mapped_column(Float)
    volume_zscore: Mapped[float | None] = mapped_column(Float)
    foreign_net: Mapped[float | None] = mapped_column(Float)
    signals: Mapped[dict] = mapped_column(JSON, default=list)
    warnings: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class NWPick(Base):
    """Mã QUÁ NÓNG trong phiên (quét toàn thị trường) — CẢNH BÁO RỦI RO, không phải gợi ý mua.

    ⚠️ Backtest toàn thị trường (~1.480 mã): nhóm mã giá vượt xa MA200 + dòng tiền vào mạnh +
    đồng thuận kỹ thuật cao chính là nhóm có kỳ vọng lợi nhuận THẤP NHẤT (t=−18). Cột `score`
    là ĐỘ NÓNG (cao = nguy hiểm), KHÔNG phải điểm chất lượng.
    """
    __tablename__ = "nw_picks"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    ts: Mapped[date] = mapped_column(Date, primary_key=True)
    rank: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[float | None] = mapped_column(Float)
    lower: Mapped[float | None] = mapped_column(Float)
    upper: Mapped[float | None] = mapped_column(Float)
    mid: Mapped[float | None] = mapped_column(Float)
    position: Mapped[float | None] = mapped_column(Float)
    liquidity: Mapped[float | None] = mapped_column(Float)
    ma200: Mapped[float | None] = mapped_column(Float)
    above_ma200: Mapped[bool | None] = mapped_column(Boolean)
    cmf: Mapped[float | None] = mapped_column(Float)            # Chaikin Money Flow 20 phiên
    foreign_net: Mapped[float | None] = mapped_column(Float)    # khối ngoại ròng phiên (VND)
    nw_buy: Mapped[bool | None] = mapped_column(Boolean)        # có tín hiệu BUY của NW không
    oracle_score: Mapped[int | None] = mapped_column(Integer)   # đồng thuận kỹ thuật 0-6
    score: Mapped[float | None] = mapped_column(Float)          # ĐỘ NÓNG 0-100 (cao = NGUY HIỂM)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DailyPick(Base):
    """Danh sách cổ phiếu NÊN ĐẦU TƯ do AI agent chọn lọc mỗi ngày (append-only theo ngày).

    ⚠️ Chọn lọc tham khảo — không phải khuyến nghị đầu tư, không cam kết lợi nhuận.
    """
    __tablename__ = "daily_picks"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    ts: Mapped[date] = mapped_column(Date, primary_key=True)
    action: Mapped[str | None] = mapped_column(String(24))         # "Mua tích lũy" | "Theo dõi" ...
    conviction: Mapped[str | None] = mapped_column(String(16))     # cao | trung bình | thấp
    final_score: Mapped[float | None] = mapped_column(Float)
    thesis: Mapped[str | None] = mapped_column(Text)
    buy_low: Mapped[float | None] = mapped_column(Float)
    buy_high: Mapped[float | None] = mapped_column(Float)
    target_price: Mapped[float | None] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float)
    method: Mapped[str | None] = mapped_column(String(8))          # llm | rule
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("symbol", "ts", "alert_type", name="uq_alert"),)

    id: Mapped[int] = mapped_column(AutoPK, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    ts: Mapped[date] = mapped_column(Date)
    alert_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class DataQualityLog(Base):
    __tablename__ = "data_quality_log"

    id: Mapped[int] = mapped_column(AutoPK, primary_key=True, autoincrement=True)
    job: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str | None] = mapped_column(String(16))
    ts: Mapped[date | None] = mapped_column(Date)
    level: Mapped[str] = mapped_column(String(16))             # INFO|WARN|ERROR
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
