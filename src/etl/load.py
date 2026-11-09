"""Load stage: transactional, idempotent ETL with per-row error reporting."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src import config
from src.audit.audit_logger import safe_log_action
from src.constants import DEFAULT_STAGE_NAMES, ETL_STATUSES
from src.cv_analysis.skills_extractor import canonicalize_skill_list
from src.database.models import (
    Application,
    ApplicationStageHistory,
    Candidate,
    ETLRowError,
    ETLRun,
    Job,
    JobRequiredSkill,
    Stage,
    User,
)
from src.etl.extract import detect_column_mapping, read_tabular_bytes, text_key
from src.etl.transform import canonicalize_dataframe, transform_row
from src.etl.validate import validate_mapping, validate_row


def ensure_default_stages(session: Session) -> list[Stage]:
    stages = list(session.scalars(select(Stage).order_by(Stage.stage_order)))
    if len(stages) >= len(DEFAULT_STAGE_NAMES):
        return stages
    existing = {stage.stage_name for stage in stages}
    next_order = max([stage.stage_order for stage in stages], default=0) + 1
    for name in DEFAULT_STAGE_NAMES:
        if name not in existing:
            session.add(
                Stage(
                    stage_name=name,
                    stage_order=next_order,
                    is_terminal=name.lower() == "hired",
                )
            )
            next_order += 1
    session.flush()
    return list(session.scalars(select(Stage).order_by(Stage.stage_order)))


def _find_or_create_job(
    session: Session,
    cache: dict[tuple[str, str], Job],
    *,
    job_title: str,
    department: str | None,
    description: str | None,
    source_name: str | None,
    skills: list[str],
) -> Job:
    key = (text_key(job_title), text_key(department or ""))
    if key in cache:
        job = cache[key]
    else:
        job = session.scalar(
            select(Job).where(
                func.lower(Job.job_title) == job_title.lower(),
                func.coalesce(func.lower(Job.department), "") == (department or "").lower(),
            )
        )
        if job is None:
            job = Job(
                job_title=job_title[:200],
                department=(department or None) and department[:150],
                job_description=(description or None) and description[:5000],
                source_name=(source_name or None) and source_name[:100],
                is_active=True,
            )
            session.add(job)
            session.flush()
        cache[key] = job

    if job.job_description == "":
        job.job_description = None
    if not job.job_description and description:
        job.job_description = description[:5000]

    existing_skills = set(
        session.scalars(select(JobRequiredSkill.skill_name).where(JobRequiredSkill.job_id == job.job_id))
    )
    if not existing_skills:
        for skill in canonicalize_skill_list(skills):
            session.add(JobRequiredSkill(job_id=job.job_id, skill_name=skill, importance=1.0, is_required=True))
        session.flush()
    return job


def run_etl(
    session: Session,
    frame,
    *,
    source_name: str,
    source_type: str,
    user_id: int | None,
    column_mapping: dict[str, str | None] | None = None,
    commit: bool = True,
) -> ETLRun:
    """Run the full load stage and return the persisted ``ETLRun`` row.

    Valid rows create/update candidates, jobs and applications. Re-running the
    same source does not create duplicate applications because of the
    ``(candidate_id, job_id)`` unique constraint and explicit duplicate checks.
    """
    started = datetime.now(timezone.utc)
    mapping = column_mapping or detect_column_mapping(list(frame.columns))
    run = ETLRun(
        source_name=(source_name or "unknown")[:255],
        source_type=(source_type or "CSV").upper()[:30],
        started_at=started,
        rows_read=len(frame),
        status="FAILED",
    )
    session.add(run)
    session.flush()

    mapping_errors = validate_mapping(mapping)
    if mapping_errors:
        for error in mapping_errors:
            session.add(
                ETLRowError(
                    etl_run_id=run.etl_run_id,
                    source_row_number=None,
                    field_name=error.get("field"),
                    error_code=error["code"],
                    error_message=error["message"],
                )
            )
        run.finished_at = datetime.now(timezone.utc)
        run.status = "FAILED"
        run.rows_rejected = len(frame)
        run.error_summary = "Cấu trúc tệp không hợp lệ: " + "; ".join(e["message"] for e in mapping_errors)
        safe_log_action(
            session,
            user_id=user_id,
            action="ETL_IMPORT",
            result="FAILURE",
            resource_type="etl_run",
            resource_id=run.etl_run_id,
            metadata={"source": run.source_name, "reason": "invalid_mapping"},
        )
        if commit:
            session.commit()
        return run

    try:
        stages = ensure_default_stages(session)
        stage_by_name = {stage.stage_name: stage for stage in stages}
        stage_names = list(stage_by_name)
        hired_stage = stage_by_name.get("Hired") or (stages[-1] if stages else None)
        default_stage = stages[0] if stages else None
        canonical = canonicalize_dataframe(frame, mapping)

        candidate_cache: dict[str, Candidate] = {
            candidate.email: candidate
            for candidate in session.scalars(select(Candidate).where(Candidate.email.is_not(None)))
        }
        job_cache: dict[tuple[str, str], Job] = {
            (text_key(job.job_title), text_key(job.department or "")): job for job in session.scalars(select(Job))
        }
        now = datetime.now(timezone.utc)
        stored_errors = 0
        rejected = 0
        valid = 0
        inserted = 0
        updated = 0
        duplicate = 0
        first_errors: list[str] = []

        for position, (_, raw) in enumerate(canonical.iterrows()):
            source_row_number = position + 2  # header occupies row 1
            row = transform_row(raw.to_dict(), stage_names=stage_names)
            errors = validate_row(row, now=now)
            if errors:
                rejected += 1
                for error in errors:
                    if stored_errors < config.MAX_STORED_ROW_ERRORS:
                        session.add(
                            ETLRowError(
                                etl_run_id=run.etl_run_id,
                                source_row_number=source_row_number,
                                field_name=error.get("field"),
                                error_code=error["code"],
                                error_message=error["message"],
                            )
                        )
                        stored_errors += 1
                if len(first_errors) < 5:
                    first_errors.append(f"Dòng {source_row_number}: {errors[0]['message']}")
                continue

            valid += 1
            applied_at = row["applied_at"] or now
            email = row["email"]
            candidate = candidate_cache.get(email) if email else None

            if candidate is not None and candidate.is_archived:
                rejected += 1
                valid -= 1
                if stored_errors < config.MAX_STORED_ROW_ERRORS:
                    session.add(
                        ETLRowError(
                            etl_run_id=run.etl_run_id,
                            source_row_number=source_row_number,
                            field_name="email",
                            error_code="CANDIDATE_ARCHIVED",
                            error_message="Ứng viên đã bị lưu trữ; không tự động tạo hồ sơ mới.",
                        )
                    )
                    stored_errors += 1
                continue

            if candidate is None:
                candidate = Candidate(
                    full_name=row["full_name"],
                    email=email,
                    phone=row["phone"],
                    is_archived=False,
                )
                session.add(candidate)
                session.flush()
                if email:
                    candidate_cache[email] = candidate
            else:
                changed = False
                if row["full_name"] and row["full_name"] != candidate.full_name:
                    candidate.full_name = row["full_name"]
                    changed = True
                if row["phone"] and row["phone"] != candidate.phone:
                    candidate.phone = row["phone"]
                    changed = True
                if changed:
                    candidate.updated_at = now
                    updated += 1

            job = _find_or_create_job(
                session,
                job_cache,
                job_title=row["job_title"],
                department=row["department"],
                description=row["job_description"],
                source_name=row["source_name"],
                skills=row["job_skills"],
            )

            existing = session.scalar(
                select(Application).where(
                    Application.candidate_id == candidate.candidate_id,
                    Application.job_id == job.job_id,
                )
            )
            if existing is not None:
                duplicate += 1
                continue

            stage = stage_by_name.get(row["stage"] or "") or default_stage
            status = row["current_status"]
            if status == "HIRED" and hired_stage is not None:
                stage = hired_stage

            application = Application(
                candidate_id=candidate.candidate_id,
                job_id=job.job_id,
                applied_at=applied_at,
                current_stage_id=stage.stage_id if stage else None,
                current_status=status,
                source_name=row["source_name"] or job.source_name,
                created_at=now,
                updated_at=now,
            )
            session.add(application)
            session.flush()

            if stage is not None:
                history = ApplicationStageHistory(
                    application_id=application.application_id,
                    stage_id=stage.stage_id,
                    entered_at=applied_at,
                    exited_at=None,
                    result="PENDING",
                )
                if status in {"HIRED", "REJECTED", "WITHDRAWN", "OFFER_DECLINED"}:
                    history.exited_at = applied_at
                    history.result = {
                        "HIRED": "PASSED",
                        "REJECTED": "FAILED",
                        "WITHDRAWN": "SKIPPED",
                        "OFFER_DECLINED": "SKIPPED",
                    }[status]
                session.add(history)
            inserted += 1

        run.finished_at = datetime.now(timezone.utc)
        run.rows_valid = valid
        run.rows_inserted = inserted
        run.rows_updated = updated
        run.rows_duplicate = duplicate
        run.rows_rejected = rejected
        if len(frame) == 0 or (valid == 0 and rejected > 0):
            run.status = "FAILED"
        elif rejected > 0:
            run.status = "PARTIAL_SUCCESS"
        else:
            run.status = "SUCCESS"
        if rejected:
            summary = f"{rejected} dòng bị từ chối."
            if first_errors:
                summary += " Ví dụ: " + " | ".join(first_errors)
            if stored_errors >= config.MAX_STORED_ROW_ERRORS:
                summary += f" (Chỉ lưu tối đa {config.MAX_STORED_ROW_ERRORS} lỗi chi tiết.)"
            run.error_summary = summary

        session.flush()
        safe_log_action(
            session,
            user_id=user_id,
            action="ETL_IMPORT",
            result="SUCCESS" if run.status == "SUCCESS" else "FAILURE",
            resource_type="etl_run",
            resource_id=run.etl_run_id,
            metadata={
                "source": run.source_name,
                "source_type": run.source_type,
                "rows_read": run.rows_read,
                "rows_inserted": run.rows_inserted,
                "rows_updated": run.rows_updated,
                "rows_duplicate": run.rows_duplicate,
                "rows_rejected": run.rows_rejected,
                "status": run.status,
            },
        )
        if commit:
            session.commit()
            session.refresh(run)
        return run

    except Exception as exc:
        session.rollback()
        failed = ETLRun(
            source_name=(source_name or "unknown")[:255],
            source_type=(source_type or "CSV").upper()[:30],
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            rows_read=len(frame),
            status="FAILED",
            error_summary=f"Lỗi hệ thống khi nạp dữ liệu: {exc}"[:2000],
        )
        session.add(failed)
        session.flush()
        safe_log_action(
            session,
            user_id=user_id,
            action="ETL_IMPORT",
            result="FAILURE",
            resource_type="etl_run",
            resource_id=failed.etl_run_id,
            metadata={"source": failed.source_name, "reason": "exception"},
        )
        if commit:
            session.commit()
            session.refresh(failed)
        return failed


def run_etl_from_bytes(
    session: Session,
    data: bytes,
    *,
    filename: str,
    source_name: str | None = None,
    user_id: int | None,
    column_mapping: dict[str, str | None] | None = None,
) -> ETLRun:
    frame = read_tabular_bytes(data, filename)
    source_type = "EXCEL" if filename.lower().endswith(".xlsx") else "CSV"
    return run_etl(
        session,
        frame,
        source_name=source_name or filename,
        source_type=source_type,
        user_id=user_id,
        column_mapping=column_mapping,
    )
