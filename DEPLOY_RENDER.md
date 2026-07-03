# 🚀 Deploy KHÔNG cần VPS — Render + Neon (Postgres miễn phí)

Chạy 24/7 mà không quản lý server: **Render** tự chạy các cron (9h/14h/17h/17h30) gửi Telegram,
dữ liệu lưu ở **Neon** (Postgres miễn phí, không hết hạn). Máy tính của bạn có thể tắt.

> Đã có sẵn [render.yaml](render.yaml) — Render đọc file này và tạo mọi thứ tự động.

---

## Bước 1 — Tạo Postgres miễn phí (Neon)

1. Vào https://neon.tech → đăng ký (miễn phí, không cần thẻ).
2. **Create project** → đặt tên (vd `stock`) → chọn region gần (Singapore).
3. Copy **Connection string** (dạng `postgresql://user:pass@ep-xxx.aws.neon.tech/neondb?sslmode=require`).
   → Giữ lại, lát nữa dán vào Render.

*(Có thể thay bằng Supabase free — cũng được, miễn có chuỗi kết nối Postgres.)*

---

## Bước 2 — Đưa mã nguồn lên GitHub (repo riêng tư)

Trên máy bạn (PowerShell trong thư mục project):
```powershell
cd C:\Workspace\2026\AI\Stock_System
git init
git add .
git commit -m "VN stock system"
```
Tạo repo **Private** trên https://github.com/new (vd `stock-system`), rồi:
```powershell
git remote add origin https://github.com/<tên-bạn>/stock-system.git
git branch -M main
git push -u origin main
```
> `.gitignore` đã loại `.env`, `stock.db`, `.venv`, `logs` — bí mật KHÔNG bị đẩy lên. An toàn.

---

## Bước 3 — Deploy trên Render

1. Vào https://render.com → **Sign up with GitHub** (miễn phí).
2. **New → Blueprint** → chọn repo `stock-system` vừa tạo.
3. Render đọc `render.yaml` → hiện danh sách: 1 web + 4 cron. Bấm **Apply**.
4. Render sẽ hỏi điền các **biến bí mật** (nhóm `stock-secrets`):
   - `DATABASE_URL` = chuỗi kết nối Neon ở Bước 1
   - `OPENAI_API_KEY` = key ChatGPT
   - `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` = bot của bạn
   - `DASHBOARD_BASE_URL` = tạm để trống, điền sau khi có URL web (vd `https://stock-dashboard.onrender.com`)
5. Bấm **Apply/Deploy**. Render build image (~vài phút).

---

## Bước 4 — Nạp dữ liệu lần đầu & kiểm tra

- Vào cron **daily-pipeline** → **Trigger Run** (chạy ngay, không chờ 17h) → xem Logs.
  Lần chạy đầu tự tạo bảng trong Neon + chấm điểm + gửi Telegram.
- Mở URL web `stock-dashboard` để xem bảng xếp hạng.
- Cập nhật `DASHBOARD_BASE_URL` = URL web đó (để link trong tin Telegram đúng), rồi Deploy lại.

Từ giờ lịch tự chạy (giờ VN, T2–T6): 09:00 & 14:00 tin tức · 17:00 chọn cổ phiếu · 17:30 penny.

---

## 💰 Chi phí (minh bạch)

- **Neon**: gói free vĩnh viễn (0đ), đủ cho dữ liệu này.
- **Render web (dashboard)**: gói **free** — ngủ sau 15 phút không dùng, tự thức khi truy cập (chậm ~30s lần đầu).
- **Render cron**: tính theo thời gian chạy thực tế (mỗi lần vài phút). Rất rẻ, thường vài chục nghìn/tháng;
  Render có thể yêu cầu thêm thẻ/credit. Nếu muốn **0đ tuyệt đối** → xem "GitHub Actions" ở cuối.

---

## 🔧 Vận hành

- Sửa code → `git push` → Render tự build & deploy lại.
- Xem log từng cron/web trong Render dashboard.
- Chạy tay 1 tác vụ: mở cron tương ứng → **Trigger Run**.

---

## Phương án 0đ tuyệt đối (nếu muốn): GitHub Actions

Nếu không muốn trả bất kỳ khoản nào cho cron: dùng **GitHub Actions** (cron miễn phí) + **Neon**.
GitHub tự chạy script theo lịch gửi Telegram; chỉ khác là **không có dashboard luôn-bật**
(mở dashboard local khi cần: `uvicorn app.main:app`). Nếu bạn muốn hướng này, mình sẽ tạo sẵn
file workflow `.github/workflows/*.yml`.

---

## Lưu ý
- Deploy dùng **Neon Postgres mới** (không mang theo `stock.db` local). Hệ thống tự nạp lại;
  lịch sử khối ngoại tích lũy dần theo ngày.
- Sau khi Render chạy ổn, nên **gỡ Task Scheduler local** (`VN_Stock_*`) để tránh gửi Telegram trùng.
- Render cron dùng giờ **UTC** (đã quy đổi sẵn trong `render.yaml`); `TZ=Asia/Ho_Chi_Minh` chỉ để
  `date.today()` ra đúng ngày VN.
