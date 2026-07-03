"""Module phân tích kỹ thuật → điểm 0-100 + diễn giải + hỗ trợ/kháng cự.

Không phụ thuộc TA-Lib (khó cài trên Windows). Dùng pandas thuần + pandas-ta nếu có.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-12)
    return 100 - 100 / (1 + rs)


def _macd(close: pd.Series):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


def analyze(df: pd.DataFrame) -> dict:
    """df: OHLCV đã sort tăng dần theo ts. Trả về {score, reasons, support, resistance, indicators}."""
    if df is None or len(df) < 60:
        return {"score": 0, "reasons": ["Không đủ dữ liệu lịch sử (<60 phiên)"],
                "support": None, "resistance": None, "indicators": {}}

    df = df.sort_values("ts").reset_index(drop=True)
    close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]

    ma20, ma50 = close.rolling(20).mean(), close.rolling(50).mean()
    ma100, ma200 = close.rolling(100).mean(), close.rolling(200).mean()
    rsi = _rsi(close)
    macd, macd_sig = _macd(close)
    bb_mid = ma20
    bb_std = close.rolling(20).std()
    bb_up, bb_low = bb_mid + 2 * bb_std, bb_mid - 2 * bb_std

    last = -1
    c = close.iloc[last]
    reasons: list[str] = []
    score = 0.0

    # 1) Xu hướng theo cấu trúc MA (tối đa 30)
    if not np.isnan(ma200.iloc[last]):
        if c > ma50.iloc[last] > ma200.iloc[last]:
            score += 30; reasons.append("Giá > MA50 > MA200 → xu hướng tăng trung/dài hạn")
        elif c > ma200.iloc[last]:
            score += 18; reasons.append("Giá trên MA200 → còn trong xu hướng tăng dài hạn")
        elif c < ma50.iloc[last] < ma200.iloc[last]:
            reasons.append("Giá < MA50 < MA200 → xu hướng giảm, rủi ro cao")
    # thứ tự MA (alignment) tối đa 15
    if not np.isnan(ma200.iloc[last]) and ma20.iloc[last] > ma50.iloc[last] > ma100.iloc[last] > ma200.iloc[last]:
        score += 15; reasons.append("Các đường MA xếp thẳng hàng tăng (MA20>MA50>MA100>MA200)")

    # 2) Momentum RSI + MACD (tối đa 25)
    r = rsi.iloc[last]
    if 50 <= r <= 70:
        score += 12; reasons.append(f"RSI={r:.0f} vùng khỏe (50–70)")
    elif r > 75:
        reasons.append(f"RSI={r:.0f} quá mua → rủi ro điều chỉnh ngắn hạn")
    elif r < 30:
        score += 4; reasons.append(f"RSI={r:.0f} quá bán → có thể hồi kỹ thuật")
    if macd.iloc[last] > macd_sig.iloc[last] and macd.iloc[last - 1] <= macd_sig.iloc[last - 1]:
        score += 13; reasons.append("MACD vừa cắt lên đường tín hiệu (tín hiệu mua động lượng)")
    elif macd.iloc[last] > macd_sig.iloc[last]:
        score += 7; reasons.append("MACD nằm trên đường tín hiệu")

    # 3) Volume breakout (tối đa 25)
    vmean = vol.tail(20).mean()
    vstd = vol.tail(20).std() + 1e-9
    vz = (vol.iloc[last] - vmean) / vstd
    up_day = c > close.iloc[last - 1]
    if vz > 2 and up_day:
        score += 25; reasons.append(f"Volume breakout (+{vz:.1f}σ so với TB20) kèm giá tăng")
    elif vz > 2 and not up_day:
        reasons.append(f"Volume đột biến (+{vz:.1f}σ) nhưng giá giảm → nghi ngờ phân phối")
    elif vz > 1:
        score += 8; reasons.append("Thanh khoản cải thiện trên trung bình")

    # 4) Vị trí trong Bollinger (bonus/cảnh báo)
    if c > bb_up.iloc[last]:
        reasons.append("Giá vượt biên trên Bollinger → có thể quá nóng")
    elif c < bb_low.iloc[last]:
        reasons.append("Giá dưới biên dưới Bollinger → quá bán ngắn hạn")

    # Hỗ trợ / kháng cự đơn giản (swing high/low 60 phiên)
    window = df.tail(60)
    support = float(window["low"].min())
    resistance = float(window["high"].max())

    indicators = {
        "close": float(c), "rsi": float(r),
        "ma20": _last(ma20), "ma50": _last(ma50),
        "ma100": _last(ma100), "ma200": _last(ma200),
        "macd": float(macd.iloc[last]), "macd_signal": float(macd_sig.iloc[last]),
        "volume_zscore": float(vz),
    }
    return {
        "score": float(min(max(score, 0), 100)),
        "reasons": reasons,
        "support": round(support, -1),
        "resistance": round(resistance, -1),
        "indicators": indicators,
    }


def _last(s: pd.Series):
    v = s.iloc[-1]
    return None if pd.isna(v) else float(v)
