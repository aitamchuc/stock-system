# 📈 Hệ thống Xếp hạng & Cảnh báo Cổ phiếu Việt Nam

Nền tảng tự động **thu thập → phân tích → chấm điểm → cảnh báo** cổ phiếu VN (HOSE/HNX/UPCOM)
dựa trên dữ liệu công khai. Kết hợp **phân tích cơ bản (BCTC)**, **kỹ thuật (chart)**,
**dòng tiền khối ngoại/tự doanh**, **tin tức/sự kiện** → điểm tổng hợp + tín hiệu + cảnh báo Telegram.

> ⚠️ **Miễn trừ trách nhiệm:** Hệ thống chỉ cung cấp điểm số xác suất, mức rủi ro và luận điểm
> tham khảo. **KHÔNG phải khuyến nghị đầu tư, KHÔNG cam kết lợi nhuận.** Bạn tự chịu trách nhiệm
> với mọi quyết định giao dịch.

---

## ✨ Tính năng

| Nhóm | Nội dung |
|---|---|
| Thu thập | Giá/khối lượng, BCTC, khối ngoại/tự doanh, tin tức & sự kiện (qua provider có thể thay) |
| Phân tích kỹ thuật | MA20/50/100/200, RSI, MACD, Bollinger, volume breakout, hỗ trợ/kháng cự → điểm 0–100 + diễn giải |
| Phân tích cơ bản | ROE/ROA, biên LN, nợ/VCSH, CFO/LNST, FCF, P/E, P/B + **phát hiện red flag** (LN tăng nhưng dòng tiền âm, tồn kho/phải thu tăng đột biến…) |
| Dòng tiền lớn | Mua/bán ròng khối ngoại + tự doanh, volume z-score → tích cực/trung tính/tiêu cực |
| Chấm điểm | 8 nhóm điểm × trọng số (chỉnh được) → Final Score + tín hiệu + rationale JSON |
| Tín hiệu | Rất tích cực / Tích cực / Theo dõi / Trung tính / Cảnh báo rủi ro / Phân phối / Tránh mua |
| Cảnh báo | Bot Telegram (điểm cao, breakout, khối ngoại mua ròng, rủi ro) kèm disclaimer |
| Dashboard | Bảng xếp hạng có filter + trang chi tiết (chart, BCTC, radar điểm, tin tức) |
| Backtest | Forward return 5/20/60 phiên, win rate, Sharpe, alpha vs benchmark — **point-in-time, chống look-ahead bias** |

---

## 🚀 Chạy nhanh (zero-config, offline)

Mặc định dùng **SQLite** + **DemoProvider** (dữ liệu synthetic) → chạy được ngay không cần
internet, Postgres hay API key.

```bash
# 1. Tạo môi trường ảo + cài đặt
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell
pip install -r requirements.txt

# 2. Nạp dữ liệu + chấm điểm 1 phiên (tạo stock.db, in cảnh báo ra console)
python scripts/seed.py

# 3. (Tùy chọn) Backfill lịch sử để backtest có dữ liệu
python scripts/backfill.py --days 150

# 4. Chạy dashboard + API
uvicorn app.main:app --reload
#   → mở http://localhost:8000
```

> Trên Windows nếu console lỗi font: `set PYTHONIOENCODING=utf-8` (hoặc `$env:PYTHONIOENCODING="utf-8"`).

---

## 🔌 API chính

| Endpoint | Mô tả |
|---|---|
| `GET /` | Dashboard xếp hạng |
| `GET /stock/{symbol}` | Trang chi tiết mã |
| `GET /api/ranking?signal=&industry=&min_score=&limit=` | Danh sách cổ phiếu xếp hạng (JSON) |
| `GET /api/stock/{symbol}` | Chi tiết mã: điểm, BCTC, dòng tiền, tin tức |
| `GET /api/backtest?signal=very_positive` | Kết quả backtest theo tín hiệu |
| `GET /api/quality-log` | Nhật ký chất lượng dữ liệu & lỗi crawl |

---

## 📲 Cảnh báo Telegram (hai chiều)

