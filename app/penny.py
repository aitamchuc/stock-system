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


def _closed_bars(df):
    """Bỏ nến của hôm nay nếu phiên đang diễn ra.

    BẮT BUỘC khi chạy trong phiên (vd 09:30): nến hôm nay mới có ~30 phút giao dịch →
    volume z-score / ATR / đà 1 tháng đều sai lệch nặng nếu tính cả nó.
    """
    if df is None or df.empty:
        return df
    df = df.sort_values("ts")
    if df["ts"].iloc[-1] >= date.today():
        df = df.iloc[:-1]
    return df


def _liquidity_from_history(df) -> float:
    """Thanh khoản THẬT = GTGD trung bình 20 phiên ĐÃ ĐÓNG.

    Không dùng volume trong ngày từ price_board: lúc 09:30 mới có ~30 phút giao dịch nên
    thanh khoản chỉ bằng ~10% cả phiên → lọc sai hoàn toàn.
    """
    if df is None or df.empty or "value" not in df.columns:
        return 0.0
    return float(df.sort_values("ts")["value"].tail(20).mean() or 0)


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

    # TẦNG 1 — SƠ TUYỂN (giá ≤ ngưỡng penny). KHÔNG lọc thanh khoản ở đây: volume từ price_board
    # là volume TÍCH LŨY TRONG NGÀY → chạy lúc 09:30 mới có ~30 phút giao dịch, lọc sẽ sai hoàn
    # toàn. Chỉ dùng nó để XẾP THỨ TỰ ứng viên (mã sôi động sớm thường là mã thanh khoản).
    pre = penny_scanner.screen(snapshot, settings.penny_price_max, min_liquidity=0)
    pre = pre[: top * 3]                       # lấy dư để tầng 2 còn loại bớt theo thanh khoản THẬT
    print(f"[penny] {len(pre)} ứng viên giá ≤ {settings.penny_price_max:,.0f}đ "
          f"→ xác minh thanh khoản thật từ nến đã đóng...")

    # TẦNG 2 — phân tích sâu trên NẾN ĐÃ ĐÓNG + xác minh thanh khoản thật (TB 20 phiên).
    # MỖI MÃ MỘT SESSION — nếu dùng chung, lỗi ở 1 mã abort transaction và mọi mã sau đều fail.
    results: list[dict] = []
    failed = thin = 0
    for cand in pre:
        sym = cand["symbol"]
        try:
            df = _closed_bars(provider.ohlcv(sym, _start(), today.isoformat()))
            liq = _liquidity_from_history(df)
            if liq < settings.penny_min_liquidity:   # thanh khoản THẬT, không phải volume nửa phiên
                thin += 1
                continue
            cand = {**cand, "value": liq}            # analyze() dùng 'value' làm thanh khoản
            res = penny_scanner.analyze(df, cand)
            st = res["stats"]
            row = {
                "exchange": ex_map.get(sym), "price": cand.get("price"),
                "liquidity": liq,
                "upside_score": res["upside_score"], "risk_score": res["risk_score"],
                "return_1m_pct": st.get("return_1m_pct"), "atr_pct": st.get("atr_pct"),
                "volume_zscore": st.get("volume_zscore"), "foreign_net": st.get("foreign_net"),
                "signals": res["signals"], "warnings": res["warnings"],
            }
            with session_scope() as session:
                repo.upsert_penny_pick(session, sym, today, row)
            results.append({"symbol": sym, **row})
            if len(results) >= top:
                break
        except Exception as exc:
            failed += 1
            print(f"[penny] {sym} lỗi: {str(exc)[:80]}")
    if thin:
        print(f"[penny] loại {thin} mã thanh khoản thật < {settings.penny_min_liquidity/1e9:.0f} tỷ.")
    if failed:
        print(f"[penny] ⚠️ {failed} mã lỗi khi phân tích.")
    print(f"[penny] {len(results)} mã đạt yêu cầu.")

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
    from app.config import banner
    banner("penny")
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
