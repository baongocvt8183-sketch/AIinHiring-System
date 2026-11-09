from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select

from src.database.models import (
    AICVAnalysis,
    AIAnalysisReview,
    Application,
    ApplicationStageHistory,
    AuditLog,
    Candidate,
    CandidateDocument,
    ETLRun,
    JobRequiredSkill,
    Role,
    Stage,
    User,
)
from src.database.seed import DEMO_ACCOUNTS, seed_database
from src.cv_analysis.pdf_extractor import resolve_storage_path


def test_seed_counts_and_referential_consistency(demo_session):
    assert demo_session.scalar(select(func.count()).select_from(Role)) == 4
    assert demo_session.scalar(select(func.count()).select_from(Stage)) == 6
    assert demo_session.scalar(select(func.count()).select_from(User)) == 4
    assert demo_session.scalar(select(func.count()).select_from(Application)) == 15
    assert demo_session.scalar(select(func.count()).select_from(JobRequiredSkill)) > 0
    assert demo_session.scalar(select(func.count()).select_from(ETLRun)) >= 1


def test_every_application_stage_is_consistent(demo_session):
    applications = list(demo_session.scalars(select(Application)))
    for application in applications:
        histories = list(
            demo_session.scalars(
                select(ApplicationStageHistory).where(
                    ApplicationStageHistory.application_id == application.application_id
                )
            )
        )
        assert histories, f"application {application.application_id} has no stage history"
        assert application.current_stage_id in {history.stage_id for history in histories}

        open_histories = [history for history in histories if history.exited_at is None]
        if application.current_status in {"IN_PROGRESS", "ON_HOLD"}:
            assert len(open_histories) == 1, (application.application_id, application.current_status)
        else:
            assert len(open_histories) == 0, (application.application_id, application.current_status)

        for history in histories:
            if history.exited_at is not None:
                assert history.exited_at >= history.entered_at


def test_seed_business_rules(demo_session):
    candidates = list(demo_session.scalars(select(Candidate)))
    emails = [candidate.email for candidate in candidates if candidate.email]
    assert len(emails) == len(set(emails))
    assert all(email == email.lower() for email in emails)
    assert any(candidate.email is None for candidate in candidates)  # missing email is not merged

    pairs = Counter((application.candidate_id, application.job_id) for application in demo_session.scalars(select(Application)))
    assert all(count == 1 for count in pairs.values())

    hired_apps = list(demo_session.scalars(select(Application).where(Application.current_status == "HIRED")))
    assert len(hired_apps) == 3
    for application in hired_apps:
        hired_history = demo_session.scalar(
            select(ApplicationStageHistory)
            .join(Stage, Stage.stage_id == ApplicationStageHistory.stage_id)
            .where(
                ApplicationStageHistory.application_id == application.application_id,
                Stage.stage_name == "Hired",
            )
        )
        assert hired_history is not None

    approved = list(demo_session.scalars(select(AICVAnalysis).where(AICVAnalysis.review_status == "APPROVED")))
    assert approved
    for analysis in approved:
        assert demo_session.scalar(
            select(func.count()).select_from(AIAnalysisReview).where(AIAnalysisReview.analysis_id == analysis.analysis_id)
        ) >= 1


def test_seed_documents_exist_in_private_storage(demo_session):
    documents = list(demo_session.scalars(select(CandidateDocument)))
    assert documents
    for document in documents:
        path = resolve_storage_path(document.storage_key)
        assert path.exists(), document.storage_key
        assert path.is_relative_to(resolve_storage_path(""))  # inside private upload root


def test_audit_log_never_contains_passwords(demo_session):
    demo_passwords = {account["password"] for account in DEMO_ACCOUNTS}
    for log in demo_session.scalars(select(AuditLog)):
        text = repr(log.log_metadata)
        assert not any(password in text for password in demo_passwords)
        assert "password_hash" not in text


def test_seed_is_idempotent(demo_session):
    before = demo_session.scalar(select(func.count()).select_from(User))
    seed_database(demo_session)
    after = demo_session.scalar(select(func.count()).select_from(User))
    assert before == after


def test_seed_reuses_existing_stage_catalogue(clean_session):
    from src.constants import DEFAULT_STAGE_NAMES

    for order, name in enumerate(DEFAULT_STAGE_NAMES, start=1):
        clean_session.add(Stage(stage_name=name, stage_order=order, is_terminal=name == "Hired"))
    clean_session.commit()

    seed_database(clean_session)
    assert clean_session.scalar(select(func.count()).select_from(Stage)) == len(DEFAULT_STAGE_NAMES)
    assert clean_session.scalar(select(func.count()).select_from(User)) == len(DEMO_ACCOUNTS)
