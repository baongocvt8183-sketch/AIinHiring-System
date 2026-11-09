"""CV analysis: secure upload, local extraction, skill matching and human review."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.audit.audit_logger import safe_log_action
from src.auth.permissions import (
    PermissionDenied,
    can_access_job,
    can_view_pii,
    has_permission,
    mask_email,
    mask_phone,
)
from src.constants import (
    PERM_ANALYZE_CV,
    PERM_REVIEW_AI,
    PERM_VIEW_AI_RESULT,
    PERM_VIEW_CV,
    REVIEW_DECISIONS,
    REVIEW_STATUS_LABELS,
)
from src.cv_analysis.pdf_extractor import (
    UploadValidationError,
    resolve_storage_path,
    validate_pdf_upload,
)
from src.cv_analysis.resume_matcher import score_label
from src.cv_analysis.service import reanalyze_document, review_analysis, upload_and_analyze_cv
from src.database.connection import new_session
from src.database.queries import (
    analyses_for_application,
    application_display,
    documents_for_application,
    list_applications,
    required_skills,
    reviews_for_analysis,
)
from src.ui.common import format_datetime, page_header, page_setup

DECISION_LABELS = {
    "APPROVED": "Duyệt kết quả",
    "REJECTED": "Từ chối kết quả",
    "REVISION_REQUESTED": "Yêu cầu chỉnh sửa",
}


def _audit_download(document_id: int, application_id: int, user_id: int) -> None:
    session = new_session()
    try:
        safe_log_action(
            session,
            user_id=user_id,
            action="CV_DOWNLOAD",
            resource_type="candidate_document",
            resource_id=document_id,
            metadata={"application_id": application_id},
        )
        session.commit()
    finally:
        session.close()


user, db = page_setup("Phân tích CV", "📄", PERM_VIEW_CV)
page_header(
    "Phân tích CV & kiểm duyệt AI",
    "Trích xuất văn bản PDF cục bộ, nhận diện kỹ năng bằng từ điển/regex và để HR duyệt kết quả.",
    "📄",
)

try:
    applications = list_applications(db, user, limit=1000)
    if not applications:
        st.info("Không có hồ sơ trong phạm vi. Hãy nhập dữ liệu hoặc kiểm tra phạm vi vị trí được giao.")
        st.stop()

    with st.sidebar:
        st.markdown("### 📄 Chọn hồ sơ")
        search = st.text_input("Tìm ứng viên / vị trí", key="cv_search")
        filtered = [
            application
            for application in applications
            if not search
            or search.lower() in application.candidate.full_name.lower()
            or search.lower() in application.job.job_title.lower()
        ]
        if not filtered:
            st.warning("Không tìm thấy hồ sơ phù hợp.")
            st.stop()
        application_id = st.selectbox(
            "Hồ sơ ứng tuyển",
            [application.application_id for application in filtered],
            format_func=lambda app_id: application_display(db, next(a for a in filtered if a.application_id == app_id)),
            key="cv_application",
        )

    application = next(app for app in filtered if app.application_id == application_id)
    can_pii = can_view_pii(user)
    st.subheader(f"👤 {application.candidate.full_name} — {application.job.job_title}")
    contact = (
        f"Email: {application.candidate.email or '—'} · Điện thoại: {application.candidate.phone or '—'}"
        if can_pii
        else f"Email: {mask_email(application.candidate.email)} · Điện thoại: {mask_phone(application.candidate.phone)}"
    )
    st.caption(f"{contact} · Nguồn: {application.source_name or '—'}")
    if not can_pii:
        st.caption("Thông tin nhận dạng đã được che theo quyền.")

    skills = required_skills(db, application.job_id)
    with st.expander("🎯 Kỹ năng yêu cầu của vị trí", expanded=False):
        if not skills:
            st.warning("Vị trí chưa cấu hình kỹ năng yêu cầu → điểm khớp sẽ là N/A (NOT_SCORABLE), không mặc định 100%.")
        else:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Kỹ năng": skill.skill_name,
                            "Trọng số": float(skill.importance),
                            "Bắt buộc": "Có" if skill.is_required else "Ưu tiên",
                        }
                        for skill in skills
                    ]
                ),
                hide_index=True,
                width="stretch",
            )

    # Upload & analyze -----------------------------------------------------
    if has_permission(user, PERM_ANALYZE_CV):
        with st.expander("📤 Tải CV PDF lên và phân tích", expanded=not bool(analyses_for_application(db, application_id))):
            st.caption("Chỉ nhận PDF có lớp văn bản, tối đa 8 MB. Tệp được lưu với tên ngẫu nhiên trong vùng riêng tư.")
            with st.form("cv_upload_form"):
                uploaded = st.file_uploader("Chọn tệp CV PDF", type=["pdf"], key="cv_upload")
                submitted = st.form_submit_button("Tải lên & phân tích", type="primary")
            if submitted:
                if uploaded is None:
                    st.warning("Vui lòng chọn tệp PDF.")
                else:
                    try:
                        validate_pdf_upload(uploaded.name, uploaded.getvalue(), uploaded.type)
                        with st.spinner("Đang lưu tệp, trích xuất văn bản và đối chiếu kỹ năng..."):
                            analysis = upload_and_analyze_cv(
                                db,
                                user=user,
                                application=application,
                                filename=uploaded.name,
                                data=uploaded.getvalue(),
                                mime_type=uploaded.type,
                            )
                    except UploadValidationError as exc:
                        st.error(str(exc))
                    except PermissionDenied as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(f"Không xử lý được CV: {exc}")
                    else:
                        st.session_state["cv_analysis_focus"] = analysis.analysis_id
                        if analysis.processing_status == "NEEDS_OCR":
                            st.warning("PDF không có lớp văn bản. Đã ghi nhận NEEDS_OCR; cần OCR trước khi chấm điểm.")
                        elif analysis.processing_status == "FAILED":
                            st.error(f"Phân tích thất bại: {analysis.processing_error}")
                        else:
                            st.success("Đã phân tích CV và lưu kết quả chờ HR duyệt.")
                        st.rerun()

    analyses = analyses_for_application(db, application_id)
    documents = documents_for_application(db, application_id)

    if analyses and has_permission(user, PERM_VIEW_AI_RESULT):
        log_key = f"ai_view_cv_{application_id}"
        if log_key not in st.session_state:
            safe_log_action(
                db,
                user_id=user.user_id,
                action="AI_RESULT_VIEWED",
                resource_type="application",
                resource_id=application_id,
                metadata={"analysis_count": len(analyses)},
            )
            db.commit()
            st.session_state[log_key] = True

    tab_result, tab_review, tab_docs = st.tabs(["🤖 Kết quả phân tích", "✅ Kiểm duyệt của HR", "📎 Tài liệu CV"])

    with tab_result:
        if not analyses:
            st.info("Chưa có kết quả phân tích cho hồ sơ này.")
        else:
            focus = st.session_state.get("cv_analysis_focus")
            ids = [analysis.analysis_id for analysis in analyses]
            selected_analysis_id = st.selectbox(
                "Chọn lần phân tích",
                ids,
                index=ids.index(focus) if focus in ids else 0,
                format_func=lambda analysis_id: next(
                    f"#{analysis_id} · {format_datetime(a.created_at)} · {REVIEW_STATUS_LABELS.get(a.review_status, a.review_status)}"
                    for a in analyses
                    if a.analysis_id == analysis_id
                ),
                key="cv_analysis_select",
            )
            analysis = next(a for a in analyses if a.analysis_id == selected_analysis_id)
            score = float(analysis.skill_match_score) if analysis.skill_match_score is not None else None
            left, right = st.columns([1, 2])
            with left:
                st.metric("Điểm khớp kỹ năng", "N/A" if score is None else f"{score:.2f}%")
                if analysis.processing_status == "NOT_SCORABLE":
                    st.info("Vị trí chưa cấu hình kỹ năng → NOT_SCORABLE.")
                else:
                    st.progress(min(max((score or 0) / 100, 0.0), 1.0))
                    st.caption(score_label(score, analysis.processing_status))
                st.markdown(f"**Xử lý:** `{analysis.processing_status}`")
                st.markdown(f"**Kiểm duyệt:** {REVIEW_STATUS_LABELS.get(analysis.review_status, analysis.review_status)}")
                st.caption(f"Phương pháp: {analysis.method_version or '—'} · {format_datetime(analysis.created_at)}")
            with right:
                if analysis.processing_error:
                    st.warning(analysis.processing_error)
                st.markdown("**Kỹ năng tìm thấy trong CV**")
                if analysis.skills_extracted:
                    st.markdown(" ".join(f"`{skill}`" for skill in analysis.skills_extracted))
                else:
                    st.caption("Không có kỹ năng nào khớp từ điển.")
                st.markdown("**Kỹ năng còn thiếu so với vị trí**")
                if analysis.missing_skills:
                    st.markdown(" ".join(f"`{skill}`" for skill in analysis.missing_skills))
                else:
                    st.caption("Không thiếu kỹ năng nào (hoặc vị trí chưa cấu hình).")

            st.divider()
            col_exp, col_proj = st.columns(2)
            col_exp.markdown("**Tóm tắt kinh nghiệm (heuristic cục bộ)**")
            col_exp.write(analysis.experience_summary or "—")
            col_proj.markdown("**Tóm tắt dự án**")
            col_proj.write(analysis.projects_summary or "—")
            st.caption("Tóm tắt chỉ hỗ trợ đọc nhanh; HR cần đối chiếu CV gốc. Điểm không phải xác suất trúng tuyển.")

            if has_permission(user, PERM_VIEW_AI_RESULT) and analysis.extracted_text:
                show_text = st.toggle("Xem văn bản CV đã trích xuất", key=f"show_text_{analysis.analysis_id}")
                if show_text:
                    safe_log_action(
                        db,
                        user_id=user.user_id,
                        action="CV_TEXT_VIEWED",
                        resource_type="ai_cv_analysis",
                        resource_id=analysis.analysis_id,
                    )
                    db.commit()
                    st.text_area("Văn bản trích xuất", analysis.extracted_text[:20000], height=320, disabled=True)

    with tab_review:
        if not has_permission(user, PERM_REVIEW_AI):
            st.info("Chỉ HR Manager/Admin được duyệt kết quả AI. Hiring Manager có thể xem và thêm nhận xét ở Pipeline.")
        elif not analyses:
            st.info("Chưa có kết quả AI để kiểm duyệt.")
        else:
            review_analysis_id = st.selectbox(
                "Chọn kết quả cần kiểm duyệt",
                [analysis.analysis_id for analysis in analyses],
                format_func=lambda analysis_id: next(
                    f"#{analysis_id} · {REVIEW_STATUS_LABELS.get(a.review_status, a.review_status)} · {format_datetime(a.created_at)}"
                    for a in analyses
                    if a.analysis_id == analysis_id
                ),
                key="review_analysis_select",
            )
            analysis = next(a for a in analyses if a.analysis_id == review_analysis_id)
            st.markdown(
                f"Trạng thái hiện tại: **{REVIEW_STATUS_LABELS.get(analysis.review_status, analysis.review_status)}**"
            )
            with st.form("review_form"):
                decision = st.radio(
                    "Quyết định",
                    REVIEW_DECISIONS,
                    format_func=lambda value: DECISION_LABELS.get(value, value),
                    horizontal=True,
                )
                note = st.text_area("Ghi chú kiểm duyệt", max_chars=2000)
                review_submit = st.form_submit_button("Lưu quyết định", type="primary")
            if review_submit:
                try:
                    review_analysis(db, user=user, analysis=analysis, decision=decision, note=note)
                except (PermissionDenied, ValueError) as exc:
                    st.error(str(exc))
                else:
                    st.success("Đã lưu quyết định kiểm duyệt và ghi audit log.")
                    st.rerun()

            reviews = reviews_for_analysis(db, analysis.analysis_id)
            if reviews:
                st.markdown("#### Lịch sử kiểm duyệt")
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Thời điểm": format_datetime(review.created_at),
                                "Người duyệt": review.reviewer.full_name if review.reviewer else "—",
                                "Quyết định": DECISION_LABELS.get(review.decision, review.decision),
                                "Ghi chú": review.review_note or "",
                            }
                            for review in reviews
                        ]
                    ),
                    hide_index=True,
                    width="stretch",
                )

    with tab_docs:
        if not documents:
            st.info("Chưa có tài liệu CV nào.")
        else:
            for document in documents:
                cols = st.columns([3, 1, 1])
                cols[0].markdown(
                    f"**{document.original_filename}**  \n"
                    f"<span class='muted'>{document.file_size_bytes:,} bytes · {format_datetime(document.uploaded_at)}</span>",
                    unsafe_allow_html=True,
                )
                try:
                    path = resolve_storage_path(document.storage_key)
                    data = path.read_bytes() if path.exists() else None
                except UploadValidationError:
                    data = None
                if data is None:
                    cols[1].warning("Tệp không còn")
                else:
                    cols[1].download_button(
                        "⬇️ Tải CV",
                        data=data,
                        file_name=document.original_filename,
                        mime=document.mime_type,
                        key=f"download_{document.document_id}",
                        on_click=_audit_download,
                        args=(document.document_id, application_id, user.user_id),
                    )
                if has_permission(user, PERM_ANALYZE_CV):
                    if cols[2].button("🔄 Phân tích lại", key=f"reanalyze_{document.document_id}"):
                        try:
                            analysis = reanalyze_document(db, user=user, application=application, document=document)
                        except (PermissionDenied, UploadValidationError) as exc:
                            st.error(str(exc))
                        else:
                            st.session_state["cv_analysis_focus"] = analysis.analysis_id
                            st.success(f"Đã tạo phân tích #{analysis.analysis_id}.")
                            st.rerun()
finally:
    db.close()
