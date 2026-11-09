"""Create the database schema and seed consistent demo data.

Usage:
    python scripts/init_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.database.connection import healthcheck, init_db  # noqa: E402
from src.database.seed import DEMO_ACCOUNTS  # noqa: E402


def main() -> int:
    config.ensure_directories()
    print(f"Database: {config.DATABASE_URL}")
    init_db(seed=True)
    ok, message = healthcheck()
    if not ok:
        print(f"Database healthcheck FAILED: {message}")
        return 1
    print(f"Database ready: {message}")
    print("Demo accounts (change passwords in any real deployment):")
    for account in DEMO_ACCOUNTS:
        print(f"  - {account['username']:<8} / {account['password']:<14} ({account['role']})")
    print("Run the app with: streamlit run app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
