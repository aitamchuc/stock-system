"""Test nhanh: quét ~180 mã đầu, lọc penny, phân tích sâu 3 ứng viên."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.engines import penny_scanner  # noqa: E402
from app.providers import get_provider  # noqa: E402

p = get_provider()
uni = [s["symbol"] for s in p.all_listed_symbols()]
print("universe:", len(uni))
snap = p.market_snapshot(uni[:180])
print("snapshot có giá:", len(snap))
cands = penny_scanner.screen(snap, settings.penny_price_max, settings.penny_min_liquidity)
print(f"penny có thanh khoản (trong 180 mã đầu): {len(cands)}")
for c in cands[:3]:
    df = p.ohlcv(c["symbol"], (date.today() - timedelta(days=200)).isoformat(), date.today().isoformat())
    r = penny_scanner.analyze(df, c)
    print(f"  {c['symbol']}: giá {c['price']:,.0f} | thanh khoản {c['value']/1e9:.1f} tỷ "
          f"| tiềm năng {r['upside_score']:.0f} | rủi ro {r['risk_score']:.0f}")
    print("     tín hiệu:", r["signals"][:2])
