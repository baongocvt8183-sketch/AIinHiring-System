"""AI in Hiring — Streamlit entrypoint with role-based navigation."""

from __future__ import annotations

import streamlit as st

from src import config
from src.auth.permissions import has_permission
from src.constants import (
    PERM_IMPORT_DATA,
    PERM_MANAGE_USERS,
    PERM_VIEW_APPLICATIONS,
    PERM_VIEW_AUDIT,
    PERM_VIEW_CANDIDATES,
    PERM_VIEW_CV,
    PERM_VIEW_DASHBOARD,
)
from src.database.connection import new_session
from src.ui.common import (
    bootstrap_database,
    get_current_user,
    render_login_page,
    render_sidebar,
)

st.set_page_config(
    page_title=f"{config.APP_NAME} · Recruitment Data Warehouse",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

bootstrap_database()

db = new_session()
user = get_current_user(db)
db.close()

if user is None:
    navigation = st.navigation(
        [st.Page(render_login_page, title="Đăng nhập", icon="🔐")],
        position="hidden",
    )
    navigation.run()
    st.stop()

pages = []
if has_permission(user, PERM_VIEW_DASHBOARD):
    pages.append(st.Page("pages/1_Overview.py", title="Tổng quan", icon="📊", default=True))
if has_permission(user, PERM_IMPORT_DATA):
    pages.append(st.Page("pages/2_Data_Import.py", title="Nhập dữ liệu ETL", icon="📥"))
if has_permission(user, PERM_VIEW_APPLICATIONS):
    pages.append(st.Page("pages/3_Recruitment_Pipeline.py", title="Pipeline tuyển dụng", icon="🧭"))
if has_permission(user, PERM_VIEW_CV):
    pages.append(st.Page("pages/4_CV_Analysis.py", title="Phân tích CV", icon="📄"))
if has_permission(user, PERM_VIEW_CANDIDATES):
    pages.append(st.Page("pages/5_Candidate_Management.py", title="Quản lý ứng viên", icon="👥"))
if has_permission(user, PERM_MANAGE_USERS):
    pages.append(st.Page("pages/6_User_Management.py", title="Quản lý người dùng", icon="🔐"))
if has_permission(user, PERM_VIEW_AUDIT):
    pages.append(st.Page("pages/7_Audit_Logs.py", title="Audit log", icon="🧾"))

if not pages:  # defensive: should not happen for configured roles
    st.error("Tài khoản chưa được cấp quyền truy cập chức năng nào.")
    st.stop()

render_sidebar(user)
navigation = st.navigation(pages)
navigation.run()
