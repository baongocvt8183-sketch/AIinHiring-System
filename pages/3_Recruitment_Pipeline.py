"""Recruitment pipeline: scoped list, stage history, transitions and notes."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from src.analytics.kpi import load_stages
from src.audit.audit_logger import safe_log_action
from src.auth.permissions import (
    PermissionDenied,
    can_view_pii,
    has_permission,
    mask_email,
    mask_phone,
)
from src.constants import (
    APPLICATION_STATUS_LABELS,
    APPLICATION_STATUSES,
    NOTE_TYPE_LABELS,
    NOTE_TYPES,
    PERM_ADD_NOTES,
    PERM_UPDATE_PIPELINE,
    PERM_VIEW_APPLICATIONS,
    PERM_VIEW_AI_RESULT,
    STAGE_RESULT_LABELS,
    STAGE_RESULTS,
    REVIEW_STATUS_LABELS,
)
from src.database.queries import (
    add_application_note,
    analyses_for_application,
    application_notes,
    list_applications,
    list_jobs,
    list_stages,
    stage_history,
    update_application,
)
from src.ui.common import format_datetime, page_header, page_setup


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _duration_days(entered, exited) -> str:
    entered = _aware(entered)
    exited = _aware(exited) or datetime.now(timezone.utc)
    if entered is None:
        return "—"
    return f"{max((exited - entered).total_seconds() / 86400, 0):.2f}"


user, db = page_setup("Pipeline tuyển dụng", "🧭", PERM_VIEW_APPLICATIONS)
page_header(
    "Pipeline tuyển dụng",
    "Theo dõi hồ sơ theo vòng, cập nhật trạng thái và lưu nhận xét có kiểm soát quyền.",
    "🧭",
)

try:
    jobs = list_jobs(db, user)
    stages = list_stages(db)
    job_by_id = {job.job_id: job for job in jobs}
    stage_by_id = {stage.stage_id: stage for stage in stages}

    with st.sidebar:
        st.markdown("### 🔎 Lọc hồ sơ")
        job_options = [job.job_id for job in jobs]
        selected_jobs = st.multiselect(
            "Vị trí",
            job_options,
            format_func=lambda job_id: f"{job_by_id[job_id].job_title} · {job_by_id[job_id].department or '—'}",
            key="pipe_jobs",
        )
        status_options = st.multiselect(
            "Trạng thái",
            APPLICATION_STATUSES,
            format_func=lambda value: APPLICATION_STATUS_LABELS.get(value, value),
            key="pipe_statuses",
        )
        stage_options = st.multiselect(
            "Vòng hiện tại",
            [stage.stage_id for stage in stages],
            format_func=lambda stage_id: stage_by_id[stage_id].stage_name,
            key="pipe_stages",
        )
        search = st.text_input("Tìm tên / email / vị trí", key="pipe_search")

    applications = list_applications(
        db,
        user,
        job_ids=selected_jobs or None,
        statuses=status_options or None,
        stage_ids=stage_options or None,
        search=search or None,
    )

    if not applications:
        st.info("Không có hồ sơ phù hợp bộ lọc hoặc phạm vi quyền của bạn.")
        st.stop()

    table = pd.DataFrame(
        [
            {
                "ID": application.application_id,
                "Ứng viên": application.candidate.full_name,
                "Vị trí": application.job.job_title,
                "Phòng ban": application.job.department or "—",
                "Vòng hiện tại": application.current_stage.stage_name if application.current_stage else "—",
                "Trạng thái": APPLICATION_STATUS_LABELS.get(application.current_status, application.current_status),
                "Ngày ứng tuyển": application.applied_at.strftime("%d/%m/%Y"),
                "Nguồn": application.source_name or "—",
            }
            for application in applications
        ]
    )
    st.caption(f"{len(applications)} hồ sơ trong phạm vi được phép xem.")
    st.dataframe(table, hide_index=True, width="stretch", height=280)

    options = [application.application_id for application in applications]
    selected_id = st.selectbox(
        "Chọn hồ sơ để xem chi tiết",
        options,
        format_func=lambda app_id: next(
            f"#{application.application_id} · {application.candidate.full_name} · {application.job.job_title}"
            for application in applications
            if application.application_id == app_id
        ),
        key="pipeline_selected_app",
    )
    application = next(app for app in applications if app.application_id == selected_id)

    st.divider()
    header_left, header_right = st.columns([2, 1])
    with header_left:
        st.subheader(f"👤 {application.candidate.full_name}")
        st.caption(
            f"{application.job.job_title} · {application.job.department or '—'} · "
            f"ứng tuyển {format_datetime(application.applied_at)} · nguồn {application.source_name or '—'}"
        )
    with header_right:
        st.metric("Trạng thái", APPLICATION_STATUS_LABELS.get(application.current_status, application.current_status))
        st.caption(
            f"Vòng hiện tại: {application.current_stage.stage_name if application.current_stage else '—'}"
        )

    can_pii = can_view_pii(user)
    contact_cols = st.columns(3)
    contact_cols[0].markdown(
        f"**Email:** {(application.candidate.email or '—') if can_pii else mask_email(application.candidate.email)}"
    )
    contact_cols[1].markdown(
        f"**Điện thoại:** {(application.candidate.phone or '—') if can_pii else mask_phone(application.candidate.phone)}"
    )
    contact_cols[2].markdown(f"**Mã ứng viên:** #{application.candidate_id}")
    if not can_pii:
        st.caption("Thông tin liên hệ được che theo quyền của vai trò hiện tại.")

    tab_history, tab_notes, tab_ai = st.tabs(["🕘 Lịch sử vòng", "💬 Nhận xét", "🤖 CV & AI"])

    with tab_history:
        histories = stage_history(db, application.application_id)
        if not histories:
            st.info("Hồ sơ chưa có lịch sử vòng.")
        else:
            history_table = pd.DataFrame(
                [
                    {
                        "Vòng": history.stage.stage_name,
                        "Vào": format_datetime(history.entered_at),
                        "Ra": format_datetime(history.exited_at, "Đang mở"),
                        "Kết quả": STAGE_RESULT_LABELS.get(history.result or "", history.result or "—"),
                        "Số ngày": _duration_days(history.entered_at, history.exited_at),
                        "Ghi chú": history.notes or "",
                    }
                    for history in histories
                ]
            )
            st.dataframe(history_table, hide_index=True, width="stretch")

        if has_permission(user, PERM_UPDATE_PIPELINE):
            with st.expander("✏️ Cập nhật vòng / trạng thái", expanded=False):
                st.caption(
                    "Chuyển vòng sẽ đóng vòng đang mở và tạo lịch sử mới. Trạng thái kết thúc "
                    "(Từ chối/Rút/Từ chối offer/Đã tuyển) sẽ đóng vòng hiện tại tương ứng. "
                    "Không thể sửa lịch sử cũ."
                )
                with st.form("update_application_form"):
                    stage_choice = st.selectbox(
                        "Vòng mới / vòng hiện tại",
                        [stage.stage_id for stage in stages],
                        index=next(
                            (i for i, stage in enumerate(stages) if stage.stage_id == application.current_stage_id),
                            0,
                        ),
                        format_func=lambda stage_id: stage_by_id[stage_id].stage_name,
                    )
                    result_choice = st.selectbox(
                        "Kết quả vòng đang mở",
                        STAGE_RESULTS,
                        format_func=lambda value: STAGE_RESULT_LABELS.get(value, value),
                    )
                    status_choice = st.selectbox(
                        "Trạng thái hồ sơ",
                        APPLICATION_STATUSES,
                        index=APPLICATION_STATUSES.index(application.current_status)
                        if application.current_status in APPLICATION_STATUSES
                        else 0,
                        format_func=lambda value: APPLICATION_STATUS_LABELS.get(value, value),
                    )
                    note = st.text_area("Ghi chú chuyển vòng (không chứa dữ liệu nhạy cảm)", max_chars=1000)
                    submitted = st.form_submit_button("Lưu cập nhật", type="primary")
                if submitted:
                    try:
                        update_application(
                            db,
                            user=user,
                            application=application,
                            new_stage_id=stage_choice,
                            new_status=status_choice,
                            result=result_choice,
                            note=note or None,
                        )
                    except (PermissionDenied, ValueError) as exc:
                        st.error(str(exc))
                    else:
                        st.success("Đã cập nhật hồ sơ và ghi audit log.")
                        st.rerun()
        else:
            st.info("Vai trò của bạn chỉ được thêm nhận xét, không được chuyển vòng/trạng thái.")

    with tab_notes:
        notes = application_notes(db, application.application_id)
        if notes:
            for note in notes:
                st.markdown(
                    f"**{note.author.full_name}** · {NOTE_TYPE_LABELS.get(note.note_type, note.note_type)} · "
                    f"{format_datetime(note.created_at)}"
                )
                st.write(note.note_text)
                st.divider()
        else:
            st.info("Chưa có nhận xét nào.")

        if has_permission(user, PERM_ADD_NOTES):
            with st.form("add_note_form", clear_on_submit=True):
                note_type = st.selectbox(
                    "Loại nhận xét",
                    NOTE_TYPES,
                    format_func=lambda value: NOTE_TYPE_LABELS.get(value, value),
                )
                note_text = st.text_area("Nội dung nhận xét", max_chars=5000)
                note_submit = st.form_submit_button("Thêm nhận xét")
            if note_submit:
                try:
                    add_application_note(
                        db,
                        user=user,
                        application=application,
                        note_text=note_text,
                        note_type=note_type,
                    )
                except (PermissionDenied, ValueError) as exc:
                    st.error(str(exc))
                else:
                    st.success("Đã thêm nhận xét.")
                    st.rerun()

    with tab_ai:
        analyses = analyses_for_application(db, application.application_id)
        if analyses and has_permission(user, PERM_VIEW_AI_RESULT):
            log_key = f"ai_view_logged_{application.application_id}"
            if log_key not in st.session_state:
                safe_log_action(
                    db,
                    user_id=user.user_id,
                    action="AI_RESULT_VIEWED",
                    resource_type="application",
                    resource_id=application.application_id,
                    metadata={"analysis_count": len(analyses)},
                )
                db.commit()
                st.session_state[log_key] = True
        if not analyses:
            st.info("Hồ sơ chưa có kết quả phân tích CV. Mở trang **Phân tích CV** để tải PDF và chạy phân tích.")
        else:
            table = pd.DataFrame(
                [
                    {
                        "Mã": analysis.analysis_id,
                        "Thời điểm": format_datetime(analysis.created_at),
                        "Xử lý": analysis.processing_status,
                        "Điểm khớp": "N/A" if analysis.skill_match_score is None else f"{float(analysis.skill_match_score):.2f}%",
                        "Kiểm duyệt": REVIEW_STATUS_LABELS.get(analysis.review_status, analysis.review_status),
                        "Phương pháp": analysis.method_version or "—",
                    }
                    for analysis in analyses
                ]
            )
            st.dataframe(table, hide_index=True, width="stretch")
            latest = analyses[0]
            if latest.processing_error:
                st.warning(latest.processing_error)
            if latest.skills_extracted:
                st.markdown("**Kỹ năng trích xuất:**")
                st.caption(" · ".join(latest.skills_extracted))
            st.caption("Điểm khớp kỹ năng chỉ mang tính tham khảo, không phải xác suất trúng tuyển. HR duyệt kết quả ở trang Phân tích CV.")
finally:
    db.close()
