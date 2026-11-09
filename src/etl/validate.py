"""Validate stage: reject bad rows with explicit, auditable reasons."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.constants import CANONICAL_ETL_COLUMNS, REQUIRED_ETL_COLUMNS
from src.etl.extract import text_key
from src.etl.transform import is_valid_email


def validate_mapping(mapping: dict[str, str | None]) -> list[dict]:
    errors: list[dict] = []
    for required in REQUIRED_ETL_COLUMNS:
        if not mapping.get(required):
            errors.append(
                {
                    "code": "MISSING_REQUIRED_COLUMN",
                    "field": required,
                    "message": f"Thiếu cột bắt buộc: {required}",
                }
            )
    return errors


def validate_row(row: dict, *, now: datetime | None = None) -> list[dict]:
    """Return a list of {code, field, message}; an empty list means valid."""
    now = now or datetime.now(timezone.utc)
    errors: list[dict] = []

    def add(code: str, field: str, message: str) -> None:
        errors.append({"code": code, "field": field, "message": message})

    full_name = row.get("full_name") or ""
    if not full_name:
        add("REQUIRED_FIELD", "full_name", "Họ tên không được để trống.")
    elif len(full_name) > 200:
        add("FIELD_TOO_LONG", "full_name", "Họ tên vượt quá 200 ký tự.")

    job_title = row.get("job_title") or ""
    if not job_title:
        add("REQUIRED_FIELD", "job_title", "Vị trí tuyển dụng không được để trống.")
    elif len(job_title) > 200:
        add("FIELD_TOO_LONG", "job_title", "Tên vị trí vượt quá 200 ký tự.")

    if row.get("email_error"):
        add("INVALID_EMAIL", "email", "Email không đúng định dạng.")
    elif row.get("email") and not is_valid_email(row.get("email")):
        add("INVALID_EMAIL", "email", "Email không đúng định dạng.")

    if row.get("date_error"):
        add("INVALID_DATE", "applied_at", "Ngày ứng tuyển không hợp lệ.")
    else:
        applied_at = row.get("applied_at")
        if applied_at and applied_at > now + timedelta(days=1):
            add("INVALID_DATE", "applied_at", "Ngày ứng tuyển nằm trong tương lai.")
        if applied_at and applied_at.year < 2000:
            add("INVALID_DATE", "applied_at", "Ngày ứng tuyển quá cũ (trước năm 2000).")

    if not row.get("status_recognized", True):
        add("INVALID_STATUS", "current_status", f"Trạng thái không hợp lệ: {row.get('status_raw')!r}")

    if not row.get("stage_recognized", True):
        add("INVALID_STAGE", "stage", f"Vòng tuyển không hợp lệ: {row.get('stage_raw')!r}")

    department = row.get("department") or ""
    if len(department) > 150:
        add("FIELD_TOO_LONG", "department", "Phòng ban vượt quá 150 ký tự.")

    source = row.get("source_name") or ""
    if len(source) > 100:
        add("FIELD_TOO_LONG", "source_name", "Nguồn tuyển dụng vượt quá 100 ký tự.")

    if row.get("phone") and len(row["phone"]) > 50:
        add("FIELD_TOO_LONG", "phone", "Số điện thoại vượt quá 50 ký tự.")

    return errors


def validate_headers(columns: list[str]) -> list[dict]:
    if not columns:
        return [{"code": "NO_COLUMNS", "field": None, "message": "Tệp không có cột dữ liệu."}]
    duplicate_keys: set[str] = set()
    seen: set[str] = set()
    for column in columns:
        key = text_key(column)
        if key in seen:
            duplicate_keys.add(column)
        seen.add(key)
    return [
        {"code": "DUPLICATE_COLUMN", "field": column, "message": f"Cột bị trùng: {column}"}
        for column in sorted(duplicate_keys)
    ]


def validate_canonical_row_keys(row: dict) -> None:
    missing = [column for column in CANONICAL_ETL_COLUMNS if column not in row]
    if missing:  # defensive programming; canonicalization guarantees these
        raise ValueError(f"Row missing canonical columns: {missing}")
