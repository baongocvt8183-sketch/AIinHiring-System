from __future__ import annotations

import pytest
from sqlalchemy import select

from src.auth.authentication import (
    AuthenticationError,
    authenticate,
    hash_password,
    set_active,
    verify_password,
)
from src.auth.permissions import (
    PermissionDenied,
    ResourceNotFound,
    can_view_pii,
    get_scoped_application,
    has_permission,
    mask_email,
    mask_name,
    mask_phone,
    role_names,
    scoped_job_ids,
    user_permissions,
)
from src.database.models import Application, User
from src.database.seed import DEMO_ACCOUNTS


def _user(session, username):
    return session.scalar(select(User).where(User.username == username))


def test_password_hashing_and_verification():
    hashed = hash_password("StrongPass123")
    assert hashed != "StrongPass123"
    assert verify_password("StrongPass123", hashed)
    assert not verify_password("wrong", hashed)
    with pytest.raises(AuthenticationError):
        hash_password("short")
    with pytest.raises(AuthenticationError):
        hash_password("x" * 80)


def test_demo_accounts_authenticate(demo_session):
    for account in DEMO_ACCOUNTS:
        user = authenticate(demo_session, account["username"], account["password"])
        assert user is not None, account["username"]
        assert user.username == account["username"]
    assert authenticate(demo_session, "hr", "wrong") is None
    assert authenticate(demo_session, "missing", "anything") is None


def test_inactive_user_cannot_authenticate(demo_session):
    user = _user(demo_session, "hr")
    set_active(demo_session, user, False)
    demo_session.commit()
    assert authenticate(demo_session, "hr", "Hr@12345") is None
    set_active(demo_session, user, True)
    demo_session.commit()


def test_role_permission_matrix(demo_session):
    hr = _user(demo_session, "hr")
    hm = _user(demo_session, "hiring")
    admin = _user(demo_session, "admin")
    auditor = _user(demo_session, "auditor")

    assert role_names(hr) == {"HR_MANAGER"}
    assert has_permission(hr, "review_ai")
    assert has_permission(hr, "import_data")
    assert not has_permission(hr, "manage_users")
    assert not has_permission(hr, "view_audit")
    assert has_permission(hr, "view_pii")

    assert has_permission(hm, "add_notes")
    assert has_permission(hm, "view_cv")
    assert not has_permission(hm, "review_ai")
    assert not has_permission(hm, "update_pipeline")
    assert not has_permission(hm, "import_data")
    assert not has_permission(hm, "view_pii")

    assert len(user_permissions(admin)) == len(user_permissions(hr)) + 2
    assert has_permission(auditor, "view_audit")
    assert not has_permission(auditor, "view_dashboard")
    assert not has_permission(auditor, "view_candidates")
    assert not has_permission(auditor, "view_pii")


def test_hiring_manager_job_scope(demo_session):
    hm = _user(demo_session, "hiring")
    hr = _user(demo_session, "hr")
    scope = scoped_job_ids(demo_session, hm)
    assert scope is not None and len(scope) == 2
    assert scoped_job_ids(demo_session, hr) is None

    ai_app = demo_session.scalar(select(Application).where(Application.job_id == scope[0]))
    backend_app = demo_session.scalar(
        select(Application).join(Application.job).where(Application.job.has(department="Engineering"))
    )
    assert get_scoped_application(demo_session, hm, ai_app.application_id) is not None
    with pytest.raises(PermissionDenied):
        get_scoped_application(demo_session, hm, backend_app.application_id)

    with pytest.raises(ResourceNotFound):
        get_scoped_application(demo_session, hr, 999999)


def test_pii_masking_and_permissions(demo_session):
    hr = _user(demo_session, "hr")
    hm = _user(demo_session, "hiring")
    assert can_view_pii(hr)
    assert not can_view_pii(hm)
    assert mask_email("an.nguyen@example.com") == "a********@example.com"
    assert mask_phone("0901234567") == "*******567"
    assert "***" in mask_name("Nguyễn Văn An")
