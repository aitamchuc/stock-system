"""Quét cổ phiếu PENNY tiềm năng (đầu cơ, rủi ro rất cao).

    python -m app.penny                 # quét toàn thị trường
    python -m app.penny --no-telegram   # không gửi Telegram

⚠️ CHỈ để nghiên cứu — KHÔNG phải khuyến nghị mua, KHÔNG hứa hẹn "x3 x4".
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.bot import telegram
from app.config import settings
from app.db import init_db, session_scope
from app.engines import penny_scanner
from app.providers import get_provider
from app import repo


def scan(*, send: bool = True, top: int | None = None) -> list[dict]:
    provider = get_provider()
    top = top or settings.penny_scan_top
    today = date.today()

    # Tầng 1: quét toàn thị trường theo giá + thanh khoản
    listed = provider.all_listed_symbols()
    universe = [s["symbol"] for s in listed]
    ex_map = {s["symbol"]: s.get("exchange") for s in listed}
    if not universe:
        print("[penny] Không lấy được danh sách mã (nguồn demo? cần vnstock).")
        return []
    print(f"[penny] Quét {len(universe)} mã niêm yết...")
    snapshot = provider.market_snapshot(universe)
    candidates = penny_scanner.screen(
        snapshot, settings.penny_price_max, settings.penny_min_liquidity)
    print(f"[penny] {len(candidates)} mã penny có thanh khoản → phân tích sâu top {top}.")

    # Tầng 2: phân tích sâu top ứng viên
    results: list[dict] = []
    with session_scope() as session:
        for cand in candidates[:top]:
            sym = cand["symbol"]
            df = provider.ohlcv(sym, _start(), today.isoformat())
            res = penny_scanner.analyze(df, cand)
            st = res["stats"]
            row = {
                "exchange": ex_map.get(sym), "price": cand.get("price"),
                "liquidity": cand.get("value"),
                "upside_score": res["upside_score"], "risk_score": res["risk_score"],
                "return_1m_pct": st.get("return_1m_pct"), "atr_pct": st.get("atr_pct"),
                "volume_zscore": st.get("volume_zscore"), "foreign_net": st.get("foreign_net"),
                "signals": res["signals"], "warnings": res["warnings"],
            }
            repo.upsert_penny_pick(session, sym, today, row)
            results.append({"symbol": sym, **row})

    results.sort(key=lambda r: r["upside_score"], reverse=True)

    # Gửi cảnh báo cho ứng viên vượt ngưỡng tiềm năng
    if send:
        for r in results:
            if r["upside_score"] >= settings.penny_min_upside:
                telegram.send_message(telegram.format_penny(r))
    return results


def _start() -> str:
    from datetime import timedelta
    return (date.today() - timedelta(days=200)).isoformat()


def run(send: bool = True) -> None:
    init_db()
    results = scan(send=send)
    if not results:
        print("[penny] Không có ứng viên penny nào đạt điều kiện thanh khoản.")
        return
    print(f"\n{'Mã':<6}{'Giá':>9}{'TiềmNăng':>10}{'RủiRo':>8}{'1M%':>7}  Tín hiệu chính")
    print("-" * 70)
    for r in results:
        sig = r["signals"][0] if r["signals"] else "—"
        print(f"{r['symbol']:<6}{(r['price'] or 0):>9,.0f}{r['upside_score']:>10.0f}"
              f"{r['risk_score']:>8.0f}{(r['return_1m_pct'] or 0):>7.0f}  {sig}")
    print("\n⚠️  Penny đầu cơ rủi ro RẤT CAO — chỉ tham khảo, không phải khuyến nghị mua.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-telegram", action="store_true")
    run(send=not ap.parse_args().no_telegram)
