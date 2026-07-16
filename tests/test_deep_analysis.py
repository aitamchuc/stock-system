"""Test lệnh phân tích sâu /<MÃ>: định tuyến, tách tin dài, và cảnh báo bắt buộc."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///./test_stock.db"
os.environ["DATA_SOURCE"] = "demo"
os.environ["TELEGRAM_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""

from app.bot import listener, telegram  # noqa: E402


def test_routing_analyze_vs_commands():
    # /<MÃ> và gõ thẳng mã → phân tích sâu
    for t in ("/FPT", "FPT", "hpg", "/VND", "ACB"):
        assert listener._is_analyze_request(t), t
    # lệnh có sẵn KHÔNG được hiểu nhầm thành mã
    for t in ("/help", "/start", "/rank", "/rank 5", "/detail FPT", "/watch"):
        assert not listener._is_analyze_request(t), t
    # chuỗi quá dài / có ký tự lạ → không phải mã
    for t in ("xyzabcd", "mua gi hom nay", "/abc-def"):
        assert not listener._is_analyze_request(t), t


def test_split_long_message_keeps_lines_intact():
    line = "x" * 100
    text = "\n".join([line] * 200)          # ~20k ký tự
    parts = listener._split(text)
    assert len(parts) > 1
    assert all(len(p) <= listener.TG_LIMIT for p in parts)
    # không mất dữ liệu và không cắt giữa dòng
    assert "\n".join(parts).replace("\n", "") == text.replace("\n", "")
    for p in parts:
        for ln in p.split("\n"):
            assert ln in ("", line)


def test_split_short_message_unchanged():
    assert listener._split("ngắn") == ["ngắn"]


def test_format_not_enough_data():
    msg = telegram.format_deep_analysis({"symbol": "ZZZZ", "error": "not_enough_data", "bars": 0})
    assert "ZZZZ" in msg and "không đủ dữ liệu" in msg


def _fake_analysis() -> dict:
    return {
        "symbol": "FPT", "ts": "2026-07-15", "price": 66_800, "company": "FPT Corp",
        "exchange": "HOSE", "liquidity": 5.88e11, "bars": 500,
        "score": {"final_score": 41, "signal": "distribution", "s_fundamental": 100,
                  "s_growth": 50, "s_health": 37, "s_valuation": 27, "s_technical": 0,
                  "s_moneyflow": 15, "s_news": 50, "s_risk": 60},
        "ta": {"support": 66_800, "resistance": 77_700, "reasons": ["Giá < MA50 < MA200"]},
        "fa": {"red_flags": ["Lợi nhuận dương nhưng dòng tiền kinh doanh ÂM"],
               "pe": 11.74, "pb": 2.84, "eps_ttm": 5688},
        "mf": {"reasons": ["Khối ngoại bán ròng 5 phiên"]},
        "nw": {"position": 0.19, "signal": None},
        "sfi": {"oracle_score": 0, "overheated": False},
        "levels": {"buy_low": 64_800, "buy_high": 67_470, "target_price": 77_700,
                   "stop_loss": 62_120, "expected_return": 0.18, "risk_reward": 2.9,
                   "conviction": "thấp", "stop_source": "dưới hỗ trợ ~7%"},
        "fin": {"period": "2026Q1", "revenue": 1.248e13, "net_income": 2.487e12,
                "roe": 0.248, "roa": 0.145, "gross_margin": 0.34, "net_margin": 0.199,
                "total_debt": 1.61e13, "equity": 4.01e13, "cfo": -2.848e12, "fcf": -3.437e12,
                "pe": 11.74, "pb": 2.84, "eps_ttm": 5688},
        "news": [],
    }


def test_report_has_all_sections_and_mandatory_warning():
    msg = telegram.format_deep_analysis(_fake_analysis(), thesis="<b>Nhận định</b> Theo dõi.")
    for section in ("Điểm tổng hợp", "Tài chính", "Kỹ thuật", "VÙNG GIÁ THAM CHIẾU",
                    "Nhận định AI"):
        assert section in msg, section
    # số liệu then chốt
    assert "P/E" in msg and "ROE" in msg
    assert "Cắt lỗ" in msg and "62,120" in msg
    assert "Cảnh báo BCTC" in msg          # red flag phải hiện
    # TUYỆT ĐỐI phải có cảnh báo không đảm bảo lợi nhuận
    assert "KHÔNG ĐẢM BẢO LỢI NHUẬN" in msg
    assert "không phải khuyến nghị đầu tư" in msg.lower()


def test_report_shows_overheat_warning():
    a = _fake_analysis()
    a["sfi"] = {"oracle_score": 6, "overheated": True}
    msg = telegram.format_deep_analysis(a)
    assert "QUÁ NÓNG" in msg and "6/6" in msg


if __name__ == "__main__":
    test_routing_analyze_vs_commands()
    test_split_long_message_keeps_lines_intact()
    test_format_not_enough_data()
    test_report_has_all_sections_and_mandatory_warning()
    test_report_shows_overheat_warning()
    print("OK")
