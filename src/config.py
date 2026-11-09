"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(DATA_DIR / "uploads"))).resolve()
SAMPLE_DIR = DATA_DIR / "sample"

# The quick-start demo uses SQLite. Set DATABASE_URL to a PostgreSQL URL for the
# full deployment described in the README.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or f"sqlite:///{DATA_DIR / 'recruitment.db'}"

APP_NAME = "AI in Hiring"
APP_SUBTITLE = "Kho dữ liệu tuyển dụng & phân tích pipeline ứng viên"
APP_VERSION = "1.0.0"

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "8"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MIN_PDF_TEXT_CHARS = int(os.getenv("MIN_PDF_TEXT_CHARS", "50"))
MAX_ETL_ROWS = int(os.getenv("MAX_ETL_ROWS", "50000"))
MAX_STORED_ROW_ERRORS = int(os.getenv("MAX_STORED_ROW_ERRORS", "500"))

# Local-only AI/NLP. No CV content is sent to an external service.
CV_METHOD_VERSION = "dictionary-regex-v1"
CV_SUMMARY_METHOD = "heuristic-section-summary-v1"

SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "true").lower() in {"1", "true", "yes", "on"}


def ensure_directories() -> None:
    """Create runtime directories (private uploads, sample data, SQLite folder)."""
    for path in (DATA_DIR, UPLOAD_DIR, SAMPLE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def is_postgres() -> bool:
    return DATABASE_URL.startswith(("postgresql://", "postgresql+"))


def safe_database_label() -> str:
    if is_postgres():
        return "PostgreSQL"
    if DATABASE_URL.startswith("sqlite"):
        return "SQLite (chế độ demo)"
    return "CSDL không xác định"
