"""Provider synthetic — cho phép chạy toàn bộ hệ thống offline, có tính tái lập.

Giá được sinh bằng geometric random walk có seed cố định theo mã, cộng một xu hướng
và vài "sự kiện" (gap volume) để TA engine có cái để phát hiện. KHÔNG phản ánh thị
trường thật — chỉ để phát triển & test pipeline.
"""
from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta

import pandas as pd

from app.providers.base import MarketDataProvider

# Một rổ mã đại diện các sàn/ngành để demo
_UNIVERSE = [
    ("FPT", "HOSE", "CTCP FPT", "Công nghệ", 200_000e9, 1_460_000_000),
    ("HPG", "HOSE", "Tập đoàn Hòa Phát", "Vật liệu", 180_000e9, 6_400_000_000),
    ("VNM", "HOSE", "Vinamilk", "Thực phẩm", 140_000e9, 2_090_000_000),
    ("MWG", "HOSE", "Thế Giới Di Động", "Bán lẻ", 90_000e9, 1_460_000_000),
    ("VCB", "HOSE", "Vietcombank", "Ngân hàng", 500_000e9, 5_580_000_000),
    ("SSI", "HOSE", "Chứng khoán SSI", "Chứng khoán", 60_000e9, 1_960_000_000),
    ("DGC", "HOSE", "Hóa chất Đức Giang", "Hóa chất", 45_000e9, 380_000_000),
    ("REE", "HOSE", "Cơ Điện Lạnh", "Tiện ích", 20_000e9, 460_000_000),
    ("SHS", "HNX", "Chứng khoán SHS", "Chứng khoán", 12_000e9, 810_000_000),
    ("IDC", "HNX", "IDICO", "Bất động sản KCN", 20_000e9, 330_000_000),
    ("BSR", "UPCOM", "Lọc hóa dầu Bình Sơn", "Dầu khí", 65_000e9, 3_100_000_000),
    ("ACV", "UPCOM", "Cảng hàng không VN", "Hạ tầng", 250_000e9, 2_170_000_000),
]


def _seed(symbol: str) -> int:
    return int(hashlib.md5(symbol.encode()).hexdigest(), 16) % (2**32)


