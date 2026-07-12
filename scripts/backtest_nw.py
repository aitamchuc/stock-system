"""Backtest tín hiệu Nadaraya-Watson trên VN30: BUY/SELL vs nền (mọi phiên).

Point-in-time: tại mỗi nến, tín hiệu chỉ dùng dữ liệu <= nến đó (engine non-repaint).
So sánh forward return sau 5/20/60 phiên của tín hiệu với "vào lệnh ngẫu nhiên" (mọi nến).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.engines import nw_envelope as nw  # noqa: E402
from app.models import Symbol  # noqa: E402
from app import repo  # noqa: E402

HORIZONS = (5, 20, 60)
FEE = 0.003  # phí + trượt giá 1 vòng


def fwd_returns(close: np.ndarray, idx: np.ndarray, h: int) -> np.ndarray:
    ok = idx + h < len(close)
    i = idx[ok]
    return close[i + h] / close[i] - 1 - FEE


def main() -> None:
    buy_r = {h: [] for h in HORIZONS}
    sell_r = {h: [] for h in HORIZONS}
    base_r = {h: [] for h in HORIZONS}
    n_buy = n_sell = 0

    with session_scope() as s:
        syms = [x.symbol for x in s.execute(select(Symbol)).scalars().all()]
        for sym in syms:
            df = repo.load_ohlcv(s, sym)
            if df is None or len(df) < 120:
                continue
            df = df.sort_values("ts").reset_index(drop=True)
            res = nw.compute(df["close"])
            if res is None:
                continue
            close = df["close"].to_numpy(float)
            valid = res["upper"].notna().to_numpy()

            b = np.where(res["buy"].to_numpy() & valid)[0]
            sl = np.where(res["sell"].to_numpy() & valid)[0]
            allbars = np.where(valid)[0]
            n_buy += len(b)
            n_sell += len(sl)
            for h in HORIZONS:
                buy_r[h].extend(fwd_returns(close, b, h))
                sell_r[h].extend(fwd_returns(close, sl, h))
                base_r[h].extend(fwd_returns(close, allbars, h))

    def stats(arr):
        a = np.asarray(arr, dtype=float)
        if a.size == 0:
            return None
        return {"n": a.size, "win": (a > 0).mean(), "avg": a.mean(), "med": np.median(a)}

    print(f"Tín hiệu tìm được: {n_buy} BUY, {n_sell} SELL (toàn bộ lịch sử VN30)\n")
    print(f"{'Phiên':<7}{'Loại':<8}{'Số lệnh':>9}{'Win rate':>10}{'TB return':>12}{'Trung vị':>11}")
    print("-" * 58)
    for h in HORIZONS:
        for name, d in (("BUY", buy_r), ("SELL", sell_r), ("Nền", base_r)):
            st = stats(d[h])
            if not st:
                continue
            print(f"{h:<7}{name:<8}{st['n']:>9,}{st['win']:>9.1%}{st['avg']:>11.2%}{st['med']:>10.2%}")
        print()

    print("=> 'Nền' = vào lệnh ở MỌI phiên (baseline). Tín hiệu chỉ có giá trị nếu vượt rõ nền.")
    print("   Phí+trượt giá đã trừ 0.30%/vòng.")


if __name__ == "__main__":
    main()
