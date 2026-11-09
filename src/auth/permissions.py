"""Server-side RBAC checks and resource scoping.

UI hiding is never sufficient: every page calls these helpers before querying
or changing data. Default deny is applied when a permission is not explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants import (
    PERM_VIEW_PII,
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_HR,
    ROLE_HIRING,
    ROLE_PERMISSIONS,
)
from src.database.models import Application, User, UserJobAssignment


class PermissionDenied(Exception):
    """Raised when a backend permission/scope check fails."""

    def __init__(self, message: str = "Bạn không có quyền thực hiện thao tác này.", permission: str | None = None):
        super().__init__(message)
        self.permission = permission


class ResourceNotFound(Exception):
    pass


def role_names(user: User | None) -> set[str]:
    if user is None:
        return set()
    return {role.role_name for role in user.roles}


def user_permissions(user: User | None) -> set[str]:
    permissions: set[str] = set()
    if user is None or not user.is_active:
        return permissions
    for role in role_names(user):
        permissions.update(ROLE_PERMISSIONS.get(role, frozenset()))
    return permissions


def has_permission(user: User | None, permission: str) -> bool:
    return permission in user_permissions(user)


def has_role(user: User | None, *roles: str) -> bool:
    return bool(role_names(user) & set(roles))


def require_permission(user: User | None, permission: str) -> None:
    if not has_permission(user, permission):
        raise PermissionDenied(permission=permission)


def require_roles(user: User | None, *roles: str) -> None:
    if not has_role(user, *roles):
        raise PermissionDenied("Bạn không có vai trò phù hợp để thực hiện thao tác này.")


def can_view_pii(user: User | None) -> bool:
    return has_permission(user, PERM_VIEW_PII)


def scoped_job_ids(session: Session, user: User | None) -> list[int] | None:
    """Return ``None`` for unrestricted access or a list of assigned job ids.

    HR Manager and Admin see the whole warehouse. Hiring Managers see only the
    jobs explicitly assigned to them. Any other role gets an empty scope.
    """
    if user is None:
        return []
    roles = role_names(user)
    if roles & {ROLE_ADMIN, ROLE_HR}:
        return None
    if ROLE_HIRING in roles:
        return list(
            session.scalars(
                select(UserJobAssignment.job_id).where(UserJobAssignment.user_id == user.user_id)
            )
        )
    return []


def can_access_job(session: Session, user: User | None, job_id: int) -> bool:
    scope = scoped_job_ids(session, user)
    return scope is None or job_id in scope


def get_scoped_application(
    session: Session,
    user: User | None,
    application_id: int,
    *,
    permission: str = "view_applications",
) -> Application:
    require_permission(user, permission)
    application = session.get(Application, application_id)
    if application is None:
        raise ResourceNotFound("Không tìm thấy hồ sơ ứng tuyển.")
    if not can_access_job(session, user, application.job_id):
        raise PermissionDenied("Hồ sơ nằm ngoài phạm vi vị trí bạn được giao.", permission=permission)
    return application


def scoped_application_ids(session: Session, user: User | None) -> list[int] | None:
    """Like :func:`scoped_job_ids`, but returns application ids."""
    require_permission(user, "view_applications")
    job_ids = scoped_job_ids(session, user)
    if job_ids is None:
        return None
    if not job_ids:
        return []
    return list(
        session.scalars(select(Application.application_id).where(Application.job_id.in_(job_ids)))
    )


def filter_jobs_for_user(session: Session, user: User | None, job_ids: Iterable[int] | None = None) -> list[int] | None:
    """Intersect requested job filters with the user's scope."""
    scope = scoped_job_ids(session, user)
    requested = list(job_ids) if job_ids else None
    if scope is None:
        return requested
    if requested is None:
        return scope
    return [job_id for job_id in requested if job_id in set(scope)]


def mask_email(email: str | None) -> str:
    if not email:
        return "—"
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    visible = local[:1] if local else ""
    return f"{visible}{'*' * max(len(local) - 1, 2)}@{domain}"


def mask_phone(phone: str | None) -> str:
    if not phone:
        return "—"
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits)
    return f"{'*' * (len(digits) - 3)}{digits[-3:]}"


def mask_name(name: str | None) -> str:
    if not name:
        return "—"
    parts = name.split()
    if len(parts) == 1:
        return parts[0][:1] + "***"
    return f"{parts[0]} {' '.join(p[:1] + '***' for p in parts[1:])}"


@dataclass(frozen=True)
class AccessContext:
    user_id: int
    roles: frozenset[str]
    permissions: frozenset[str]
    job_scope: tuple[int, ...] | None

    @property
    def unrestricted(self) -> bool:
        return self.job_scope is None

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def job_allowed(self, job_id: int) -> bool:
        return self.job_scope is None or job_id in self.job_scope


def access_context(session: Session, user: User) -> AccessContext:
    scope = scoped_job_ids(session, user)
    return AccessContext(
        user_id=user.user_id,
        roles=frozenset(role_names(user)),
        permissions=frozenset(user_permissions(user)),
        job_scope=None if scope is None else tuple(scope),
    )


__all__ = [
    "PermissionDenied",
    "ResourceNotFound",
    "AccessContext",
    "access_context",
    "can_access_job",
    "can_view_pii",
    "filter_jobs_for_user",
    "get_scoped_application",
    "has_permission",
    "has_role",
    "mask_email",
    "mask_name",
    "mask_phone",
    "require_permission",
    "require_roles",
    "role_names",
    "scoped_application_ids",
    "scoped_job_ids",
    "user_permissions",
]
