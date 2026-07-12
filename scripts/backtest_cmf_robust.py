"""Kiểm định độ bền của yếu tố CMF: dùng mẫu KHÔNG CHỒNG LẤN.

Vấn đề: forward return 60 phiên của các nến liền kề chồng lấn gần như hoàn toàn → mẫu bị
tương quan chuỗi, t-stat bị thổi phồng. Cách sửa: lấy mẫu cách nhau đúng h phiên
(mỗi lệnh có cửa sổ tương lai rời nhau) rồi mới kiểm định.
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
from scripts.backtest_combo import cmf, fwd, tstat  # noqa: E402

HORIZONS = (5, 20, 60)


def main() -> None:
    for overlap in (True, False):
        label = "CHỒNG LẤN (mọi nến)" if overlap else "KHÔNG CHỒNG LẤN (cách nhau h phiên)"
        print(f"\n=== {label} ===")
        print(f"{'Kỳ':<5}{'N vào':>8}{'N ra':>8}{'Win vào':>10}{'TB vào':>10}"
              f"{'TB ra':>10}{'Chênh':>9}{'t-stat':>9}  Kết luận")
        print("-" * 76)
        for h in HORIZONS:
            A, B = [], []
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
                    cm = cmf(df)
                    valid = ~np.isnan(res["upper"].to_numpy()) & ~np.isnan(cm)
                    idx = np.where(valid)[0]
                    if not overlap:
                        idx = idx[::h]          # cửa sổ tương lai rời nhau
                    inflow = cm[idx] > 0
                    A.extend(fwd(close, idx[inflow], h))
                    B.extend(fwd(close, idx[~inflow], h))
            a, b = np.asarray(A, float), np.asarray(B, float)
            if a.size < 20 or b.size < 20:
                print(f"{h:<5}{a.size:>8}   (mẫu quá nhỏ)")
                continue
            t = tstat(a, b)
            v = "CÓ EDGE" if t >= 2 else ("ngược" if t <= -2 else "nhiễu")
            print(f"{h:<5}{a.size:>8,}{b.size:>8,}{(a > 0).mean():>9.1%}"
                  f"{a.mean():>9.2%}{b.mean():>10.2%}{a.mean()-b.mean():>+8.2%}{t:>9.2f}  {v}")

    print("\n=> Chỉ tin kết quả ở bảng KHÔNG CHỒNG LẤN. Phí+trượt giá 0.30%/vòng đã trừ.")


if __name__ == "__main__":
    main()
