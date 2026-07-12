"""Backtest bộ SFI Multi-Strength trên TOÀN THỊ TRƯỜNG — mẫu KHÔNG CHỒNG LẤN.

Kiểm định cả 2 dạng tín hiệu:
  • TRẠNG THÁI  (đang bullish): st_rising, ut_long, kalman_up, oracle_bull, all_bull
  • SỰ KIỆN     (vừa chuyển bullish — điểm vào lệnh thật): *_cross
  • Oracle theo từng ngưỡng điểm 0..6 (xem điểm đồng thuận cao có tốt hơn không)

|t| >= 2 mới có ý nghĩa. Phí+trượt giá 0.30%/vòng.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.engines import sfi  # noqa: E402
from app.models import Symbol  # noqa: E402
from app import repo  # noqa: E402
from scripts.backtest_combo import fwd, tstat  # noqa: E402

HORIZONS = (5, 20, 60)
STATE = ["st_rising", "ut_long", "kalman_up", "oracle_bull", "all_bull"]
EVENT = [s + "_cross" for s in STATE]


def build(session):
    data = []
    syms = [x.symbol for x in session.execute(select(Symbol)).scalars().all()]
    for i, sym in enumerate(syms):
        df = repo.load_ohlcv(session, sym)
        if df is None or len(df) < 300:
            continue
        df = df.sort_values("ts").reset_index(drop=True)
        try:
            r = sfi.compute(df)
        except Exception:
            continue
        close = df["close"].to_numpy(float)
        valid = r["oracle"].notna().to_numpy() & r["ut_stop"].notna().to_numpy() \
            & r["smart_trail"].notna().to_numpy()
        valid[:60] = False           # bỏ giai đoạn khởi động chỉ báo
        sigs = {k: r[k].fillna(False).to_numpy(bool) for k in STATE + EVENT}
        sigs["oracle_score"] = r["oracle"].to_numpy()
        data.append((close, valid, sigs))
        if (i + 1) % 300 == 0:
            print(f"  ...đã tính {len(data)} mã")
    return data


def table(data, keys, overlap=False, title=""):
    print(f"\n=== {title} ===")
    print(f"{'Tín hiệu':<18}{'Kỳ':<4}{'N thỏa':>8}{'N không':>9}{'Win':>7}"
          f"{'TB thỏa':>10}{'TB không':>11}{'Chênh':>9}{'t-stat':>9}  Kết luận")
    print("-" * 92)
    for k in keys:
        for h in HORIZONS:
            A, B = [], []
            for close, valid, sigs in data:
                idx = np.where(valid)[0]
                if not overlap:
                    idx = idx[::h]
                if idx.size == 0:
                    continue
                m = sigs[k][idx]
                A.extend(fwd(close, idx[m], h))
                B.extend(fwd(close, idx[~m], h))
            a, b = np.asarray(A, float), np.asarray(B, float)
            if a.size < 30 or b.size < 30:
                print(f"{k:<18}{h:<4}{a.size:>8}   (mẫu quá nhỏ)")
                continue
            t = tstat(a, b)
            v = "CÓ EDGE" if t >= 2 else ("CÓ HẠI" if t <= -2 else "nhiễu")
            print(f"{k:<18}{h:<4}{a.size:>8,}{b.size:>9,}{(a > 0).mean():>6.1%}"
                  f"{a.mean():>10.2%}{b.mean():>11.2%}{a.mean()-b.mean():>+8.2%}{t:>9.2f}  {v}")
        print()


def oracle_levels(data):
    print("\n=== ORACLE CONSENSUS theo từng mức điểm (mẫu độc lập, kỳ 20 phiên) ===")
    print(f"{'Điểm':<7}{'N':>9}{'Win':>8}{'TB return':>12}  (nền = tất cả)")
    print("-" * 46)
    h = 20
    allr = []
    for close, valid, sigs in data:
        idx = np.where(valid)[0][::h]
        allr.extend(fwd(close, idx, h))
    base = np.asarray(allr, float)
    print(f"{'nền':<7}{base.size:>9,}{(base > 0).mean():>7.1%}{base.mean():>11.2%}")
    for lvl in range(0, 7):
        R = []
        for close, valid, sigs in data:
            idx = np.where(valid)[0][::h]
            m = sigs["oracle_score"][idx] == lvl
            R.extend(fwd(close, idx[m], h))
        r = np.asarray(R, float)
        if r.size < 30:
            print(f"{lvl:<7}{r.size:>9}   (mẫu nhỏ)")
            continue
        t = tstat(r, base)
        print(f"{lvl:<7}{r.size:>9,}{(r > 0).mean():>7.1%}{r.mean():>11.2%}   t={t:+.2f}")


def main() -> None:
    with session_scope() as s:
        data = build(s)
    print(f"\nSố mã dùng: {len(data)}")
    table(data, STATE, overlap=False, title="TRẠNG THÁI bullish (mẫu độc lập)")
    table(data, EVENT, overlap=False, title="SỰ KIỆN vừa chuyển bullish (mẫu độc lập)")
    oracle_levels(data)
    print("\n=> |t| >= 2 mới có ý nghĩa. Phí+trượt giá 0.30%/vòng đã trừ.")


if __name__ == "__main__":
    main()
