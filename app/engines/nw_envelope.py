"""Nadaraya-Watson Envelope — tín hiệu THỜI ĐIỂM mua/bán.

Port từ Pine Script "Nadaraya-Watson Envelope [LuxAlgo]" (chế độ non-repaint / endpoint).
Bản gốc © LuxAlgo, giấy phép CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/)
→ Sử dụng PHI THƯƠNG MẠI, ghi công tác giả, chia sẻ tương tự.

Thuật toán (non-repaint, không nhìn trước tương lai):
  gauss(i, h) = exp(-i² / (2h²))                    # trọng số theo khoảng cách i nến về trước
  out[t]      = Σ close[t-i]·gauss(i,h) / Σ gauss   # hồi quy nhân Gaussian một phía (nhân quả)
  mae[t]      = SMA(|close - out|, 499) × mult
  upper = out + mae ; lower = out - mae

Tín hiệu (theo độ cong của dải):
  BUY  khi lower[t] > lower[t-1] và lower[t-1] <= lower[t-2]   → dải dưới vừa bẻ lên (đáy)
  SELL khi upper[t] < upper[t-1] và upper[t-1] >= upper[t-2]   → dải trên vừa bẻ xuống (đỉnh)

⚠️ Tín hiệu kỹ thuật tham khảo — KHÔNG phải khuyến nghị đầu tư, không cam kết lợi nhuận.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

H = 8.0            # bandwidth
MULT = 3.0         # hệ số biên
WINDOW = 500       # số nến tối đa dùng cho nhân Gaussian
MAE_WINDOW = 499   # cửa sổ SMA của sai số tuyệt đối
MIN_BARS = 60      # tối thiểu để tính (trọng số Gaussian h=8 tắt dần sau ~40 nến)
MAE_MIN_PERIODS = 50


def compute(close: pd.Series, h: float = H, mult: float = MULT,
            window: int = WINDOW, mae_window: int = MAE_WINDOW) -> pd.DataFrame | None:
    """Trả DataFrame [out, upper, lower, buy, sell] cùng index với close. None nếu thiếu dữ liệu."""
    close = pd.Series(close).astype(float).reset_index(drop=True)
    n = len(close)
    if n < MIN_BARS:
        return None

    w_len = min(window, n)
    i = np.arange(w_len, dtype=float)
    w = np.exp(-(i * i) / (2.0 * h * h))          # gauss(i, h)

    vals = close.to_numpy(dtype=float)
    # out[t] = Σ_i close[t-i]·w[i]  (tích chập nhân quả)
    conv = np.convolve(vals, w)[:n]
    # Chuẩn hóa: những nến đầu chỉ có t+1 trọng số → chia đúng tổng trọng số đã dùng
    cumw = np.cumsum(w)
    den = cumw[np.minimum(np.arange(n), w_len - 1)]
    out = conv / den

    out_s = pd.Series(out)
    mae = (close - out_s).abs().rolling(mae_window, min_periods=MAE_MIN_PERIODS).mean() * mult

    upper = out_s + mae
    lower = out_s - mae

    buy = (lower > lower.shift(1)) & (lower.shift(1) <= lower.shift(2))
    sell = (upper < upper.shift(1)) & (upper.shift(1) >= upper.shift(2))

    return pd.DataFrame({
        "out": out_s, "upper": upper, "lower": lower,
        "buy": buy.fillna(False), "sell": sell.fillna(False),
    })


def latest_signal(ohlcv: pd.DataFrame, **kw) -> dict | None:
    """Tín hiệu tại nến gần nhất + khoảng cách tới tín hiệu gần nhất.

    Trả {signal: 'BUY'|'SELL'|None, bars_since_buy, bars_since_sell, upper, lower, mid, price,
         position: vị trí giá trong dải 0..1}
    """
    if ohlcv is None or ohlcv.empty:
        return None
    df = ohlcv.sort_values("ts")
    res = compute(df["close"], **kw)
    if res is None or res["upper"].isna().all():
        return None

    last = len(res) - 1
    buy_idx = res.index[res["buy"]].tolist()
    sell_idx = res.index[res["sell"]].tolist()

    signal = None
    if bool(res["buy"].iloc[last]):
        signal = "BUY"
    elif bool(res["sell"].iloc[last]):
        signal = "SELL"

    upper = _f(res["upper"].iloc[last])
    lower = _f(res["lower"].iloc[last])
    mid = _f(res["out"].iloc[last])
    price = float(df["close"].iloc[-1])
    pos = ((price - lower) / (upper - lower)) if (upper and lower and upper > lower) else None

    return {
        "signal": signal,
        "bars_since_buy": (last - buy_idx[-1]) if buy_idx else None,
        "bars_since_sell": (last - sell_idx[-1]) if sell_idx else None,
        "upper": upper, "lower": lower, "mid": mid, "price": price,
        "position": round(pos, 3) if pos is not None else None,
    }


def _f(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)
