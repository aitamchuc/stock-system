"""Kiểm định BỀN cho MỌI yếu tố: mẫu KHÔNG CHỒNG LẤN (cửa sổ tương lai rời nhau).

Vì sao cần: forward return h phiên của các nến liền kề chồng lấn ~100% → mẫu tương quan chuỗi,
t-stat bị thổi phồng nhiều lần (dễ thấy |t| > 7 hoàn toàn giả). Lấy mẫu cách nhau h phiên
để mỗi quan sát độc lập, rồi mới kiểm định.

In cả 2 bảng để thấy rõ mức độ thổi phồng.
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
FACTORS = ["ma200", "fund", "cmf", "nw_buy"]


def build(session):
    """Tính sẵn mọi chuỗi cho từng mã (1 lần).

    QUAN TRỌNG: chỉ yếu tố 'fund' mới cần điểm cơ bản. Nếu bắt buộc có BCTC cho MỌI yếu tố thì
    ~1500 mã không có BCTC sẽ bị loại im lặng khỏi nghiên cứu → mỗi yếu tố có mặt nạ hợp lệ RIÊNG.
    """
    data = []
    for sym in [x.symbol for x in session.execute(select(Symbol)).scalars().all()]:
        df = repo.load_ohlcv(session, sym)
        if df is None or len(df) < 300:
            continue
        df = df.sort_values("ts").reset_index(drop=True)
        res = nw.compute(df["close"])
        if res is None:
            continue
        close = df["close"].to_numpy(float)
        ma200 = df["close"].rolling(200).mean().to_numpy()
        cm = cmf(df)
        fq = fundamental_series(session, sym, df)

        base = ~np.isnan(res["upper"].to_numpy()) & ~np.isnan(ma200) & ~np.isnan(cm)
        conds = {
            "ma200": close > ma200,
            "fund": fq >= FUND_MIN,
            "cmf": cm > 0,
            "nw_buy": res["buy"].to_numpy(),
        }
        valids = {
            "ma200": base,
            "fund": base & ~np.isnan(fq),      # chỉ mã có BCTC
            "cmf": base,
            "nw_buy": base,
        }
        data.append((close, valids, conds))
    return data


def report(data, overlap: bool) -> None:
    label = "CHỒNG LẤN (mọi nến — t-stat BỊ THỔI PHỒNG)" if overlap \
        else "KHÔNG CHỒNG LẤN (đáng tin)"
    print(f"\n=== {label} ===")
    print(f"{'Yếu tố':<9}{'Kỳ':<4}{'N thỏa':>8}{'N không':>9}{'Win':>7}"
          f"{'TB thỏa':>10}{'TB không':>11}{'Chênh':>9}{'t-stat':>9}  Kết luận")
    print("-" * 86)
    for f in FACTORS:
        for h in HORIZONS:
            A, B = [], []
            for close, valids, conds in data:
                idx = np.where(valids[f])[0]
                if idx.size == 0:
                    continue
                if not overlap:
                    idx = idx[::h]
                m = conds[f][idx]
                A.extend(fwd(close, idx[m], h))
                B.extend(fwd(close, idx[~m], h))
            a, b = np.asarray(A, float), np.asarray(B, float)
            if a.size < 20 or b.size < 20:
                print(f"{f:<9}{h:<4}{a.size:>8}   (mẫu quá nhỏ)")
                continue
            t = tstat(a, b)
            v = "CÓ EDGE" if t >= 2 else ("NGƯỢC" if t <= -2 else "nhiễu")
            print(f"{f:<9}{h:<4}{a.size:>8,}{b.size:>9,}{(a > 0).mean():>6.1%}"
                  f"{a.mean():>10.2%}{b.mean():>11.2%}{a.mean()-b.mean():>+8.2%}{t:>9.2f}  {v}")
        print()


def main() -> None:
    with session_scope() as s:
        data = build(s)
    print(f"Số mã dùng: {len(data)}")
    report(data, overlap=True)
    report(data, overlap=False)
    print("=> CHỈ tin bảng KHÔNG CHỒNG LẤN. Phí+trượt giá 0.30%/vòng đã trừ.")
    print("   Mẫu VN30, ~2 năm, một chế độ thị trường → kể cả có ý nghĩa cũng cần thận trọng.")


if __name__ == "__main__":
    main()
