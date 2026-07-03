"""Kiểm tra giá thị trường trực tiếp qua provider."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.providers import get_provider  # noqa: E402

p = get_provider()
syms = ["HPG", "FPT", "VCB", "VNM", "MWG"]
live = p.live_prices(syms)
if not live:
    print("Provider không hỗ trợ giá trực tiếp (hoặc lỗi).")
for sym, d in live.items():
    chg = d["change_pct"]
    chg_s = f"{chg:+.2f}%" if chg is not None else "—"
    print(f"{sym}: giá {d['price']:>10,.0f}  (TC {d['ref_price']:>10,.0f})  {chg_s:>8}  TB {d['avg_price']:>10,.0f}")
