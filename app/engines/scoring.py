"""Gộp 8 nhóm điểm → final score, tín hiệu, rationale (JSON)."""
from __future__ import annotations

SIGNAL_LABELS = {
    "very_positive": "Rất tích cực",
    "positive": "Tích cực",
    "watch": "Theo dõi",
    "neutral": "Trung tính",
    "risk_warning": "Cảnh báo rủi ro",
    "distribution": "Có dấu hiệu phân phối",
    "avoid": "Tránh mua",
}


def compute_risk_score(*, red_flags: list[str], liquidity_value: float,
                       ta_indicators: dict, moneyflow_label: str) -> tuple[float, list[str]]:
    """Điểm rủi ro: CAO = rủi ro THẤP (đồng hướng với các nhóm khác)."""
    score = 100.0
    reasons: list[str] = []

    score -= 15 * len(red_flags)
    if red_flags:
        reasons.append(f"{len(red_flags)} red flag từ BCTC")

    if liquidity_value and liquidity_value < 1e9:      # < ~1 tỷ/phiên
        score -= 25; reasons.append("Thanh khoản thấp (khó vào/ra)")

    close = ta_indicators.get("close")
    ma200 = ta_indicators.get("ma200")
    if close and ma200 and close < ma200:
        score -= 15; reasons.append("Giá dưới MA200 (xu hướng dài hạn yếu)")

    rsi = ta_indicators.get("rsi")
    if rsi and rsi > 80:
        score -= 10; reasons.append("RSI quá mua cực đoan")

    if moneyflow_label == "negative":
        score -= 10; reasons.append("Dòng tiền lớn đang rút ra")

    return max(0.0, min(100.0, score)), reasons


def classify(final: float, *, red_flags: list[str], ta: dict,
             moneyflow_label: str, health: float, liquidity_value: float) -> str:
    """Ánh xạ tín hiệu (có ưu tiên các điều kiện cảnh báo)."""
    ind = ta.get("indicators", {})
    distribution = (ind.get("volume_zscore", 0) > 2
                    and ind.get("close", 0) < (ind.get("ma20") or 1e18))

    if health < 30 or (liquidity_value and liquidity_value < 5e8):
        return "avoid"
    if distribution or moneyflow_label == "negative" and len(red_flags) >= 1:
        return "distribution"
    if len(red_flags) >= 2 or final < 45:
        return "risk_warning"
    if final >= 80:
        return "very_positive"
    if final >= 70:
        return "positive"
    if final >= 60:
        return "watch"
    return "neutral"


def combine(*, ta: dict, fa: dict, mf: dict, news: dict,
            liquidity_value: float, weights: dict) -> dict:
    """Trả về dict đầy đủ để ghi DailyScore."""
    risk_score, risk_reasons = compute_risk_score(
        red_flags=fa["red_flags"], liquidity_value=liquidity_value,
        ta_indicators=ta.get("indicators", {}), moneyflow_label=mf["label"],
    )

    parts = {
        "fundamental": fa["fundamental"],
        "growth": fa["growth"],
        "health": fa["health"],
        "valuation": fa["valuation"],
        "technical": ta["score"],
        "moneyflow": mf["score"],
        "news": news["score"],
        "risk": risk_score,
    }
    total_w = sum(weights.values()) or 1.0
    final = sum(parts[k] * weights.get(k, 0) for k in parts) / total_w

    signal = classify(
        final, red_flags=fa["red_flags"], ta=ta, moneyflow_label=mf["label"],
        health=fa["health"], liquidity_value=liquidity_value,
    )

    # Điều kiện làm tín hiệu vô hiệu (invalidation)
    invalidation = []
    if ta.get("support"):
        invalidation.append(f"Đóng cửa thủng hỗ trợ {ta['support']:,.0f}")
    if mf["label"] == "positive":
        invalidation.append("Khối ngoại chuyển sang bán ròng mạnh")
    invalidation.append("Xuất hiện tin xấu/điều tra/hủy niêm yết")

    rationale = {
        "why": _why(signal, parts),
        "supporting_data": {
            "technical": ta["reasons"],
            "fundamental": fa["reasons"],
            "moneyflow": mf["reasons"],
            "news": news["reasons"],
        },
        "main_risks": risk_reasons + fa["red_flags"],
        "invalidation": invalidation,
        "support": ta.get("support"),
        "resistance": ta.get("resistance"),
        "parts": {k: round(v, 1) for k, v in parts.items()},
    }

    return {
        "s_fundamental": parts["fundamental"], "s_growth": parts["growth"],
        "s_health": parts["health"], "s_valuation": parts["valuation"],
        "s_technical": parts["technical"], "s_moneyflow": parts["moneyflow"],
        "s_news": parts["news"], "s_risk": parts["risk"],
        "final_score": round(final, 1),
        "signal": signal,
        "rationale": rationale,
    }


def _why(signal: str, parts: dict) -> str:
    top = sorted(parts.items(), key=lambda kv: kv[1], reverse=True)[:2]
    drivers = ", ".join(f"{k}={v:.0f}" for k, v in top)
    return f"Tín hiệu '{SIGNAL_LABELS[signal]}' dẫn dắt bởi: {drivers}"
