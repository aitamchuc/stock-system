"""Kiểm tra Nadaraya-Watson Envelope trên dữ liệu thật trong DB."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.engines import nw_envelope as nw  # noqa: E402
from app.models import Symbol  # noqa: E402
from app import repo  # noqa: E402

with session_scope() as s:
    syms = [x.symbol for x in s.execute(select(Symbol)).scalars().all()]
    print(f"{'Mã':<6}{'Nến':>5}{'Giá':>10}{'Dải dưới':>11}{'Dải trên':>11}{'Vị trí':>8}  Tín hiệu / gần nhất")
    print("-" * 82)
    n_buy = n_sell = 0
    for sym in syms:
        df = repo.load_ohlcv(s, sym)
        r = nw.latest_signal(df)
        if not r:
            print(f"{sym:<6}{len(df):>5}  (không đủ dữ liệu)")
            continue
        sig = r["signal"] or "—"
        if sig == "BUY":
            n_buy += 1
        if sig == "SELL":
            n_sell += 1
        near = []
        if r["bars_since_buy"] is not None:
            near.append(f"BUY cách {r['bars_since_buy']} nến")
        if r["bars_since_sell"] is not None:
            near.append(f"SELL cách {r['bars_since_sell']} nến")
        pos = f"{r['position']:.2f}" if r["position"] is not None else "—"
        print(f"{sym:<6}{len(df):>5}{r['price']:>10,.0f}{(r['lower'] or 0):>11,.0f}"
              f"{(r['upper'] or 0):>11,.0f}{pos:>8}  {sig:<5} | {', '.join(near)}")
    print(f"\nHôm nay: {n_buy} tín hiệu BUY, {n_sell} tín hiệu SELL")
