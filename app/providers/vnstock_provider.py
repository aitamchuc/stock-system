"""Adapter dữ liệu THẬT qua thư viện vnstock v4 (API `vnstock.api.*`).

Bật bằng: `pip install vnstock` + đặt `DATA_SOURCE=vnstock` trong .env.

LƯU Ý PHÁP LÝ / KỸ THUẬT:
  - vnstock wrap API không chính thức của các CTCK (VCI/TCBS...); cấu trúc có thể đổi/khóa.
  - Community edition giới hạn BCTC 4 kỳ gần nhất và có rate-limit → chỉ quét watchlist
    (config.vnstock_watchlist), không quét toàn thị trường.
  - Chỉ dùng cho mục đích cá nhân/nghiên cứu; không tái phân phối dữ liệu thô.
  - Mọi lỗi được nuốt, trả rỗng để pipeline không sập; quality log ghi nhận mã thiếu dữ liệu.
"""
from __future__ import annotations

import re
import time
from collections import deque
from datetime import date, timedelta

import pandas as pd

from app.config import settings
from app.providers.base import MarketDataProvider

_PERIOD_COL = re.compile(r"^\d{4}-Q\d$")

# --- Rate limiter: gói Guest của vnstock giới hạn ~20 request/phút ---
# Đặt 16 (biên an toàn) vì đôi khi có tiến trình khác cùng dùng API → tránh vượt hạn.
_MAX_PER_MIN = 16
_calls: deque[float] = deque()


def _throttle() -> None:
    """Chặn để không vượt _MAX_PER_MIN request trong 60s trượt."""
    now = time.monotonic()
    while _calls and now - _calls[0] > 60:
        _calls.popleft()
    if len(_calls) >= _MAX_PER_MIN:
        wait = 60 - (now - _calls[0]) + 0.5
        if wait > 0:
            print(f"[vnstock] chạm rate-limit, chờ {wait:.0f}s...")
            time.sleep(wait)
        now = time.monotonic()
        while _calls and now - _calls[0] > 60:
            _calls.popleft()
    _calls.append(time.monotonic())


# --- Cache price_board: 1 lần cho cả watchlist, gồm giá khớp lệnh + khối ngoại ---
# Dùng cho: (1) dòng tiền khối ngoại trong pipeline, (2) giá thị trường trực tiếp cho API.
_BOARD: dict[str, dict] = {}
_BOARD_TS: float = 0.0

# Các leaf cần lấy từ price_board (MultiIndex) — tên leaf là duy nhất trong các nhóm này.
_BOARD_KEYS = (
    "match_price", "ref_price", "avg_match_price",
    "foreign_buy_value", "foreign_sell_value",
    "foreign_buy_volume", "foreign_sell_volume",
)


def reset_board_cache() -> None:
    """Gọi ở đầu mỗi lần chạy pipeline để buộc lấy snapshot mới."""
    global _BOARD_TS
    _BOARD.clear()
    _BOARD_TS = 0.0


def _leaf(col):
    return col[-1] if isinstance(col, tuple) else col


def _ensure_board(watchlist: list[str], max_age: float | None) -> None:
    """Đảm bảo _BOARD có dữ liệu. max_age=None → không tự làm mới (dùng trong 1 lần chạy pipeline);
    max_age=N giây → làm mới nếu quá cũ (dùng cho API cần giá gần thời gian thực)."""
    global _BOARD_TS
    now = time.monotonic()
    fresh = bool(_BOARD) and (max_age is None or (now - _BOARD_TS) <= max_age)
    if fresh:
        return
    try:
        from vnstock.api.trading import Trading
        _throttle()
        syms = list(watchlist)
        pb = Trading(symbol=syms[0], source="VCI").price_board(syms)
        if pb is None or pb.empty:
            return
        sym_col = next((c for c in pb.columns if _leaf(c) == "symbol"), None)
        _BOARD.clear()
        for i, (_, r) in enumerate(pb.iterrows()):
            sym = (str(r[sym_col]).upper() if sym_col is not None
                   else (syms[i] if i < len(syms) else None))
            if not sym:
                continue
            _BOARD[sym] = {_leaf(c): r[c] for c in pb.columns if _leaf(c) in _BOARD_KEYS}
        _BOARD_TS = now
    except Exception as exc:
        print(f"[vnstock] price_board lỗi: {exc}")


