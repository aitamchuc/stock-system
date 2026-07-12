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
from app.nw_scan import _rank_score, cmf20  # noqa: E402


def test_rank_score_bounds_and_monotonic():
    lo = _rank_score(1e9, 0.9, 100, 100, cmf=-0.1)
    hi = _rank_score(5e10, 0.1, 120, 100, cmf=0.2, foreign_net=1e9, nw_buy=True)
    assert 0 <= lo <= 100 and 0 <= hi <= 100
    assert hi > lo
    # thanh khoản cao hơn -> điểm cao hơn
    assert _rank_score(5e10, 0.5, 110, 100) > _rank_score(1e9, 0.5, 110, 100)
    # dòng tiền vào mạnh hơn -> điểm cao hơn
    assert _rank_score(1e10, 0.5, 110, 100, cmf=0.15) > _rank_score(1e10, 0.5, 110, 100, cmf=0.0)
    # khối ngoại mua ròng -> điểm cao hơn bán ròng
    assert (_rank_score(1e10, 0.5, 110, 100, foreign_net=5e8)
            > _rank_score(1e10, 0.5, 110, 100, foreign_net=-5e8))
    # thiếu dữ liệu khối ngoại -> trung tính, vẫn hợp lệ
    assert 0 <= _rank_score(1e10, 0.5, 110, 100, foreign_net=None) <= 100


def test_cmf20_sign():
    # đóng cửa sát đỉnh nến -> dòng tiền vào (CMF > 0)
    up = pd.DataFrame({"high": [10] * 20, "low": [8] * 20, "close": [9.9] * 20,
                       "volume": [1000] * 20})
    # đóng cửa sát đáy nến -> dòng tiền ra (CMF < 0)
    dn = pd.DataFrame({"high": [10] * 20, "low": [8] * 20, "close": [8.1] * 20,
                       "volume": [1000] * 20})
    assert cmf20(up) > 0 > cmf20(dn)


def test_format_empty_says_no_signal():
    msg = telegram.format_nw_picks([], "2026-07-09", scanned=250)
    assert "không mã nào" in msg.lower()
    assert "khuyến nghị" in msg.lower()          # vẫn có disclaimer


def test_format_picks_render():
    picks = [
        {"rank": 1, "symbol": "FPT", "price": 72000, "lower": 65000, "upper": 79000,
         "position": 0.35, "liquidity": 3.2e11, "ma200": 68000, "score": 71.0,
         "cmf": 0.12, "foreign_net": 3.2e10, "nw_buy": True},
        {"rank": 2, "symbol": "HPG", "price": 23400, "lower": 22000, "upper": 25000,
         "position": 0.47, "liquidity": 5.0e10, "ma200": 22800, "score": 63.0,
         "cmf": 0.04, "foreign_net": -5e9, "nw_buy": False},
    ]
    msg = telegram.format_nw_picks(picks, "2026-07-09", scanned=250)
    assert "FPT" in msg and "HPG" in msg
    assert "TOP 2" in msg
    assert "CMF" in msg and "khối ngoại" in msg          # hiện đủ 3 yếu tố
    # bắt buộc nêu rõ không phải khuyến nghị mua + cảnh báo backtest
    assert "KHÔNG PHẢI KHUYẾN NGHỊ MUA" in msg
    assert "ý nghĩa thống kê" in msg


if __name__ == "__main__":
    test_rank_score_bounds_and_monotonic()
    test_format_empty_says_no_signal()
    test_format_picks_render()
    print("OK")