class DemoProvider(MarketDataProvider):
    def list_symbols(self) -> list[dict]:
        return [
            {
                "symbol": s, "exchange": ex, "company_name": name,
                "industry": ind, "market_cap": cap, "listed_shares": shares,
            }
            for s, ex, name, ind, cap, shares in _UNIVERSE
        ]

    def ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        rng = random.Random(_seed(symbol))
        start_d = datetime.strptime(start, "%Y-%m-%d").date()
        end_d = datetime.strptime(end, "%Y-%m-%d").date()

        price = 20_000 + rng.random() * 80_000
        trend = rng.uniform(-0.0005, 0.0012)        # xu hướng nhẹ theo mã
        base_vol = int(1e6 + rng.random() * 5e6)

        rows = []
        d = start_d
        i = 0
        while d <= end_d:
            if d.weekday() < 5:                      # bỏ cuối tuần
                shock = rng.gauss(0, 0.018)
                # thỉnh thoảng có phiên breakout volume
                spike = 3.5 if (i % 57 == 0 and i > 0) else 1.0
                drift = trend + shock
                o = price
                c = max(1000, price * (1 + drift))
                h = max(o, c) * (1 + abs(rng.gauss(0, 0.006)))
                l = min(o, c) * (1 - abs(rng.gauss(0, 0.006)))
                vol = int(base_vol * spike * (0.6 + rng.random()))
                rows.append({
                    "ts": d, "open": round(o, -1), "high": round(h, -1),
                    "low": round(l, -1), "close": round(c, -1),
                    "volume": vol, "value": round(c * vol, -3),
                })
                price = c
                i += 1
            d += timedelta(days=1)
        return pd.DataFrame(rows)

    def money_flow(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        rng = random.Random(_seed(symbol) + 7)
        px = self.ohlcv(symbol, start, end)
        rows = []
        bias = rng.uniform(-0.4, 0.6)                # mã được khối ngoại ưa thích hay không
        for _, r in px.iterrows():
            gross = r["value"] * rng.uniform(0.05, 0.25)
            net_ratio = max(-1, min(1, rng.gauss(bias, 0.5)))
            fbuy = gross * (0.5 + net_ratio / 2)
            fsell = gross * (0.5 - net_ratio / 2)
            rows.append({
                "ts": r["ts"],
                "foreign_buy_val": round(fbuy, -3),
                "foreign_sell_val": round(fsell, -3),
                "foreign_net": round(fbuy - fsell, -3),
                "prop_net": round(gross * rng.gauss(0, 0.2), -3),
            })
        return pd.DataFrame(rows)

    def financials(self, symbol: str) -> list[dict]:
        rng = random.Random(_seed(symbol) + 13)
        periods = ["2024Q2", "2024Q3", "2024Q4", "2025Q1"]
        out = []
        revenue = rng.uniform(2_000e9, 30_000e9)
        equity = rng.uniform(5_000e9, 80_000e9)
        pub = date(2024, 8, 15)
        for p in periods:
            revenue *= rng.uniform(0.95, 1.15)
            gm = rng.uniform(0.10, 0.45)
            nm = gm * rng.uniform(0.3, 0.7)
            ni = revenue * nm
            debt = equity * rng.uniform(0.2, 1.4)
            cfo = ni * rng.uniform(0.4, 1.6)         # đôi khi < NI => red flag
            shares = rng.uniform(3e8, 3e9)
            out.append({
                "symbol": symbol, "period": p,
                "revenue": revenue, "gross_profit": revenue * gm, "net_income": ni,
                "gross_margin": gm, "net_margin": nm,
                "roe": ni * 4 / equity, "roa": ni * 4 / (equity + debt),
                "total_debt": debt, "equity": equity,
                "share_capital": shares * 10000,       # số cp × mệnh giá 10.000đ
                "cash": equity * rng.uniform(0.05, 0.3),
                "cfo": cfo, "fcf": cfo - revenue * rng.uniform(0.02, 0.08),
                "inventory": revenue * rng.uniform(0.05, 0.25),
                "receivables": revenue * rng.uniform(0.05, 0.30),
                "payables": revenue * rng.uniform(0.05, 0.20),
                "eps": ni / shares,
                "pe": rng.uniform(6, 25), "pb": rng.uniform(0.6, 4.0),
                "ev_ebitda": rng.uniform(4, 16),
                "publish_date": pub,
            })
            pub = pub + timedelta(days=90)
        return out

    def latest_price(self, symbol: str) -> dict | None:
        # Demo: "giá trực tiếp" = giá đóng cửa gần nhất + biến động nhỏ giả lập
        df = self.ohlcv(symbol, "2024-01-01", "2026-12-31")
        if df.empty:
            return None
        last, prev = df.iloc[-1]["close"], (df.iloc[-2]["close"] if len(df) > 1 else df.iloc[-1]["close"])
        return {
            "price": float(last), "ref_price": float(prev),
            "avg_price": float(last),
            "change_pct": round((last - prev) / prev * 100, 2) if prev else None,
        }

    def news(self, symbol: str | None = None) -> list[dict]:
        symbols = [symbol] if symbol else [s[0] for s in _UNIVERSE]
        samples = [
            ("Doanh nghiệp công bố KQKD quý tăng trưởng so với cùng kỳ", "other"),
            ("HĐQT thông qua phương án chia cổ tức bằng tiền mặt", "dividend"),
            ("Cổ đông lớn đăng ký mua vào cổ phiếu", "insider"),
            ("Doanh nghiệp dự kiến phát hành thêm cổ phiếu tăng vốn", "issuance"),
            ("Thông báo ngày họp Đại hội đồng cổ đông thường niên", "agm"),
            ("Công ty đăng ký mua cổ phiếu quỹ", "buyback"),
        ]
        rng = random.Random(_seed(symbol or "all") + 99)
        out = []
        for s in symbols:
            for _ in range(rng.randint(0, 3)):
                title, etype = rng.choice(samples)
                out.append({
                    "symbol": s,
                    "published_at": datetime(2025, 6, rng.randint(1, 28), 9, 0),
                    "source": "demo-feed",
                    "title": f"[{s}] {title}",
                    "url": f"https://example.com/news/{s}",
                    "event_type": etype,
                })
        return out
