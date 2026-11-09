from __future__ import annotations

import pytest
from sqlalchemy import select

from src.auth.permissions import PermissionDenied
from src.cv_analysis.service import review_analysis, upload_and_analyze_cv
from src.database.models import AICVAnalysis, Application, AuditLog, Candidate, User
from src.database.sample_data import write_sample_files


def _user(session, username):
    return session.scalar(select(User).where(User.username == username))


def _application_for(session, candidate_name):
    return session.scalar(
        select(Application)
        .join(Candidate, Candidate.candidate_id == Application.candidate_id)
        .where(Candidate.full_name == candidate_name)
        .limit(1)
    )


def test_upload_cv_creates_analysis_and_can_be_reviewed(demo_session):
    hr = _user(demo_session, "hr")
    application = _application_for(demo_session, "Trần Thị Bình")
    paths = write_sample_files()
    data = paths["cv_tran_thi_binh.pdf"].read_bytes()

    analysis = upload_and_analyze_cv(
        demo_session,
        user=hr,
        application=application,
        filename="binh_cv.pdf",
        data=data,
        mime_type="application/pdf",
    )
    assert analysis.processing_status == "SUCCESS"
    assert analysis.review_status == "PENDING_REVIEW"
    assert analysis.skill_match_score is not None
    assert float(analysis.skill_match_score) == pytest.approx(33.33, abs=0.01)
    assert "Python" in analysis.skills_extracted
    assert "Docker" in analysis.missing_skills
    assert analysis.method_version
    assert analysis.document_id is not None
    assert analysis.document.storage_key.endswith(".pdf")

    review = review_analysis(
        demo_session,
        user=hr,
        analysis=analysis,
        decision="APPROVED",
        note="Đã đối chiếu CV gốc.",
    )
    demo_session.refresh(analysis)
    assert review.decision == "APPROVED"
    assert analysis.review_status == "APPROVED"
    audit_actions = set(demo_session.scalars(select(AuditLog.action)))
    assert {"CV_UPLOAD", "CV_ANALYZE", "AI_ANALYSIS_REVIEW"} <= audit_actions


def test_hiring_manager_cannot_analyze_or_review(demo_session):
    hm = _user(demo_session, "hiring")
    application = _application_for(demo_session, "Nguyễn Văn An")
    paths = write_sample_files()
    data = paths["cv_nguyen_van_an.pdf"].read_bytes()

    with pytest.raises(PermissionDenied):
        upload_and_analyze_cv(
            demo_session,
            user=hm,
            application=application,
            filename="an.pdf",
            data=data,
            mime_type="application/pdf",
        )

    analysis = demo_session.scalar(
        select(AICVAnalysis).where(AICVAnalysis.application_id == application.application_id)
    )
    with pytest.raises(PermissionDenied):
        review_analysis(demo_session, user=hm, analysis=analysis, decision="APPROVED")


def test_image_only_pdf_flagged_needs_ocr(demo_session):
    hr = _user(demo_session, "hr")
    application = _application_for(demo_session, "Đinh Thị Nga")
    paths = write_sample_files()
    data = paths["cv_scan_only.pdf"].read_bytes()

    analysis = upload_and_analyze_cv(
        demo_session,
        user=hr,
        application=application,
        filename="scan.pdf",
        data=data,
        mime_type="application/pdf",
    )
    assert analysis.processing_status == "NEEDS_OCR"
    assert analysis.skill_match_score is None
    assert "OCR" in (analysis.processing_error or "")
