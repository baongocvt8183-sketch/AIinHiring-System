"""User administration: accounts, roles and Hiring Manager job scopes."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from src.audit.audit_logger import safe_log_action
from src.auth.authentication import (
    AuthenticationError,
    create_user,
    set_active,
    set_password,
    set_roles,
)
from src.auth.permissions import PermissionDenied, role_names
from src.constants import PERM_MANAGE_USERS, ROLE_LABELS
from src.database.models import Role, User, UserJobAssignment
from src.database.queries import list_jobs
from src.ui.common import format_datetime, page_header, page_setup

user, db = page_setup("Quản lý người dùng", "🔐", PERM_MANAGE_USERS)
page_header(
    "Quản lý người dùng & phân quyền",
    "Tài khoản, vai trò và phạm vi vị trí của Hiring Manager. Mọi thay đổi đều ghi audit log.",
    "🔐",
)

try:
    roles = list(db.scalars(select(Role).order_by(Role.role_name)))
    role_options = [role.role_name for role in roles]
    all_jobs = list_jobs(db, user)
    jobs_by_id = {job.job_id: job for job in all_jobs}
    users = list(db.scalars(select(User).order_by(User.created_at.desc())))

    with st.expander("➕ Tạo tài khoản", expanded=False):
        with st.form("create_user_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            username = col1.text_input("Tên đăng nhập *")
            email = col2.text_input("Email *")
            full_name = st.text_input("Họ tên *")
            password = st.text_input("Mật khẩu * (tối thiểu 8 ký tự)", type="password")
            selected_roles = st.multiselect(
                "Vai trò *",
                role_options,
                format_func=lambda value: ROLE_LABELS.get(value, value),
            )
            selected_jobs = st.multiselect(
                "Phạm vi vị trí (dành cho Hiring Manager)",
                list(jobs_by_id),
                format_func=lambda job_id: f"{jobs_by_id[job_id].job_title} · {jobs_by_id[job_id].department or '—'}",
            )
            create_submit = st.form_submit_button("Tạo tài khoản", type="primary")
        if create_submit:
            try:
                new_user = create_user(
                    db,
                    username=username,
                    email=email,
                    full_name=full_name,
                    password=password,
                    role_names=selected_roles,
                    assigned_by=user.user_id,
                )
                for job_id in selected_jobs:
                    db.add(
                        UserJobAssignment(
                            user_id=new_user.user_id,
                            job_id=job_id,
                            assigned_by=user.user_id,
                        )
                    )
                safe_log_action(
                    db,
                    user_id=user.user_id,
                    action="USER_CREATE",
                    resource_type="user",
                    resource_id=new_user.user_id,
                    metadata={"roles": selected_roles, "job_ids": selected_jobs},
                )
                db.commit()
            except (AuthenticationError, PermissionDenied, ValueError) as exc:
                db.rollback()
                st.error(str(exc))
            else:
                st.success(f"Đã tạo tài khoản {username}.")
                st.rerun()

    table = pd.DataFrame(
        [
            {
                "ID": account.user_id,
                "Tên đăng nhập": account.username,
                "Họ tên": account.full_name,
                "Email": account.email,
                "Vai trò": ", ".join(ROLE_LABELS.get(role, role) for role in sorted(role_names(account))),
                "Vị trí được giao": len(account.job_assignments),
                "Hoạt động": "Có" if account.is_active else "Không",
                "Tạo lúc": format_datetime(account.created_at),
            }
            for account in users
        ]
    )
    st.subheader("Danh sách tài khoản")
    st.dataframe(table, hide_index=True, width="stretch")

    selected_id = st.selectbox(
        "Chọn tài khoản để quản lý",
        [account.user_id for account in users],
        format_func=lambda user_id: next(
            f"#{user_id} · {account.username} · {account.full_name}"
            for account in users
            if account.user_id == user_id
        ),
        key="user_selected",
    )
    account = next(account for account in users if account.user_id == selected_id)
    is_self = account.user_id == user.user_id

    st.divider()
    st.subheader(f"🔐 {account.username} — {account.full_name}")
    st.caption(f"Email: {account.email} · tạo {format_datetime(account.created_at)} · cập nhật {format_datetime(account.updated_at)}")

    col_roles, col_jobs = st.columns(2, gap="large")
    with col_roles:
        st.markdown("#### Vai trò")
        with st.form("user_roles_form"):
            new_roles = st.multiselect(
                "Vai trò",
                role_options,
                default=sorted(role_names(account)),
                format_func=lambda value: ROLE_LABELS.get(value, value),
                disabled=is_self,
            )
            save_roles = st.form_submit_button("Lưu vai trò", disabled=is_self)
        if save_roles:
            try:
                set_roles(db, account, new_roles, assigned_by=user.user_id)
                safe_log_action(
                    db,
                    user_id=user.user_id,
                    action="USER_ROLE_CHANGE",
                    resource_type="user",
                    resource_id=account.user_id,
                    metadata={"roles": new_roles},
                )
                db.commit()
            except (AuthenticationError, PermissionDenied, ValueError) as exc:
                db.rollback()
                st.error(str(exc))
            else:
                st.success("Đã cập nhật vai trò.")
                st.rerun()
        if is_self:
            st.caption("Không thể tự thay đổi vai trò/trạng thái của chính mình (tránh tự khóa quyền quản trị).")

    with col_jobs:
        st.markdown("#### Phạm vi vị trí")
        assigned_ids = [assignment.job_id for assignment in account.job_assignments if assignment.job_id in jobs_by_id]
        with st.form("user_jobs_form"):
            new_jobs = st.multiselect(
                "Vị trí được giao",
                list(jobs_by_id),
                default=assigned_ids,
                format_func=lambda job_id: f"{jobs_by_id[job_id].job_title} · {jobs_by_id[job_id].department or '—'}",
            )
            save_jobs = st.form_submit_button("Lưu phạm vi")
        if save_jobs:
            current = {assignment.job_id: assignment for assignment in account.job_assignments}
            for job_id in new_jobs:
                if job_id not in current:
                    db.add(UserJobAssignment(user_id=account.user_id, job_id=job_id, assigned_by=user.user_id))
            for job_id, assignment in current.items():
                if job_id not in new_jobs:
                    db.delete(assignment)
            safe_log_action(
                db,
                user_id=user.user_id,
                action="USER_JOB_SCOPE_CHANGE",
                resource_type="user",
                resource_id=account.user_id,
                metadata={"job_ids": new_jobs},
            )
            db.commit()
            st.success("Đã cập nhật phạm vi vị trí.")
            st.rerun()

    col_status, col_password = st.columns(2, gap="large")
    with col_status:
        st.markdown("#### Trạng thái tài khoản")
        if account.is_active:
            if st.button("🚫 Vô hiệu hóa tài khoản", disabled=is_self):
                set_active(db, account, False)
                safe_log_action(
                    db,
                    user_id=user.user_id,
                    action="USER_DEACTIVATE",
                    resource_type="user",
                    resource_id=account.user_id,
                )
                db.commit()
                st.success("Đã vô hiệu hóa tài khoản.")
                st.rerun()
        else:
            if st.button("✅ Kích hoạt tài khoản"):
                set_active(db, account, True)
                safe_log_action(
                    db,
                    user_id=user.user_id,
                    action="USER_ACTIVATE",
                    resource_type="user",
                    resource_id=account.user_id,
                )
                db.commit()
                st.success("Đã kích hoạt tài khoản.")
                st.rerun()

    with col_password:
        st.markdown("#### Đặt lại mật khẩu")
        with st.form("reset_password_form", clear_on_submit=True):
            new_password = st.text_input("Mật khẩu mới (tối thiểu 8 ký tự)", type="password")
            reset_submit = st.form_submit_button("Đặt lại mật khẩu")
        if reset_submit:
            try:
                set_password(db, account, new_password)
                safe_log_action(
                    db,
                    user_id=user.user_id,
                    action="USER_PASSWORD_RESET",
                    resource_type="user",
                    resource_id=account.user_id,
                )
                db.commit()
            except (AuthenticationError, ValueError) as exc:
                db.rollback()
                st.error(str(exc))
            else:
                st.success("Đã đặt lại mật khẩu. Không có mật khẩu nào được ghi vào log.")
finally:
    db.close()
