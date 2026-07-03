"""Telegram bot: format & gửi cảnh báo.

- Không có token → in ra console (dev mode).
- Có token → gửi thật qua Telegram Bot API (parse_mode=HTML, an toàn với ký tự tiếng Việt).
"""
from __future__ import annotations

import html
import re

import httpx

from app.config import settings
from app.engines.scoring import SIGNAL_LABELS

_API = "https://api.telegram.org/bot{token}/{method}"

_DISCLAIMER = ("<i>Thông tin tham khảo, KHÔNG phải khuyến nghị đầu tư và không cam kết "
               "lợi nhuận. Bạn tự chịu trách nhiệm với quyết định của mình.</i>")

_TYPE_ICON = {
    "high_score": "⭐", "breakout": "🚀",
    "foreign_inflow": "🌊", "risk": "⚠️",
}


def _esc(v) -> str:
    return html.escape(str(v))


def enabled() -> bool:
    return bool(settings.telegram_token and settings.telegram_chat_id)


def format_alert(a: dict) -> str:
    signal_label = SIGNAL_LABELS.get(a["signal"], a["signal"])
    icon = _TYPE_ICON.get(a["alert_type"], "🔔")
    price = f"{a['price']:,.0f}" if a.get("price") else "N/A"
    support = f"{a['support']:,.0f}" if a.get("support") else "—"
    resistance = f"{a['resistance']:,.0f}" if a.get("resistance") else "—"
    return (
        f"{icon} <b>{_esc(a['symbol'])}</b> | Giá: {_esc(price)}\n"
        f"📊 Điểm tổng hợp: <b>{a['final_score']:.0f}/100</b> → {_esc(signal_label)}\n"
        f"🧠 {_esc(a['main_reason'])}\n"
        f"🎯 Hỗ trợ: {_esc(support)} | Kháng cự: {_esc(resistance)}\n"
        f"⚠️ Rủi ro: {_esc(a['main_risk'])}\n"
        f"🔗 <a href=\"{_esc(a['dashboard_url'])}\">Xem chi tiết</a>\n"
        f"—\n{_DISCLAIMER}"
    )


def format_recommendation(r: dict) -> str:
    """Tin khuyến nghị giá mua/bán do AI agent tạo (mã có BCTC mới)."""
    def money(v):
        return f"{v:,.0f}" if v is not None else "—"

    exp = r.get("expected_return")
    rr = r.get("risk_reward")
    fv = f"\n💡 Giá hợp lý (P/E tham chiếu): {money(r.get('fair_value'))}" if r.get("fair_value") else ""
    tag = "🤖AI" if r.get("method") == "llm" else "📐Quy tắc"
    return (
        f"🎯 <b>KHUYẾN NGHỊ GIÁ — {_esc(r['symbol'])}</b>  <i>({tag})</i>\n"
        f"BCTC kỳ: {_esc(r.get('report_period') or '—')} | Giá hiện tại: {money(r.get('current_price'))}\n"
        f"🟢 <b>Vùng MUA:</b> {money(r.get('buy_low'))} – {money(r.get('buy_high'))}\n"
        f"🔴 <b>Giá BÁN (chốt lời):</b> {money(r.get('target_price'))}"
        + (f" ({exp*100:+.0f}%)" if exp is not None else "") + "\n"
        f"🛑 <b>Cắt lỗ:</b> {money(r.get('stop_loss'))}"
        + (f" | R:R ≈ {rr:.1f}" if rr is not None else "")
        + f" | Độ tin cậy: {_esc(r.get('conviction') or '—')}"
        + fv + "\n"
        f"🧠 {_esc(r.get('thesis') or '')}\n"
        f"—\n{_DISCLAIMER}"
    )


def format_penny(r: dict) -> str:
    """Tin cảnh báo ứng viên penny — nhấn mạnh rủi ro."""
    def money(v):
        return f"{v:,.0f}" if v is not None else "—"

    sigs = "\n".join(f"  • {_esc(s)}" for s in (r.get("signals") or [])[:4]) or "  • —"
    warns = "\n".join(f"  ⚠️ {_esc(w)}" for w in (r.get("warnings") or [])[:5])
    liq = (r.get("liquidity") or 0) / 1e9
    return (
        f"🪙 <b>PENNY TIỀM NĂNG — {_esc(r['symbol'])}</b>\n"
        f"Giá: {money(r.get('price'))} | Thanh khoản: {liq:,.1f} tỷ | 1 tháng: {r.get('return_1m_pct',0):+.0f}%\n"
        f"📈 <b>Tiềm năng: {r.get('upside_score',0):.0f}/100</b> | "
        f"🔥 <b>Rủi ro: {r.get('risk_score',0):.0f}/100</b>\n"
        f"Tín hiệu:\n{sigs}\n"
        f"{warns}\n"
        f"—\n🚨 <b>ĐẦU CƠ RỦI RO RẤT CAO</b> — có thể bị làm giá/kéo xả và mất phần lớn vốn.\n{_DISCLAIMER}"
    )


_DIR_ICON = {"tích cực": "🟢", "tiêu cực": "🔴", "trung tính": "⚪"}
_LVL_ICON = {"cao": "🔥", "trung bình": "▶️", "thấp": "·"}


