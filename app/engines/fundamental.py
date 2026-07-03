"""Phân tích cơ bản từ BCTC đã chuẩn hóa.

Trả về 4 nhóm điểm (0-100): fundamental, growth, health, valuation + danh sách red flags.
Chỉ dùng các kỳ có publish_date <= as_of (point-in-time) để tránh look-ahead bias.
"""
from __future__ import annotations

from datetime import date

from app.models import Financial


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


PAR_VALUE = 10_000.0   # mệnh giá cổ phiếu VN (gần như phổ quát)


def compute_valuation_metrics(fins: list[Financial], price: float | None) -> dict:
    """Tính P/E, P/B từ giá thị trường + LNST TTM + book value.

    - Số cổ phiếu = vốn góp (share_capital) / mệnh giá 10.000đ  → cách chuẩn & ổn định ở VN.
      (Dự phòng: LNST_TTM / EPS_TTM khi thiếu vốn góp.)
    - EPS_TTM = LNST_TTM / số cp ; P/E = giá / EPS_TTM.
    - P/B = giá / (vốn CSH / số cp).
    Trả {pe, pb, eps_ttm, shares} — None khi không đủ dữ liệu.
    """
    out = {"pe": None, "pb": None, "eps_ttm": None, "shares": None}
    if not price or not fins:
        return out

    q = sorted(fins, key=lambda f: f.period)
    latest = q[-1]
    ni_list = [f.net_income for f in q[-4:] if f.net_income]
    ni_ttm = sum(ni_list) if len(ni_list) >= 4 else ((ni_list[-1] * 4) if ni_list else None)

    # Số cổ phiếu: ưu tiên vốn góp / mệnh giá
    shares = None
    if latest.share_capital and latest.share_capital > 0:
        shares = latest.share_capital / PAR_VALUE
    else:                                            # dự phòng: suy từ EPS quý gần nhất
        eps_list = [f.eps for f in q[-4:] if f.eps]
        eps_ttm_fb = sum(eps_list) if len(eps_list) >= 4 else ((eps_list[-1] * 4) if eps_list else None)
        if ni_ttm and eps_ttm_fb:
            shares = ni_ttm / eps_ttm_fb

    if shares and shares > 0:
        out["shares"] = round(shares)
        if ni_ttm and ni_ttm > 0:
            eps_ttm = ni_ttm / shares
            out["eps_ttm"] = round(eps_ttm, 1)
            out["pe"] = round(min(price / eps_ttm, 200), 2)
        if latest.equity and latest.equity > 0:
            bvps = latest.equity / shares
            if bvps > 0:
                out["pb"] = round(min(price / bvps, 50), 2)
    return out


