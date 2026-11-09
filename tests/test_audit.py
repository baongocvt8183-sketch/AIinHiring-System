from __future__ import annotations

from sqlalchemy import select

from src.audit.audit_logger import log_action, log_denied, log_login
from src.database.models import AuditLog


def test_audit_metadata_is_sanitized(clean_session):
    entry = log_action(
        clean_session,
        user_id=None,
        action="TEST_ACTION",
        resource_type="candidate",
        resource_id=42,
        metadata={
            "password": "Secret123",
            "email": "an@example.com",
            "review_note": "private",
            "safe": "ok",
            "rows": 3,
        },
    )
    clean_session.commit()
    stored = clean_session.get(AuditLog, entry.audit_id)
    assert stored.log_metadata["password"] == "[redacted]"
    assert stored.log_metadata["email"] == "[redacted]"
    assert stored.log_metadata["review_note"] == "[redacted]"
    assert stored.log_metadata["safe"] == "ok"
    assert stored.log_metadata["rows"] == 3
    assert stored.resource_id == "42"


def test_invalid_ip_never_breaks_audit_logging(clean_session):
    entry = log_action(
        clean_session,
        user_id=None,
        action="TEST_IP",
        ip_address="127.0.0.1:8520",
    )
    clean_session.commit()
    assert entry.ip_address is None


def test_login_and_denied_events(clean_session):
    login = log_login(clean_session, None, False, "unknown-user", ip_address="127.0.0.1")
    log_denied(clean_session, None, "manage_users", "page")
    clean_session.commit()
    assert login.ip_address == "127.0.0.1"
    logs = list(clean_session.scalars(select(AuditLog).order_by(AuditLog.audit_id)))
    actions = [log.action for log in logs]
    assert "LOGIN_FAILED" in actions
    assert "ACCESS_DENIED" in actions
    denied = next(log for log in logs if log.action == "ACCESS_DENIED")
    assert denied.result == "DENIED"
    assert denied.log_metadata["permission"] == "manage_users"
