"""Pydantic response models cho API."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

DISCLAIMER = ("Thông tin chỉ mang tính tham khảo, KHÔNG phải khuyến nghị đầu tư và "
              "không cam kết lợi nhuận. Nhà đầu tư tự chịu trách nhiệm quyết định.")


class RankingItem(BaseModel):
    symbol: str
    exchange: str | None = None
    industry: str | None = None
    company_name: str | None = None
    close: float | None = None
    liquidity: float | None = None
    final_score: float
    signal: str
    signal_label: str


class RankingResponse(BaseModel):
    as_of: date | None
    disclaimer: str = DISCLAIMER
    count: int
    items: list[RankingItem]


class WeightsIn(BaseModel):
    fundamental: float = 0.18
    growth: float = 0.15
    health: float = 0.12
    valuation: float = 0.10
    technical: float = 0.20
    moneyflow: float = 0.13
    news: float = 0.05
    risk: float = 0.07