def _foreign_board_row(symbol: str, watchlist: list[str]) -> dict | None:
    _ensure_board(list(watchlist) or [symbol], max_age=None)
    return _BOARD.get(symbol)


def _to_period(col: str) -> str:
    return str(col).replace("-", "")  # '2026-Q1' -> '2026Q1'


def _period_publish_date(period: str) -> date | None:
    """Ước lượng ngày công bố ~ 45 ngày sau khi kết thúc quý (cho point-in-time)."""
    m = re.match(r"(\d{4})Q(\d)", period)
    if not m:
        return None
    year, q = int(m.group(1)), int(m.group(2))
    end = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[q]
    return date(year, end[0], end[1]) + timedelta(days=45)


def _num(v):
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _transposed_map(df: pd.DataFrame) -> tuple[list[str], dict[str, dict[str, float]]]:
    """income/balance/cashflow: hàng = item_id, cột = kỳ. Trả (periods, {item_id: {period: val}})."""
    if df is None or df.empty or "item_id" not in df.columns:
        return [], {}
    period_cols = [c for c in df.columns if _PERIOD_COL.match(str(c))]
    out: dict[str, dict[str, float]] = {}
    for _, row in df.iterrows():
        key = str(row["item_id"])
        if key in out:  # giữ lần xuất hiện đầu (một số item_id trùng)
            continue
        out[key] = {_to_period(c): _num(row[c]) for c in period_cols}
    return [_to_period(c) for c in period_cols], out


