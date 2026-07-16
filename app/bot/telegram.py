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


def format_nw_picks(picks: list[dict], ts: str, scanned: int = 0) -> str:
    """CẢNH BÁO QUÁ NÓNG — các mã đang được kỹ thuật đồng thuận tăng mạnh nhất.

    ⚠️ Đây KHÔNG phải danh sách mua. Backtest toàn thị trường cho thấy đúng nhóm mã này
    (giá vượt xa MA200 + dòng tiền vào + đồng thuận kỹ thuật cao) có kỳ vọng lợi nhuận
    THẤP NHẤT. Trình bày như "top mã đáng theo dõi" sẽ dẫn người đọc đi sai.
    """
    head = (f"🔥 <b>CẢNH BÁO QUÁ NÓNG — {_esc(ts)}</b>\n"
            f"<i>{len(picks)} mã đang tăng nóng nhất trong {scanned} mã thanh khoản cao "
            f"(vượt MA200 + dòng tiền vào mạnh)</i>\n"
            f"<b>⛔ ĐỪNG ĐUỔI MUA</b> — dữ liệu cho thấy đây là lúc kỳ vọng lợi nhuận THẤP NHẤT.\n")
    if not picks:
        return (head.replace("⛔ ĐỪNG ĐUỔI MUA</b>", "</b>")
                + "\nHôm nay không mã nào rơi vào vùng quá nóng.\n—\n" + _DISCLAIMER)
    lines = [head]
    for p in picks:
        liq = (p.get("liquidity") or 0) / 1e9
        fn = p.get("foreign_net")
        fn_s = f" · khối ngoại {fn/1e9:+.1f} tỷ" if fn else ""
        oracle = p.get("oracle_score")
        or_s = f" · đồng thuận kỹ thuật <b>{oracle}/6</b>" if oracle is not None else ""
        above = (p["price"] / p["ma200"] - 1)
        lines.append(
            f"\n🔥 <b>{_esc(p['symbol'])}</b> — {p['price']:,.0f} "
            f"(<b>+{above:.0%} trên MA200</b>){or_s}\n"
            f"   Độ nóng {p['score']:.0f}/100 · thanh khoản {liq:,.1f} tỷ"
            f" · dòng tiền CMF {p.get('cmf', 0):+.3f}{fn_s}"
        )
    lines.append(
        "\n—\n🚨 <b>ĐÂY LÀ CẢNH BÁO RỦI RO, KHÔNG PHẢI GỢI Ý MUA.</b>\n"
        "<i>Backtest toàn thị trường (~1.480 mã, 45.000+ quan sát độc lập): mua khi giá vượt MA200 "
        "cho lợi nhuận ÂM (t=−18); mua khi đồng thuận kỹ thuật cao cũng ÂM (điểm 6/6 → ~0% sau 20 "
        "phiên, trong khi điểm 0/6 → +2.9%). Thị trường VN giai đoạn này HỒI QUY VỀ TRUNG BÌNH — "
        "mua lúc mạnh thua mua lúc yếu. 'Độ nóng' càng cao càng nên THẬN TRỌNG, không phải càng "
        "nên mua. Nếu đang nắm giữ các mã này: cân nhắc mức cắt lỗ.</i>\n" + _DISCLAIMER)
    return "\n".join(lines)


def format_nw_signals(buys: list[dict], sells: list[dict], ts: str) -> str:
    """Tín hiệu THỜI ĐIỂM mua/bán theo Nadaraya-Watson Envelope (LuxAlgo, CC BY-NC-SA)."""
    head = f"⏱ <b>TÍN HIỆU THỜI ĐIỂM — {_esc(ts)}</b>\n<i>Nadaraya-Watson Envelope</i>\n"
    if not buys and not sells:
        return head + "\nHôm nay không có tín hiệu mua/bán nào.\n—\n" + _DISCLAIMER

    def block(items, icon, label):
        if not items:
            return ""
        lines = [f"\n{icon} <b>{label}</b>"]
        for it in items:
            pos = it.get("position")
            pos_s = f" · vị trí trong dải {pos:.0%}" if pos is not None else ""
            lines.append(
                f"  • <b>{_esc(it['symbol'])}</b> — giá {it['price']:,.0f}"
                f" (dải {it['lower']:,.0f}–{it['upper']:,.0f}){pos_s}"
            )
        return "\n".join(lines)

    body = block(buys, "🟢", "MUA (dải dưới bẻ lên)") + "\n" + \
        block(sells, "🔴", "BÁN (dải trên bẻ xuống)")
    return (head + body +
            "\n—\n<i>Tín hiệu kỹ thuật ngắn hạn, hay nhiễu — nên đối chiếu với điểm cơ bản.</i>\n"
            + _DISCLAIMER)


