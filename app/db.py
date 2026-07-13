"""Kết nối DB + session factory (SQLAlchemy 2.0, sync)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def _normalize_url(url: str) -> str:
    """Chuẩn hóa chuỗi kết nối Postgres của các nền tảng (Render/Neon/Supabase hay dùng
    'postgres://' hoặc 'postgresql://') về driver psycopg2 mà SQLAlchemy hiểu."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


_db_url = _normalize_url(settings.database_url)
_connect_args = {"check_same_thread": False} if _db_url.startswith("sqlite") else {}

engine = create_engine(
    _db_url,
    echo=False,
    future=True,
    pool_pre_ping=True,          # tránh lỗi kết nối chết với DB cloud
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def session_scope() -> Iterator[Session]:
    """Session dùng trong pipeline/worker (tự commit/rollback)."""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db() -> Iterator[Session]:
    """Dependency cho FastAPI."""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _add_missing_columns() -> None:
    """Thêm các cột mới vào bảng ĐÃ TỒN TẠI (create_all KHÔNG làm việc này).

    Không có bước này, mỗi lần thêm cột vào model là DB cũ (Supabase) sẽ thiếu cột và mọi
    INSERT đều sập — trong khi máy local vẫn chạy tốt vì DB được tạo mới. Chỉ thêm cột
    NULLABLE (an toàn, không cần backfill); cột NOT NULL sẽ được báo để xử lý thủ công.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            if not col.nullable and col.default is None and col.server_default is None:
                print(f"[db] ⚠️ Cột {table.name}.{col.name} là NOT NULL — cần migration thủ công.")
                continue
            col_type = col.type.compile(engine.dialect)
            try:
                with engine.begin() as conn:
                    conn.execute(text(
                        f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type}'))
                print(f"[db] Đã thêm cột {table.name}.{col.name} ({col_type})")
            except Exception as exc:  # pragma: no cover
                print(f"[db] Không thêm được cột {table.name}.{col.name}: {str(exc)[:80]}")


def init_db() -> None:
    from app import models  # noqa: F401  đảm bảo models được import trước create_all

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
