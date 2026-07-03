"""Celery app + lịch chạy tự động (production, 24/7).

Chạy trên VPS/cloud qua Docker: worker + beat sẽ tự thực thi theo lịch dưới đây, KHÔNG phụ thuộc
máy tính cá nhân. Dev cục bộ có thể bỏ qua và dùng `python -m app.pipeline` / Task Scheduler.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery = Celery("stock_system", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(timezone="Asia/Ho_Chi_Minh", enable_utc=False)


@celery.task(name="tasks.run_daily_pipeline")
def run_daily_pipeline():
    """17:00 T2–T6: nạp dữ liệu + chấm điểm + AI chọn lọc cổ phiếu nên đầu tư → Telegram."""
    from app.pipeline import run_daily
    return run_daily(ingest_data=True)


@celery.task(name="tasks.scan_news")
def scan_news():
    """9:00 & 14:00 T2–T6: quét tin tức + AI phân tích ảnh hưởng → Telegram."""
    from app.db import init_db
    from app.news_scan import scan
    init_db()
    return scan(send=True)


@celery.task(name="tasks.scan_penny")
def scan_penny():
    """17:30 T2–T6: quét cổ phiếu penny tiềm năng (đầu cơ) → Telegram."""
    from app.db import init_db
    from app.penny import scan
    init_db()
    return scan(send=True)


celery.conf.beat_schedule = {
    "news-morning": {                    # tin tức phiên sáng
        "task": "tasks.scan_news",
        "schedule": crontab(hour=9, minute=0, day_of_week="1-5"),
    },
    "news-afternoon": {                  # tin tức phiên chiều
        "task": "tasks.scan_news",
        "schedule": crontab(hour=14, minute=0, day_of_week="1-5"),
    },
    "daily-pipeline": {                  # sau khi thị trường đóng cửa + có dữ liệu EOD
        "task": "tasks.run_daily_pipeline",
        "schedule": crontab(hour=17, minute=0, day_of_week="1-5"),
    },
    "penny-scan": {                      # quét penny sau pipeline chính
        "task": "tasks.scan_penny",
        "schedule": crontab(hour=17, minute=30, day_of_week="1-5"),
    },
}