def format_news_digest(items: list[dict], run_label: str = "") -> str:
    """Bản tin tổng hợp: tin có ảnh hưởng đáng chú ý tới TTCK."""
    header = f"📰 <b>BẢN TIN ẢNH HƯỞNG TTCK</b>{(' — ' + run_label) if run_label else ''}\n"
    if not items:
        return header + "Không có tin đáng chú ý trong đợt quét này.\n—\n" + _DISCLAIMER
    lines = [header]
    for it in items:
        di = _DIR_ICON.get(it.get("direction"), "⚪")
        lv = _LVL_ICON.get(it.get("impact_level"), "·")
        syms = it.get("affected_symbols") or []
        secs = it.get("sectors") or []
        tag = ""
        if syms:
            tag = " | Mã: " + ", ".join(_esc(s) for s in syms[:5])
        elif secs:
            tag = " | Ngành: " + ", ".join(_esc(s) for s in secs[:3])
        lines.append(
            f"{lv}{di} <b>{_esc(it['title'][:110])}</b>{tag}\n"
            f"   {_esc((it.get('analysis') or '')[:220])}\n"
            f"   <a href=\"{_esc(it['url'])}\">{_esc(it.get('source') or 'nguồn')}</a>"
        )
    lines.append("—\n" + _DISCLAIMER)
    return "\n".join(lines)


def _md_bold_to_html(text: str) -> str:
    """LLM đôi khi lẫn **bold** Markdown → chuyển sang <b> cho parse_mode=HTML."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text or "")


def format_news_brief(brief: str, sources: list[dict], run_label: str = "") -> str:
    """Bản tin phân tích SÂU (AI tổng hợp) + danh sách nguồn."""
    brief = _md_bold_to_html(brief)
    header = f"🧠 <b>PHÂN TÍCH TIN TỨC — TÁC ĐỘNG TTCK</b>{(' · ' + run_label) if run_label else ''}\n\n"
    src_lines = "\n".join(
        f"• <a href=\"{_esc(s['url'])}\">{_esc((s.get('title') or '')[:80])}</a>"
        for s in sources[:8]
    )
    src_block = ("\n\n📎 <b>Nguồn:</b>\n" + src_lines) if src_lines else ""
    return f"{header}{brief}{src_block}\n—\n{_DISCLAIMER}"


def format_daily_picks(picks: list[dict], ts: str) -> str:
    """Danh sách cổ phiếu NÊN ĐẦU TƯ do AI chọn lọc."""
    head = f"✅ <b>CỔ PHIẾU NÊN ĐẦU TƯ — {_esc(ts)}</b> (AI chọn lọc)\n"
    if not picks:
        return (head + "\nHôm nay AI không chọn mã nào đủ tin cậy để tích lũy — nên đứng ngoài "
                "quan sát.\n—\n" + _DISCLAIMER)
    lines = [head]
    for i, p in enumerate(picks, 1):
        def money(v):
            return f"{v:,.0f}" if v is not None else "—"
        conv = f" · độ tin cậy {_esc(p.get('conviction'))}" if p.get("conviction") else ""
        zone = ""
        if p.get("buy_low") and p.get("buy_high"):
            zone = (f"\n   🟢 Vùng mua: {money(p['buy_low'])}–{money(p['buy_high'])}"
                    f" | 🎯 {money(p.get('target_price'))} | 🛑 {money(p.get('stop_loss'))}")
        lines.append(
            f"\n{i}. <b>{_esc(p['symbol'])}</b> — {_esc(p.get('action') or 'Mua tích lũy')} "
            f"(điểm {p.get('final_score', 0):.0f}/100{conv})"
            f"{zone}\n   🧠 {_esc(p.get('thesis') or '')}"
        )
    lines.append("\n—\n" + _DISCLAIMER)
    return "\n".join(lines)


def _post(method: str, payload: dict) -> dict | None:
    try:
        resp = httpx.post(_API.format(token=settings.telegram_token, method=method),
                          json=payload, timeout=15)
        data = resp.json()
        if not data.get("ok"):
            print(f"[telegram] API trả lỗi: {data}")
            return None
        return data
    except Exception as exc:  # pragma: no cover
        print(f"[telegram] gọi {method} lỗi: {exc}")
        return None


def send_message(text: str, chat_id: str | None = None) -> bool:
    if not settings.telegram_token or not (chat_id or settings.telegram_chat_id):
        print("\n[TELEGRAM - DEV MODE]\n" + text + "\n")
        return True
    ok = _post("sendMessage", {
        "chat_id": chat_id or settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    })
    return ok is not None


def send(a: dict) -> bool:
    return send_message(format_alert(a))


def send_many(alerts: list[dict]) -> int:
    return sum(1 for a in alerts if send(a))


def send_test() -> bool:
    """Gửi 1 tin mẫu để kiểm tra cấu hình."""
    sample = {
        "symbol": "FPT", "price": 72500, "final_score": 82, "signal": "very_positive",
        "alert_type": "high_score",
        "main_reason": "Tin kiểm tra kết nối Telegram — hệ thống hoạt động ✅",
        "support": 68000, "resistance": 76000,
        "main_risk": "Đây chỉ là tin test, không phải tín hiệu thật",
        "dashboard_url": f"{settings.dashboard_base_url}/stock/FPT",
    }
    return send(sample)


if __name__ == "__main__":
    print("Trạng thái:", "ĐÃ CẤU HÌNH" if enabled() else "chưa có token/chat_id (dev mode)")
    send_test()
