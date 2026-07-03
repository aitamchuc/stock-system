"""Kiểm tra API giá trực tiếp + trang chi tiết/dashboard."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)

live = c.get("/api/live?symbols=HPG,FPT,VCB").json()
print("live count:", live.get("count"))
for s, d in live.get("prices", {}).items():
    chg = d.get("change_pct")
    print(f"  {s}: {d['price']:,.0f}  {chg:+.2f}%" if chg is not None else f"  {s}: {d['price']:,.0f}")

d = c.get("/api/stock/HPG").json()
print("HPG live in detail:", d.get("live"))

r = c.get("/stock/HPG")
print("detail page:", r.status_code, "| có 'Giá trực tiếp':", "Giá trực tiếp" in r.text)
r2 = c.get("/")
print("dashboard:", r2.status_code, "| có loadLive:", "loadLive" in r2.text)
