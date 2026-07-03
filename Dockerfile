FROM python:3.11-slim

# Đặt múi giờ Việt Nam để date.today()/lịch chạy đúng giờ VN
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=Asia/Ho_Chi_Minh

WORKDIR /app

# Thư viện hệ thống tối thiểu + tzdata (pandas/numpy build sẵn wheel nên nhẹ)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl tzdata && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
