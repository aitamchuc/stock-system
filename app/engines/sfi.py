"""SFI Multi-Strength — port từ Pine Script "SFI MULTI-STRENGTH INDEPENDENT LINES".

5 đường độc lập:
  1. NW Baseline      — hồi quy nhân Gaussian (non-repaint, xem nw_envelope.py)
  2. Smart Trail (TFL)— avg(HMA(0.8·len), DWMA(len/3))
  3. UT Bot           — trailing stop theo ATR (Chandelier)
  4. Kalman           — lọc nhiễu Kalman 1 chiều
  5. Oracle Consensus — 6 phiếu: close>EMA20, EMA20>EMA50, RSI>50, MACD>signal,
                        Supertrend tăng, close>SAR  → điểm 0..6

Tất cả đều NHÂN QUẢ (chỉ dùng dữ liệu quá khứ) → dùng được để backtest point-in-time.

⚠️ Chỉ báo kỹ thuật — PHẢI backtest trước khi tin (xem scripts/backtest_sfi.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


# ---------- tiện ích ----------
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder smoothing (Pine ta.rma)."""
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def wma(s: pd.Series, n: int) -> pd.Series:
    """Weighted MA — trọng số tăng dần, nến gần nhất nặng nhất (Pine ta.wma)."""
    n = max(int(n), 1)
    v = s.to_numpy(float)
    out = np.full(len(v), np.nan)
    if len(v) >= n:
        w = np.arange(1, n + 1, dtype=float)
        w /= w.sum()
        out[n - 1:] = sliding_window_view(v, n) @ w
    return pd.Series(out, index=s.index)


def hma(s: pd.Series, n: int) -> pd.Series:
    n = max(int(n), 2)
    raw = 2 * wma(s, max(int(n / 2), 1)) - wma(s, n)
    return wma(raw, max(int(np.floor(np.sqrt(n))), 1))


def atr(df: pd.DataFrame, n: int = 10) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    return rma(tr, n)


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    return 100 - 100 / (1 + rma(d.clip(lower=0), n) / (rma(-d.clip(upper=0), n) + 1e-12))


# ---------- 2. Smart Trail (TFL) ----------
def smart_trail(close: pd.Series, length: int = 24) -> pd.Series:
    hma_len = max(int(length * 0.8), 2)
    h = hma(close, hma_len)
    w1 = max(int(round(length / 3)), 1)
    dwma = wma(wma(close, w1), w1)
    return (h + dwma) / 2.0


# ---------- 3. UT Bot trailing stop ----------
def ut_bot(df: pd.DataFrame, key: float = 2.0, atr_period: int = 10) -> pd.Series:
    c = df["close"].to_numpy(float)
    nloss = (key * atr(df, atr_period)).to_numpy(float)
    stop = np.full(len(c), np.nan)
    prev = 0.0
    for i in range(len(c)):
        if np.isnan(nloss[i]):
            stop[i] = np.nan
            continue
        if i == 0 or np.isnan(stop[i - 1]):
            prev = c[i] - nloss[i]
        else:
            p = stop[i - 1]
            if c[i] > p and c[i - 1] > p:
                prev = max(p, c[i] - nloss[i])
            elif c[i] < p and c[i - 1] < p:
                prev = min(p, c[i] + nloss[i])
            elif c[i] > p:
                prev = c[i] - nloss[i]
            else:
                prev = c[i] + nloss[i]
        stop[i] = prev
    return pd.Series(stop, index=df.index)


# ---------- 4. Kalman ----------
def kalman(close: pd.Series, q: float = 0.0005, r: float = 0.4) -> pd.Series:
    v = close.to_numpy(float)
    out = np.full(len(v), np.nan)
    x = p = None
    for i, s in enumerate(v):
        if np.isnan(s):
            continue
        if x is None:
            x, p = s, 1.0
        else:
            p += q
            k = p / (p + r)
            x = x + k * (s - x)
            p = (1 - k) * p
        out[i] = x
    return pd.Series(out, index=close.index)


# ---------- Supertrend & SAR (cho Oracle) ----------
def supertrend_up(df: pd.DataFrame, factor: float = 3.0, period: int = 10) -> pd.Series:
    """True khi Supertrend đang trong xu hướng TĂNG (Pine direction == -1)."""
    hl2 = (df["high"] + df["low"]) / 2
    a = atr(df, period)
    ub = (hl2 + factor * a).to_numpy(float)
    lb = (hl2 - factor * a).to_numpy(float)
    c = df["close"].to_numpy(float)
    n = len(c)
    up = np.zeros(n, dtype=bool)
    prev_u = prev_l = np.nan
    prev_st = np.nan
    prev_dir = 1
    for i in range(n):
        if np.isnan(ub[i]):
            continue
        u, l = ub[i], lb[i]
        if not np.isnan(prev_l) and not (l > prev_l or c[i - 1] < prev_l):
            l = prev_l
        if not np.isnan(prev_u) and not (u < prev_u or c[i - 1] > prev_u):
            u = prev_u
        if np.isnan(prev_st):
            d = 1
        elif prev_st == prev_u:
            d = -1 if c[i] > u else 1
        else:
            d = 1 if c[i] < l else -1
        st = l if d == -1 else u
        up[i] = (d == -1)
        prev_u, prev_l, prev_st, prev_dir = u, l, st, d
    return pd.Series(up, index=df.index)