def analyze(financials: list[Financial], as_of: date | None = None,
            price: float | None = None) -> dict:
    # Lọc point-in-time
    fins = [
        f for f in financials
        if as_of is None or f.publish_date is None or f.publish_date <= as_of
    ]
    fins = sorted(fins, key=lambda f: f.period)
    if not fins:
        return _empty("Chưa có báo cáo tài chính khả dụng tại thời điểm xét")

    latest = fins[-1]
    prev = fins[-2] if len(fins) >= 2 else None
    year_ago = fins[-5] if len(fins) >= 5 else None
    reasons: list[str] = []
    red_flags: list[str] = []

    # ---- Fundamental: chất lượng lợi nhuận cốt lõi ----
    roe = latest.roe or 0
    net_margin = latest.net_margin or 0
    fundamental = 100 * _clip(
        0.5 * _clip(roe / 0.20) + 0.3 * _clip(net_margin / 0.15) + 0.2 * _clip((latest.gross_margin or 0) / 0.30)
    )
    if roe:
        reasons.append(f"ROE≈{roe*100:.0f}%")
    if net_margin:
        reasons.append(f"Biên LN ròng≈{net_margin*100:.0f}%")

    # ---- Growth: tăng trưởng QoQ & YoY ----
    growth = 50.0
    if prev and prev.revenue:
        qoq = (latest.revenue - prev.revenue) / abs(prev.revenue)
        growth += 100 * _clip(qoq / 0.10) * 0.25
        reasons.append(f"Doanh thu QoQ {qoq*100:+.0f}%")
    if year_ago and year_ago.net_income:
        yoy = (latest.net_income - year_ago.net_income) / abs(year_ago.net_income)
        growth += 100 * _clip(yoy / 0.20) * 0.25
        reasons.append(f"LNST YoY {yoy*100:+.0f}%")
    growth = _clip(growth / 100) * 100

    # ---- Health: sức khỏe tài chính ----
    debt_equity = (latest.total_debt or 0) / ((latest.equity or 0) + 1e-9)
    cfo_ni = (latest.cfo or 0) / ((latest.net_income or 0) + 1e-9)
    health = 100 * _clip(
        0.35 * _clip(1 - debt_equity / 2)
        + 0.35 * _clip(cfo_ni / 1.0)
        + 0.30 * (1.0 if (latest.fcf or 0) > 0 else 0.3)
    )
    reasons.append(f"Nợ/VCSH≈{debt_equity:.2f}")

    # ---- Valuation: định giá (điểm cao = rẻ hơn), tính P/E-P/B từ giá thị trường ----
    metrics = compute_valuation_metrics(fins, price)
    pe, pb = metrics["pe"], metrics["pb"]
    parts_v: list[tuple[float, float]] = []          # (score_0_1, weight)
    if pe is not None:
        parts_v.append((_clip((20 - pe) / 20), 0.6))  # P/E<=0..20 → rẻ..đắt
    if pb is not None:
        parts_v.append((_clip((3 - pb) / 3), 0.4))    # P/B<=0..3
    if parts_v:
        wsum = sum(w for _, w in parts_v)
        valuation = 100 * sum(v * w for v, w in parts_v) / wsum
        reasons.append(
            "Định giá: " + ", ".join(
                x for x in [
                    f"P/E≈{pe:.1f}" if pe is not None else None,
                    f"P/B≈{pb:.1f}" if pb is not None else None,
                ] if x
            )
        )
    else:
        valuation = 50.0                              # thiếu dữ liệu → trung tính (không phạt)
        reasons.append("Chưa đủ dữ liệu định giá (P/E, P/B)")

    # ---- Red flags (cảnh báo bất thường) ----
    if (latest.net_income or 0) > 0 and (latest.cfo or 0) < 0:
        red_flags.append("Lợi nhuận dương nhưng dòng tiền kinh doanh ÂM")
    if prev and prev.receivables and latest.receivables and \
            latest.receivables > prev.receivables * 1.5:
        red_flags.append("Phải thu tăng đột biến (>50% QoQ)")
    if prev and prev.inventory and latest.inventory and \
            latest.inventory > prev.inventory * 1.5:
        red_flags.append("Tồn kho tăng mạnh (>50% QoQ)")
    if prev and prev.total_debt and latest.total_debt and \
            latest.total_debt > prev.total_debt * 1.4:
        red_flags.append("Nợ vay tăng mạnh (>40% QoQ)")
    if prev and (latest.gross_margin or 0) < (prev.gross_margin or 0) - 0.05:
        red_flags.append("Biên lợi nhuận gộp suy giảm rõ rệt")

    return {
        "fundamental": round(fundamental, 1),
        "growth": round(growth, 1),
        "health": round(health, 1),
        "valuation": round(valuation, 1),
        "reasons": reasons,
        "red_flags": red_flags,
        "period": latest.period,
        "pe": pe,
        "pb": pb,
        "eps_ttm": metrics["eps_ttm"],
    }


def _empty(msg: str) -> dict:
    return {
        "fundamental": 0, "growth": 0, "health": 0, "valuation": 50,
        "reasons": [msg], "red_flags": [], "period": None,
        "pe": None, "pb": None, "eps_ttm": None,
    }
