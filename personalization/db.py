from __future__ import annotations

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from webapp.config import get_settings


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    settings = get_settings()
    if settings.database_url:
        return settings.database_url
    return f"sqlite:///{Path('data/personalization_dev.sqlite').resolve()}"


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


DATABASE_URL = _database_url()
ENGINE = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    connect_args=_connect_args(DATABASE_URL),
)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def ensure_database() -> None:
    from personalization import models  # noqa: F401

    settings = get_settings()
    if settings.auto_create_db:
        Base.metadata.create_all(bind=ENGINE)


def check_database_ready() -> dict:
    with ENGINE.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ready", "database_url": DATABASE_URL}
