"""SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine(settings: Settings) -> None:
    """Initialize global engine and session factory."""
    global _engine, _SessionLocal
    _engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)


def get_engine():
    if _engine is None:
        raise RuntimeError("Database engine not initialized")
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        raise RuntimeError("Database session factory not initialized")
    return _SessionLocal


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a DB session."""
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
