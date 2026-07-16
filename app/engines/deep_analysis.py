"""Phân tích SÂU một mã theo yêu cầu (dùng cho lệnh Telegram /<MÃ>).

Gộp toàn bộ năng lực hệ thống cho MỘT mã:
  • Giá + kỹ thuật (MA/RSI/MACD/hỗ trợ-kháng cự)  → ta_engine
  • BCTC: doanh thu, LNST, ROE, biên LN, nợ, dòng tiền, red flags → fundamental
  • Định giá P/E, P/B (từ giá thị trường + EPS TTM)               → fundamental
  • Dòng tiền khối ngoại + CMF                                     → moneyflow
  • Thời điểm Nadaraya-Watson (dải trên/dưới, vị trí)              → nw_envelope
  • Cảnh báo quá nóng + cắt lỗ UT Bot                              → sfi
  • Vùng giá mua/bán/cắt lỗ                                        → recommend
  • Luận điểm tổng hợp                                             → LLM (Cố vấn Đầu tư AI)

⚠️ Tự nạp dữ liệu nếu DB chưa có mã đó (tốn lệnh gọi API, có throttle).
⚠️ KHÔNG "đảm bảo lợi nhuận": backtest toàn thị trường cho thấy không chỉ báo nào dự báo
   được lợi nhuận. Kết quả chỉ là phân tích tham khảo, luôn kèm mức cắt lỗ và cảnh báo.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.config import settings
from app.db import session_scope
from app.engines import fundamental, moneyflow, nw_envelope, recommend, scoring, sfi, ta_engine
from app.providers import get_provider
from app import repo

MIN_BARS = 120          # tối thiểu để tính chỉ báo có nghĩa
HISTORY_DAYS = 760      # ~500 phiên


def _ensure_data(session, symbol: str) -> None:
    """Nạp giá + BCTC nếu DB chưa có/đã cũ. Chấp nhận tốn lệnh gọi API (lệnh do người dùng gọi)."""
    df = repo.load_ohlcv(session, symbol)
    have = 0 if df is None or df.empty else len(df)
    fresh = have >= MIN_BARS and df["ts"].max() >= date.today() - timedelta(days=4)
    if not fresh:
        provider = get_provider()
        # bảng ohlcv có khóa ngoại tới symbols → phải đăng ký mã trước
        repo.upsert_symbols(session, [{"symbol": symbol, "exchange": "?", "is_active": False}])
        start = (date.today() - timedelta(days=HISTORY_DAYS)).isoformat()
        new = provider.ohlcv(symbol, start, date.today().isoformat())
        repo.upsert_ohlcv(session, symbol, new)
    if not repo.load_financials(session, symbol):
        from app.ingestion import ingest
        ingest.ingest_financials(session, symbol)


def _closed_bars(df):
    """Bỏ nến hôm nay nếu phiên đang chạy → chỉ số không đổi trong ngày."""
    if df is None or df.empty:
        return df
    df = df.sort_values("ts")
    if df["ts"].iloc[-1] >= date.today():
        df = df.iloc[:-1]
    return df


def analyze(symbol: str) -> dict | None:
    """Trả về dict đầy đủ để render báo cáo. None nếu không đủ dữ liệu."""
    symbol = symbol.upper().strip()
    with session_scope() as s:
        try:
            _ensure_data(s, symbol)
        except Exception as exc:
            print(f"[deep] {symbol} lỗi nạp dữ liệu: {str(exc)[:80]}")
        df = _closed_bars(repo.load_ohlcv(s, symbol))
        if df is None or len(df) < MIN_BARS:
            return {"symbol": symbol, "error": "not_enough_data",
                    "bars": 0 if df is None else len(df)}

        fins = repo.load_financials(s, symbol)
        mf_df = repo.load_money_flow(s, symbol)
        news_items = repo.load_recent_news(s, symbol, limit=5)
        sym_row = s.get(repo.Symbol, symbol) if hasattr(repo, "Symbol") else None

    price = float(df["close"].iloc[-1])
    ts = df["ts"].iloc[-1]

    ta = ta_engine.analyze(df)
    fa = fundamental.analyze(fins, as_of=ts, price=price)
    mf = moneyflow.analyze(mf_df, df)
    nw = nw_envelope.latest_signal(df) or {}
    sf = sfi.latest(df) or {}
    liquidity = float(df["value"].tail(20).mean() or 0)

    # Điểm tổng hợp (cùng công thức với pipeline hằng ngày)
    from app.engines import news_nlp
    news = news_nlp.aggregate(news_items)
    score = scoring.combine(ta=ta, fa=fa, mf=mf, news=news,
                            liquidity_value=liquidity, weights=settings.weights)

    # Vùng giá: dùng cắt lỗ UT Bot khi hợp lệ (dưới giá & không quá xa)
    levels = recommend.compute_levels(price, ta.get("support"), ta.get("resistance"),
                                      score["final_score"])
    ut = sf.get("ut_stop")
    if ut and 0 < ut < price and (price / ut - 1) < 0.25:
        levels["stop_loss"] = ut
        levels["stop_source"] = "UT Bot (ATR trailing)"
    else:
        levels["stop_source"] = "dưới hỗ trợ ~7%"

    latest_fin = max(fins, key=lambda f: f.period) if fins else None
    return {
        "symbol": symbol, "ts": str(ts), "price": price,
        "company": getattr(sym_row, "company_name", None),
        "exchange": getattr(sym_row, "exchange", None),
        "liquidity": liquidity, "bars": len(df),
        "score": score, "ta": ta, "fa": fa, "mf": mf, "nw": nw, "sfi": sf,
        "levels": levels,
        "fin": None if not latest_fin else {
            "period": latest_fin.period, "revenue": latest_fin.revenue,
            "net_income": latest_fin.net_income, "roe": latest_fin.roe,
            "roa": latest_fin.roa, "gross_margin": latest_fin.gross_margin,
            "net_margin": latest_fin.net_margin, "total_debt": latest_fin.total_debt,
            "equity": latest_fin.equity, "cfo": latest_fin.cfo, "fcf": latest_fin.fcf,
            "pe": fa.get("pe"), "pb": fa.get("pb"), "eps_ttm": fa.get("eps_ttm"),
        },
        "news": [{"title": n.title, "sentiment": n.sentiment} for n in news_items],
    }


def llm_thesis(a: dict) -> str | None:
    """Luận điểm tổng hợp do 'Cố vấn Đầu tư AI' viết. None nếu chưa cấu hình LLM."""
    from app import llm
    if not llm.available():
        return None

    import json
    ctx = {
        "ma": a["symbol"], "gia": a["price"], "phien": a["ts"],
        "diem_tong": a["score"]["final_score"], "tin_hieu": a["score"]["signal"],
        "diem_thanh_phan_0_100_CAO_LA_TOT": {
            "co_ban": a["score"]["s_fundamental"], "tang_truong": a["score"]["s_growth"],
            "suc_khoe_tai_chinh": a["score"]["s_health"], "dinh_gia_re": a["score"]["s_valuation"],
            "ky_thuat": a["score"]["s_technical"], "dong_tien_lon": a["score"]["s_moneyflow"],
            "an_toan_tai_chinh": a["score"]["s_risk"],
        },
        "bctc": a.get("fin"),
        "ky_thuat": {"ly_do": a["ta"].get("reasons"),
                     "ho_tro": a["ta"].get("support"), "khang_cu": a["ta"].get("resistance")},
        "dong_tien": a["mf"].get("reasons"),
        "red_flags_bctc": a["fa"].get("red_flags"),
        "thoi_diem_NW": {"tin_hieu": a["nw"].get("signal"), "vi_tri_dai": a["nw"].get("position")},
        "canh_bao_qua_nong": {
            "diem_dong_thuan_ky_thuat_0_6": a["sfi"].get("oracle_score"),
            "qua_nong": a["sfi"].get("overheated"),
            "GHI_CHU": "Backtest 1.483 mã: điểm đồng thuận CÀNG CAO thì lợi nhuận 20 phiên tới "
                       "CÀNG THẤP (0/6 → +2.9%; 6/6 → ~0%). Cao = cảnh báo, KHÔNG phải tín hiệu mua.",
        },
        "vung_gia_he_thong": a["levels"],
    }
    prompt = (
        "Phân tích cổ phiếu này cho nhà đầu tư trung hạn. Viết NGẮN GỌN bằng tiếng Việt, "
        "có cấu trúc, dùng thẻ HTML <b> cho tiêu đề mục (KHÔNG dùng Markdown):\n"
        "<b>Điểm mạnh</b>: 2-3 gạch đầu dòng, DẪN SỐ LIỆU cụ thể.\n"
        "<b>Điểm yếu / Rủi ro</b>: 2-3 gạch đầu dòng.\n"
        "<b>Nhận định</b>: 2-3 câu — nên MUA TÍCH LŨY / THEO DÕI / TRÁNH và VÌ SAO.\n"
        "<b>Điều kiện vô hiệu</b>: 1 câu — điều gì khiến luận điểm sai.\n"
        "Tổng dưới 1200 ký tự. TUYỆT ĐỐI không hứa hẹn lợi nhuận.\n\n"
        f"DỮ LIỆU:\n{json.dumps(ctx, ensure_ascii=False, default=str)}"
    )
    try:
        return llm.chat(prompt, max_tokens=1200, system=recommend.advisor_system()).strip()
    except Exception as exc:  # pragma: no cover
        print(f"[deep] LLM lỗi: {exc}")
        return None
