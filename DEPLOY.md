# 🚀 Deploy hệ thống chạy 24/7 (độc lập máy tính)

Chạy toàn bộ hệ thống trên **VPS/cloud** để nó tự động quét tin (9h & 14h), chấm điểm + chọn cổ
phiếu (17h), quét penny (17h30) và gửi Telegram **kể cả khi tắt máy tính của bạn**.

Kiến trúc Docker: `db` (Postgres/TimescaleDB) · `redis` · `api` (dashboard) · `worker` + `beat`
(chạy lịch tự động qua Celery). Tất cả tự khởi động lại khi VPS reboot (`restart: unless-stopped`).

---

## 1) Chuẩn bị VPS

Cần 1 VPS Linux **Ubuntu 22.04, ≥ 2GB RAM** (pandas cần bộ nhớ). Gợi ý:

| Nhà cung cấp | Gói tham khảo | Giá ~ |
|---|---|---|
| Vultr / DigitalOcean / Linode | 2GB RAM / 1 vCPU | 10–12$/tháng |
| AWS Lightsail | 2GB | ~10$/tháng |
| VN: BizFly Cloud, Viettel IDC, VNG Cloud | 2GB | ~150–250k/tháng |

> Muốn rẻ hơn: gói 1GB + bật swap 2GB vẫn chạy được VN30 (chậm hơn). VN30 nạp ~7 phút/lần.

Tạo VPS → lấy **IP** + tài khoản `root` (hoặc user sudo).

---

## 2) Cài Docker trên VPS

SSH vào VPS rồi chạy:
```bash
ssh root@<IP_VPS>

# Cài Docker + Docker Compose plugin
curl -fsSL https://get.docker.com | sh
docker compose version   # kiểm tra đã có
```

---

## 3) Đưa mã nguồn lên VPS

**Cách A — qua Git** (nếu bạn đẩy project lên GitHub riêng tư):
```bash
git clone <repo-cua-ban> stock_system && cd stock_system
```

**Cách B — copy trực tiếp từ máy Windows** (PowerShell trên máy bạn):
```powershell
# Nén rồi scp (bỏ .venv, stock.db, logs cho nhẹ)
cd C:\Workspace\2026\AI
scp -r Stock_System root@<IP_VPS>:/root/stock_system
```
(Hoặc dùng WinSCP kéo-thả thư mục, nhớ **bỏ** `.venv`, `stock.db`, `logs/`.)

---

## 4) Cấu hình `.env` trên VPS

```bash
cd /root/stock_system
cp .env.example .env
nano .env
```
Đặt các giá trị THẬT:
```ini
DATA_SOURCE=vnstock
VNSTOCK_WATCHLIST=ACB,BCM,BID,BVH,CTG,FPT,GAS,GVR,HDB,HPG,MBB,MSN,MWG,PLX,POW,SAB,SHB,SSB,SSI,STB,TCB,TPB,VCB,VHM,VIB,VIC,VJC,VNM,VPB,VRE

OPENAI_API_KEY=sk-...            # key ChatGPT của bạn
OPENAI_MODEL=gpt-4o-mini

TELEGRAM_TOKEN=...               # token bot
TELEGRAM_CHAT_ID=...             # chat id của bạn

POSTGRES_PASSWORD=<đặt-mật-khẩu-mạnh>
DASHBOARD_BASE_URL=http://<IP_VPS>:8000
```
> KHÔNG cần đặt `DATABASE_URL`/`REDIS_URL` — docker-compose tự trỏ vào Postgres/Redis nội bộ.

---

## 5) Khởi động

```bash
docker compose up -d --build      # build + chạy nền
docker compose ps                 # kiểm tra 5 service đều "Up"
```

Nạp dữ liệu lần đầu ngay (không cần chờ 17h):
```bash
docker compose exec api python -m app.pipeline        # nạp VN30 + chấm điểm + chọn cổ phiếu
docker compose exec api python -m app.news_scan       # quét tin tức (tùy chọn)
```

---

## 6) Kiểm tra

```bash
curl http://localhost:8000/api/health                 # {"status":"ok",...}
docker compose logs -f beat                            # xem lịch Celery
docker compose logs -f worker                          # xem task chạy
```
Mở dashboard: `http://<IP_VPS>:8000`

Lịch tự động (giờ VN, T2–T6) — beat lo hết, không cần máy bạn:
```
09:00 & 14:00  → quét tin + AI phân tích ảnh hưởng → Telegram
17:00          → nạp dữ liệu + chấm điểm + AI chọn cổ phiếu nên đầu tư → Telegram
17:30          → quét penny tiềm năng → Telegram
```

---

## 7) 🔒 Bảo mật (quan trọng)

- `db` và `redis` **không mở ra internet** (đã cấu hình). Chỉ cổng **8000** (dashboard) ra ngoài.
- Dashboard/API **chưa có đăng nhập** → ai biết IP đều xem được. Nên một trong:
  - Bật tường lửa chỉ cho IP của bạn: `ufw allow from <IP_cua_ban> to any port 8000 && ufw enable`
  - Hoặc đặt sau reverse proxy (Nginx/Caddy) + Basic Auth + HTTPS (khuyến nghị nếu công khai).
- Đổi `POSTGRES_PASSWORD` mạnh. Đừng commit `.env` lên Git công khai.
- Cân nhắc **thu hồi & tạo lại** OPENAI/TELEGRAM key nếu từng dán ở nơi công khai.

---

## 8) Vận hành thường ngày

```bash
docker compose logs -f worker          # theo dõi
docker compose restart worker beat     # khởi động lại
docker compose down                    # dừng (giữ dữ liệu)
docker compose up -d --build           # cập nhật sau khi sửa code
```
**Sao lưu DB:**
```bash
docker compose exec db pg_dump -U stock stock > backup_$(date +%F).sql
```
**Chạy thủ công 1 tác vụ bất kỳ:**
```bash
docker compose exec api python -m app.curate          # chọn cổ phiếu nên đầu tư
docker compose exec api python -m app.penny           # quét penny
```

---

## Ghi chú
- Deploy dùng **Postgres mới** (không mang theo `stock.db` local). Hệ thống tự nạp lại dữ liệu; lịch
  sử dòng tiền khối ngoại sẽ tích lũy dần theo ngày như khi chạy local.
- Múi giờ container đã đặt `Asia/Ho_Chi_Minh` (Dockerfile) nên giờ chạy & `date.today()` đúng giờ VN.
- Máy tính cá nhân giờ **không cần bật**; có thể gỡ các Task Scheduler local (`VN_Stock_*`) nếu muốn
  tránh chạy trùng: `Unregister-ScheduledTask -TaskName "VN_Stock_Daily" -Confirm:$false` (và News/Penny).
