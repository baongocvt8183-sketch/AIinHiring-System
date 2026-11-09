"""Shared Streamlit UI helpers: bootstrap, authentication and layout."""

from __future__ import annotations

import ipaddress
from datetime import date, datetime, timezone

import streamlit as st

from src import config
from src.audit.audit_logger import log_denied, log_login, safe_log_action
from src.auth.authentication import authenticate
from src.auth.permissions import (
    PermissionDenied,
    has_permission,
    role_names,
    user_permissions,
)
from src.constants import ROLE_LABELS
from src.database.connection import init_db, new_session
from src.database.models import User
from src.database.seed import DEMO_ACCOUNTS

CSS = """
<style>
    .block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .app-hero {
        background: linear-gradient(120deg, #0f2b46 0%, #145374 55%, #1d7a8c 100%);
        color: white; border-radius: 18px; padding: 1.6rem 1.9rem; margin-bottom: 1.2rem;
        box-shadow: 0 8px 24px rgba(15, 43, 70, .18);
    }
    .app-hero h1 {color: #fff; margin: 0 0 .35rem 0; font-size: 1.9rem; letter-spacing: -.02em;}
    .app-hero p {color: #d9ecf5; margin: 0; font-size: 1rem;}
    .page-title {margin-bottom: .15rem;}
    .muted {color: #64748b; font-size: .9rem;}
    .role-chip {
        display: inline-block; background: #e8f1f7; color: #145374; border-radius: 999px;
        padding: .12rem .6rem; margin: .1rem .2rem .1rem 0; font-size: .75rem; font-weight: 600;
    }
    .status-chip {
        display: inline-block; border-radius: 999px; padding: .15rem .65rem;
        font-size: .78rem; font-weight: 600; background: #eef2f7; color: #334155;
    }
    .demo-card {background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1rem 1.2rem;}
    div[data-testid="stMetric"] {
        background: #ffffff; border: 1px solid #e5eaf0; border-radius: 12px;
        padding: .65rem .9rem; box-shadow: 0 2px 8px rgba(15,23,42,.04);
    }
    div[data-testid="stMetricLabel"] {font-size: .82rem;}
    div[data-testid="stMetricValue"] {font-size: 1.55rem;}
    .stAlert {border-radius: 10px;}
</style>
"""


@st.cache_resource(show_spinner=False)
def bootstrap_database() -> bool:
    """Create/seed the database once per Streamlit process."""
    try:
        init_db(seed=True)
        return True
    except Exception as exc:  # pragma: no cover - shown in UI
        st.error(f"Không khởi tạo được cơ sở dữ liệu: {exc}")
        st.stop()
        return False


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def get_current_user(session) -> User | None:
    user_id = st.session_state.get("user_id")
    if not user_id:
        return None
    user = session.get(User, int(user_id))
    if user is None or not user.is_active:
        st.session_state.pop("user_id", None)
        return None
    return user


def login(username: str, password: str) -> bool:
    db = new_session()
    try:
        user = authenticate(db, username, password)
        log_login(
            db,
            user_id=user.user_id if user else None,
            success=user is not None,
            username=username,
            ip_address=_client_ip(),
        )
        db.commit()
        if user is None:
            return False
        st.session_state["user_id"] = user.user_id
        st.session_state["login_at"] = datetime.now(timezone.utc).isoformat()
        return True
    finally:
        db.close()


def logout() -> None:
    db = new_session()
    try:
        user_id = st.session_state.get("user_id")
        if user_id:
            safe_log_action(
                db,
                user_id=int(user_id),
                action="LOGOUT",
                resource_type="session",
                result="SUCCESS",
            )
            db.commit()
    finally:
        db.close()
    st.session_state.clear()
    st.rerun()


def _client_ip() -> str | None:
    try:
        headers = getattr(st.context, "headers", {}) or {}
        forwarded = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
        raw = forwarded.split(",")[0].strip() if forwarded else headers.get("Remote-Addr") or headers.get("remote-addr")
        if not raw:
            return None
        # Some proxies append a port; INET columns require a bare address.
        if raw.startswith("[") and "]" in raw:
            raw = raw[1 : raw.index("]")]
        elif raw.count(":") == 1:
            raw = raw.rsplit(":", 1)[0]
        return str(ipaddress.ip_address(raw.strip()))
    except (ValueError, AttributeError):  # pragma: no cover - Streamlit version dependent
        return None


