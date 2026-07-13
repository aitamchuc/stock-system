"""Test bộ quét NW: điểm xếp hạng + định dạng Telegram (không cần mạng)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///./test_stock.db"
os.environ["DATA_SOURCE"] = "demo"
os.environ["TELEGRAM_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""

import pandas as pd  # noqa: E402

from app.bot import telegram  # noqa: E402
from app.nw_scan import _heat_score, cmf20  # noqa: E402


def test_heat_score_higher_means_more_dangerous():
    """ĐỘ NÓNG: cao = nguy hiểm (vượt xa MA200 + đồng thuận cao + dòng tiền mạnh)."""
    mat = _heat_score(close=100, ma200=100, cmf=0.0, oracle=0, position=0.1)   # nguội
    nong = _heat_score(close=140, ma200=100, cmf=0.25, oracle=6, position=0.95)  # cực nóng
    assert 0 <= mat <= 100 and 0 <= nong <= 100
    assert nong > mat
    # càng vượt xa MA200 càng nóng
    assert _heat_score(130, 100, oracle=3) > _heat_score(105, 100, oracle=3)
    # đồng thuận kỹ thuật càng cao càng nóng
    assert _heat_score(110, 100, oracle=6) > _heat_score(110, 100, oracle=1)
    # dòng tiền vào càng mạnh càng nóng
    assert _heat_score(110, 100, cmf=0.25, oracle=3) > _heat_score(110, 100, cmf=0.0, oracle=3)
    # thiếu oracle vẫn hợp lệ
    assert 0 <= _heat_score(110, 100, oracle=None) <= 100


def test_cmf20_sign():
    # đóng cửa sát đỉnh nến -> dòng tiền vào (CMF > 0)
    up = pd.DataFrame({"high": [10] * 20, "low": [8] * 20, "close": [9.9] * 20,
                       "volume": [1000] * 20})
    # đóng cửa sát đáy nến -> dòng tiền ra (CMF < 0)
    dn = pd.DataFrame({"high": [10] * 20, "low": [8] * 20, "close": [8.1] * 20,
                       "volume": [1000] * 20})
    assert cmf20(up) > 0 > cmf20(dn)


def test_format_empty_says_no_overheat():
    msg = telegram.format_nw_picks([], "2026-07-09", scanned=250)
    assert "không mã nào" in msg.lower()
    assert "khuyến nghị" in msg.lower()          # vẫn có disclaimer


def test_format_frames_as_warning_not_buy_list():
    """Bản tin PHẢI đóng khung là CẢNH BÁO, tuyệt đối không được gợi ý mua."""
    picks = [
        {"rank": 1, "symbol": "VIC", "price": 223000, "lower": 200000, "upper": 240000,
         "position": 0.60, "liquidity": 4.28e11, "ma200": 156000, "score": 92.0,
         "cmf": 0.348, "foreign_net": 2.87e10, "nw_buy": False, "oracle_score": 6},
    ]
    msg = telegram.format_nw_picks(picks, "2026-07-10", scanned=139)
    assert "VIC" in msg
    assert "QUÁ NÓNG" in msg
    assert "ĐỪNG ĐUỔI MUA" in msg
    assert "6/6" in msg                                   # hiện đồng thuận kỹ thuật
    assert "Độ nóng" in msg                               # không phải "điểm xếp hạng"
    # TUYỆT ĐỐI không được đóng khung là cơ hội
    assert "ĐÁNG THEO DÕI" not in msg.upper()
    assert "xếp hạng" not in msg.lower()
    assert "THẤP NHẤT" in msg                             # nêu rõ kỳ vọng lợi nhuận thấp nhất


if __name__ == "__main__":
    test_rank_score_bounds_and_monotonic()
    test_format_empty_says_no_signal()
    test_format_picks_render()
    print("OK")
