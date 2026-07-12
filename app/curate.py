"""AI chọn lọc cổ phiếu NÊN ĐẦU TƯ mỗi ngày — chỉ gửi Telegram danh sách này.

AI ("Cố vấn Đầu tư") xem các mã điểm cao, giữ lại CHỈ những mã đáng tích lũy (thà ít mà chất),
kèm luận điểm + vùng mua/mục tiêu/cắt lỗ. Chạy trong pipeline (bước cuối) hoặc:
    python -m app.curate

⚠️ Chọn lọc tham khảo — không phải khuyến nghị đầu tư, không cam kết lợi nhuận.
"""
from __future__ import annotations

import json
import sys
from datetime import date

from sqlalchemy import func, select

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app import llm, repo
from app.bot import telegram
from app.config import settings
from app.db import init_db, session_scope
from app.engines import recommend
from app.models import DailyScore, Financial, OHLCV

_BUY_ACTIONS = ("mua", "tích lũy")            # action coi là "nên đầu tư"
_GOOD_SIGNALS = ("very_positive", "positive", "watch")


def _label_scores(parts: dict) -> dict:
    """Gắn nhãn tiếng Việt + làm rõ 'risk' đã đảo (cao = an toàn) để AI không hiểu nhầm."""
    return {
        "co_ban": parts.get("fundamental"),
        "tang_truong": parts.get("growth"),
        "suc_khoe_tai_chinh": parts.get("health"),
        "dinh_gia_re": parts.get("valuation"),          # cao = rẻ/hấp dẫn
        "ky_thuat": parts.get("technical"),
        "dong_tien_lon": parts.get("moneyflow"),
        "tin_tuc": parts.get("news"),
        "an_toan_tai_chinh": parts.get("risk"),          # cao = ít rủi ro
    }


def _candidates(session, ts: date) -> list[dict]:
    rows = session.execute(
        select(DailyScore).where(
            DailyScore.ts == ts,
            DailyScore.final_score >= settings.curate_min_score,
            DailyScore.signal.in_(_GOOD_SIGNALS),
        ).order_by(DailyScore.final_score.desc()).limit(settings.curate_top_n)
    ).scalars().all()

    out = []
    for sc in rows:
        fin = session.execute(
            select(Financial).where(Financial.symbol == sc.symbol)
            .order_by(Financial.period.desc()).limit(1)
        ).scalar_one_or_none()
        close = session.execute(
            select(OHLCV.close).where(OHLCV.symbol == sc.symbol, OHLCV.ts == ts)
        ).scalar_one_or_none()
        r = sc.rationale or {}
        out.append({
            "symbol": sc.symbol, "final_score": sc.final_score, "signal": sc.signal,
            "parts": r.get("parts", {}), "pe": fin.pe if fin else None,
            "pb": fin.pb if fin else None, "why": r.get("why", ""),
            "main_risks": (r.get("main_risks") or [])[:3],
            "support": r.get("support"), "resistance": r.get("resistance"),
            "nw": r.get("nw") or {},
            "sfi": r.get("sfi") or {},
            "_close": float(close) if close else None,
        })
    return out


def _sfi_context(s: dict) -> dict:
    """Cảnh báo SFI cho AI. Backtest: điểm Oracle càng cao → lợi nhuận tương lai càng KÉM."""
    if not s:
        return {}
    return {
        "diem_dong_thuan_ky_thuat_0_6": s.get("oracle_score"),
        "canh_bao_qua_nong": s.get("overheated"),
        "GHI_CHU": ("Backtest 1.483 mã: quan hệ NGHỊCH ĐẢO — điểm đồng thuận càng CAO thì lợi nhuận "
                    "20 phiên tới càng THẤP (điểm 0: +2.9%; điểm 5-6: ~0%). Điểm cao = cảnh báo "
                    "QUÁ NÓNG, KHÔNG phải tín hiệu mua."),
        "muc_cat_lo_dong_UTBot": s.get("ut_stop"),
    }


def _nw_context(nw: dict) -> dict:
    """Tóm tắt tín hiệu thời điểm Nadaraya-Watson cho AI."""
    if not nw:
        return {}
    return {
        "tin_hieu_hom_nay": nw.get("signal") or "không",
        "so_nen_tu_tin_hieu_MUA_gan_nhat": nw.get("bars_since_buy"),
        "so_nen_tu_tin_hieu_BAN_gan_nhat": nw.get("bars_since_sell"),
        "vi_tri_trong_dai_0_1": nw.get("position"),  # gần 0 = sát dải dưới (rẻ), gần 1 = sát dải trên
    }


