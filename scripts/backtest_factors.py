"""Đo TỪNG YẾU TỐ có mang thông tin dự báo không (thay vì cố cứu tín hiệu NW).

Với mỗi điều kiện, so sánh forward return của các phiên THỎA vs KHÔNG THỎA (t-test 2 mẫu).
Đây là cách kiểm tra một yếu tố có "edge" hay không, độc lập với NW.

Yếu tố:
  ma200  : giá > MA200 (xu hướng tăng)
  fund   : điểm chất lượng cơ bản >= 60 (point-in-time theo publish_date)
  cmf    : Chaikin Money Flow 20 phiên > 0 (proxy dòng tiền vào)
  nw_buy : có tín hiệu BUY của Nadaraya-Watson
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.engines import nw_envelope as nw  # noqa: E402
from app.models import Symbol  # noqa: E402
from app import repo  # noqa: E402
from scripts.backtest_combo import FUND_MIN, cmf, fundamental_series, fwd, tstat  # noqa: E402

HORIZONS = (5, 20, 60)


def main() -> None:
    factors = ["ma200", "fund", "cmf", "nw_buy", "cmf+ma200"]
    yes = {f: {h: [] for h in HORIZONS} for f in factors}
    no = {f: {h: [] for h in HORIZONS} for f in factors}

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

            conds = {
                "ma200": close > ma200,
                "fund": fq >= FUND_MIN,
                "cmf": cm > 0,
                "nw_buy": res["buy"].to_numpy(),
                "cmf+ma200": (cm > 0) & (close > ma200),
            }
            for name, c in conds.items():
                yi = np.where(valid & c)[0]
                ni = np.where(valid & ~c)[0]
                for h in HORIZONS:
                    yes[name][h].extend(fwd(close, yi, h))
                    no[name][h].extend(fwd(close, ni, h))

    print(f"{'Yếu tố':<12}{'Kỳ':<4}{'N thỏa':>9}{'Win thỏa':>10}{'TB thỏa':>10}"
          f"{'TB không':>11}{'Chênh':>9}{'t-stat':>9}  Kết luận")
    print("-" * 88)
    for f in factors:
        for h in HORIZONS:
            a = np.asarray(yes[f][h], float)
            b = np.asarray(no[f][h], float)
            if a.size < 30 or b.size < 30:
                print(f"{f:<12}{h:<4}{a.size:>9}   (mẫu quá nhỏ)")
                continue
            t = tstat(a, b)
            d = a.mean() - b.mean()
            v = "CÓ EDGE" if t >= 2 else ("NGƯỢC (xấu)" if t <= -2 else "nhiễu")
            print(f"{f:<12}{h:<4}{a.size:>9,}{(a > 0).mean():>9.1%}{a.mean():>9.2%}"
                  f"{b.mean():>11.2%}{d:>+8.2%}{t:>9.2f}  {v}")
        print()
    print("t-stat = (TB thỏa − TB không thỏa)/SE. |t| ≥ 2 mới có ý nghĩa thống kê.")
    print("Mẫu: VN30, ~1 chế độ thị trường → cần thận trọng, dễ overfit.")


if __name__ == "__main__":
    main()
