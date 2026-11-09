"""Password hashing, authentication and user provisioning."""

from __future__ import annotations

from datetime import datetime, timezone

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.database.models import Role, User, UserRole
from src.constants import ROLE_ADMIN, ROLE_HR, ROLE_HIRING, ROLE_AUDITOR


MIN_PASSWORD_LENGTH = 8
MAX_BCRYPT_BYTES = 72


class AuthenticationError(ValueError):
    pass


def hash_password(password: str) -> str:
    """Hash a password with bcrypt. Plain passwords are never stored or logged."""
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise AuthenticationError(f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự.")
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_BCRYPT_BYTES:
        raise AuthenticationError("Mật khẩu quá dài (tối đa 72 byte khi dùng bcrypt).")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def authenticate(session: Session, username: str, password: str) -> User | None:
    """Return the active user matching ``username`` (or email) and password."""
    identifier = (username or "").strip().lower()
    if not identifier or not password:
        return None

    user = session.scalar(
        select(User).where(
            (func.lower(User.username) == identifier) | (func.lower(User.email) == identifier)
        )
    )
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def create_user(
    session: Session,
    *,
    username: str,
    email: str,
    full_name: str,
    password: str,
    role_names: list[str] | tuple[str, ...],
    assigned_by: int | None = None,
    is_active: bool = True,
) -> User:
    username = (username or "").strip()
    email = (email or "").strip().lower()
    full_name = " ".join((full_name or "").split())

    if not username or len(username) > 100:
        raise AuthenticationError("Tên đăng nhập không hợp lệ.")
    if not email or "@" not in email:
        raise AuthenticationError("Email không hợp lệ.")
    if not full_name:
        raise AuthenticationError("Họ tên không được để trống.")
    if session.scalar(select(User).where(func.lower(User.username) == username.lower())):
        raise AuthenticationError("Tên đăng nhập đã tồn tại.")
    if session.scalar(select(User).where(func.lower(User.email) == email)):
        raise AuthenticationError("Email đã được sử dụng.")

    roles = list(session.scalars(select(Role).where(Role.role_name.in_(list(role_names)))))
    if not roles:
        raise AuthenticationError("Cần chọn ít nhất một vai trò hợp lệ.")

    user = User(
        username=username,
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
        is_active=is_active,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()

    for role in roles:
        session.add(
            UserRole(
                user_id=user.user_id,
                role_id=role.role_id,
                assigned_by=assigned_by,
            )
        )
    session.flush()
    session.refresh(user)
    return user


def set_password(session: Session, user: User, new_password: str) -> None:
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.now(timezone.utc)
    session.flush()


def set_active(session: Session, user: User, active: bool) -> None:
    user.is_active = bool(active)
    user.updated_at = datetime.now(timezone.utc)
    session.flush()


def set_roles(
    session: Session,
    user: User,
    role_names: list[str] | tuple[str, ...],
    assigned_by: int | None = None,
) -> None:
    desired = set(role_names)
    roles = list(session.scalars(select(Role).where(Role.role_name.in_(desired))))
    if len(roles) != len(desired):
        raise AuthenticationError("Có vai trò không hợp lệ.")

    current = {role.role_name: role for role in user.roles}
    for role_name in desired - set(current):
        role = next(r for r in roles if r.role_name == role_name)
        session.add(UserRole(user_id=user.user_id, role_id=role.role_id, assigned_by=assigned_by))
    for role_name in set(current) - desired:
        link = session.get(UserRole, {"user_id": user.user_id, "role_id": current[role_name].role_id})
        if link:
            session.delete(link)
    session.flush()
    session.expire(user, ["roles"])
    session.refresh(user)


def role_names_for_user(user: User) -> list[str]:
    return sorted(role.role_name for role in user.roles)


DEMO_ROLES = (ROLE_HR, ROLE_HIRING, ROLE_ADMIN, ROLE_AUDITOR)
