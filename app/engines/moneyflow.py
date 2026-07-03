"""Phát hiện dòng tiền lớn (khối ngoại/tự doanh) và phân loại tích cực/trung tính/tiêu cực."""
from __future__ import annotations

import numpy as np
import pandas as pd


def analyze(mf: pd.DataFrame, ohlcv: pd.DataFrame) -> dict:
    """mf: DataFrame money_flow; ohlcv: DataFrame giá. Trả {score, label, reasons}."""
    reasons: list[str] = []
    score = 50.0  # trung tính

    if mf is None or mf.empty:
        return {"score": 50.0, "label": "unknown",
                "reasons": ["Không có dữ liệu dòng tiền khối ngoại/tự doanh"]}

    mf = mf.sort_values("ts").reset_index(drop=True)
    recent = mf.tail(5)
    net5 = recent["foreign_net"].sum()
    net20 = mf.tail(20)["foreign_net"].sum()

    # Chuẩn hóa theo độ lớn giao dịch để so sánh giữa các mã
    scale = mf.tail(20)["foreign_buy_val"].add(mf.tail(20)["foreign_sell_val"]).mean() + 1e-9
    intensity5 = net5 / scale

    if net5 > 0:
        buy_days = int((recent["foreign_net"] > 0).sum())
        score += min(30, 30 * intensity5)
        reasons.append(f"Khối ngoại mua ròng {buy_days}/5 phiên gần nhất")
    else:
        score -= min(30, 30 * abs(intensity5))
        reasons.append("Khối ngoại bán ròng 5 phiên gần nhất")

    if net20 > 0:
        score += 5; reasons.append("Xu hướng 20 phiên: mua ròng")
    else:
        score -= 5; reasons.append("Xu hướng 20 phiên: bán ròng")

    # Tự doanh
    prop5 = mf.tail(5)["prop_net"].sum()
    if prop5 > 0:
        score += 5; reasons.append("Tự doanh mua ròng ngắn hạn")
    elif prop5 < 0:
        score -= 5; reasons.append("Tự doanh bán ròng ngắn hạn")

    # Volume đột biến so với TB20 (từ ohlcv)
    if ohlcv is not None and len(ohlcv) >= 21:
        vol = ohlcv.sort_values("ts")["volume"]
        vz = (vol.iloc[-1] - vol.tail(20).mean()) / (vol.tail(20).std() + 1e-9)
        if vz > 2:
            reasons.append(f"Khối lượng phiên cuối đột biến (+{vz:.1f}σ)")

    score = float(np.clip(score, 0, 100))
    label = "positive" if score >= 62 else "negative" if score <= 38 else "neutral"
    return {"score": round(score, 1), "label": label, "reasons": reasons}
