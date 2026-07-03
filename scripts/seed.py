"""Khởi tạo DB + nạp dữ liệu + chạy pipeline 1 lần. Dùng để bootstrap nhanh.

    python scripts/seed.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import init_db  # noqa: E402
from app.pipeline import run_daily  # noqa: E402


def main() -> None:
    print("[seed] Tạo bảng...")
    init_db()
    print("[seed] Chạy pipeline (ingest + score + alert)...")
    summary = run_daily(ingest_data=True)
    print("[seed] Xong:", summary)
    print("[seed] Mở http://localhost:8000 sau khi chạy: uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()
