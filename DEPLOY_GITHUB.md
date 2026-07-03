# 🆓 Deploy 0đ tuyệt đối — GitHub Actions + Neon

Chạy 24/7 **hoàn toàn miễn phí**, không server, không thẻ tín dụng (nếu repo Public).
GitHub tự chạy script theo lịch (9h/14h/17h/17h30) và gửi Telegram; dữ liệu lưu ở **Neon**
(Postgres free). Máy tính của bạn có thể tắt.

> Đã có sẵn workflow: [.github/workflows/scheduled.yml](.github/workflows/scheduled.yml).

---

## Bước 1 — Postgres miễn phí (Neon)
1. https://neon.tech → đăng ký free → **Create project** (region Singapore).
2. Copy **Connection string** (`postgresql://...neon.tech/neondb?sslmode=require`). Giữ lại.

*(Có thể thay bằng Supabase free.)*

---

## Bước 2 — Đưa code lên GitHub
```powershell
cd C:\Workspace\2026\AI\Stock_System
git init
git add .
git commit -m "VN stock system"
git remote add origin https://github.com/<tên-bạn>/stock-system.git
git branch -M main
git push -u origin main
```
> `.env`/`stock.db`/secrets đã bị `.gitignore` — không lên GitHub.
> **Mẹo:** để repo **Public** → GitHub Actions **miễn phí không giới hạn phút**. (Code không chứa
> bí mật; mọi key nằm ở Secrets bên dưới. Nhưng nếu ngại lộ chiến lược thì để Private — vẫn free
> 2000 phút/tháng, đủ dùng.)

---

## Bước 3 — Đặt Secrets trên GitHub
Vào repo → **Settings → Secrets and variables → Actions → New repository secret**, thêm:

| Secret | Giá trị |
|---|---|
| `DATABASE_URL` | Chuỗi kết nối Neon (Bước 1) |
| `OPENAI_API_KEY` | Key ChatGPT |
| `TELEGRAM_TOKEN` | Token bot |
| `TELEGRAM_CHAT_ID` | Chat id của bạn |
| `DASHBOARD_BASE_URL` | (tùy chọn) để trống cũng được |

---

## Bước 4 — Chạy thử & bật lịch
1. Repo → tab **Actions** → nếu hỏi thì bấm **I understand... enable workflows**.
2. Chọn workflow **"VN Stock — chạy tự động"** → **Run workflow** → chọn `pipeline` → **Run**.
   - Lần chạy đầu tạo bảng trong Neon + chấm điểm + gửi Telegram. Xem log ngay trong Actions.
3. Nếu Telegram nhận được tin → xong! Từ giờ lịch tự chạy (giờ VN, T2–T6):
   `09:00 & 14:00` tin tức · `17:00` chọn cổ phiếu · `17:30` penny.

---

## Xem dashboard (khi cần)
GitHub Actions không có web luôn-bật. Khi muốn xem giao diện, chạy **local** trỏ vào Neon:
```powershell
$env:DATABASE_URL="postgresql://...neon.tech/neondb?sslmode=require"
.\.venv\Scripts\python.exe -m uvicorn app.main:app   # mở http://localhost:8000
```
(Dữ liệu giống hệt trên cloud vì cùng 1 DB Neon.)

---

## 💰 Chi phí & lưu ý
- **0đ**: Neon free + GitHub Actions free (Public: không giới hạn; Private: 2000 phút/tháng — dự án
  này dùng ~450 phút/tháng).
- ⏰ Lịch GitHub có thể **trễ 5–15 phút** lúc cao điểm (chấp nhận được với cảnh báo ngày).
- 😴 GitHub **tạm dừng lịch nếu repo 60 ngày không có hoạt động** → thỉnh thoảng push 1 commit nhỏ,
  hoặc vào Actions bấm Run là đủ giữ "sống".
- Deploy dùng **Neon mới** (không mang `stock.db` local); dữ liệu tự nạp lại, lịch sử tích lũy dần.
- Sau khi chạy ổn, nên **gỡ Task Scheduler local** (`VN_Stock_*`) để tránh gửi Telegram trùng.

---

## Muốn có dashboard luôn-bật mà vẫn ~0đ?
Kết hợp: giữ cron ở GitHub Actions (miễn phí) + deploy **chỉ mỗi web dashboard** lên Render gói
free (trỏ cùng `DATABASE_URL` Neon). Xem [DEPLOY_RENDER.md](DEPLOY_RENDER.md) phần web service.
