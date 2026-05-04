"""SQLite store"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
)
from sqlalchemy.types import DateTime as SQLDateTime
from sqlalchemy.types import TypeDecorator

logger = structlog.get_logger(__name__)


class UTCDateTime(TypeDecorator):
    impl = SQLDateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError('naive datetime cannot be stored; pass timezone-aware')
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    """Declarative base for all ORM models in the substrate."""

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _default_db_path() -> Path:
    home = os.environ.get('LATTICE_HOME')
    base = Path(home) if home else Path.home() / '.lattice'
    return base / 'events.db'


def _create_engine_for_path(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f'sqlite:///{path}',
        future=True,
        json_serializer=lambda obj: __import__('json').dumps(obj, sort_keys=True),
    )

    @event.listens_for(engine, 'connect')
    def _on_connect(dbapi_conn, _: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.execute('PRAGMA synchronous=NORMAL')
        cursor.close()

    return engine


def init_db(path: Path | None = None) -> None:
    """Initialize the global engine and session factory.
    """
    global _engine, _session_factory

    target = path or _default_db_path()
    if _engine is not None:
        return

    logger.info('db.init', path=str(target))
    _engine = _create_engine_for_path(target)
    Base.metadata.create_all(_engine)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)


def reset_db_for_tests() -> None:
    """Test-only helper: drop the cached engine so the next init reconnects."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def get_session() -> Generator[Session, None, None]:
    if _session_factory is None:
        init_db()

    assert _session_factory is not None
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
