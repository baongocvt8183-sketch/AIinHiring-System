"""Shared pytest fixtures: an isolated seeded SQLite database per test run."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

# Keep generated CV demo files out of the repository working tree during tests.
_TEST_UPLOAD_ROOT = Path(tempfile.mkdtemp(prefix="aihiring-test-uploads-"))
os.environ["UPLOAD_DIR"] = str(_TEST_UPLOAD_ROOT)

from src.database.connection import make_engine
from src.database.models import Base
from src.database.seed import seed_database


def _engine_for(path: Path):
    return make_engine(f"sqlite:///{path}")


@pytest.fixture(scope="session")
def demo_engine(tmp_path_factory):
    path = tmp_path_factory.mktemp("demo_db") / "seeded.db"
    engine = _engine_for(path)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as session:
        seed_database(session)
    return engine


@pytest.fixture
def demo_session(demo_engine):
    factory = sessionmaker(bind=demo_engine, expire_on_commit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def clean_session(tmp_path):
    engine = _engine_for(tmp_path / f"clean_{uuid4().hex}.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TEST_UPLOAD_ROOT, ignore_errors=True)