def sar(df: pd.DataFrame, start: float = 0.02, inc: float = 0.02, mx: float = 0.2) -> pd.Series:
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    n = len(h)
    out = np.full(n, np.nan)
    if n < 2:
        return pd.Series(out, index=df.index)
    bull = True
    af = start
    ep = h[0]
    s = l[0]
    for i in range(1, n):
        s = s + af * (ep - s)
        if bull:
            s = min(s, l[i - 1], l[i])
            if h[i] > ep:
                ep, af = h[i], min(af + inc, mx)
            if l[i] < s:                       # đảo chiều
                bull, s, ep, af = False, ep, l[i], start
        else:
            s = max(s, h[i - 1], h[i])
            if l[i] < ep:
                ep, af = l[i], min(af + inc, mx)
            if h[i] > s:
                bull, s, ep, af = True, ep, h[i], start
        out[i] = s
    return pd.Series(out, index=df.index)


# ---------- 5. Oracle Consensus ----------
def oracle_score(df: pd.DataFrame) -> pd.Series:
    c = df["close"]
    e20, e50 = ema(c, 20), ema(c, 50)
    macd = ema(c, 12) - ema(c, 26)
    sig = macd.ewm(span=9, adjust=False).mean()
    votes = (
        (c > e20).astype(int)
        + (e20 > e50).astype(int)
        + (rsi(c, 14) > 50).astype(int)
        + (macd > sig).astype(int)
        + supertrend_up(df).astype(int)
        + (c > sar(df)).astype(int)
    )
    return votes


# ---------- Tổng hợp ----------
def compute(df: pd.DataFrame, st_len: int = 24, ut_key: float = 2.0,
            ut_atr: int = 10, k_q: float = 0.0005, k_r: float = 0.4) -> pd.DataFrame:
    """Trả DataFrame các đường + tín hiệu nhị phân (đều nhân quả)."""
    df = df.sort_values("ts").reset_index(drop=True)
    c = df["close"]

    st = smart_trail(c, st_len)
    ub = ut_bot(df, ut_key, ut_atr)
    km = kalman(c, k_q, k_r)
    osc = oracle_score(df)

    out = pd.DataFrame({
        "smart_trail": st, "ut_stop": ub, "kalman": km, "oracle": osc,
    })
    # Tín hiệu trạng thái (đang bullish?)
    out["st_rising"] = st > st.shift(1)
    out["ut_long"] = c > ub
    out["kalman_up"] = c > km
    out["oracle_bull"] = osc >= 4
    out["all_bull"] = (out["st_rising"] & out["ut_long"]
                       & out["kalman_up"] & out["oracle_bull"])
    # Tín hiệu SỰ KIỆN (vừa chuyển sang bullish) — điểm vào lệnh thực tế
    for k in ("st_rising", "ut_long", "kalman_up", "oracle_bull", "all_bull"):
        prev = out[k].shift(1).astype("boolean").fillna(False).astype(bool)
        out[k + "_cross"] = out[k] & ~prev
    return out


# ---------- Dùng thực tế: CẢNH BÁO, không phải tín hiệu mua ----------
OVERHEAT_MIN = 5          # Oracle >= 5 → kỹ thuật quá đồng thuận tăng (backtest: return kém nhất)


def latest(df: pd.DataFrame, **kw) -> dict | None:
    """Giá trị chỉ báo tại nến gần nhất, phục vụ CẢNH BÁO & QUẢN TRỊ RỦI RO.

    ⚠️ Backtest toàn thị trường (1.483 mã, mẫu độc lập): dùng các tín hiệu này để MUA là CÓ HẠI
    (Oracle bật ≥4 → −1.8% sau 20 phiên, t=−6.4). Quan hệ giữa điểm Oracle và lợi nhuận tương lai
    là NGHỊCH ĐẢO đơn điệu. Vì vậy chỉ dùng:
      • oracle_score cao (≥5)  → cảnh báo QUÁ NÓNG / kỳ vọng lợi nhuận thấp
      • ut_stop                 → mức CẮT LỖ động (đúng mục đích thiết kế của UT Bot)
      • smart_trail / kalman    → đường bối cảnh xu hướng
    """
    if df is None or len(df) < 120:
        return None
    r = compute(df, **kw)
    i = len(r) - 1
    close = float(df.sort_values("ts")["close"].iloc[-1])
    o = r["oracle"].iloc[i]
    if pd.isna(o):
        return None
    o = int(o)
    stop = r["ut_stop"].iloc[i]
    return {
        "oracle_score": o,
        "overheated": o >= OVERHEAT_MIN,
        "ut_stop": None if pd.isna(stop) else round(float(stop), -1),
        "stop_distance_pct": (None if pd.isna(stop) or not close
                              else round((close / float(stop) - 1) * 100, 1)),
        "smart_trail_rising": bool(r["st_rising"].iloc[i]),
        "kalman": None if pd.isna(r["kalman"].iloc[i]) else round(float(r["kalman"].iloc[i]), -1),
        "price_above_kalman": bool(r["kalman_up"].iloc[i]),
    }
