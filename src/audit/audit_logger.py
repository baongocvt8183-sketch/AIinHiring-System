"""Immutable audit logging with minimal, non-sensitive metadata."""

from __future__ import annotations

import ipaddress
import logging
from typing import Any, Mapping

from sqlalchemy.orm import Session

from src.database.models import AuditLog

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "secret",
    "cv_text",
    "extracted_text",
    "email",
    "phone",
    "review_note",
}


def _sanitize(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if key.lower() in SENSITIVE_KEYS:
            clean[key] = "[redacted]"
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            # Keep individual values short; audit logs never store full documents.
            clean[key] = value[:300] if isinstance(value, str) else value
        elif isinstance(value, (list, tuple)):
            clean[key] = [item[:100] if isinstance(item, str) else item for item in value[:20]]
        else:
            clean[key] = str(value)[:300]
    return clean


def _safe_ip(value: str | None) -> str | None:
    """Return a valid IP address, or None.

    PostgreSQL's INET type rejects host:port strings and arbitrary proxy
    headers. Audit logging must never break authentication or a business
    action, so invalid values are simply omitted.
    """
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        return None


def log_action(
    session: Session,
    *,
    user_id: int | None,
    action: str,
    result: str = "SUCCESS",
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    ip_address: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action[:100],
        resource_type=(resource_type or "")[:100] or None,
        resource_id=str(resource_id)[:100] if resource_id is not None else None,
        result=result,
        ip_address=_safe_ip(ip_address),
        log_metadata=_sanitize(metadata),
    )
    session.add(entry)
    session.flush()
    return entry


def safe_log_action(session: Session, **kwargs: Any) -> None:
    """Best-effort audit logging that never breaks the user-facing action."""
    try:
        log_action(session, **kwargs)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Unable to write audit log for action=%s", kwargs.get("action"))


def log_login(
    session: Session,
    user_id: int | None,
    success: bool,
    username: str,
    ip_address: str | None = None,
) -> AuditLog:
    return log_action(
        session,
        user_id=user_id,
        action="LOGIN_SUCCESS" if success else "LOGIN_FAILED",
        result="SUCCESS" if success else "FAILURE",
        resource_type="session",
        ip_address=ip_address,
        metadata={"username_attempt": username[:100]},
    )


def log_denied(session: Session, user_id: int | None, permission: str, resource_type: str, resource_id: Any = None) -> None:
    safe_log_action(
        session,
        user_id=user_id,
        action="ACCESS_DENIED",
        result="DENIED",
        resource_type=resource_type,
        resource_id=resource_id,
        metadata={"permission": permission},
    )