class VnstockProvider(MarketDataProvider):
    def __init__(self) -> None:
        from vnstock.api.quote import Quote
        from vnstock.api.listing import Listing
        from vnstock.api.financial import Finance

        self._Quote = Quote
        self._Listing = Listing
        self._Finance = Finance
        self._source = settings.vnstock_source
        self._watchlist = [s.strip().upper() for s in settings.vnstock_watchlist.split(",") if s.strip()]

    # ---------- Universe ----------
    def list_symbols(self) -> list[dict]:
        meta: dict[str, dict] = {}
        try:
            _throttle()
            lst = self._Listing(source=self._source).symbols_by_exchange()
            for _, r in lst.iterrows():
                sym = str(r.get("symbol") or "").upper()
                if sym:
                    ex = str(r.get("exchange") or "").upper()
                    meta[sym] = {
                        "exchange": "HOSE" if ex == "HSX" else ex,
                        "company_name": r.get("organ_name"),
                        "type": r.get("type"),
                    }
        except Exception as exc:
            print(f"[vnstock] listing lỗi: {exc}")

        out = []
        for sym in self._watchlist:
            m = meta.get(sym, {})
            out.append({
                "symbol": sym,
                "exchange": m.get("exchange") or "HOSE",
                "company_name": m.get("company_name"),
                "industry": None,          # bổ sung qua symbols_by_industries nếu cần
                "market_cap": None,
                "listed_shares": None,
            })
        return out

    # ---------- Giá ----------
    def ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        try:
            _throttle()
            df = self._Quote(symbol=symbol, source=self._source).history(
                start=start, end=end, interval="1D")
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.rename(columns={"time": "ts"})
            if not {"open", "high", "low", "close", "volume"} <= set(df.columns):
                return pd.DataFrame()
            df["ts"] = pd.to_datetime(df["ts"]).dt.date
            # vnstock trả giá theo nghìn đồng (đã điều chỉnh) -> quy về VND
            for c in ("open", "high", "low", "close"):
                df[c] = df[c] * 1000
            df["value"] = df["close"] * df["volume"]
            return df[["ts", "open", "high", "low", "close", "volume", "value"]]
        except Exception as exc:
            print(f"[vnstock] ohlcv {symbol} lỗi: {exc}")
            return pd.DataFrame()

    # ---------- Dòng tiền khối ngoại ----------
    def money_flow(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """Lấy mua/bán ròng khối ngoại của PHIÊN GẦN NHẤT qua price_board.

        vnstock chưa hỗ trợ chuỗi lịch sử foreign_trade; price_board chỉ có snapshot phiên
        hiện tại. Mỗi lần chạy pipeline sẽ ghi 1 dòng (theo ngày) → tích lũy dần thành lịch sử.
        """
        row = _foreign_board_row(symbol, self._watchlist)
        if not row:
            return pd.DataFrame()
        buy = _num(row.get("foreign_buy_value"))
        sell = _num(row.get("foreign_sell_value"))
        if buy is None and sell is None:
            return pd.DataFrame()
        buy, sell = buy or 0.0, sell or 0.0
        return pd.DataFrame([{
            "ts": date.today(),
            "foreign_buy_val": buy,
            "foreign_sell_val": sell,
            "foreign_net": buy - sell,
            "prop_net": 0.0,
        }])

    # ---------- BCTC ----------
    def financials(self, symbol: str) -> list[dict]:
        try:
            fin = self._Finance(symbol=symbol, source=self._source)
            _throttle(); income = fin.income_statement(period="quarter", lang="en")
            _throttle(); balance = fin.balance_sheet(period="quarter", lang="en")
            _throttle(); cashflow = fin.cash_flow(period="quarter", lang="en")
        except Exception as exc:
            print(f"[vnstock] financials {symbol} lỗi: {exc}")
            return []

        # Community edition: ratio() trả các kỳ cũ (không khớp income) -> tự tính tỷ số
        # từ income + balance (đều trả 4 kỳ gần nhất). P/E, P/B cần giá thị trường nên bỏ trống.
        _, inc = _transposed_map(income)
        _, bal = _transposed_map(balance)
        _, cf = _transposed_map(cashflow)

        def g(m: dict, key: str, period: str):
            return (m.get(key) or {}).get(period)

        def safe_div(a, b):
            if a is None or not b:
                return None
            return a / b

        periods = sorted({p for v in inc.values() for p in v})
        out = []
        for period in periods:
            revenue = g(inc, "net_sales", period) or g(inc, "sales", period)
            gross_profit = g(inc, "gross_profit", period)
            net_income = (g(inc, "attributable_to_parent_company", period)
                          or g(inc, "net_profit_loss_after_tax", period))
            equity = g(bal, "owners_equity", period)
            total_assets = g(bal, "total_assets", period)
            debt = (g(bal, "short_term_borrowings", period) or 0) + \
                   (g(bal, "long_term_borrowings", period) or 0)
            cfo = g(cf, "net_cash_inflows_outflows_from_operating_activities", period)
            capex = g(cf, "purchases_of_fixed_assets_and_other_long_term_assets", period)
            out.append({
                "symbol": symbol, "period": period,
                "revenue": revenue,
                "gross_profit": gross_profit,
                "net_income": net_income,
                "gross_margin": safe_div(gross_profit, revenue),
                "net_margin": safe_div(net_income, revenue),
                # ROE/ROA quy năm xấp xỉ (LN quý × 4)
                "roe": safe_div((net_income or 0) * 4, equity) if equity else None,
                "roa": safe_div((net_income or 0) * 4, total_assets) if total_assets else None,
                "total_debt": debt or None,
                "equity": equity,
                "share_capital": g(bal, "paid_in_capital", period),
                "cash": g(bal, "cash_and_cash_equivalents", period),
                "cfo": cfo,
                "fcf": (cfo + capex) if (cfo is not None and capex is not None) else None,
                "inventory": g(bal, "inventories_net", period),
                "receivables": g(bal, "accounts_receivable", period),
                "payables": g(bal, "trade_accounts_payable", period),
                "eps": g(inc, "eps_basic_vnd", period),
                "pe": None, "pb": None, "ev_ebitda": None,  # cần giá thị trường -> Phase 2
                "publish_date": _period_publish_date(period),
            })
        return out

    def news(self, symbol: str | None = None) -> list[dict]:
        # Tin tức: dùng module RSS riêng (CafeF/Vietstock) — vnstock không phải nguồn tin chuẩn.
        return []

    # ---------- Giá thị trường trực tiếp (gần thời gian thực) ----------
    def latest_price(self, symbol: str, max_age: float = 20.0) -> dict | None:
        """Giá khớp lệnh mới nhất qua price_board. Trả {price, ref_price, change_pct, avg_price}."""
        symbol = symbol.upper()
        wl = self._watchlist if symbol in self._watchlist else [symbol]
        _ensure_board(wl, max_age=max_age)
        row = _BOARD.get(symbol)
        if not row:
            return None
        price = _num(row.get("match_price"))
        ref = _num(row.get("ref_price"))
        if price is None:
            return None
        change_pct = ((price - ref) / ref * 100) if ref else None
        return {
            "price": price, "ref_price": ref,
            "avg_price": _num(row.get("avg_match_price")),
            "change_pct": round(change_pct, 2) if change_pct is not None else None,
        }

    # ---------- Quét toàn thị trường (cho bộ lọc penny) ----------
    def all_listed_symbols(self) -> list[dict]:
        try:
            _throttle()
            lst = self._Listing(source=self._source).symbols_by_exchange()
            act = lst[(lst["type"] == "STOCK") &
                      (lst["exchange"].isin(["HSX", "HNX", "UPCOM"]))]
            return [{"symbol": str(r["symbol"]).upper(),
                     "exchange": "HOSE" if r["exchange"] == "HSX" else r["exchange"]}
                    for _, r in act.iterrows()]
        except Exception as exc:
            print(f"[vnstock] all_listed_symbols lỗi: {exc}")
            return []

    def market_snapshot(self, symbols: list[str], chunk: int = 60) -> dict[str, dict]:
        from vnstock.api.trading import Trading

        out: dict[str, dict] = {}
        for i in range(0, len(symbols), chunk):
            batch = symbols[i:i + chunk]
            try:
                _throttle()
                pb = Trading(symbol=batch[0], source="VCI").price_board(batch)
                if pb is None or pb.empty:
                    continue
                sym_col = next((c for c in pb.columns if _leaf(c) == "symbol"), None)
                keys = ("match_price", "accumulated_volume", "accumulated_value",
                        "foreign_buy_value", "foreign_sell_value")
                for j, (_, r) in enumerate(pb.iterrows()):
                    sym = (str(r[sym_col]).upper() if sym_col is not None
                           else (batch[j] if j < len(batch) else None))
                    if not sym:
                        continue
                    d = {_leaf(c): r[c] for c in pb.columns if _leaf(c) in keys}
                    price = _num(d.get("match_price"))
                    if price is None:
                        continue
                    fbuy, fsell = _num(d.get("foreign_buy_value")), _num(d.get("foreign_sell_value"))
                    out[sym] = {
                        "price": price,
                        "volume": _num(d.get("accumulated_volume")),
                        "value": _num(d.get("accumulated_value")),
                        "foreign_net": (fbuy or 0) - (fsell or 0) if (fbuy or fsell) else None,
                    }
            except Exception as exc:
                print(f"[vnstock] market_snapshot batch lỗi: {exc}")
        return out

    def live_prices(self, symbols: list[str], max_age: float = 20.0) -> dict[str, dict]:
        """Giá trực tiếp cho nhiều mã (1 lần gọi price_board)."""
        _ensure_board(list(symbols), max_age=max_age)
        out: dict[str, dict] = {}
        for s in symbols:
            row = _BOARD.get(s.upper())
            if not row:
                continue
            price = _num(row.get("match_price"))
            ref = _num(row.get("ref_price"))
            if price is None:
                continue
            out[s.upper()] = {
                "price": price, "ref_price": ref,
                "avg_price": _num(row.get("avg_match_price")),
                "change_pct": round((price - ref) / ref * 100, 2) if ref else None,
            }
        return out
