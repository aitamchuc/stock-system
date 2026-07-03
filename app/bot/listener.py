"""Bot Telegram hai chiều: lắng nghe lệnh người dùng và trả lời (long-polling).

Chạy: `python -m app.bot.listener`  (cần TELEGRAM_TOKEN trong .env).

Lệnh hỗ trợ:
  /start, /help        — hướng dẫn
  /rank [n]            — top n cổ phiếu điểm cao nhất (mặc định 10)
  /detail <MÃ>         — chi tiết điểm + luận điểm 1 mã
  /watch               — danh mục đang theo dõi
"""
from __future__ import annotations

import html
import sys
import time

import httpx
from sqlalchemy import func, select

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.config import settings
from app.db import session_scope
from app.engines.scoring import SIGNAL_LABELS
from app.models import DailyScore, OHLCV, Symbol

_API = "https://api.telegram.org/bot{token}/{method}"
_DISCLAIMER = "<i>Tham khảo, không phải khuyến nghị đầu tư.</i>"


def _esc(v) -> str:
    return html.escape(str(v))


def _api(method: str, **params):
    r = httpx.get(_API.format(token=settings.telegram_token, method=method),
                  params=params, timeout=40)
    return r.json()


def _send(chat_id, text: str) -> None:
    httpx.post(_API.format(token=settings.telegram_token, method="sendMessage"),
               json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                     "disable_web_page_preview": True}, timeout=15)


# ---------------- Command handlers ----------------
def _latest_ts(s):
    return s.execute(select(func.max(DailyScore.ts))).scalar_one_or_none()


def cmd_rank(n: int = 10) -> str:
    with session_scope() as s:
        ts = _latest_ts(s)
        if not ts:
            return "Chưa có dữ liệu. Hãy chạy <code>python -m app.pipeline</code> trước."
        rows = s.execute(
            select(DailyScore, OHLCV.close).join(
                OHLCV, (OHLCV.symbol == DailyScore.symbol) & (OHLCV.ts == DailyScore.ts))
            .where(DailyScore.ts == ts).order_by(DailyScore.final_score.desc()).limit(n)
        ).all()
        lines = [f"🏆 <b>Top {len(rows)} cổ phiếu</b> (phiên {ts})"]
        for i, (sc, close) in enumerate(rows, 1):
            label = SIGNAL_LABELS.get(sc.signal, sc.signal)
            lines.append(f"{i}. <b>{_esc(sc.symbol)}</b> — {sc.final_score:.0f}/100 "
                         f"· {close:,.0f} · {_esc(label)}")
        lines.append("—\n" + _DISCLAIMER)
        return "\n".join(lines)


def cmd_detail(symbol: str) -> str:
    symbol = symbol.upper().strip()
    with session_scope() as s:
        ts = _latest_ts(s)
        sc = s.execute(select(DailyScore).where(
            DailyScore.symbol == symbol, DailyScore.ts == ts)).scalar_one_or_none()
        if not sc:
            return f"Không có dữ liệu cho <b>{_esc(symbol)}</b>. Thử /rank để xem danh sách."
        close = s.execute(select(OHLCV.close).where(
            OHLCV.symbol == symbol, OHLCV.ts == ts)).scalar_one_or_none()
        r = sc.rationale or {}
        risks = "; ".join((r.get("main_risks") or [])[:3]) or "—"
        p = r.get("parts", {})
        return (
            f"📊 <b>{_esc(symbol)}</b> — {sc.final_score:.0f}/100 · "
            f"{_esc(SIGNAL_LABELS.get(sc.signal, sc.signal))}\n"
            f"Giá: {close:,.0f} | Hỗ trợ: {r.get('support') or '—'} | "
            f"Kháng cự: {r.get('resistance') or '—'}\n"
            f"Cơ bản {p.get('fundamental',0):.0f} · KT {p.get('technical',0):.0f} · "
            f"Sức khỏe {p.get('health',0):.0f} · Dòng tiền {p.get('moneyflow',0):.0f} · "
            f"Rủi ro {p.get('risk',0):.0f}\n"
            f"🧠 {_esc(r.get('why',''))}\n"
            f"⚠️ Rủi ro: {_esc(risks)}\n"
            f"🔗 {settings.dashboard_base_url}/stock/{_esc(symbol)}\n—\n{_DISCLAIMER}"
        )


def cmd_watch() -> str:
    return "👀 Danh mục theo dõi:\n" + _esc(settings.vnstock_watchlist)


_HELP = (
    "🤖 <b>Bot cảnh báo cổ phiếu VN</b>\n"
    "/rank [n] — top n mã điểm cao nhất\n"
    "/detail &lt;MÃ&gt; — chi tiết 1 mã (vd /detail FPT)\n"
    "/watch — danh mục theo dõi\n"
    "/help — trợ giúp\n—\n" + _DISCLAIMER
)


def handle(text: str) -> str:
    parts = text.strip().split()
    if not parts:
        return _HELP
    cmd = parts[0].lower().split("@")[0]
    if cmd in ("/start", "/help"):
        return _HELP
    if cmd == "/rank":
        n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
        return cmd_rank(min(n, 30))
    if cmd == "/detail" and len(parts) > 1:
        return cmd_detail(parts[1])
    if cmd == "/watch":
        return cmd_watch()
    return "Lệnh không hợp lệ. Gõ /help để xem hướng dẫn."


def run() -> None:
    if not settings.telegram_token:
        print("❌ Chưa có TELEGRAM_TOKEN trong .env.")
        return
    me = _api("getMe")
    if not me.get("ok"):
        print(f"❌ Token lỗi: {me}")
        return
    print(f"✅ Lắng nghe @{me['result']['username']} ... (Ctrl+C để dừng)")
    offset = None
    while True:
        try:
            resp = _api("getUpdates", timeout=30, offset=offset)
            for u in resp.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                text = msg.get("text")
                chat = (msg.get("chat") or {}).get("id")
                if text and chat:
                    print(f"  ↩ {text}")
                    _send(chat, handle(text))
        except KeyboardInterrupt:
            print("\nĐã dừng.")
            break
        except Exception as exc:  # pragma: no cover
            print(f"[listener] lỗi: {exc}")
            time.sleep(3)


if __name__ == "__main__":
    run()
