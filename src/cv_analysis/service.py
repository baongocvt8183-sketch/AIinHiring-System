"""High-level CV upload/analysis/review service."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src import config
from src.audit.audit_logger import log_action, safe_log_action
from src.auth.permissions import (
    PermissionDenied,
    can_access_job,
    has_permission,
    require_permission,
)
from src.constants import REVIEW_DECISIONS
from src.cv_analysis.pdf_extractor import (
    PDFExtraction,
    UploadValidationError,
    extract_pdf_text,
    store_pdf,
    validate_pdf_upload,
)
from src.cv_analysis.resume_matcher import SkillMatchResult, match_skills
from src.cv_analysis.skills_extractor import extract_skills, summarize_sections
from src.database.models import (
    AICVAnalysis,
    AIAnalysisReview,
    Application,
    CandidateDocument,
    JobRequiredSkill,
    User,
)


def _job_required_skills(session: Session, job_id: int) -> list[str]:
    return list(
        session.scalars(
            select(JobRequiredSkill.skill_name)
            .where(JobRequiredSkill.job_id == job_id)
            .order_by(JobRequiredSkill.skill_name)
        )
    )


def _persist_analysis(
    session: Session,
    *,
    application: Application,
    document: CandidateDocument,
    extraction: PDFExtraction,
) -> AICVAnalysis:
    required = _job_required_skills(session, application.job_id)
    analysis = AICVAnalysis(
        application_id=application.application_id,
        document_id=document.document_id,
        skills_extracted=[],
        missing_skills=[],
        processing_status="FAILED",
        review_status="PENDING_REVIEW",
        method_version=config.CV_METHOD_VERSION,
        created_at=datetime.now(timezone.utc),
    )

    if extraction.error:
        analysis.processing_status = "FAILED"
        analysis.processing_error = extraction.error
        analysis.experience_summary = None
        analysis.projects_summary = None
        session.add(analysis)
        session.flush()
        return analysis

    if extraction.needs_ocr:
        analysis.processing_status = "NEEDS_OCR"
        analysis.processing_error = (
            f"PDF chỉ có {extraction.char_count} ký tự văn bản; cần OCR hoặc tệp PDF có lớp văn bản."
        )
        analysis.extracted_text = extraction.text[:200_000]
        session.add(analysis)
        session.flush()
        return analysis

    skills = extract_skills(extraction.text)
    result: SkillMatchResult = match_skills(skills, required)
    experience_summary, projects_summary = summarize_sections(extraction.text)

    analysis.skills_extracted = skills
    analysis.missing_skills = result.missing_skills
    analysis.skill_match_score = result.score
    analysis.experience_summary = experience_summary or None
    analysis.projects_summary = projects_summary or None
    analysis.extracted_text = extraction.text[:200_000]
    analysis.processing_status = result.status
    analysis.processing_error = None
    analysis.method_version = config.CV_METHOD_VERSION
    session.add(analysis)
    session.flush()
    return analysis


def upload_and_analyze_cv(
    session: Session,
    *,
    user: User,
    application: Application,
    filename: str,
    data: bytes,
    mime_type: str | None,
    commit: bool = True,
) -> AICVAnalysis:
    require_permission(user, "analyze_cv")
    if not can_access_job(session, user, application.job_id):
        raise PermissionDenied("Hồ sơ nằm ngoài phạm vi vị trí bạn được giao.")

    resolved_mime = validate_pdf_upload(filename, data, mime_type)
    stored = store_pdf(data, filename, resolved_mime)

    try:
        document = CandidateDocument(
            candidate_id=application.candidate_id,
            application_id=application.application_id,
            storage_key=stored.storage_key,
            original_filename=stored.original_filename,
            mime_type=stored.mime_type,
            file_size_bytes=stored.size_bytes,
            sha256_hash=stored.sha256,
            uploaded_by=user.user_id,
        )
        session.add(document)
        session.flush()

        log_action(
            session,
            user_id=user.user_id,
            action="CV_UPLOAD",
            resource_type="candidate_document",
            resource_id=document.document_id,
            metadata={
                "application_id": application.application_id,
                "file_size": stored.size_bytes,
                "mime_type": stored.mime_type,
            },
        )

        extraction = extract_pdf_text(stored.path)
        analysis = _persist_analysis(session, application=application, document=document, extraction=extraction)

        safe_log_action(
            session,
            user_id=user.user_id,
            action="CV_ANALYZE",
            result="SUCCESS" if analysis.processing_status != "FAILED" else "FAILURE",
            resource_type="ai_cv_analysis",
            resource_id=analysis.analysis_id,
            metadata={
                "application_id": application.application_id,
                "document_id": document.document_id,
                "processing_status": analysis.processing_status,
                "skill_match_score": float(analysis.skill_match_score) if analysis.skill_match_score is not None else None,
                "method_version": analysis.method_version,
            },
        )
        if commit:
            session.commit()
            session.refresh(analysis)
        return analysis
    except Exception:
        try:
            stored.path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def reanalyze_document(
    session: Session,
    *,
    user: User,
    application: Application,
    document: CandidateDocument,
    commit: bool = True,
) -> AICVAnalysis:
    require_permission(user, "analyze_cv")
    if not can_access_job(session, user, application.job_id):
        raise PermissionDenied("Hồ sơ nằm ngoài phạm vi vị trí bạn được giao.")
    if document.application_id not in {None, application.application_id}:
        raise UploadValidationError("Tài liệu không thuộc hồ sơ ứng tuyển đã chọn.")

    from src.cv_analysis.pdf_extractor import resolve_storage_path

    path = resolve_storage_path(document.storage_key)
    if not path.exists():
        raise UploadValidationError("Không tìm thấy tệp CV trong vùng lưu trữ riêng.")
    extraction = extract_pdf_text(path)
    analysis = _persist_analysis(session, application=application, document=document, extraction=extraction)
    safe_log_action(
        session,
        user_id=user.user_id,
        action="CV_ANALYZE",
        result="SUCCESS" if analysis.processing_status != "FAILED" else "FAILURE",
        resource_type="ai_cv_analysis",
        resource_id=analysis.analysis_id,
        metadata={
            "application_id": application.application_id,
            "document_id": document.document_id,
            "processing_status": analysis.processing_status,
        },
    )
    if commit:
        session.commit()
        session.refresh(analysis)
    return analysis


def review_analysis(
    session: Session,
    *,
    user: User,
    analysis: AICVAnalysis,
    decision: str,
    note: str | None = None,
    commit: bool = True,
) -> AIAnalysisReview:
    require_permission(user, "review_ai")
    if decision not in REVIEW_DECISIONS:
        raise ValueError("Quyết định kiểm duyệt không hợp lệ.")
    if decision in {"REJECTED", "REVISION_REQUESTED"} and not (note or "").strip():
        raise ValueError("Cần ghi lý do khi từ chối hoặc yêu cầu chỉnh sửa.")

    application = analysis.application
    if application is not None and not can_access_job(session, user, application.job_id):
        raise PermissionDenied("Hồ sơ nằm ngoài phạm vi vị trí bạn được giao.")

    review = AIAnalysisReview(
        analysis_id=analysis.analysis_id,
        reviewer_id=user.user_id,
        decision=decision,
        review_note=(note or "").strip() or None,
        created_at=datetime.now(timezone.utc),
    )
    session.add(review)
    analysis.review_status = decision
    session.flush()

    safe_log_action(
        session,
        user_id=user.user_id,
        action="AI_ANALYSIS_REVIEW",
        resource_type="ai_cv_analysis",
        resource_id=analysis.analysis_id,
        metadata={
            "decision": decision,
            "application_id": analysis.application_id,
            "has_note": bool(note and note.strip()),
        },
    )
    if commit:
        session.commit()
        session.refresh(review)
    return review


def can_review(user: User | None) -> bool:
    return has_permission(user, "review_ai")
