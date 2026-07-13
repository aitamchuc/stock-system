"""Quét TOÀN THỊ TRƯỜNG tìm tín hiệu MUA Nadaraya-Watson → gửi top N qua Telegram (~10h).

    python -m app.nw_scan
    python -m app.nw_scan --no-telegram --max 40     # chạy thử nhanh

Quy trình:
  Tầng 1 — sàng lọc rẻ: 1 lượt price_board (~26 lệnh gọi) cho toàn bộ ~1500 mã niêm yết,
           giữ mã có thanh khoản ≥ NW_MIN_LIQUIDITY và giá ≥ NW_MIN_PRICE (tối đa NW_SCAN_MAX mã).
  Tầng 2 — tải lịch sử giá (throttle), tính Nadaraya-Watson non-repaint trên các NẾN ĐÃ ĐÓNG
           (bỏ nến hôm nay nếu phiên đang diễn ra → tín hiệu không đổi trong ngày).
  Lọc tổ hợp: giá > MA200 (xu hướng) VÀ CMF20 > 0 (dòng tiền đang vào).
           Xếp hạng: 25% thanh khoản · 25% CMF · 20% khối ngoại ròng (thật, từ price_board)
           · 20% độ mạnh xu hướng · 10% thời điểm NW.

⚠️ TRUNG THỰC — kết quả backtest (scripts/backtest_factors.py, backtest_cmf_robust.py):
  • Với mẫu KHÔNG CHỒNG LẤN, KHÔNG yếu tố nào (NW, điểm cơ bản, dòng tiền CMF) đạt ý nghĩa
    thống kê trong dự báo lợi nhuận (|t| < 2).
  • Riêng việc BẮT BUỘC có tín hiệu BUY của NW làm kết quả KÉM ĐI có ý nghĩa (alpha −2.9%,
    t = −2.4 ở 20 phiên) → vì vậy NW KHÔNG dùng làm điều kiện lọc, chỉ làm bối cảnh thời điểm.
  • Dòng tiền khối ngoại THẬT chưa có lịch sử để backtest (vnstock chỉ cho snapshot phiên).
Đây là công cụ SÀNG LỌC để nghiên cứu, KHÔNG phải khuyến nghị mua.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.bot import telegram
from app.config import settings
from app.db import init_db, session_scope
from app.engines import nw_envelope as nw
from app.engines import sfi
from app.providers import get_provider
from app import repo


def _closed_bars(df):
    """Bỏ nến của hôm nay nếu phiên đang diễn ra → chỉ dùng nến đã đóng."""
    if df is None or df.empty:
        return df
    df = df.sort_values("ts")
    if df["ts"].iloc[-1] >= date.today():
        df = df.iloc[:-1]
    return df


# Chỉ bỏ qua gọi API khi DB đã có nến của hôm nay/hôm qua (tức đã có nến đóng gần nhất).
# Đặt >1 sẽ dùng dữ liệu cũ và bỏ sót nến mới → sai tín hiệu.
FRESH_DAYS = 1


def _get_ohlcv(session, provider, symbol: str):
    """Ưu tiên DB. Chỉ gọi API khi thiếu lịch sử hoặc dữ liệu đã cũ (tiết kiệm rate-limit)."""
    df = repo.load_ohlcv(session, symbol)
    have = 0 if df is None or df.empty else len(df)
    today = date.today()
    fresh = have >= 220 and df["ts"].max() >= today - timedelta(days=FRESH_DAYS)
    if fresh:
        return df

    # AN TOÀN: không bao giờ để dữ liệu synthetic (demo) ghi đè giá thật đã có trong DB.
    if settings.data_source == "demo" and have > 0:
        return df

    lookback = 30 if have >= 400 else 760
    start = (today - timedelta(days=lookback)).isoformat()
    new = provider.ohlcv(symbol, start, today.isoformat())
    if new is not None and not new.empty:
        repo.upsert_ohlcv(session, symbol, new)
        df = repo.load_ohlcv(session, symbol)
    return df


def cmf20(df) -> float:
    """Chaikin Money Flow 20 phiên: >0 = dòng tiền đang vào (tính từ OHLCV)."""
    d = df.tail(20)
    hl = (d["high"] - d["low"]).replace(0, np.nan)
    mfm = ((d["close"] - d["low"]) - (d["high"] - d["close"])) / hl
    mfv = (mfm * d["volume"]).fillna(0)
    vol = d["volume"].sum()
    return float(mfv.sum() / vol) if vol else 0.0


def _clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _heat_score(close: float, ma200: float, cmf: float = 0.0,
                oracle: int | None = None, position: float = 0.5) -> float:
    """ĐỘ NÓNG 0-100 — CAO = NGUY HIỂM, không phải "tốt".

    Backtest toàn thị trường: nhóm mã có giá vượt xa MA200 + dòng tiền vào mạnh + đồng thuận
    kỹ thuật cao chính là nhóm có kỳ vọng lợi nhuận THẤP NHẤT (giá>MA200: t=−18; Oracle 6/6:
    ~0% sau 20 phiên vs Oracle 0/6: +2.9%). Vì vậy điểm này đo MỨC ĐỘ RỦI RO ĐUỔI MUA,
    KHÔNG phải chất lượng cơ hội.

    35% giá vượt MA200 · 25% đồng thuận kỹ thuật (Oracle) · 25% dòng tiền vào · 15% giá sát mép trên dải
    """
    trend = _clip((close / ma200 - 1.0) / 0.40)          # vượt MA200 tới +40% = nóng tối đa
    consensus = _clip((oracle or 0) / 6.0)               # 6/6 = đồng thuận tuyệt đối
    flow = _clip(cmf / 0.20)                             # dòng tiền vào càng mạnh càng nóng
    top_of_band = _clip(position)                        # giá càng sát mép trên dải càng nóng
    return round(100 * (0.35 * trend + 0.25 * consensus
                        + 0.25 * flow + 0.15 * top_of_band), 1)


def scan(*, send: bool = True, max_symbols: int | None = None,
         symbols: list[str] | None = None) -> list[dict]:
    """symbols: chỉ định danh sách mã (bỏ qua tầng 1 — dùng để chạy thử/offline)."""
    provider = get_provider()
    max_symbols = max_symbols or settings.nw_scan_max

    listed: list[dict] = []
    if symbols:
        cands = [{"symbol": s.upper(), "liquidity": 0.0} for s in symbols][:max_symbols]
    else:
        # --- Tầng 1: sàng lọc toàn thị trường ---
        listed = provider.all_listed_symbols()
        universe = [s["symbol"] for s in listed]
        if not universe:
            print("[nw] Không lấy được danh sách mã (cần DATA_SOURCE=vnstock, API đang khả dụng).")
            return []
        print(f"[nw] Sàng lọc {len(universe)} mã niêm yết...")
        snap = provider.market_snapshot(universe)

        cands = []
        for sym, d in snap.items():
            price, vol = d.get("price"), d.get("volume") or 0
            if not price or price < settings.nw_min_price:
                continue
            liq = vol * price
            if liq < settings.nw_min_liquidity:
                continue
            # market_snapshot đã có khối ngoại ròng THẬT của phiên → dùng miễn phí, không tốn call
            cands.append({"symbol": sym, "liquidity": liq, "foreign_net": d.get("foreign_net")})
        cands.sort(key=lambda c: c["liquidity"], reverse=True)
        cands = cands[:max_symbols]
    print(f"[nw] {len(cands)} mã đủ thanh khoản → phân tích tổ hợp (có thể mất vài phút)...")

    # Đăng ký mã vào bảng symbols TRƯỚC (ohlcv có khóa ngoại tới symbols → không có bước này
    # sẽ ForeignKeyViolation, và lỗi đó làm hỏng cả transaction → mọi mã sau đều fail).
    ex_map = {s["symbol"]: s.get("exchange") for s in listed}
    with session_scope() as session:
        existing = {x.symbol for x in repo.active_symbols(session)}   # giữ nguyên watchlist đang active
        repo.upsert_symbols(session, [
            {"symbol": c["symbol"], "exchange": ex_map.get(c["symbol"]) or "?", "is_active": False}
            for c in cands if c["symbol"] not in existing
        ])

    # --- Tầng 2: tính chỉ báo trên nến đã đóng ---
    # MỖI MÃ MỘT SESSION: nếu dùng chung 1 session, lỗi ở 1 mã sẽ abort transaction và
    # MỌI mã sau đó đều fail ("current transaction is aborted") — từng làm hỏng 148/250 mã.
    hits: list[dict] = []
    failed = 0
    for c in cands:
        sym = c["symbol"]
        try:
            with session_scope() as session:
                df = _closed_bars(_get_ohlcv(session, provider, sym))
        except Exception as exc:
            failed += 1
            print(f"[nw] {sym} lỗi tải giá: {str(exc)[:80]}")
            continue

        if df is None or len(df) < 220:          # cần đủ cho MA200 + NW
            continue
        r = nw.latest_signal(df)
        if not r:
            continue
        nw_buy = r["signal"] == "BUY"
        # NW BUY KHÔNG dùng làm điều kiện bắt buộc (backtest: gate theo nó làm kém đi rõ rệt)
        if settings.nw_require_buy_signal and not nw_buy:
            continue

        close = float(df["close"].iloc[-1])
        ma200 = float(df["close"].rolling(200).mean().iloc[-1])
        above = close > ma200
        if settings.nw_require_uptrend and not above:
            continue

        flow = cmf20(df)                         # dòng tiền 20 phiên (proxy tích lũy)
        if settings.nw_require_inflow and flow <= 0:
            continue

        liq = c["liquidity"] or float(df["value"].tail(20).mean() or 0)
        sf = sfi.latest(df) or {}                # điểm đồng thuận kỹ thuật (Oracle 0-6)
        pos = r["position"] or 0.5
        hits.append({
            "symbol": sym, "price": close,
            "lower": r["lower"], "upper": r["upper"], "mid": r["mid"],
            "position": pos, "liquidity": liq,
            "ma200": ma200, "above_ma200": above,
            "cmf": round(flow, 4), "foreign_net": c.get("foreign_net"), "nw_buy": nw_buy,
            "oracle_score": sf.get("oracle_score"),
            "score": _heat_score(close, ma200, cmf=flow,
                                 oracle=sf.get("oracle_score"), position=pos),
            "ts": df["ts"].iloc[-1],
        })

    hits.sort(key=lambda x: x["score"], reverse=True)   # nóng nhất lên đầu
    top = hits[: settings.nw_top_n]
    for i, h in enumerate(top, 1):
        h["rank"] = i

    if top:
        with session_scope() as session:
            repo.replace_nw_picks(session, top[0]["ts"], top)
    if failed:
        print(f"[nw] ⚠️ {failed}/{len(cands)} mã lỗi khi tải giá.")
    print(f"[nw] {len(hits)} mã QUÁ NÓNG → gửi top {len(top)}.")

    if send:
        ts = str(top[0]["ts"]) if top else str(date.today())
        telegram.send_message(telegram.format_nw_picks(top, ts, scanned=len(cands)))
    return top


def run(send: bool = True, max_symbols: int | None = None,
        symbols: list[str] | None = None) -> None:
    from app.config import banner
    banner("nw_scan")
    init_db()
    top = scan(send=send, max_symbols=max_symbols, symbols=symbols)
    if not top:
        print("[nw] Hôm nay không có mã nào rơi vào vùng quá nóng.")
        return
    print(f"\n{'Mã':<7}{'Giá':>10}{'>MA200':>9}{'Oracle':>8}{'CMF':>8}"
          f"{'NgoạiRòng(tỷ)':>15}{'ĐộNóng':>8}")
    print("-" * 66)
    for h in top:
        fn = (h.get("foreign_net") or 0) / 1e9
        orc = h.get("oracle_score")
        print(f"{h['symbol']:<7}{h['price']:>10,.0f}{(h['price']/h['ma200']-1):>8.1%}"
              f"{(f'{orc}/6' if orc is not None else '—'):>8}{h['cmf']:>8.3f}"
              f"{fn:>15,.1f}{h['score']:>8.0f}")
    print("\n🔥 CẢNH BÁO QUÁ NÓNG — ĐỪNG ĐUỔI MUA. Backtest toàn thị trường: đây là nhóm mã có kỳ "
          "vọng lợi nhuận THẤP NHẤT (giá>MA200: t=−18; Oracle 6/6 → ~0% vs Oracle 0/6 → +2.9%).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--max", type=int, default=None, help="Giới hạn số mã phân tích (chạy thử)")
    ap.add_argument("--symbols", default="", help="Danh sách mã, phân tách phẩy (bỏ qua sàng lọc)")
    a = ap.parse_args()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()] or None
    run(send=not a.no_telegram, max_symbols=a.max, symbols=syms)
