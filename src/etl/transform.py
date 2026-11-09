"""Transform stage: normalize names, emails, phones, dates and statuses."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

from src.constants import (
    APPLICATION_STATUSES,
    CANONICAL_ETL_COLUMNS,
    DEFAULT_STAGE_NAMES,
    STAGE_RESULT_ALIASES,
    STATUS_ALIASES,
)
from src.etl.extract import text_key

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_NORMALIZED_STATUS = {text_key(key): value for key, value in STATUS_ALIASES.items()}
_NORMALIZED_STAGE_RESULT = {text_key(key): value for key, value in STAGE_RESULT_ALIASES.items()}
_STAGE_ALIASES = {
    "cv": "CV Screening",
    "cv screening": "CV Screening",
    "sang loc cv": "CV Screening",
    "sang loc ho so": "CV Screening",
    "review cv": "CV Screening",
    "online test": "Online Test",
    "test": "Online Test",
    "bai test": "Online Test",
    "technical interview": "Technical Interview",
    "phong van ky thuat": "Technical Interview",
    "technical": "Technical Interview",
    "hr interview": "HR Interview",
    "phong van hr": "HR Interview",
    "hr": "HR Interview",
    "offer": "Offer",
    "de xuat": "Offer",
    "hired": "Hired",
    "tuyen dung": "Hired",
    "da tuyen": "Hired",
}


def normalize_name(value: object) -> str:
    """Collapse whitespace only; never change the meaning of a person's name."""
    return " ".join(str(value or "").split())


def normalize_email(value: object) -> str | None:
    email = str(value or "").strip().lower()
    if not email or email.lower() in {"nan", "none", "null"}:
        return None
    return email


def is_valid_email(email: str | None) -> bool:
    return bool(email) and bool(EMAIL_RE.match(email)) and len(email) <= 255


def normalize_phone(value: object) -> str | None:
    phone = str(value or "").strip()
    if not phone or phone.lower() in {"nan", "none", "null"}:
        return None
    has_plus = phone.startswith("+")
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    return f"+{digits}" if has_plus else digits


def normalize_status(value: object) -> str | None:
    key = text_key(value)
    if not key:
        return None
    return _NORMALIZED_STATUS.get(key)


def normalize_stage_result(value: object) -> str | None:
    key = text_key(value)
    if not key:
        return None
    return _NORMALIZED_STAGE_RESULT.get(key)


def normalize_stage(value: object, stage_names: Iterable[str] | None = None) -> str | None:
    """Map a source stage label to a configured stage name."""
    text = str(value or "").strip()
    if not text:
        return None
    names = list(stage_names or DEFAULT_STAGE_NAMES)
    direct = {text_key(name): name for name in names}
    key = text_key(text)
    if key in direct:
        return direct[key]
    alias = _STAGE_ALIASES.get(key)
    if alias and text_key(alias) in direct:
        return direct[text_key(alias)]
    # Prefix/contains fallback for labels like "Vòng CV Screening".
    for normalized_name, original_name in direct.items():
        if normalized_key_contains(key, normalized_name):
            return original_name
    return None


def normalized_key_contains(haystack: str, needle: str) -> bool:
    return haystack == needle or haystack.startswith(needle + " ") or haystack.endswith(" " + needle)


def parse_datetime(value: object) -> tuple[datetime | None, str | None]:
    """Parse many human date formats into a UTC-aware datetime."""
    if value is None:
        return None, None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, pd.Timestamp):
        parsed = value.to_pydatetime()
    else:
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "null", "nat"}:
            return None, None
        # Excel serial date (e.g. 45200) may arrive as text from read_excel(dtype=str).
        if re.fullmatch(r"\d{5}(\.\d+)?", text):
            try:
                parsed = pd.to_datetime(float(text), unit="D", origin="1899-12-30").to_pydatetime()
            except (ValueError, OverflowError):
                return None, "INVALID_DATE"
        else:
            dayfirst = "/" in text or "." in text
            try:
                stamp = pd.to_datetime(text, errors="coerce", dayfirst=dayfirst)
            except (ValueError, TypeError):
                return None, "INVALID_DATE"
            if pd.isna(stamp):
                return None, "INVALID_DATE"
            parsed = stamp.to_pydatetime()

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc), None
    return parsed.astimezone(timezone.utc), None


def split_skills(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return []
    return [part.strip() for part in re.split(r"[,;|\n]+", text) if part.strip()]


def canonicalize_dataframe(frame: pd.DataFrame, mapping: dict[str, str | None]) -> pd.DataFrame:
    """Apply a canonical mapping and guarantee all expected columns exist."""
    result = pd.DataFrame(index=frame.index)
    for target in CANONICAL_ETL_COLUMNS:
        source = mapping.get(target)
        if source and source in frame.columns:
            result[target] = frame[source]
        else:
            result[target] = ""
    return result


def transform_row(raw: dict, stage_names: Iterable[str] | None = None) -> dict:
    """Normalize one canonical row. Validation happens separately."""
    email = normalize_email(raw.get("email"))
    email_error = bool(email) and not is_valid_email(email)
    applied_at, date_error = parse_datetime(raw.get("applied_at"))
    status_raw = str(raw.get("current_status") or "").strip()
    status = normalize_status(status_raw)
    stage_raw = str(raw.get("stage") or "").strip()
    stage = normalize_stage(stage_raw, stage_names)

    return {
        "full_name": normalize_name(raw.get("full_name")),
        "email": email,
        "email_error": email_error,
        "phone": normalize_phone(raw.get("phone")),
        "job_title": normalize_name(raw.get("job_title")),
        "department": normalize_name(raw.get("department")),
        "source_name": normalize_name(raw.get("source_name")),
        "applied_at": applied_at,
        "date_error": date_error,
        "current_status": status or "IN_PROGRESS",
        "status_raw": status_raw,
        "status_recognized": status is not None or not status_raw,
        "stage": stage,
        "stage_raw": stage_raw,
        "stage_recognized": stage is not None or not stage_raw,
        "job_description": str(raw.get("job_description") or "").strip(),
        "job_skills": split_skills(raw.get("job_skills")),
    }


def is_valid_status(status: str | None) -> bool:
    return status in APPLICATION_STATUSES
