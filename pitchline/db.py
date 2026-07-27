"""Engine and session plumbing. SQLite by default, Postgres-swappable via URL."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from pitchline import models  # noqa: F401  (import registers tables on SQLModel.metadata)

DEFAULT_DB_PATH = Path(os.environ.get("PITCHLINE_DB", "pitchline.db"))

_engine: Engine | None = None


def database_url(path: Path | str | None = None) -> str:
    if url := os.environ.get("PITCHLINE_DATABASE_URL"):
        return url
    return f"sqlite:///{Path(path or DEFAULT_DB_PATH).resolve()}"


def get_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """Process-wide engine. Pass an explicit URL for tests or a second database."""
    global _engine
    if url is not None:
        return create_engine(url, echo=echo, connect_args=_connect_args(url))
    if _engine is None:
        resolved = database_url()
        _engine = create_engine(resolved, echo=echo, connect_args=_connect_args(resolved))
    return _engine


def _connect_args(url: str) -> dict:
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


def init_db(engine: Engine | None = None) -> Engine:
    """Create all tables. Idempotent — safe to call on every CLI invocation."""
    engine = engine or get_engine()
    SQLModel.metadata.create_all(engine)
    return engine


def reset_db(engine: Engine | None = None) -> Engine:
    engine = engine or get_engine()
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    return engine


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Transactional session: commits on success, rolls back on exception."""
    engine = engine or get_engine()
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
