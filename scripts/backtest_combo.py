"""Backtest TỔ HỢP: tín hiệu NW + điểm cơ bản + dòng tiền — có kiểm định ý nghĩa thống kê.

GIỚI HẠN DỮ LIỆU (nêu rõ, không giấu):
  • Dòng tiền KHỐI NGOẠI thật KHÔNG có lịch sử (vnstock chỉ cho snapshot phiên hiện tại)
    → dùng PROXY dòng tiền tính từ OHLCV: Chaikin Money Flow 20 phiên (CMF20 > 0 = tiền vào).
  • Điểm CƠ BẢN chỉ có 4 quý BCTC → tính tại mỗi publish_date rồi forward-fill (point-in-time).

So sánh CÔNG BẰNG: mỗi "NW BUY + lọc X" so với "mọi phiên + cùng lọc X" (khử ảnh hưởng chế độ TT).
t-stat của chênh lệch trung bình; |t| < 2 ⇒ coi như nhiễu.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.engines import fundamental, nw_envelope as nw  # noqa: E402
from app.models import Symbol  # noqa: E402
from app import repo  # noqa: E402

HORIZONS = (5, 20, 60)
FEE = 0.003
FUND_MIN = 60.0          # ngưỡng điểm chất lượng cơ bản


def cmf(df: pd.DataFrame, n: int = 20) -> np.ndarray:
    hl = (df["high"] - df["low"]).replace(0, np.nan)
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / hl
    mfv = (mfm * df["volume"]).fillna(0)
    return (mfv.rolling(n).sum() / df["volume"].rolling(n).sum().replace(0, np.nan)).to_numpy()


def fundamental_series(session, symbol: str, df: pd.DataFrame) -> np.ndarray:
    """Điểm chất lượng cơ bản (0-100) point-in-time, forward-fill từ các publish_date."""
    fins = repo.load_financials(session, symbol)
    pubs = sorted({f.publish_date for f in fins if f.publish_date})
    out = pd.Series(np.nan, index=df.index)
    if not pubs:
        return out.to_numpy()
    ts = pd.to_datetime(df["ts"]).dt.date
    for p in pubs:
        fa = fundamental.analyze(fins, as_of=p, price=None)
        quality = np.mean([fa["fundamental"], fa["growth"], fa["health"]])
        out[ts >= p] = quality          # ghi đè dần → hiệu quả là forward-fill theo kỳ mới nhất
    return out.to_numpy()


def fwd(close: np.ndarray, idx: np.ndarray, h: int) -> np.ndarray:
    ok = idx + h < len(close)
    i = idx[ok]
    return close[i + h] / close[i] - 1 - FEE


def tstat(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 5 or b.size < 5:
        return np.nan
    se = np.sqrt(a.var(ddof=1) / a.size + b.var(ddof=1) / b.size)
    return (a.mean() - b.mean()) / se if se > 0 else np.nan


def main() -> None:
    filters = ["none", "ma200", "fund", "cmf", "ma200+fund", "ma200+cmf", "tất cả"]
    sig = {f: {h: [] for h in HORIZONS} for f in filters}
    base = {f: {h: [] for h in HORIZONS} for f in filters}

    with session_scope() as s:
        for sym in [x.symbol for x in s.execute(select(Symbol)).scalars().all()]:
            df = repo.load_ohlcv(s, sym)
            if df is None or len(df) < 260:
                continue
            df = df.sort_values("ts").reset_index(drop=True)
            res = nw.compute(df["close"])
            if res is None:
                continue

            close = df["close"].to_numpy(float)
            ma200 = df["close"].rolling(200).mean().to_numpy()
            cm = cmf(df)
            fq = fundamental_series(s, sym, df)

            valid = (~np.isnan(res["upper"].to_numpy()) & ~np.isnan(ma200)
                     & ~np.isnan(cm) & ~np.isnan(fq))
            buy = res["buy"].to_numpy() & valid

            f_ma = close > ma200
            f_fu = fq >= FUND_MIN
            f_cm = cm > 0
            conds = {
                "none": valid,
                "ma200": valid & f_ma,
                "fund": valid & f_fu,
                "cmf": valid & f_cm,
                "ma200+fund": valid & f_ma & f_fu,
                "ma200+cmf": valid & f_ma & f_cm,
                "tất cả": valid & f_ma & f_fu & f_cm,
            }
            for name, cond in conds.items():
                bi = np.where(cond)[0]
                si = np.where(buy & cond)[0]
                for h in HORIZONS:
                    base[name][h].extend(fwd(close, bi, h))
                    sig[name][h].extend(fwd(close, si, h))

    print(f"{'Bộ lọc':<12}{'Kỳ':<4}{'N':>7}{'Win':>8}{'TB tín hiệu':>13}"
          f"{'TB nền':>10}{'Alpha':>9}{'t-stat':>9}  Kết luận")
    print("-" * 84)
    for f in filters:
        for h in HORIZONS:
            a = np.asarray(sig[f][h], float)
            b = np.asarray(base[f][h], float)
            if a.size < 30:
                print(f"{f:<12}{h:<4}{a.size:>7}   (mẫu quá nhỏ, bỏ qua)")
                continue
            t = tstat(a, b)
            alpha = a.mean() - b.mean()
            verdict = "CÓ Ý NGHĨA" if abs(t) >= 2 else "nhiễu"
            print(f"{f:<12}{h:<4}{a.size:>7,}{(a > 0).mean():>7.1%}{a.mean():>12.2%}"
                  f"{b.mean():>10.2%}{alpha:>+8.2%}{t:>9.2f}  {verdict}")
        print()

    print("Alpha = TB tín hiệu − TB nền (cùng bộ lọc). |t| ≥ 2 mới coi là có ý nghĩa thống kê.")
    print("Phí+trượt giá 0.30%/vòng. CMF20 = proxy dòng tiền (khối ngoại thật chưa có lịch sử).")


if __name__ == "__main__":
    main()