def require_user(permission: str | None = None) -> tuple[User, object]:
    """Return (user, db_session) or stop with a backend-enforced denial."""
    db = new_session()
    user = get_current_user(db)
    if user is None:
        db.close()
        st.error("Phiên đăng nhập không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại.")
        st.stop()
    if permission and not has_permission(user, permission):
        log_denied(db, user.user_id, permission, "page")
        try:
            db.commit()
        except Exception:
            db.rollback()
        db.close()
        st.error("⛔ Bạn không có quyền truy cập chức năng này. Hành động đã được ghi nhật ký.")
        st.stop()
    return user, db


def page_setup(title: str, icon: str = "📄", permission: str | None = None) -> tuple[User, object]:
    inject_css()
    user, db = require_user(permission)
    st.markdown(f"## {icon} {title}")
    return user, db


def page_header(title: str, subtitle: str, icon: str = "📊") -> None:
    st.markdown(
        f'<div class="app-hero"><h1>{icon} {title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def render_sidebar(user: User) -> None:
    with st.sidebar:
        st.markdown("### 🧭 AI in Hiring")
        st.markdown(f"**{user.full_name}**")
        chips = " ".join(
            f'<span class="role-chip">{ROLE_LABELS.get(name, name)}</span>' for name in sorted(role_names(user))
        )
        st.markdown(chips, unsafe_allow_html=True)
        st.caption(f"CSDL: {config.safe_database_label()} · v{config.APP_VERSION}")
        st.divider()
        if st.button("🚪 Đăng xuất", width="stretch"):
            logout()
        st.divider()
        st.caption("AI chỉ hỗ trợ tham khảo. Quyết định tuyển dụng cần HR kiểm duyệt.")


def render_login_page() -> None:
    inject_css()
    st.markdown(
        """
        <div class="app-hero">
            <h1>🤖 AI in Hiring System</h1>
            <p>Kho dữ liệu tuyển dụng · ETL · Dashboard pipeline · Phân tích CV · RBAC &amp; Audit</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.05, 0.95], gap="large")
    with left:
        st.subheader("Đăng nhập")
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Tên đăng nhập hoặc email", placeholder="hr")
            password = st.text_input("Mật khẩu", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Đăng nhập", type="primary", width="stretch")
        if submitted:
            if not username or not password:
                st.warning("Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu.")
            elif login(username, password):
                st.success("Đăng nhập thành công.")
                st.rerun()
            else:
                st.error("Sai thông tin đăng nhập hoặc tài khoản đã bị khóa. Sự kiện đã được ghi nhật ký.")

        st.caption("Tài khoản demo chỉ dùng cho môi trường học tập. Mật khẩu được băm bằng bcrypt.")

    with right:
        st.subheader("Tài khoản demo")
        st.dataframe(
            [
                {
                    "Vai trò": ROLE_LABELS.get(account["role"], account["role"]),
                    "Tên đăng nhập": account["username"],
                    "Mật khẩu": account["password"],
                }
                for account in DEMO_ACCOUNTS
            ],
            hide_index=True,
            width="stretch",
        )
        st.markdown(
            """
            <div class="demo-card">
            <b>Luồng demo gợi ý</b><br/>
            1. <b>HR</b> nhập CSV/Excel, xem log ETL.<br/>
            2. Mở dashboard KPI &amp; funnel.<br/>
            3. Tải CV PDF, chạy phân tích kỹ năng và duyệt kết quả AI.<br/>
            4. Đăng nhập <b>Hiring Manager</b> để thấy phạm vi bị giới hạn.<br/>
            5. Đăng nhập <b>Auditor/Admin</b> để xem audit log.
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.divider()
    st.caption(
        "Dữ liệu demo là giả lập. Không đưa thông tin cá nhân thật vào môi trường thử nghiệm. "
        "CV được lưu trong vùng riêng tư và không gửi ra dịch vụ AI bên ngoài."
    )


def format_datetime(value: datetime | None, fallback: str = "—") -> str:
    if not value:
        return fallback
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime("%d/%m/%Y %H:%M")


def format_date(value: datetime | date | None, fallback: str = "—") -> str:
    if not value:
        return fallback
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    return value.strftime("%d/%m/%Y")


def format_days(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f} ngày"


def handle_permission_error(db, user: User, exc: PermissionDenied, *, resource_type: str = "page") -> None:
    log_denied(db, user.user_id, exc.permission or "unknown", resource_type)
    try:
        db.commit()
    except Exception:
        db.rollback()
    st.error("⛔ Bạn không có quyền thực hiện thao tác này hoặc tài nguyên nằm ngoài phạm vi được giao.")


def mask_or_value(value: str | None, can_view_pii: bool, masker) -> str:
    if can_view_pii:
        return value or "—"
    return masker(value)


def sidebar_permissions(user: User) -> set[str]:
    return user_permissions(user)
