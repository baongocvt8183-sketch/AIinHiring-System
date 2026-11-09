"""Candidate management with scoped lists, PII masking and archive."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.auth.permissions import (
    PermissionDenied,
    can_access_job,
    can_view_pii,
    has_permission,
    mask_email,
    mask_phone,
)
from src.constants import APPLICATION_STATUS_LABELS, PERM_MANAGE_CANDIDATES, PERM_VIEW_CANDIDATES
from src.database.queries import (
    archive_candidate,
    create_candidate,
    list_candidates,
    update_candidate,
)
from src.ui.common import format_datetime, page_header, page_setup

user, db = page_setup("Quản lý ứng viên", "👥", PERM_VIEW_CANDIDATES)
page_header(
    "Quản lý ứng viên",
    "Một ứng viên có thể có nhiều hồ sơ; dữ liệu nhận dạng được che theo quyền và phạm vi vị trí.",
    "👥",
)
can_manage = has_permission(user, PERM_MANAGE_CANDIDATES)
can_pii = can_view_pii(user)

try:
    with st.sidebar:
        st.markdown("### 🔎 Tìm ứng viên")
        search = st.text_input("Tên / email / điện thoại", key="cand_search")
        include_archived = False
        if can_manage:
            include_archived = st.checkbox("Bao gồm ứng viên đã lưu trữ", key="cand_archived")

    if can_manage:
        with st.expander("➕ Thêm ứng viên mới", expanded=False):
            with st.form("create_candidate_form", clear_on_submit=True):
                new_name = st.text_input("Họ tên *")
                new_email = st.text_input("Email")
                new_phone = st.text_input("Điện thoại")
                create_submit = st.form_submit_button("Tạo ứng viên")
            if create_submit:
                try:
                    candidate = create_candidate(
                        db,
                        user=user,
                        full_name=new_name,
                        email=new_email,
                        phone=new_phone,
                    )
                except (PermissionDenied, ValueError) as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Đã tạo ứng viên #{candidate.candidate_id}.")
                    st.rerun()

    candidates = list_candidates(db, user, search=search or None, include_archived=include_archived)
    if not candidates:
        st.info("Không có ứng viên phù hợp bộ lọc hoặc phạm vi quyền.")
        st.stop()

    visible_apps_by_candidate = {
        candidate.candidate_id: [app for app in candidate.applications if can_access_job(db, user, app.job_id)]
        for candidate in candidates
    }
    table = pd.DataFrame(
        [
            {
                "ID": candidate.candidate_id,
                "Họ tên": candidate.full_name,
                "Email": (candidate.email or "—") if can_pii else mask_email(candidate.email),
                "Điện thoại": (candidate.phone or "—") if can_pii else mask_phone(candidate.phone),
                "Số hồ sơ": len(visible_apps_by_candidate[candidate.candidate_id]),
                "Lưu trữ": "Có" if candidate.is_archived else "Không",
                "Cập nhật": format_datetime(candidate.updated_at),
            }
            for candidate in candidates
        ]
    )
    st.caption(f"{len(candidates)} ứng viên trong phạm vi được xem.")
    st.dataframe(table, hide_index=True, width="stretch", height=280)

    selected_id = st.selectbox(
        "Chọn ứng viên để xem chi tiết",
        [candidate.candidate_id for candidate in candidates],
        format_func=lambda candidate_id: next(
            f"#{candidate_id} · {candidate.full_name}" for candidate in candidates if candidate.candidate_id == candidate_id
        ),
        key="candidate_selected",
    )
    candidate = next(candidate for candidate in candidates if candidate.candidate_id == selected_id)

    st.divider()
    left, right = st.columns([2, 1])
    with left:
        st.subheader(f"👤 {candidate.full_name}")
        st.caption(
            f"Mã ứng viên #{candidate.candidate_id} · tạo {format_datetime(candidate.created_at)} · "
            f"cập nhật {format_datetime(candidate.updated_at)}"
        )
    applications = visible_apps_by_candidate.get(candidate.candidate_id, [])
    with right:
        st.metric("Số hồ sơ ứng tuyển", len(applications))
        if candidate.is_archived:
            st.warning("Ứng viên đang được lưu trữ.")

    contact = st.columns(2)
    contact[0].markdown(f"**Email:** {(candidate.email or '—') if can_pii else mask_email(candidate.email)}")
    contact[1].markdown(f"**Điện thoại:** {(candidate.phone or '—') if can_pii else mask_phone(candidate.phone)}")
    if not can_pii:
        st.caption("Thông tin liên hệ được che theo quyền. Chỉ HR/Admin được xem đầy đủ.")

    st.markdown("#### Hồ sơ ứng tuyển")
    if not applications:
        st.info("Không có hồ sơ trong phạm vi được xem.")
    else:
        app_table = pd.DataFrame(
            [
                {
                    "Mã": application.application_id,
                    "Vị trí": application.job.job_title,
                    "Phòng ban": application.job.department or "—",
                    "Vòng hiện tại": application.current_stage.stage_name if application.current_stage else "—",
                    "Trạng thái": APPLICATION_STATUS_LABELS.get(
                        application.current_status, application.current_status
                    ),
                    "Ngày ứng tuyển": format_datetime(application.applied_at),
                    "Nguồn": application.source_name or "—",
                }
                for application in applications
            ]
        )
        st.dataframe(app_table, hide_index=True, width="stretch")

    if can_manage:
        edit_tab, archive_tab = st.tabs(["✏️ Chỉnh sửa", "🗄️ Lưu trữ"])
        with edit_tab:
            with st.form("edit_candidate_form"):
                edit_name = st.text_input("Họ tên *", value=candidate.full_name)
                edit_email = st.text_input("Email", value=candidate.email or "")
                edit_phone = st.text_input("Điện thoại", value=candidate.phone or "")
                save = st.form_submit_button("Lưu thay đổi")
            if save:
                try:
                    update_candidate(
                        db,
                        user=user,
                        candidate=candidate,
                        full_name=edit_name,
                        email=edit_email,
                        phone=edit_phone,
                    )
                except (PermissionDenied, ValueError) as exc:
                    st.error(str(exc))
                else:
                    st.success("Đã cập nhật ứng viên và ghi audit log.")
                    st.rerun()
        with archive_tab:
            st.caption("Lưu trữ là thao tác mềm: dữ liệu và lịch sử vẫn được giữ để kiểm toán.")
            if candidate.is_archived:
                if st.button("♻️ Khôi phục ứng viên"):
                    archive_candidate(db, user=user, candidate=candidate, archived=False)
                    st.success("Đã khôi phục ứng viên.")
                    st.rerun()
            else:
                confirm = st.checkbox("Tôi hiểu ứng viên sẽ bị ẩn khỏi danh sách mặc định.", key="confirm_archive")
                if st.button("🗄️ Lưu trữ ứng viên", disabled=not confirm):
                    archive_candidate(db, user=user, candidate=candidate, archived=True)
                    st.success("Đã lưu trữ ứng viên.")
                    st.rerun()
finally:
    db.close()
