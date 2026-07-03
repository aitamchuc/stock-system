"""Bộ quét cổ phiếu PENNY tiềm năng tăng mạnh — KÈM cảnh báo rủi ro cao.

⚠️ CỰC KỲ QUAN TRỌNG: Penny là cổ phiếu đầu cơ, rủi ro RẤT CAO — dễ bị làm giá/kéo xả,
thanh khoản thấp, nguy cơ hủy niêm yết. Công cụ này CHỈ phát hiện ỨNG VIÊN để nghiên cứu,
KHÔNG phải khuyến nghị mua, KHÔNG hứa hẹn "x3 x4". Luôn đọc phần cảnh báo rủi ro.

Hai tầng:
  screen()   — lọc nhanh toàn thị trường theo giá + thanh khoản (từ market_snapshot).
  analyze()  — phân tích sâu 1 ứng viên từ lịch sử giá → điểm tiềm năng + điểm rủi ro.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def screen(snapshot: dict[str, dict], price_max: float, min_liquidity: float) -> list[dict]:
    """Lọc penny có thanh khoản. snapshot: {symbol: {price, volume, value, foreign_net}}."""
    cands = []
    for sym, d in snapshot.items():
        price = d.get("price")
        if not price or price > price_max or price <= 0:
            continue
        # Thanh khoản (VND): ưu tiên khối lượng × giá (đơn vị rõ ràng);
        # dự phòng accumulated_value (đơn vị TRIỆU đồng → ×1e6).
        vol = d.get("volume") or 0
        value = (vol * price) if vol else ((d.get("value") or 0) * 1e6)
        if value < min_liquidity:
            continue
        fn = d.get("foreign_net") or 0
        stage1 = np.log10(max(value, 1)) + (1 if fn > 0 else 0)
        cands.append({**d, "symbol": sym, "value": value,
                      "stage1_score": round(float(stage1), 2)})
    return sorted(cands, key=lambda c: c["stage1_score"], reverse=True)


def _atr_pct(df: pd.DataFrame) -> float:
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.tail(14).mean()
    return float(atr / df["close"].iloc[-1] * 100) if df["close"].iloc[-1] else 0.0


def analyze(ohlcv: pd.DataFrame, snap: dict) -> dict:
    """Trả {upside_score, risk_score, signals, warnings, stats}. Điểm rủi ro cao = rủi ro lớn."""
    warnings: list[str] = ["Penny đầu cơ — rủi ro RẤT CAO, có thể bị làm giá/kéo xả và mất phần lớn vốn."]
    signals: list[str] = []
    if ohlcv is None or len(ohlcv) < 40:
        return {"upside_score": 0, "risk_score": 100, "signals": [],
                "warnings": warnings + ["Không đủ lịch sử giá để đánh giá."], "stats": {}}

    df = ohlcv.sort_values("ts").reset_index(drop=True)
    close, vol = df["close"], df["volume"]
    c = close.iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1]

    vmean = vol.tail(20).mean()
    vstd = vol.tail(20).std() + 1e-9
    vz = float((vol.iloc[-1] - vmean) / vstd)

    low60 = float(close.tail(60).min())
    high60 = float(close.tail(60).max())
    from_low = (c - low60) / low60 * 100 if low60 else 0        # % trên đáy 60 phiên
    ret_1m = (c / close.iloc[-21] - 1) * 100 if len(close) > 21 else 0
    ret_3m = (c / close.iloc[-63] - 1) * 100 if len(close) > 63 else 0
    atrp = _atr_pct(df)
    value = snap.get("value")
    foreign_net = snap.get("foreign_net") or 0

    # ---------- Điểm TIỀM NĂNG (0-100) ----------
    up = 0.0
    if vz > 2 and c > close.iloc[-2]:
        up += 30; signals.append(f"Volume breakout (+{vz:.1f}σ) kèm giá tăng")
    elif vz > 1:
        up += 10; signals.append("Thanh khoản cải thiện")
    if not np.isnan(ma20) and c > ma20:
        up += 15; signals.append("Giá vượt MA20 (đảo chiều ngắn hạn)")
    if not np.isnan(ma50) and c > ma50:
        up += 10; signals.append("Giá vượt MA50")
    if from_low < 20 and vz > 1:
        up += 15; signals.append(f"Đang tích lũy sát đáy 60 phiên (+{from_low:.0f}%)")
    if foreign_net > 0:
        up += 15; signals.append("Khối ngoại mua ròng phiên gần nhất")
    if 0 < ret_1m < 30:
        up += 15; signals.append(f"Động lượng 1 tháng lành mạnh ({ret_1m:+.0f}%)")
    upside = float(min(up, 100))

    # ---------- Điểm RỦI RO (0-100, cao = rủi ro lớn) ----------
    risk = 20.0
    if value is not None and value < 3e9:
        risk += 25; warnings.append("Thanh khoản thấp (khó vào/ra, dễ bị đẩy giá).")
    if atrp > 6:
        risk += 20; warnings.append(f"Biến động cực cao (ATR≈{atrp:.0f}%/phiên).")
    if ret_1m > 60:
        risk += 25; warnings.append(f"Đã tăng nóng 1 tháng ({ret_1m:+.0f}%) → rủi ro kéo xả/mua đỉnh.")
    if c < 3000:
        risk += 15; warnings.append("Thị giá rất thấp (<3.000đ) → nguy cơ doanh nghiệp yếu/hủy niêm yết.")
    if foreign_net < 0:
        risk += 10; warnings.append("Khối ngoại đang bán ròng.")
    # "kéo xả": đỉnh 10 phiên cao hơn hiện tại >25% (đã xả sau khi kéo)
    peak10 = float(close.tail(10).max())
    if peak10 > c * 1.25:
        risk += 15; warnings.append("Có dấu hiệu kéo–xả (giá đã rơi mạnh từ đỉnh gần đây).")
    risk = float(min(risk, 100))

    return {
        "upside_score": round(upside, 1),
        "risk_score": round(risk, 1),
        "signals": signals,
        "warnings": warnings,
        "stats": {
            "price": float(c), "ma20": _f(ma20), "ma50": _f(ma50),
            "volume_zscore": round(vz, 2), "from_low60_pct": round(from_low, 1),
            "return_1m_pct": round(ret_1m, 1), "return_3m_pct": round(ret_3m, 1),
            "atr_pct": round(atrp, 1), "liquidity": value, "foreign_net": foreign_net,
        },
    }


def _f(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)