def _ai_select(cands: list[dict]) -> dict[str, dict]:
    """Trả {symbol: {action, conviction, thesis}}. Dùng LLM nếu có, else quy tắc."""
    if not cands:
        return {}
    if not llm.available():
        res = {}
        for c in cands:
            buy = c["signal"] in ("very_positive", "positive")
            res[c["symbol"]] = {
                "action": "Mua tích lũy" if buy else "Theo dõi",
                "conviction": "cao" if c["final_score"] >= 75 else "trung bình",
                "thesis": c.get("why", ""),
            }
        return res

    payload = [{
        "symbol": c["symbol"], "diem_tong": c["final_score"], "tin_hieu": c["signal"],
        "diem": _label_scores(c["parts"]), "pe": c["pe"], "pb": c["pb"],
        "luan_diem_he_thong": c["why"], "rui_ro_luu_y": c["main_risks"],
        "thoi_diem_nadaraya_watson": _nw_context(c.get("nw")),
        "canh_bao_ky_thuat_sfi": _sfi_context(c.get("sfi")),
    } for c in cands]
    prompt = (
        "Đây là các cổ phiếu được hệ thống chấm điểm cao nhất hôm nay. TẤT CẢ điểm thang 0-100 và "
        "CAO = TỐT (kể cả 'an_toan_tai_chinh': cao nghĩa là ÍT rủi ro).\n"
        "Trường 'thoi_diem_nadaraya_watson' là tín hiệu THỜI ĐIỂM kỹ thuật: tín_hiệu_hôm_nay=BUY "
        "(dải dưới bẻ lên → điểm vào tốt), =SELL (dải trên bẻ xuống → nên chờ/giảm), "
        "vi_tri_trong_dai gần 0 = giá sát dải dưới (rẻ tương đối), gần 1 = sát dải trên (đắt).\n"
        "Với vai trò cố vấn đầu tư TRUNG HẠN, hãy CHỌN LỌC — thà ít mà chất. Cân nhắc CẢ nền tảng "
        "LẪN thời điểm: nền tảng tốt nhưng đang có SELL/sát dải trên thì nên 'Theo dõi' chờ điểm vào.\n"
        "Với mỗi mã, quyết định action:\n"
        '  "Mua tích lũy" = thực sự đáng giải ngân/tích lũy lúc này,\n'
        '  "Theo dõi" = tiềm năng nhưng chờ thêm,\n'
        '  "Tránh" = không nên mua dù điểm cao (định giá quá đắt, rủi ro lớn...).\n'
        "CHỈ để 'Mua tích lũy' cho mã bạn thật sự tin tưởng (ưu tiên chất lượng hơn số lượng). "
        "Dẫn chiếu số liệu, nêu rủi ro. KHÔNG cam kết lợi nhuận.\n\n"
        "Trả về DUY NHẤT JSON array: "
        '[{"symbol","action":"Mua tích lũy|Theo dõi|Tránh","conviction":"cao|trung bình|thấp",'
        '"thesis":"1-2 câu tiếng Việt: vì sao + rủi ro chính"}]\n\n'
        f"DỮ LIỆU:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        text = llm.chat(prompt, max_tokens=1500, system=recommend.advisor_system())
        s, e = text.find("["), text.rfind("]")
        data = json.loads(text[s:e + 1]) if s >= 0 and e >= 0 else []
    except Exception as exc:  # pragma: no cover
        print(f"[curate] LLM lỗi, dùng quy tắc: {exc}")
        return _ai_select_rule(cands)
    return {d["symbol"]: d for d in data if isinstance(d, dict) and d.get("symbol")}


def _ai_select_rule(cands):
    llm_backup = llm.available
    llm.available = lambda: False
    try:
        return _ai_select(cands)
    finally:
        llm.available = llm_backup


def curate(session, ts: date, *, send: bool = True) -> list[dict]:
    cands = _candidates(session, ts)
    verdicts = _ai_select(cands)
    method = "llm" if llm.available() else "rule"

    picks = []
    for c in cands:
        v = verdicts.get(c["symbol"])
        if not v:
            continue
        action = (v.get("action") or "").strip()
        if not any(k in action.lower() for k in _BUY_ACTIONS):
            continue  # chỉ giữ mã "nên đầu tư"
        price = c.get("_close") or 0
        levels = recommend.compute_levels(price, c.get("support"), c.get("resistance"),
                                          c["final_score"]) if price else {}
        nw = c.get("nw") or {}
        sf = c.get("sfi") or {}
        # Cắt lỗ: ưu tiên UT Bot (trailing stop theo ATR — đúng mục đích thiết kế của chỉ báo),
        # chỉ dùng khi nó nằm DƯỚI giá hiện tại và không quá xa (<25%).
        stop = levels.get("stop_loss")
        ut = sf.get("ut_stop")
        if ut and price and 0 < ut < price and (price / ut - 1) < 0.25:
            stop = ut
        picks.append({
            "symbol": c["symbol"], "action": action or "Mua tích lũy",
            "conviction": v.get("conviction"), "final_score": c["final_score"],
            "thesis": v.get("thesis", c.get("why", "")),
            "buy_low": levels.get("buy_low"), "buy_high": levels.get("buy_high"),
            "target_price": levels.get("target_price"), "stop_loss": stop,
            "method": method,
            # thêm để hiển thị (repo tự lọc cột không có trong bảng)
            "nw_signal": nw.get("signal"), "nw_position": nw.get("position"),
            "nw_bars_since_buy": nw.get("bars_since_buy"),
            "oracle_score": sf.get("oracle_score"), "overheated": sf.get("overheated"),
        })

    repo.replace_daily_picks(session, ts, picks)
    if send:
        telegram.send_message(telegram.format_daily_picks(picks, str(ts)))
    return picks


def run(send: bool = True) -> None:
    init_db()
    with session_scope() as s:
        ts = s.execute(select(func.max(DailyScore.ts))).scalar_one_or_none()
        if ts is None:
            print("Chưa có điểm số. Chạy python -m app.pipeline trước.")
            return
        picks = curate(s, ts, send=send)
    print(f"[curate] {len(picks)} mã NÊN ĐẦU TƯ (phiên {ts}):")
    for p in picks:
        print(f"  {p['symbol']}: {p['action']} ({p['conviction']}) — điểm {p['final_score']:.0f}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-telegram", action="store_true")
    run(send=not ap.parse_args().no_telegram)
