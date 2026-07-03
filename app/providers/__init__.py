"""Data providers — cô lập nguồn dữ liệu khỏi business logic.

`get_provider()` chọn provider theo settings.data_source:
  - "demo"    : dữ liệu synthetic, chạy offline (mặc định)
  - "vnstock" : dữ liệu thật qua thư viện vnstock (cần cài đặt)
"""
from __future__ import annotations

from app.config import settings
from app.providers.base import MarketDataProvider
from app.providers.demo_provider import DemoProvider


def get_provider() -> MarketDataProvider:
    if settings.data_source == "vnstock":
        try:
            from app.providers.vnstock_provider import VnstockProvider

            return VnstockProvider()
        except Exception as exc:  # pragma: no cover - fallback an toàn
            print(f"[providers] vnstock không khả dụng ({exc}); fallback DemoProvider")
            return DemoProvider()
    return DemoProvider()
