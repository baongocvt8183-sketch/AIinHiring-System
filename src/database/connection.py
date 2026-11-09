"""Database engine/session helpers with PostgreSQL and SQLite support."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src import config
from src.database.models import Base


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


@lru_cache(maxsize=8)
def make_engine(url: str | None = None) -> Engine:
    """Create a cached SQLAlchemy engine for ``url`` (defaults to config)."""
    database_url = url or config.DATABASE_URL
    config.ensure_directories()

    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if _is_sqlite(database_url):
        kwargs["connect_args"] = {"check_same_thread": False}
        if database_url in {"sqlite://", "sqlite:///:memory:"} or ":memory:" in database_url:
            kwargs["poolclass"] = StaticPool

    engine = create_engine(database_url, **kwargs)

    if _is_sqlite(database_url):
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):  # pragma: no cover - driver hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_engine() -> Engine:
    return make_engine(config.DATABASE_URL)


@lru_cache(maxsize=8)
def make_session_factory(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=make_engine(url), expire_on_commit=False, future=True)


def get_session_factory() -> sessionmaker[Session]:
    return make_session_factory(config.DATABASE_URL)


def new_session(url: str | None = None) -> Session:
    return make_session_factory(url)()


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    session = new_session(url)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all(engine: Engine | None = None) -> None:
    Base.metadata.create_all(bind=engine or get_engine())


def init_db(seed: bool = True, engine: Engine | None = None) -> None:
    """Create tables and seed demo data when the database is empty."""
    config.ensure_directories()
    target_engine = engine or get_engine()
    Base.metadata.create_all(bind=target_engine)

    if not seed or not config.SEED_DEMO_DATA:
        return

    from src.database.seed import seed_database  # local import avoids a cycle

    factory = sessionmaker(bind=target_engine, expire_on_commit=False, future=True)
    with factory() as session:
        seed_database(session)


def healthcheck() -> tuple[bool, str]:
    """Return (ok, message) for the configured database."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, config.safe_database_label()
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, str(exc)
