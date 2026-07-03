"""AI agent đề xuất vùng giá MUA / giá BÁN (chốt lời) / cắt lỗ cho một mã.

Kết hợp: điểm số 8 nhóm + luận điểm + hỗ trợ/kháng cự (kỹ thuật) + P/E–P/B (định giá).

- Nếu có ANTHROPIC_API_KEY → dùng Claude "nghiên cứu & đánh giá" để tinh chỉnh mức giá và viết
  luận điểm; kết quả bị RÀNG BUỘC & kiểm tra tính hợp lệ (buy_low ≤ buy_high < target, stop < buy_low).
- Nếu không có key → dùng mức giá theo QUY TẮC xác định (hỗ trợ/kháng cự + điểm số) + luận điểm mẫu.

⚠️ Mọi kết quả CHỈ THAM KHẢO — không phải khuyến nghị đầu tư, không cam kết lợi nhuận.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app import llm

TARGET_PE = 12.0        # P/E tham chiếu để ước lượng "giá hợp lý" (chỉ mang tính tham khảo)
STOP_BUFFER = 0.93      # cắt lỗ ~7% dưới hỗ trợ

_ADVISOR_FALLBACK = (
    "Bạn là chuyên gia phân tích tài chính & quản trị danh mục cho chứng khoán Việt Nam, tư duy "
    "thận trọng, ưu tiên quản trị rủi ro, chỉ dùng dữ liệu được cung cấp, không cam kết lợi nhuận."
)


@lru_cache
def advisor_system() -> str:
    """Nạp system prompt 'Cố vấn Đầu tư AI' từ app/prompts/advisor.md (cache)."""
    p = Path(__file__).resolve().parent.parent / "prompts" / "advisor.md"
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return _ADVISOR_FALLBACK


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, -1)


def fair_value(current: float, pe: float | None) -> float | None:
    """Giá hợp lý tham chiếu = TARGET_PE × EPS_TTM, với EPS_TTM = current/pe."""
    if not pe or pe <= 0:
        return None
    eps_ttm = current / pe
    return _round(TARGET_PE * eps_ttm)


def compute_levels(current: float, support: float | None, resistance: float | None,
                   final_score: float) -> dict:
    """Mức giá theo quy tắc xác định (không dùng LLM)."""
    # Phòng thủ khi thiếu hỗ trợ/kháng cự hợp lệ
    if not support or not resistance or support >= resistance:
        support = current * 0.92
        resistance = current * 1.12
    band = resistance - support

    # Vùng mua: nửa dưới của nền giá, gần hỗ trợ
    buy_low = support
    buy_high = support + 0.35 * band
    if current < buy_high:                      # giá đã về gần hỗ trợ → mua quanh giá hiện tại
        buy_high = min(buy_high, current * 1.01)
        buy_low = min(buy_low, current * 0.97)

    target = resistance
    if final_score >= 75:                       # điểm cao → nới mục tiêu chốt lời
        target = resistance + 0.30 * band
    stop_loss = support * STOP_BUFFER

    buy_mid = (buy_low + buy_high) / 2
    exp_ret = target / buy_mid - 1 if buy_mid else None
    rr = (target - buy_mid) / (buy_mid - stop_loss) if (buy_mid - stop_loss) > 0 else None

    conviction = "cao" if final_score >= 75 else "trung bình" if final_score >= 60 else "thấp"
    return {
        "buy_low": _round(buy_low), "buy_high": _round(buy_high),
        "target_price": _round(target), "stop_loss": _round(stop_loss),
        "expected_return": round(exp_ret, 3) if exp_ret is not None else None,
        "risk_reward": round(rr, 2) if rr is not None else None,
        "conviction": conviction,
    }


def _template_thesis(ctx: dict, levels: dict) -> str:
    why = ctx.get("why", "")
    risks = "; ".join((ctx.get("main_risks") or [])[:2])
    val = ""
    if ctx.get("pe"):
        val = f" Định giá P/E≈{ctx['pe']:.1f}, P/B≈{ctx.get('pb') or float('nan'):.1f}."
    return (
        f"{why}.{val} Vùng mua quanh hỗ trợ {levels['buy_low']:,.0f}–{levels['buy_high']:,.0f}; "
        f"mục tiêu {levels['target_price']:,.0f} (tỷ suất kỳ vọng "
        f"{(levels['expected_return'] or 0)*100:+.0f}%), cắt lỗ dưới {levels['stop_loss']:,.0f}. "
        f"Rủi ro chính: {risks or 'biến động thị trường'}."
    )


def _validate(llm: dict, current: float) -> bool:
    try:
        bl, bh = float(llm["buy_low"]), float(llm["buy_high"])
        tp, sl = float(llm["target_price"]), float(llm["stop_loss"])
    except (KeyError, TypeError, ValueError):
        return False
    # Ràng buộc logic: cắt lỗ < mua thấp ≤ mua cao < mục tiêu; và trong biên hợp lý so với giá
    if not (sl < bl <= bh < tp):
        return False
    if not (0.4 * current < sl and tp < 3.0 * current):
        return False
    return True


def _llm_refine(ctx: dict, levels: dict) -> dict | None:
    """Dùng LLM (ChatGPT/Claude) tinh chỉnh mức giá + luận điểm. None nếu lỗi/không hợp lệ."""
    prompt = (
        "Áp dụng khung phân tích & nguyên tắc của bạn cho dữ liệu định lượng dưới đây, đề xuất vùng "
        "giá MUA, giá BÁN (chốt lời) và CẮT LỖ cho nhà đầu tư trung hạn.\n"
        "Ràng buộc: cắt_lỗ < mua_thấp ≤ mua_cao < mục_tiêu. Mức giá bám theo hỗ trợ/kháng cự và "
        "định giá, không bịa. Giá tính bằng VND.\n"
        "VỚI TÁC VỤ NÀY: bỏ qua định dạng nhiều mục mặc định, CHỈ trả về DUY NHẤT một JSON "
        "(luận điểm dồn vào trường 'thesis').\n\n"
        f"DỮ LIỆU:\n{json.dumps(ctx, ensure_ascii=False, indent=2)}\n\n"
        f"GỢI Ý MỨC GIÁ THEO QUY TẮC (có thể tinh chỉnh):\n{json.dumps(levels, ensure_ascii=False)}\n\n"
        "JSON: {\"buy_low\":số,\"buy_high\":số,\"target_price\":số,"
        "\"stop_loss\":số,\"conviction\":\"cao|trung bình|thấp\",\"thesis\":\"2-3 câu tiếng Việt "
        "nêu luận điểm + rủi ro chính\"}"
    )
    text = llm.chat(prompt, max_tokens=600, system=advisor_system())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not _validate(data, ctx["current_price"]):
        return None
    return data


def recommend(ctx: dict) -> dict:
    """ctx: {symbol, current_price, support, resistance, final_score, pe, pb, why, main_risks, period}.

    Trả dict đầy đủ để lưu Recommendation.
    """
    current = ctx["current_price"]
    levels = compute_levels(current, ctx.get("support"), ctx.get("resistance"), ctx["final_score"])
    fv = fair_value(current, ctx.get("pe"))
    method, thesis = "rule", _template_thesis(ctx, levels)

    if llm.available():
        try:
            refined = _llm_refine(ctx, levels)
            if refined:
                levels.update({
                    "buy_low": _round(float(refined["buy_low"])),
                    "buy_high": _round(float(refined["buy_high"])),
                    "target_price": _round(float(refined["target_price"])),
                    "stop_loss": _round(float(refined["stop_loss"])),
                    "conviction": refined.get("conviction", levels["conviction"]),
                })
                buy_mid = (levels["buy_low"] + levels["buy_high"]) / 2
                levels["expected_return"] = round(levels["target_price"] / buy_mid - 1, 3)
                levels["risk_reward"] = round(
                    (levels["target_price"] - buy_mid) / max(buy_mid - levels["stop_loss"], 1e-9), 2)
                thesis, method = refined.get("thesis", thesis), "llm"
        except Exception as exc:  # pragma: no cover
            print(f"[recommend] LLM lỗi, dùng quy tắc: {exc}")

    return {
        "report_period": ctx.get("period"),
        "current_price": current,
        "fair_value": fv,
        "thesis": thesis,
        "method": method,
        **levels,
    }