**Bước 1 — Tạo bot:** chat với [@BotFather](https://t.me/BotFather) → `/newbot` → đặt tên → copy **TOKEN**.

**Bước 2 — Lấy chat_id + gửi test:** mở bot vừa tạo, bấm **Start** và gửi 1 tin ("hello"), rồi chạy:
```bash
python scripts/telegram_setup.py --token 123456:ABC-XYZ...
# → in ra chat_id và gửi 1 tin test vào Telegram của bạn
```
**Bước 3 — Dán vào `.env`:**
```
TELEGRAM_TOKEN=123456:ABC-XYZ...
TELEGRAM_CHAT_ID=987654321
```
Từ giờ mỗi lần `python -m app.pipeline`, cảnh báo (điểm cao / breakout / rủi ro…) sẽ **gửi thật** vào Telegram.
Gửi thử 1 tin mẫu bất cứ lúc nào: `python -m app.bot.telegram`.

**Bot hai chiều (tùy chọn)** — trả lời lệnh trực tiếp trong Telegram:
```bash
python -m app.bot.listener
```
| Lệnh | Chức năng |
|---|---|
| `/rank [n]` | Top n mã điểm cao nhất |
| `/detail FPT` | Chi tiết điểm + luận điểm + rủi ro của 1 mã |
| `/watch` | Danh mục đang theo dõi |
| `/help` | Trợ giúp |

> Tin nhắn dùng `parse_mode=HTML` (an toàn với ký tự tiếng Việt & dấu `_`), luôn kèm disclaimer.
> Khi chưa cấu hình token, mọi cảnh báo in ra console (dev mode) để bạn xem trước format.

## ⏰ Chạy tự động hằng ngày (Windows Task Scheduler)

Để hệ thống tự quét dữ liệu, chấm điểm, **tích lũy lịch sử khối ngoại** và gửi cảnh báo Telegram
lúc **17:00 các ngày T2–T6** (sau khi thị trường đóng cửa & có dữ liệu EOD):

```powershell
# Đăng ký (không cần quyền admin — task cấp user)
powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1

# Chạy thử ngay
Start-ScheduledTask -TaskName "VN_Stock_Daily"
# Xem trạng thái / lần chạy kế tiếp
Get-ScheduledTaskInfo -TaskName "VN_Stock_Daily"
# Gỡ bỏ
Unregister-ScheduledTask -TaskName "VN_Stock_Daily" -Confirm:$false
```

- Wrapper [scripts/run_daily.ps1](scripts/run_daily.ps1) chạy `python -m app.pipeline` trong `.venv`
  và ghi log UTF-8 vào `logs\pipeline_YYYY-MM-DD.log`.
- `-StartWhenAvailable`: nếu máy tắt lúc 17:00 → tự chạy bù khi bật máy lần sau.
- `LogonType Interactive`: chỉ chạy khi bạn đã đăng nhập Windows (không cần lưu mật khẩu). Muốn chạy
  cả khi chưa đăng nhập → sửa `install_task.ps1` sang `-LogonType Password` (phải nhập mật khẩu).
- Vì dòng tiền khối ngoại chỉ là snapshot mỗi phiên, **chạy đều mỗi ngày** sẽ tích lũy dần chuỗi
  lịch sử để tính mua/bán ròng 5/20 phiên chính xác hơn.

## 🏭 Deploy 24/7 online (độc lập máy tính) — xem [DEPLOY.md](DEPLOY.md)

Để hệ thống tự chạy **kể cả khi tắt máy tính**, deploy lên VPS/cloud bằng Docker:
```bash
cp .env.example .env        # đặt DATA_SOURCE=vnstock, OPENAI_API_KEY, TELEGRAM_*, POSTGRES_PASSWORD...
docker compose up -d --build
docker compose exec api python -m app.pipeline   # nạp dữ liệu lần đầu
```
Docker Compose khởi động (tự restart khi reboot): `db` (Postgres/TimescaleDB) · `redis` ·
`api` (dashboard :8000) · `worker` + `beat` (Celery chạy lịch tự động).

**Lịch tự động qua Celery beat** ([app/celery_app.py](app/celery_app.py), giờ VN, T2–T6):
`09:00 & 14:00` quét tin + AI phân tích → Telegram · `17:00` chấm điểm + AI chọn cổ phiếu →
Telegram · `17:30` quét penny → Telegram.

👉 **Có VPS**: hướng dẫn đầy đủ (cài Docker, cấu hình, bảo mật, sao lưu) → **[DEPLOY.md](DEPLOY.md)**.
👉 **KHÔNG dùng VPS** (Render + Neon Postgres miễn phí, cron tự chạy) → **[DEPLOY_RENDER.md](DEPLOY_RENDER.md)**
+ Blueprint [render.yaml](render.yaml).
👉 **Miễn phí 0đ** (GitHub Actions cron + Neon, không server, không thẻ) → **[DEPLOY_GITHUB.md](DEPLOY_GITHUB.md)**
+ workflow [.github/workflows/scheduled.yml](.github/workflows/scheduled.yml). Dashboard mở local khi cần.

---

## 🔧 Cấu hình (.env)

| Biến | Ý nghĩa |
|---|---|
| `DATABASE_URL` | `sqlite:///./stock.db` (mặc định) hoặc `postgresql+psycopg2://...` |
| `DATA_SOURCE` | `demo` (offline) hoặc `vnstock` (dữ liệu thật — cần `pip install vnstock`) |
| `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` | Để trống = in cảnh báo ra console (dev) |
| `OPENAI_API_KEY` | Có key = dùng **ChatGPT** cho agent khuyến nghị + tóm tắt tin; không có = fallback |
| `OPENAI_MODEL` | Model OpenAI (mặc định `gpt-4o-mini`) |
| `ANTHROPIC_API_KEY` | (Tùy chọn) dùng Claude thay ChatGPT |
| `LLM_PROVIDER` | Ép cứng `openai`\|`anthropic` (để trống = tự nhận theo key) |
| `ALERT_MIN_SCORE` | Ngưỡng điểm để bắn cảnh báo (mặc định 75) |
| `W_*` | Trọng số 8 nhóm điểm (tổng = 1.0) |

### Dùng dữ liệu VN thật (vnstock v4) ✅ đã bật
```bash
pip install vnstock          # đã cài; kéo dữ liệu VCI/TCBS thật
# .env:
#   DATA_SOURCE=vnstock
#   VNSTOCK_SOURCE=VCI
#   VNSTOCK_WATCHLIST=FPT,HPG,VCB,MWG,SSI,VNM,MBB,DGC
python -m app.pipeline        # ingest + chấm điểm dữ liệu thật
python scripts/show_ranking.py
```
Adapter: [app/providers/vnstock_provider.py](app/providers/vnstock_provider.py) — dùng
`vnstock.api` (Quote / Listing / Finance). Lấy về **thật**: giá OHLCV, BCTC (doanh thu, LNST,
ROE/ROA, biên LN, nợ vay, CFO, FCF, tồn kho, phải thu... tự tính từ income+balance+cashflow).

**Giới hạn của gói community/guest (nêu rõ để minh bạch):**
- **Rate limit ~20 request/phút** → provider có bộ throttle tự động (`_throttle`, 18 req/phút);
  vì vậy **chỉ quét watchlist** (`VNSTOCK_WATCHLIST`), không quét toàn bộ ~1600 mã. Muốn nhiều
  mã hơn: nâng gói tài trợ vnstock rồi tăng `_MAX_PER_MIN` và mở rộng watchlist.
- **BCTC giới hạn 4 kỳ gần nhất** → tăng trưởng chỉ tính được QoQ (chưa đủ 4 quý cho YoY).
- **P/E, P/B đã tính từ giá thị trường** ✅: số cổ phiếu = vốn góp (`paid_in_capital`) / mệnh giá
  10.000đ; EPS_TTM = LNST 4 quý / số cp; **P/E = giá / EPS_TTM**, **P/B = giá / (VCSH / số cp)**.
  Tính trong [engines/fundamental.py](app/engines/fundamental.py) `compute_valuation_metrics`
  lúc chấm điểm (giá đổi hằng ngày). Lưu ý: giá vnstock là giá *điều chỉnh* còn EPS theo số cp
  hiện tại → với mã có chia tách/thưởng lớn, P/E có thể lệch nhẹ so với bảng giá CTCK.
- **Dòng tiền khối ngoại đã bật** ✅: vnstock chưa hỗ trợ *chuỗi lịch sử* `foreign_trade`, nên hệ
  thống lấy **mua/bán ròng khối ngoại phiên gần nhất** qua `price_board` (1 lần cho cả watchlist
  mỗi lần chạy) và ghi vào bảng `money_flow` → tích lũy dần thành lịch sử. Điểm dòng tiền phân hóa
  theo mua/bán ròng thật (vd HPG bán ròng → điểm thấp, FPT mua ròng → điểm cao). *Tự doanh* chưa
  có nguồn công khai ổn định → để 0.
- `publish_date` của BCTC ước lượng ~45 ngày sau khi chốt quý (đảm bảo point-in-time cho backtest).

vnstock wrap API **không chính thức** của các CTCK; cấu trúc có thể đổi/khóa. Provider bọc lỗi để
pipeline không sập và ghi `data_quality_log`. Chỉ dùng cho mục đích cá nhân/nghiên cứu, không tái
phân phối dữ liệu thô.

---

## 🗂️ Cấu trúc

```
app/
  config.py            # cấu hình + trọng số
  db.py / models.py    # SQLAlchemy engine + schema (daily_scores APPEND-ONLY, point-in-time)
  providers/           # DemoProvider (offline) + VnstockProvider (thật) sau interface chung
  ingestion/           # thu thập dữ liệu (idempotent + retry)
  quality/             # kiểm tra chất lượng, quarantine mã dữ liệu hỏng
  engines/
    ta_engine.py       # phân tích kỹ thuật → điểm + diễn giải
    fundamental.py     # BCTC → 4 nhóm điểm + red flags
    moneyflow.py       # dòng tiền khối ngoại/tự doanh
    news_nlp.py        # sentiment/tóm tắt (LLM hoặc keyword)
    scoring.py         # gộp 8 nhóm → final score + tín hiệu + rationale
  alerting/rules.py    # rule engine sinh cảnh báo (dedupe)
  bot/telegram.py      # gửi + format tin nhắn Telegram
  backtest/engine.py   # backtest point-in-time
  pipeline.py          # orchestrator hằng ngày (chạy độc lập, không cần Celery)
  celery_app.py        # scheduler production
  main.py + templates/ # FastAPI + dashboard
scripts/               # seed.py, backfill.py
tests/                 # smoke test end-to-end
```

---

## 🧮 Công thức chấm điểm

`Final = Σ (điểm_nhóm × trọng_số) / Σ trọng_số`, 8 nhóm (0–100):
cơ bản, tăng trưởng, sức khỏe TC, định giá, kỹ thuật, dòng tiền, tin tức, **rủi ro**
(điểm rủi ro cao = rủi ro thấp, đã đảo dấu để cùng hướng). Trọng số mặc định cho NĐT
trung hạn VN trong [app/config.py](app/config.py): technical 0.20, fundamental 0.18,
growth 0.15, moneyflow 0.13, health 0.12, valuation 0.10, risk 0.07, news 0.05.

---

## 📰 Quét tin tức kinh tế + AI phân tích ảnh hưởng (9h & 14h)

Quét RSS các báo lớn (VN + thế giới), cho AI phân tích **mức độ & chiều ảnh hưởng tới giá cổ phiếu**,
map vào watchlist, và gửi **bản tin Telegram** — chạy tự động 2 lần/ngày.

```bash
python -m app.news_scan               # quét + phân tích + gửi Telegram
python -m app.news_scan --no-telegram # không gửi
```

- **Nguồn** ([app/news_sources.py](app/news_sources.py)): VnExpress, CafeF (CK/DN/vĩ mô), VietnamNet,
  + tin thế giới qua Google News RSS (kinh tế toàn cầu, Fed/lãi suất). Chỉ dùng **RSS công khai**.
- **Tầng 1 — phân loại theo lô** ([engines/news_impact.py](app/engines/news_impact.py) `analyze_batch`):
  mỗi bài gắn `relevant`, `scope` (macro/sector/company), `impact_level` (cao/trung bình/thấp),
  `direction` (tích cực/tiêu cực/trung tính), `affected_symbols` (chỉ mã trong watchlist, nói
  trực tiếp), `sectors`, giải thích ngắn. Gộp ~12 bài/lệnh gọi LLM để tiết kiệm chi phí.
- **Tầng 2 — phân tích SÂU trước khi gửi** (`synthesize`): AI đóng vai "Cố vấn Đầu tư AI" tổng
  hợp các tin đáng chú ý thành **bản tin sắc bén**: 🌐 bối cảnh & tâm lý thị trường → 🔑 chủ đề
  chính (gộp tin liên quan) → 🎯 tác động cụ thể tới mã/ngành (chiều, mức độ, khung thời gian) →
  ⚠️ rủi ro cần theo dõi. Đây mới là nội dung gửi Telegram (kèm link nguồn).
- **Khử trùng theo URL** (không phân tích lại bài cũ). Lưu bảng `news_impact`.
- **Bản tin Telegram**: chỉ tổng hợp từ tin **liên quan + ảnh hưởng cao/trung bình**. Không có LLM
  key → gửi danh sách rút gọn thay cho bản tin sâu.
- Xem: `GET /api/news` (mặc định chỉ tin đáng chú ý; `?only_notable=false` để xem tất cả).
- Không có LLM key → fallback keyword (relevant + direction thô).

**Lịch chạy tự động** (Task Scheduler `VN_Stock_News`, 09:00 & 14:00 T2–T6):
```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1 `
  -TaskName "VN_Stock_News" -Time "09:00,14:00" -Wrapper "run_news.ps1" `
  -Description "Quet tin tuc + AI phan tich anh huong - 9h & 14h T2-T6."
```

## 📡 Giá thị trường trực tiếp (gần thời gian thực)

Lấy **giá khớp lệnh mới nhất** qua `price_board` của vnstock (raw VND), kèm %thay đổi so với giá
tham chiếu — chính xác hơn giá đóng cửa EOD trong phiên.

- API: `GET /api/live` (toàn watchlist) hoặc `GET /api/live?symbols=HPG,FPT` · và trường `live`
  trong `GET /api/stock/{mã}`.
- Dashboard: cột **Giá** tự cập nhật mỗi 30s (JS gọi `/api/live`); trang chi tiết hiện "Giá trực tiếp".
- Provider có **cache TTL ~20s** để không vượt rate-limit; 1 lần gọi `price_board` phục vụ cả watchlist.
- **Agent khuyến nghị** dùng giá trực tiếp làm `current_price` khi tạo cho phiên hôm nay (bám sát
  giá hiện tại thay vì giá EOD).
- Ngoài giờ giao dịch, giá trực tiếp = giá khớp cuối phiên (bằng giá đóng cửa) — điều này bình thường.

```bash
python scripts/check_live.py     # in giá trực tiếp watchlist
```

## ✅ AI chọn lọc cổ phiếu NÊN ĐẦU TƯ (nội dung chính gửi Telegram)

Thay vì gửi mọi cảnh báo lẻ, hệ thống để **AI agent chọn lọc** — chỉ giữ những mã thực sự đáng
tích lũy ("thà ít mà chất") và gửi **một danh sách gọn** lên Telegram.

```bash
python -m app.curate                # chọn lọc + gửi Telegram
python -m app.curate --no-telegram
```

- Chạy ở **bước 7 (cuối) của pipeline** — là **nội dung DUY NHẤT** gửi Telegram mỗi ngày.
- Ứng viên: mã có `final_score ≥ CURATE_MIN_SCORE` (mặc định 58) và tín hiệu tích cực/theo dõi,
  lấy top `CURATE_TOP_N` (mặc định 15).
- AI ("Cố vấn Đầu tư") phân loại mỗi mã: **Mua tích lũy** | Theo dõi | Tránh — chỉ mã "Mua tích
  lũy" được đưa vào danh sách, kèm luận điểm + vùng mua/mục tiêu/cắt lỗ ([engines/recommend.py](app/engines/recommend.py)).
  ⚠️ Điểm rủi ro của hệ thống đã đảo (cao = an toàn) nên được **gắn nhãn rõ** khi đưa cho AI để
  tránh hiểu nhầm.
- Nếu AI không chọn mã nào đủ tin cậy → gửi tin "nên đứng ngoài quan sát" (trung thực, không ép mua).
- Cảnh báo lẻ (breakout/khối ngoại/rủi ro…) **vẫn lưu DB** cho dashboard nhưng **không spam Telegram**
  (bật lại bằng `PUSH_INDIVIDUAL_ALERTS=true`). Xem: `GET /api/picks`. Bảng `daily_picks`.

## 🎯 Khuyến nghị giá mua/bán (AI agent)

Cho các mã **có BCTC quý/năm mới công bố trong ngày**, hệ thống sinh **vùng giá MUA, giá BÁN
(chốt lời) và CẮT LỖ** kèm luận điểm — dựa trên điểm số + hỗ trợ/kháng cự + định giá P/E.

```bash
python -m app.recommend            # chỉ mã có BCTC mới (publish_date trong 3 ngày gần nhất)
python -m app.recommend --force    # ép chạy cho toàn bộ mã đã chấm điểm (để xem thử ngay)
```
Tự động chạy trong pipeline hằng ngày (bước 6) và gửi Telegram (`format_recommendation`).
Xem trên dashboard: panel "🎯 Khuyến nghị giá" ở trang chi tiết mã, hoặc API `/api/recommendations`.

**Nhân cách agent:** LLM được nạp **system prompt "Cố vấn Đầu tư AI"** ([app/prompts/advisor.md](app/prompts/advisor.md))
— chuyên gia phân tích & quản trị danh mục, tư duy thận trọng, rủi ro-trước-tiên, chỉ dùng dữ liệu
được cấp, không cam kết lợi nhuận. Sửa file này để đổi "tính cách"/nguyên tắc của agent.

**Hai chế độ** ([engines/recommend.py](app/engines/recommend.py) qua lớp LLM chung [app/llm.py](app/llm.py)):
- **Có `OPENAI_API_KEY` (ChatGPT)** hoặc `ANTHROPIC_API_KEY` (Claude) → LLM đóng vai chuyên viên
  phân tích, "nghiên cứu & đánh giá" toàn bộ dữ liệu định lượng để tinh chỉnh mức giá + viết luận
  điểm. Output bị **ràng buộc & kiểm tra hợp lệ** (cắt_lỗ < mua_thấp ≤ mua_cao < mục_tiêu; trong
  biên hợp lý so với giá) — nếu LLM trả số vô lý sẽ tự động lùi về mức theo quy tắc. `method=llm`.
- **Không có key** → mức giá theo **quy tắc xác định**: vùng mua bám hỗ trợ, mục tiêu theo kháng
  cự (nới thêm khi điểm ≥75), cắt lỗ ~7% dưới hỗ trợ. `method=rule`.

> ⚠️ **Đây là tính năng rủi ro nhất** — đưa ra giá cụ thể. Mọi mức giá CHỈ THAM KHẢO, không phải
> khuyến nghị đầu tư, không cam kết lợi nhuận; luôn kèm cảnh báo và luận điểm rủi ro.

## 🪙 Bộ quét cổ phiếu penny tiềm năng (ĐẦU CƠ — RỦI RO RẤT CAO)

Phát hiện **ứng viên** cổ phiếu penny có dấu hiệu tăng mạnh, **kèm chấm điểm rủi ro** — để
nghiên cứu, **KHÔNG phải khuyến nghị mua, KHÔNG hứa hẹn "x3 x4"**.

```bash
python -m app.penny                # quét toàn thị trường (~1500 mã), gửi Telegram
python -m app.penny --no-telegram  # không gửi Telegram
```

**Hai tầng** ([engines/penny_scanner.py](app/engines/penny_scanner.py)):
- **Tầng 1 — quét nhanh toàn thị trường**: `market_snapshot` gộp ~60 mã/lệnh gọi `price_board`
  (~26 lệnh cho cả ~1500 mã) → lọc **giá ≤ `PENNY_PRICE_MAX`** (mặc định 10.000đ) và **thanh khoản
  ≥ `PENNY_MIN_LIQUIDITY`** (mặc định 1 tỷ, tính bằng KL×giá).
- **Tầng 2 — phân tích sâu top `PENNY_SCAN_TOP`** (mặc định 20): từ lịch sử giá tính volume
  breakout, vượt MA20/MA50, tích lũy sát đáy, khối ngoại mua → **Điểm TIỀM NĂNG (0-100)**; và
  thanh khoản thấp, biến động cực cao (ATR%), đã tăng nóng (kéo–xả), thị giá <3.000đ, khối ngoại
  bán → **Điểm RỦI RO (0-100, cao = nguy hiểm)**.

Xem: `GET /api/penny` · Telegram `format_penny` (gửi khi điểm tiềm năng ≥ `PENNY_MIN_UPSIDE`).

> 🚨 **Cảnh báo bắt buộc:** Penny đầu cơ dễ bị **làm giá/kéo xả**, thanh khoản thấp, có thể
> **hủy niêm yết** và **mất phần lớn vốn**. Mọi tín hiệu chỉ tham khảo. Không dùng đòn bẩy với penny.

## 🧪 Kiểm thử

```bash
pytest -q                       # smoke test: pipeline + TA + backtest end-to-end
```

---

## ⚠️ Giới hạn & rủi ro

- **Dữ liệu demo là synthetic** (random walk) — không có tín hiệu dự báo thật; dùng để phát
  triển/kiểm thử. Muốn đánh giá thực chất phải chuyển sang `vnstock` và backfill dữ liệu thật.
- **vnstock** không chính thức → có thể bị đổi/khóa; cần theo dõi và có nguồn dự phòng.
- Khối ngoại/tự doanh chỉ có **cuối phiên (EOD)**, có độ trễ công bố.
- OCR đọc BCTC bản PDF gốc chưa bật (Phase 2) — hiện dùng số liệu chuẩn hóa từ provider.
- **Pháp lý:** tôn trọng ToS từng nguồn; không dùng dữ liệu nội bộ/rò rỉ; hệ thống là công cụ
  thông tin/giáo dục, không phải dịch vụ tư vấn đầu tư có giấy phép.
```
