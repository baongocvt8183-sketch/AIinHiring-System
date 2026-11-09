"""Reusable database queries and business actions for pipeline pages."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.audit.audit_logger import safe_log_action
from src.auth.permissions import (
    PermissionDenied,
    can_access_job,
    get_scoped_application,
    require_permission,
    scoped_job_ids,
)
from src.constants import APPLICATION_STATUS_LABELS, APPLICATION_STATUSES, STAGE_RESULTS
from src.database.models import (
    AICVAnalysis,
    AIAnalysisReview,
    Application,
    ApplicationNote,
    ApplicationStageHistory,
    Candidate,
    CandidateDocument,
    Job,
    JobRequiredSkill,
    Stage,
    User,
    UserJobAssignment,
)


def list_stages(session: Session) -> list[Stage]:
    return list(session.scalars(select(Stage).order_by(Stage.stage_order)))


def stage_by_name(session: Session, name: str) -> Stage | None:
    return session.scalar(select(Stage).where(func.lower(Stage.stage_name) == name.lower()))


def list_jobs(session: Session, user: User | None, active_only: bool = False) -> list[Job]:
    stmt = select(Job).order_by(Job.job_title)
    scope = scoped_job_ids(session, user)
    if scope is not None:
        if not scope:
            return []
        stmt = stmt.where(Job.job_id.in_(scope))
    if active_only:
        stmt = stmt.where(Job.is_active.is_(True))
    return list(session.scalars(stmt))


def list_applications(
    session: Session,
    user: User,
    *,
    job_ids: list[int] | None = None,
    statuses: list[str] | None = None,
    stage_ids: list[int] | None = None,
    search: str | None = None,
    limit: int = 500,
) -> list[Application]:
    require_permission(user, "view_applications")
    stmt = (
        select(Application)
        .join(Candidate, Candidate.candidate_id == Application.candidate_id)
        .join(Job, Job.job_id == Application.job_id)
        .order_by(Application.applied_at.desc())
        .limit(limit)
    )
    scope = scoped_job_ids(session, user)
    if scope is not None:
        if not scope:
            return []
        stmt = stmt.where(Application.job_id.in_(scope))
    if job_ids:
        stmt = stmt.where(Application.job_id.in_(job_ids))
    if statuses:
        stmt = stmt.where(Application.current_status.in_(statuses))
    if stage_ids:
        stmt = stmt.where(Application.current_stage_id.in_(stage_ids))
    if search:
        needle = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            (func.lower(Candidate.full_name).like(needle))
            | (func.lower(Candidate.email).like(needle))
            | (func.lower(Job.job_title).like(needle))
        )
    return list(session.scalars(stmt))


def list_candidates(
    session: Session,
    user: User,
    *,
    search: str | None = None,
    include_archived: bool = False,
    limit: int = 1000,
) -> list[Candidate]:
    require_permission(user, "view_candidates")
    stmt = select(Candidate).order_by(Candidate.created_at.desc()).limit(limit)
    scope = scoped_job_ids(session, user)
    if scope is not None:
        if not scope:
            return []
        stmt = stmt.join(Application, Application.candidate_id == Candidate.candidate_id).where(
            Application.job_id.in_(scope)
        ).distinct()
    if not include_archived:
        stmt = stmt.where(Candidate.is_archived.is_(False))
    if search:
        needle = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            (func.lower(Candidate.full_name).like(needle))
            | (func.lower(Candidate.email).like(needle))
            | (func.lower(Candidate.phone).like(needle))
        )
    return list(session.scalars(stmt))


def application_notes(session: Session, application_id: int) -> list[ApplicationNote]:
    return list(
        session.scalars(
            select(ApplicationNote)
            .where(ApplicationNote.application_id == application_id)
            .order_by(ApplicationNote.created_at.desc())
        )
    )


def stage_history(session: Session, application_id: int) -> list[ApplicationStageHistory]:
    return list(
        session.scalars(
            select(ApplicationStageHistory)
            .where(ApplicationStageHistory.application_id == application_id)
            .order_by(ApplicationStageHistory.entered_at)
        )
    )


def analyses_for_application(session: Session, application_id: int) -> list[AICVAnalysis]:
    return list(
        session.scalars(
            select(AICVAnalysis)
            .where(AICVAnalysis.application_id == application_id)
            .order_by(AICVAnalysis.created_at.desc())
        )
    )


def reviews_for_analysis(session: Session, analysis_id: int) -> list[AIAnalysisReview]:
    return list(
        session.scalars(
            select(AIAnalysisReview)
            .where(AIAnalysisReview.analysis_id == analysis_id)
            .order_by(AIAnalysisReview.created_at.desc())
        )
    )


def documents_for_application(session: Session, application_id: int) -> list[CandidateDocument]:
    return list(
        session.scalars(
            select(CandidateDocument)
            .where(CandidateDocument.application_id == application_id)
            .order_by(CandidateDocument.uploaded_at.desc())
        )
    )


def required_skills(session: Session, job_id: int) -> list[JobRequiredSkill]:
    return list(
        session.scalars(
            select(JobRequiredSkill)
            .where(JobRequiredSkill.job_id == job_id)
            .order_by(JobRequiredSkill.skill_name)
        )
    )


def application_display(session: Session, application: Application) -> str:
    candidate = application.candidate
    job = application.job
    return f"#{application.application_id} · {candidate.full_name} · {job.job_title}"


def _open_histories(session: Session, application_id: int) -> list[ApplicationStageHistory]:
    return list(
        session.scalars(
            select(ApplicationStageHistory).where(
                ApplicationStageHistory.application_id == application_id,
                ApplicationStageHistory.exited_at.is_(None),
            )
        )
    )


def _close_histories(histories: list[ApplicationStageHistory], *, result: str, now: datetime, note: str | None) -> None:
    for history in histories:
        history.exited_at = now
        history.result = result
        if note:
            history.notes = note[:1000]


def update_application(
    session: Session,
    *,
    user: User,
    application: Application,
    new_stage_id: int | None = None,
    new_status: str | None = None,
    result: str | None = None,
    note: str | None = None,
    commit: bool = True,
) -> Application:
    """Move an application through stages while keeping history synchronized."""
    require_permission(user, "update_pipeline")
    if not can_access_job(session, user, application.job_id):
        raise PermissionDenied("Hồ sơ nằm ngoài phạm vi vị trí bạn được giao.")
    if new_status is not None and new_status not in APPLICATION_STATUSES:
        raise ValueError("Trạng thái hồ sơ không hợp lệ.")
    if result is not None and result not in STAGE_RESULTS:
        raise ValueError("Kết quả vòng không hợp lệ.")

    now = datetime.now(timezone.utc)
    old_status = application.current_status
    old_stage_id = application.current_stage_id
    status = new_status or application.current_status

    target_stage: Stage | None = None
    if new_stage_id is not None:
        target_stage = session.get(Stage, new_stage_id)
        if target_stage is None:
            raise ValueError("Vòng tuyển không tồn tại.")
    if status == "HIRED":
        hired_stage = stage_by_name(session, "Hired")
        if hired_stage is not None:
            target_stage = hired_stage
        elif target_stage is None:
            raise ValueError("Chưa cấu hình vòng Hired.")

    open_histories = _open_histories(session, application.application_id)
    note_text = (note or "").strip() or None
    closing_result = result or "PASSED"

    # Status-only transitions that end the process close the current stage.
    terminal_result = {
        "REJECTED": "FAILED",
        "WITHDRAWN": "SKIPPED",
        "OFFER_DECLINED": "SKIPPED",
        "HIRED": "PASSED",
    }
    if status in terminal_result:
        closing_result = terminal_result[status]
        if status == "HIRED" and target_stage is not None:
            has_target_open = any(h.stage_id == target_stage.stage_id for h in open_histories)
            already_recorded = any(
                h.stage_id == target_stage.stage_id and h.application_id == application.application_id
                for h in application.stage_history
            )
            if not has_target_open and not already_recorded:
                hired_history = ApplicationStageHistory(
                    application_id=application.application_id,
                    stage_id=target_stage.stage_id,
                    entered_at=now,
                    exited_at=now,
                    result="PASSED",
                    notes=note_text,
                )
                session.add(hired_history)
        _close_histories(open_histories, result=closing_result, now=now, note=note_text)
        if target_stage is None:
            target_stage = application.current_stage
    elif status == "ON_HOLD":
        # Keep the current stage open; the dashboard reports the ongoing wait.
        pass
    elif target_stage is not None and target_stage.stage_id != application.current_stage_id:
        _close_histories(open_histories, result=closing_result, now=now, note=note_text)
        history = ApplicationStageHistory(
            application_id=application.application_id,
            stage_id=target_stage.stage_id,
            entered_at=now,
            exited_at=None,
            result="PENDING",
        )
        session.add(history)
        open_histories = [history]
        status = "IN_PROGRESS" if new_status in {None, "IN_PROGRESS"} else status
    elif target_stage is not None and not open_histories and status not in {"HIRED"}:
        session.add(
            ApplicationStageHistory(
                application_id=application.application_id,
                stage_id=target_stage.stage_id,
                entered_at=now,
                exited_at=None,
                result="PENDING",
            )
        )

    if status == "HIRED" and target_stage is not None:
        # Hired is terminal: close it immediately so it is not reported as waiting.
        hired_open = _open_histories(session, application.application_id)
        _close_histories(hired_open, result="PASSED", now=now, note=note_text)

    if target_stage is not None:
        application.current_stage_id = target_stage.stage_id
    application.current_status = status
    application.updated_at = now
    session.flush()

    safe_log_action(
        session,
        user_id=user.user_id,
        action="APPLICATION_STATUS_CHANGE",
        resource_type="application",
        resource_id=application.application_id,
        metadata={
            "old_status": old_status,
            "new_status": status,
            "old_stage_id": old_stage_id,
            "new_stage_id": application.current_stage_id,
            "has_note": bool(note_text),
        },
    )
    if commit:
        session.commit()
        session.refresh(application)
    return application


def add_application_note(
    session: Session,
    *,
    user: User,
    application: Application,
    note_text: str,
    note_type: str = "GENERAL",
    commit: bool = True,
) -> ApplicationNote:
    require_permission(user, "add_notes")
    if not can_access_job(session, user, application.job_id):
        raise PermissionDenied("Hồ sơ nằm ngoài phạm vi vị trí bạn được giao.")
    text = " ".join((note_text or "").split())
    if not text:
        raise ValueError("Nội dung nhận xét không được để trống.")
    if len(text) > 5000:
        raise ValueError("Nhận xét quá dài (tối đa 5.000 ký tự).")

    note = ApplicationNote(
        application_id=application.application_id,
        author_id=user.user_id,
        note_type=note_type if note_type else "GENERAL",
        note_text=text,
        created_at=datetime.now(timezone.utc),
    )
    session.add(note)
    session.flush()
    safe_log_action(
        session,
        user_id=user.user_id,
        action="APPLICATION_NOTE_ADDED",
        resource_type="application",
        resource_id=application.application_id,
        metadata={"note_id": note.note_id, "note_type": note.note_type},
    )
    if commit:
        session.commit()
        session.refresh(note)
    return note


def create_candidate(
    session: Session,
    *,
    user: User,
    full_name: str,
    email: str | None,
    phone: str | None,
    commit: bool = True,
) -> Candidate:
    from src.etl.transform import is_valid_email, normalize_email, normalize_name, normalize_phone

    require_permission(user, "manage_candidates")
    name = normalize_name(full_name)
    normalized_email = normalize_email(email)
    if not name:
        raise ValueError("Họ tên không được để trống.")
    if normalized_email and not is_valid_email(normalized_email):
        raise ValueError("Email không đúng định dạng.")
    if normalized_email and session.scalar(select(Candidate).where(Candidate.email == normalized_email)):
        raise ValueError("Email đã thuộc về một ứng viên khác.")
    candidate = Candidate(
        full_name=name,
        email=normalized_email,
        phone=normalize_phone(phone),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(candidate)
    session.flush()
    safe_log_action(
        session,
        user_id=user.user_id,
        action="CANDIDATE_CREATE",
        resource_type="candidate",
        resource_id=candidate.candidate_id,
    )
    if commit:
        session.commit()
        session.refresh(candidate)
    return candidate


def update_candidate(
    session: Session,
    *,
    user: User,
    candidate: Candidate,
    full_name: str,
    email: str | None,
    phone: str | None,
    commit: bool = True,
) -> Candidate:
    from src.etl.transform import is_valid_email, normalize_email, normalize_name, normalize_phone

    require_permission(user, "manage_candidates")
    name = normalize_name(full_name)
    normalized_email = normalize_email(email)
    if not name:
        raise ValueError("Họ tên không được để trống.")
    if normalized_email and not is_valid_email(normalized_email):
        raise ValueError("Email không đúng định dạng.")
    if normalized_email:
        existing = session.scalar(select(Candidate).where(Candidate.email == normalized_email))
        if existing is not None and existing.candidate_id != candidate.candidate_id:
            raise ValueError("Email đã thuộc về một ứng viên khác.")
    candidate.full_name = name
    candidate.email = normalized_email
    candidate.phone = normalize_phone(phone)
    candidate.updated_at = datetime.now(timezone.utc)
    session.flush()
    safe_log_action(
        session,
        user_id=user.user_id,
        action="CANDIDATE_UPDATE",
        resource_type="candidate",
        resource_id=candidate.candidate_id,
    )
    if commit:
        session.commit()
        session.refresh(candidate)
    return candidate


def archive_candidate(
    session: Session,
    *,
    user: User,
    candidate: Candidate,
    archived: bool = True,
    commit: bool = True,
) -> Candidate:
    require_permission(user, "manage_candidates")
    candidate.is_archived = archived
    candidate.updated_at = datetime.now(timezone.utc)
    session.flush()
    safe_log_action(
        session,
        user_id=user.user_id,
        action="CANDIDATE_ARCHIVE" if archived else "CANDIDATE_RESTORE",
        resource_type="candidate",
        resource_id=candidate.candidate_id,
    )
    if commit:
        session.commit()
        session.refresh(candidate)
    return candidate


def can_access_application(session: Session, user: User, application_id: int) -> bool:
    try:
        get_scoped_application(session, user, application_id)
        return True
    except (PermissionDenied, Exception):
        return False


def assign_job_to_user(
    session: Session,
    *,
    user_id: int,
    job_id: int,
    assigned_by: int | None,
    commit: bool = True,
) -> UserJobAssignment:
    existing = session.get(UserJobAssignment, {"user_id": user_id, "job_id": job_id})
    if existing:
        return existing
    assignment = UserJobAssignment(user_id=user_id, job_id=job_id, assigned_by=assigned_by)
    session.add(assignment)
    session.flush()
    if commit:
        session.commit()
    return assignment


def remove_job_from_user(session: Session, *, user_id: int, job_id: int, commit: bool = True) -> None:
    existing = session.get(UserJobAssignment, {"user_id": user_id, "job_id": job_id})
    if existing:
        session.delete(existing)
        session.flush()
        if commit:
            session.commit()


def user_assigned_jobs(session: Session, user_id: int) -> list[Job]:
    return list(
        session.scalars(
            select(Job)
            .join(UserJobAssignment, UserJobAssignment.job_id == Job.job_id)
            .where(UserJobAssignment.user_id == user_id)
            .order_by(Job.job_title)
        )
    )
