"""Tìm bộ lọc biến tín hiệu Nadaraya-Watson BUY thành tín hiệu CÓ EDGE.

So sánh CÔNG BẰNG: mỗi biến thể "BUY + lọc X" được so với "nền + cùng lọc X"
(nếu không, lợi thế có thể chỉ đến từ chế độ thị trường chứ không từ tín hiệu).
Point-in-time: NW non-repaint; MA tính từ dữ liệu quá khứ.
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
FEE = 0.003


def fwd(close: np.ndarray, idx: np.ndarray, h: int) -> np.ndarray:
    ok = idx + h < len(close)
    i = idx[ok]
    return close[i + h] / close[i] - 1 - FEE


def main() -> None:
    # variant -> {horizon: [returns]}   ; mỗi variant có cặp (signal, base)
    variants = ["all", "ma200", "pos30", "ma200+pos40", "ma50+pos40"]
    sig = {v: {h: [] for h in HORIZONS} for v in variants}
    base = {v: {h: [] for h in HORIZONS} for v in variants}
    counts = {v: 0 for v in variants}

    with session_scope() as s:
        syms = [x.symbol for x in s.execute(select(Symbol)).scalars().all()]
        for sym in syms:
            df = repo.load_ohlcv(s, sym)
            if df is None or len(df) < 260:
                continue
            df = df.sort_values("ts").reset_index(drop=True)
            res = nw.compute(df["close"])
            if res is None:
                continue
            close = df["close"].to_numpy(float)
            c = df["close"]
            ma50 = c.rolling(50).mean().to_numpy()
            ma200 = c.rolling(200).mean().to_numpy()

            upper, lower = res["upper"].to_numpy(), res["lower"].to_numpy()
            with np.errstate(invalid="ignore", divide="ignore"):
                pos = (close - lower) / (upper - lower)

            valid = ~np.isnan(upper) & ~np.isnan(ma200)
            buy = res["buy"].to_numpy() & valid

            masks = {
                "all": (valid, buy),
                "ma200": (valid & (close > ma200), buy & (close > ma200)),
                "pos30": (valid & (pos <= 0.30), buy & (pos <= 0.30)),
                "ma200+pos40": (valid & (close > ma200) & (pos <= 0.40),
                                buy & (close > ma200) & (pos <= 0.40)),
                "ma50+pos40": (valid & (close > ma50) & (pos <= 0.40),
                               buy & (close > ma50) & (pos <= 0.40)),
            }
            for v, (bmask, smask) in masks.items():
                bi, si = np.where(bmask)[0], np.where(smask)[0]
                counts[v] += len(si)
                for h in HORIZONS:
                    base[v][h].extend(fwd(close, bi, h))
                    sig[v][h].extend(fwd(close, si, h))

    def st(a):
        a = np.asarray(a, float)
        return (a.size, (a > 0).mean(), a.mean()) if a.size else (0, np.nan, np.nan)

    print(f"{'Bộ lọc':<14}{'Kỳ':<5}{'N tín hiệu':>11}{'Win tín hiệu':>14}"
          f"{'TB tín hiệu':>13}{'TB nền':>10}{'Alpha':>9}")
    print("-" * 76)
    for v in variants:
        for h in HORIZONS:
            ns, ws, ms = st(sig[v][h])
            nb, wb, mb = st(base[v][h])
            if ns < 30:
                print(f"{v:<14}{h:<5}{ns:>11}   (mẫu quá nhỏ)")
                continue
            alpha = ms - mb
            flag = "  <<<" if alpha > 0 and ws > wb else ""
            print(f"{v:<14}{h:<5}{ns:>11,}{ws:>13.1%}{ms:>12.2%}{mb:>10.2%}{alpha:>+8.2%}{flag}")
        print()
    print("Alpha = TB tín hiệu − TB nền (cùng bộ lọc). '<<<' = vượt nền cả win rate lẫn return.")
    print("Đã trừ phí+trượt giá 0.30%/vòng.")


if __name__ == "__main__":
    main()