def format_deep_analysis(a: dict, thesis: str | None = None) -> str:
    """Báo cáo phân tích SÂU 1 mã (lệnh /<MÃ>) — cơ bản + kỹ thuật + dòng tiền + vùng giá."""
    if a.get("error") == "not_enough_data":
        return (f"❌ <b>{_esc(a['symbol'])}</b>: không đủ dữ liệu để phân tích "
                f"(chỉ có {a.get('bars', 0)} nến, cần ≥120).\n"
                f"Có thể mã này mới niêm yết, thanh khoản quá thấp, hoặc mã không tồn tại.")

    def money(v):
        return f"{v:,.0f}" if v is not None else "—"

    def ty(v):
        return f"{v/1e9:,.0f} tỷ" if v else "—"

    s, lv, fin = a["score"], a["levels"], a.get("fin")
    p = a["price"]
    head = (f"📊 <b>{_esc(a['symbol'])}</b>"
            + (f" — {_esc(a['company'])}" if a.get("company") else "")
            + f"\n<b>{money(p)}</b> · phiên {_esc(a['ts'])}"
            + f" · thanh khoản {ty(a.get('liquidity'))}\n")

    # Điểm số
    sc = (f"\n🎯 <b>Điểm tổng hợp: {s['final_score']:.0f}/100</b> — "
          f"{_esc(SIGNAL_LABELS.get(s['signal'], s['signal']))}\n"
          f"<code>Cơ bản {s['s_fundamental']:.0f} · Tăng trưởng {s['s_growth']:.0f} · "
          f"Sức khỏe {s['s_health']:.0f}\nĐịnh giá {s['s_valuation']:.0f} · "
          f"Kỹ thuật {s['s_technical']:.0f} · Dòng tiền {s['s_moneyflow']:.0f} · "
          f"An toàn {s['s_risk']:.0f}</code>\n<i>(thang 0-100, cao = tốt)</i>\n")

    # Báo cáo tài chính
    fi = ""
    if fin:
        fi = (f"\n💼 <b>Tài chính</b> (kỳ {_esc(fin['period'])})\n"
              f"Doanh thu {ty(fin['revenue'])} · LNST {ty(fin['net_income'])}\n"
              f"ROE {(fin['roe'] or 0)*100:.1f}% · Biên ròng {(fin['net_margin'] or 0)*100:.1f}%"
              f" · Nợ vay {ty(fin['total_debt'])}\n"
              f"Dòng tiền KD {ty(fin['cfo'])} · FCF {ty(fin['fcf'])}\n"
              f"P/E {fin['pe'] or '—'} · P/B {fin['pb'] or '—'}"
              + (f" · EPS(TTM) {money(fin['eps_ttm'])}" if fin.get("eps_ttm") else ""))
    red = a["fa"].get("red_flags") or []
    if red:
        fi += "\n⚠️ <b>Cảnh báo BCTC:</b> " + "; ".join(_esc(x) for x in red[:3])

    # Kỹ thuật
    ta, nw, sf = a["ta"], a.get("nw") or {}, a.get("sfi") or {}
    tech = (f"\n\n📈 <b>Kỹ thuật</b>\n"
            f"Hỗ trợ {money(ta.get('support'))} · Kháng cự {money(ta.get('resistance'))}\n")
    if ta.get("reasons"):
        tech += "\n".join(f"• {_esc(r)}" for r in ta["reasons"][:3]) + "\n"
    if nw.get("position") is not None:
        tech += f"Vị trí trong dải NW: {nw['position']:.0%}"
        if nw.get("signal"):
            tech += f" · tín hiệu {nw['signal']} hôm nay"
        tech += "\n"
    if sf.get("oracle_score") is not None:
        tech += f"Đồng thuận kỹ thuật: {sf['oracle_score']}/6"
        if sf.get("overheated"):
            tech += " → 🔥 <b>QUÁ NÓNG</b> (lịch sử: lợi nhuận kỳ vọng thấp nhất)"
        tech += "\n"

    # Dòng tiền
    flow = ""
    if a["mf"].get("reasons"):
        flow = "\n💧 <b>Dòng tiền</b>\n" + "\n".join(f"• {_esc(r)}" for r in a["mf"]["reasons"][:3])

    # Vùng giá
    exp = lv.get("expected_return")
    rr = lv.get("risk_reward")
    zone = (f"\n\n💰 <b>VÙNG GIÁ THAM CHIẾU</b>\n"
            f"🟢 Mua tích lũy: <b>{money(lv['buy_low'])} – {money(lv['buy_high'])}</b>\n"
            f"🎯 Chốt lời: <b>{money(lv['target_price'])}</b>"
            + (f" ({exp*100:+.0f}%)" if exp is not None else "") + "\n"
            f"🛑 Cắt lỗ: <b>{money(lv['stop_loss'])}</b> "
            f"<i>({_esc(lv.get('stop_source', ''))})</i>"
            + (f"\n⚖️ Lời/Lỗ ≈ {rr:.1f} · độ tin cậy {_esc(lv.get('conviction', '—'))}"
               if rr is not None else ""))

    th = f"\n\n🧠 <b>Nhận định AI</b>\n{_md_bold_to_html(thesis)}" if thesis else ""

    warn = ("\n\n—\n🚨 <b>KHÔNG ĐẢM BẢO LỢI NHUẬN.</b> <i>Backtest toàn thị trường (1.480 mã, "
            "45.000+ quan sát độc lập): KHÔNG chỉ báo nào — kỹ thuật lẫn cơ bản — dự báo được "
            "lợi nhuận; một số tín hiệu 'mua' còn cho lợi nhuận ÂM có ý nghĩa thống kê. Vùng giá "
            "trên dựa vào hỗ trợ/kháng cự và định giá, KHÔNG phải dự báo. Luôn đặt cắt lỗ và "
            "chỉ dùng vốn bạn chấp nhận rủi ro.</i>\n")
    return head + sc + fi + tech + flow + zone + th + warn + _DISCLAIMER


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
        timing = ""
        if p.get("nw_signal") or p.get("nw_position") is not None:
            sig = p.get("nw_signal")
            tag = {"BUY": "🟢 tín hiệu MUA hôm nay", "SELL": "🔴 tín hiệu BÁN hôm nay"}.get(sig, "—")
            pos = p.get("nw_position")
            pos_s = f", giá ở {pos:.0%} dải" if pos is not None else ""
            timing = f"\n   ⏱ Thời điểm (NW): {tag}{pos_s}"
        # Cảnh báo quá nóng: điểm đồng thuận kỹ thuật CAO = lợi nhuận kỳ vọng THẤP (theo backtest)
        if p.get("overheated"):
            timing += (f"\n   🔥 <b>CẢNH BÁO QUÁ NÓNG</b>: {p.get('oracle_score')}/6 chỉ báo cùng "
                       f"báo tăng — lịch sử cho thấy đây là lúc lợi nhuận 20 phiên tới THẤP NHẤT")
        lines.append(
            f"\n{i}. <b>{_esc(p['symbol'])}</b> — {_esc(p.get('action') or 'Mua tích lũy')} "
            f"(điểm {p.get('final_score', 0):.0f}/100{conv})"
            f"{zone}{timing}\n   🧠 {_esc(p.get('thesis') or '')}"
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
