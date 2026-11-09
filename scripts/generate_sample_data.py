"""Regenerate the fictional CSV/Excel sample files and CV PDFs."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.sample_data import write_sample_files  # noqa: E402


def main() -> int:
    paths = write_sample_files(force=True)
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
