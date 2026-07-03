"""Interface chuẩn cho mọi nguồn dữ liệu. Mọi DataFrame trả về đã chuẩn hóa tên cột."""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class MarketDataProvider(ABC):
    @abstractmethod
    def list_symbols(self) -> list[dict]:
        """[{symbol, exchange, company_name, industry, market_cap, listed_shares}, ...]"""

    @abstractmethod
    def ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """Cột: ts, open, high, low, close, volume, value"""

    @abstractmethod
    def money_flow(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """Cột: ts, foreign_buy_val, foreign_sell_val, foreign_net, prop_net"""

    @abstractmethod
    def financials(self, symbol: str) -> list[dict]:
        """List các kỳ BCTC đã chuẩn hóa (khớp cột model Financial)."""

    @abstractmethod
    def news(self, symbol: str | None = None) -> list[dict]:
        """[{symbol, published_at, source, title, url}, ...]"""

    def latest_price(self, symbol: str) -> dict | None:
        """Giá thị trường trực tiếp: {price, ref_price, change_pct, avg_price}. None nếu không hỗ trợ."""
        return None

    def live_prices(self, symbols: list[str]) -> dict[str, dict]:
        return {s: p for s in symbols if (p := self.latest_price(s))}

    def all_listed_symbols(self) -> list[dict]:
        """Toàn bộ mã đang niêm yết [{symbol, exchange}]. Mặc định = list_symbols()."""
        return [{"symbol": s["symbol"], "exchange": s.get("exchange")} for s in self.list_symbols()]

    def market_snapshot(self, symbols: list[str]) -> dict[str, dict]:
        """Snapshot phiên hiện tại cho nhiều mã: {symbol: {price, volume, value, foreign_net}}.
        Mặc định suy từ latest_price (chậm); provider nên override để quét hàng loạt."""
        out: dict[str, dict] = {}
        for s in symbols:
            lp = self.latest_price(s)
            if lp:
                out[s] = {"price": lp["price"], "volume": None, "value": None, "foreign_net": None}
        return out
