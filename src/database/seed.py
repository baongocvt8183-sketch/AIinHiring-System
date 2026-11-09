"""Deterministic demo seed data (fictional people only)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src import config
from src.auth.authentication import create_user
from src.constants import (
    APPLICATION_STATUSES,
    DEFAULT_STAGE_NAMES,
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_HR,
    ROLE_HIRING,
    ROLE_LABELS,
)
from src.cv_analysis.pdf_extractor import extract_pdf_text, store_pdf
from src.cv_analysis.resume_matcher import match_skills
from src.cv_analysis.skills_extractor import extract_skills, summarize_sections
from src.database.models import (
    AICVAnalysis,
    AIAnalysisReview,
    Application,
    ApplicationNote,
    ApplicationStageHistory,
    AuditLog,
    Candidate,
    CandidateDocument,
    ETLRowError,
    ETLRun,
    Job,
    JobRequiredSkill,
    Role,
    Stage,
    User,
    UserJobAssignment,
    UserRole,
)
from src.database.sample_data import write_sample_files


DEMO_ACCOUNTS = [
    {
        "username": "hr",
        "password": "Hr@12345",
        "email": "hr@demo.local",
        "full_name": "Nguyễn Thu HR",
        "role": ROLE_HR,
    },
    {
        "username": "hiring",
        "password": "Hiring@12345",
        "email": "hiring@demo.local",
        "full_name": "Trần Minh Hiring",
        "role": ROLE_HIRING,
    },
    {
        "username": "admin",
        "password": "Admin@12345",
        "email": "admin@demo.local",
        "full_name": "Quản trị hệ thống",
        "role": ROLE_ADMIN,
    },
    {
        "username": "auditor",
        "password": "Auditor@12345",
        "email": "auditor@demo.local",
        "full_name": "Lê Kiểm Toán",
        "role": ROLE_AUDITOR,
    },
]


def _dt(now: datetime, days_ago: float) -> datetime:
    return now - timedelta(days=days_ago)


def _stage_id(stages: dict[str, Stage], name: str) -> int:
    if name not in stages:
        raise KeyError(f"Stage not configured: {name}")
    return stages[name].stage_id


def _add_application(
    session: Session,
    *,
    candidate: Candidate,
    job: Job,
    stages: dict[str, Stage],
    now: datetime,
    applied_days: float,
    source: str,
    status: str,
    current_stage: str,
    history: list[tuple[str, float, float | None, str]],
) -> Application:
    application = Application(
        candidate_id=candidate.candidate_id,
        job_id=job.job_id,
        applied_at=_dt(now, applied_days),
        current_stage_id=_stage_id(stages, current_stage),
        current_status=status,
        source_name=source,
        created_at=_dt(now, applied_days),
        updated_at=_dt(now, 1),
    )
    session.add(application)
    session.flush()
    for stage_name, entered, exited, result in history:
        session.add(
            ApplicationStageHistory(
                application_id=application.application_id,
                stage_id=_stage_id(stages, stage_name),
                entered_at=_dt(now, entered),
                exited_at=None if exited is None else _dt(now, exited),
                result=result,
            )
        )
    session.flush()
    return application


def _add_analysis(
    session: Session,
    *,
    application: Application,
    candidate: Candidate,
    file_path,
    uploaded_by: int,
    reviewer_id: int | None = None,
    review_decision: str | None = None,
    created_at: datetime | None = None,
    needs_ocr_only: bool = False,
) -> AICVAnalysis:
    data = file_path.read_bytes()
    stored = store_pdf(data, file_path.name)
    document = CandidateDocument(
        candidate_id=candidate.candidate_id,
        application_id=application.application_id,
        storage_key=stored.storage_key,
        original_filename=stored.original_filename,
        mime_type=stored.mime_type,
        file_size_bytes=stored.size_bytes,
        sha256_hash=stored.sha256,
        uploaded_by=uploaded_by,
        uploaded_at=created_at or datetime.now(timezone.utc),
    )
    session.add(document)
    session.flush()

    extraction = extract_pdf_text(stored.path)
    required = list(
        session.scalars(select(JobRequiredSkill.skill_name).where(JobRequiredSkill.job_id == application.job_id))
    )
    analysis = AICVAnalysis(
        application_id=application.application_id,
        document_id=document.document_id,
        skills_extracted=[],
        missing_skills=[],
        processing_status="NEEDS_OCR" if needs_ocr_only else "FAILED",
        review_status="PENDING_REVIEW",
        method_version=config.CV_METHOD_VERSION,
        created_at=created_at or datetime.now(timezone.utc),
    )
    if extraction.needs_ocr:
        analysis.processing_status = "NEEDS_OCR"
        analysis.processing_error = f"PDF chỉ có {extraction.char_count} ký tự; cần OCR."
    elif extraction.error:
        analysis.processing_status = "FAILED"
        analysis.processing_error = extraction.error
    else:
        skills = extract_skills(extraction.text)
        result = match_skills(skills, required)
        experience, projects = summarize_sections(extraction.text)
        analysis.skills_extracted = skills
        analysis.missing_skills = result.missing_skills
        analysis.skill_match_score = result.score
        analysis.processing_status = result.status
        analysis.experience_summary = experience or None
        analysis.projects_summary = projects or None
        analysis.extracted_text = extraction.text[:200_000]
    session.add(analysis)
    session.flush()

    if reviewer_id and review_decision:
        session.add(
            AIAnalysisReview(
                analysis_id=analysis.analysis_id,
                reviewer_id=reviewer_id,
                decision=review_decision,
                review_note="Duyệt kết quả demo sau khi HR kiểm tra thủ công.",
                created_at=created_at or datetime.now(timezone.utc),
            )
        )
        analysis.review_status = review_decision
        session.flush()
    return analysis


def seed_database(session: Session) -> None:
    """Seed a fresh database. Safe to call repeatedly (no-op when users exist)."""
    if session.scalar(select(func.count(User.user_id))) > 0:
        return

    now = datetime.now(timezone.utc)

    # Roles -----------------------------------------------------------------
    role_specs = {
        ROLE_HR: "Quản lý tuyển dụng, nhập dữ liệu, duyệt kết quả AI.",
        ROLE_HIRING: "Quản lý tuyển dụng theo vị trí được giao, thêm nhận xét.",
        ROLE_ADMIN: "Quản trị hệ thống, tài khoản và cấu hình.",
        ROLE_AUDITOR: "Kiểm toán nhật ký, chỉ đọc.",
    }
    roles: dict[str, Role] = {}
    for name, description in role_specs.items():
        role = session.scalar(select(Role).where(Role.role_name == name))
        if role is None:
            role = Role(role_name=name, description=description)
            session.add(role)
            session.flush()
        roles[name] = role

    # Stages ----------------------------------------------------------------
    # `sql/seed.sql` may already have inserted the catalogue; reuse it instead
    # of violating the unique stage name/order constraints.
    stages: dict[str, Stage] = {}
    for order, name in enumerate(DEFAULT_STAGE_NAMES, start=1):
        stage = session.scalar(select(Stage).where(Stage.stage_name == name))
        if stage is None:
            stage = Stage(stage_name=name, stage_order=order, is_terminal=(name == "Hired"))
            session.add(stage)
            session.flush()
        else:
            stage.stage_order = order
            stage.is_terminal = name == "Hired"
        stages[name] = stage
    session.flush()

    # Users -----------------------------------------------------------------
    users: dict[str, User] = {}
    for account in DEMO_ACCOUNTS:
        user = create_user(
            session,
            username=account["username"],
            email=account["email"],
            full_name=account["full_name"],
            password=account["password"],
            role_names=[account["role"]],
        )
        users[account["username"]] = user
    hr = users["hr"]
    hiring = users["hiring"]
    auditor = users["auditor"]

    # Jobs and required skills ---------------------------------------------
    job_specs = [
        (
            "AI Engineer",
            "AI Lab",
            "Thiết kế, huấn luyện và triển khai mô hình AI/NLP; làm việc với dữ liệu tiếng Việt.",
            [("Python", 1.0), ("Machine Learning", 1.0), ("PyTorch", 1.0), ("SQL", 0.8), ("Docker", 0.7), ("NLP", 0.6)],
        ),
        (
            "Data Analyst",
            "Data",
            "Phân tích dữ liệu tuyển dụng, xây dựng dashboard và báo cáo KPI.",
            [("SQL", 1.0), ("Python", 1.0), ("Power BI", 0.9), ("Excel", 0.8), ("Statistics", 0.7)],
        ),
        (
            "Backend Developer",
            "Engineering",
            "Xây dựng API và dịch vụ backend ổn định, bảo mật cho hệ thống tuyển dụng.",
            [("Python", 1.0), ("FastAPI", 0.9), ("PostgreSQL", 0.9), ("Docker", 0.7), ("REST API", 0.7)],
        ),
    ]
    jobs: dict[str, Job] = {}
    for title, department, description, skills in job_specs:
        job = Job(
            job_title=title,
            department=department,
            job_description=description,
            source_name="Demo Seed",
            is_active=True,
            created_at=now - timedelta(days=120),
        )
        session.add(job)
        session.flush()
        jobs[title] = job
        for skill_name, importance in skills:
            session.add(
                JobRequiredSkill(job_id=job.job_id, skill_name=skill_name, importance=importance, is_required=True)
            )
    session.flush()

    # Hiring Manager is scoped to AI Engineer + Data Analyst only.
    for title in ("AI Engineer", "Data Analyst"):
        session.add(
            UserJobAssignment(
                user_id=hiring.user_id,
                job_id=jobs[title].job_id,
                assigned_by=hr.user_id,
            )
        )
    session.flush()

    # Candidates ------------------------------------------------------------
    candidate_specs = [
        ("Nguyễn Văn An", "an.nguyen@example.com", "0901234567"),
        ("Trần Thị Bình", "binh.tran@example.com", "0912345678"),
        ("Lê Minh Cường", "cuong.le@example.com", "0923456789"),
        ("Phạm Thu Dung", "dung.pham@example.com", "0934567890"),
        ("Hoàng Văn Em", "em.hoang@example.com", "0945678901"),
        ("Vũ Thị Giang", "giang.vu@example.com", "0956789012"),
        ("Đỗ Văn Hùng", "hung.do@example.com", "0967890123"),
        ("Bùi Thị Lan", "lan.bui@example.com", "0978901234"),
        ("Ngô Văn Minh", "minh.ngo@example.com", "0989012345"),
        ("Đinh Thị Nga", "nga.dinh@example.com", "0990123456"),
        ("Lý Văn Phong", "phong.ly@example.com", "0901234568"),
        ("Trương Thị Quỳnh", "quynh.truong@example.com", "0912345679"),
        ("Phan Văn Sơn", None, "0923456780"),
        ("Hồ Thị Tâm", "tam.ho@example.com", "0934567891"),
    ]
    candidates: list[Candidate] = []
    for name, email, phone in candidate_specs:
        candidate = Candidate(
            full_name=name,
            email=email,
            phone=phone,
            created_at=now - timedelta(days=90),
            updated_at=now - timedelta(days=10),
        )
        session.add(candidate)
        candidates.append(candidate)
    session.flush()

    # Applications + stage histories ---------------------------------------
    app_specs = [
        # candidate, job, applied_days, source, status, current stage, histories
        (candidates[0], "AI Engineer", 70, "LinkedIn", "HIRED", "Hired", [
            ("CV Screening", 70, 66, "PASSED"), ("Online Test", 66, 61, "PASSED"),
            ("Technical Interview", 61, 55, "PASSED"), ("HR Interview", 55, 49, "PASSED"),
            ("Offer", 49, 44, "PASSED"), ("Hired", 44, 43, "PASSED"),
        ]),
        (candidates[1], "AI Engineer", 32, "TopCV", "IN_PROGRESS", "Technical Interview", [
            ("CV Screening", 32, 29, "PASSED"), ("Online Test", 29, 24, "PASSED"),
            ("Technical Interview", 24, None, "PENDING"),
        ]),
        (candidates[2], "Data Analyst", 65, "CareerViet", "HIRED", "Hired", [
            ("CV Screening", 65, 61, "PASSED"), ("Online Test", 61, 56, "PASSED"),
            ("Technical Interview", 56, 50, "PASSED"), ("HR Interview", 50, 45, "PASSED"),
            ("Offer", 45, 40, "PASSED"), ("Hired", 40, 39, "PASSED"),
        ]),
        (candidates[3], "Data Analyst", 28, "LinkedIn", "REJECTED", "CV Screening", [
            ("CV Screening", 28, 26, "FAILED"),
        ]),
        (candidates[4], "Backend Developer", 40, "TopCV", "IN_PROGRESS", "HR Interview", [
            ("CV Screening", 40, 36, "PASSED"), ("Online Test", 36, 31, "PASSED"),
            ("Technical Interview", 31, 25, "PASSED"), ("HR Interview", 25, None, "PENDING"),
        ]),
        (candidates[5], "AI Engineer", 24, "Facebook", "WITHDRAWN", "Online Test", [
            ("CV Screening", 24, 22, "PASSED"), ("Online Test", 22, 20, "SKIPPED"),
        ]),
        (candidates[6], "Data Analyst", 55, "LinkedIn", "OFFER_DECLINED", "Offer", [
            ("CV Screening", 55, 52, "PASSED"), ("Online Test", 52, 48, "PASSED"),
            ("Technical Interview", 48, 43, "PASSED"), ("HR Interview", 43, 38, "PASSED"),
            ("Offer", 38, 34, "SKIPPED"),
        ]),
        (candidates[7], "Backend Developer", 48, "Referral", "HIRED", "Hired", [
            ("CV Screening", 48, 44, "PASSED"), ("Online Test", 44, 39, "PASSED"),
            ("Technical Interview", 39, 33, "PASSED"), ("HR Interview", 33, 28, "PASSED"),
            ("Offer", 28, 23, "PASSED"), ("Hired", 23, 22, "PASSED"),
        ]),
        (candidates[8], "Data Analyst", 18, "TopCV", "IN_PROGRESS", "Online Test", [
            ("CV Screening", 18, 15, "PASSED"), ("Online Test", 15, None, "PENDING"),
        ]),
        (candidates[9], "AI Engineer", 12, "LinkedIn", "IN_PROGRESS", "CV Screening", [
            ("CV Screening", 12, None, "PENDING"),
        ]),
        (candidates[10], "Backend Developer", 26, "CareerViet", "REJECTED", "Technical Interview", [
            ("CV Screening", 26, 23, "PASSED"), ("Online Test", 23, 19, "PASSED"),
            ("Technical Interview", 19, 16, "FAILED"),
        ]),
        (candidates[11], "Data Analyst", 35, "Facebook", "ON_HOLD", "HR Interview", [
            ("CV Screening", 35, 31, "PASSED"), ("Online Test", 31, 26, "PASSED"),
            ("Technical Interview", 26, 21, "PASSED"), ("HR Interview", 21, None, "PENDING"),
        ]),
        (candidates[12], "Data Analyst", 9, "Referral", "IN_PROGRESS", "CV Screening", [
            ("CV Screening", 9, None, "PENDING"),
        ]),
        (candidates[13], "AI Engineer", 7, "TopCV", "IN_PROGRESS", "CV Screening", [
            ("CV Screening", 7, None, "PENDING"),
        ]),
        (candidates[12], "Backend Developer", 3, "Referral", "IN_PROGRESS", "CV Screening", [
            ("CV Screening", 3, None, "PENDING"),
        ]),
    ]
    applications: list[Application] = []
    for candidate, title, applied_days, source, status, current_stage, history in app_specs:
        applications.append(
            _add_application(
                session,
                candidate=candidate,
                job=jobs[title],
                stages=stages,
                now=now,
                applied_days=applied_days,
                source=source,
                status=status,
                current_stage=current_stage,
                history=history,
            )
        )

    # Notes -----------------------------------------------------------------
    note_specs = [
        (applications[0], hr, "INTERVIEW", "Ứng viên trình bày tốt, tư duy hệ thống rõ ràng. Đề xuất offer."),
        (applications[1], hiring, "ASSESSMENT", "Cần kiểm tra thêm kinh nghiệm triển khai mô hình NLP thực tế."),
        (applications[4], hiring, "INTERVIEW", "Kỹ năng backend tốt, cần xác nhận lịch onsite."),
        (applications[11], hr, "REVIEW", "Tạm dừng do vị trí đang chờ phê duyệt ngân sách."),
    ]
    for application, author, note_type, text in note_specs:
        session.add(
            ApplicationNote(
                application_id=application.application_id,
                author_id=author.user_id,
                note_type=note_type,
                note_text=text,
                created_at=now - timedelta(days=2),
            )
        )
    session.flush()

    # Documents and AI analyses --------------------------------------------
    paths = write_sample_files()
    _add_analysis(
        session,
        application=applications[0],
        candidate=candidates[0],
        file_path=paths["cv_nguyen_van_an.pdf"],
        uploaded_by=hr.user_id,
        reviewer_id=hr.user_id,
        review_decision="APPROVED",
        created_at=now - timedelta(days=45),
    )
    _add_analysis(
        session,
        application=applications[1],
        candidate=candidates[1],
        file_path=paths["cv_tran_thi_binh.pdf"],
        uploaded_by=hr.user_id,
        created_at=now - timedelta(days=20),
    )
    _add_analysis(
        session,
        application=applications[2],
        candidate=candidates[2],
        file_path=paths["cv_le_minh_cuong.pdf"],
        uploaded_by=hr.user_id,
        reviewer_id=hr.user_id,
        review_decision="APPROVED",
        created_at=now - timedelta(days=35),
    )
    _add_analysis(
        session,
        application=applications[9],
        candidate=candidates[9],
        file_path=paths["cv_scan_only.pdf"],
        uploaded_by=hr.user_id,
        created_at=now - timedelta(days=4),
        needs_ocr_only=True,
    )

    # ETL history ------------------------------------------------------------
    etl_run = ETLRun(
        source_name="candidates_sample.csv",
        source_type="CSV",
        started_at=now - timedelta(days=5, minutes=3),
        finished_at=now - timedelta(days=5, minutes=2),
        rows_read=18,
        rows_valid=14,
        rows_inserted=12,
        rows_updated=1,
        rows_duplicate=1,
        rows_rejected=4,
        status="PARTIAL_SUCCESS",
        error_summary="4 dòng bị từ chối. Ví dụ: Dòng 6: Họ tên không được để trống. | Dòng 16: Ngày ứng tuyển không hợp lệ.",
    )
    session.add(etl_run)
    session.flush()
    for row_number, field, code, message in [
        (5, "email", "INVALID_EMAIL", "Email không đúng định dạng."),
        (6, "full_name", "REQUIRED_FIELD", "Họ tên không được để trống."),
        (16, "applied_at", "INVALID_DATE", "Ngày ứng tuyển không hợp lệ."),
        (17, "applied_at", "INVALID_DATE", "Ngày ứng tuyển nằm trong tương lai."),
    ]:
        session.add(
            ETLRowError(
                etl_run_id=etl_run.etl_run_id,
                source_row_number=row_number,
                field_name=field,
                error_code=code,
                error_message=message,
            )
        )

    # Audit history ----------------------------------------------------------
    audit_specs = [
        (hr.user_id, "LOGIN_SUCCESS", "session", None, "SUCCESS", {}, now - timedelta(hours=1)),
        (hr.user_id, "ETL_IMPORT", "etl_run", etl_run.etl_run_id, "SUCCESS", {"status": "PARTIAL_SUCCESS", "rows_inserted": 12}, now - timedelta(days=5)),
        (hr.user_id, "AI_ANALYSIS_REVIEW", "ai_cv_analysis", 1, "SUCCESS", {"decision": "APPROVED"}, now - timedelta(days=2)),
        (hr.user_id, "CV_ANALYZE", "ai_cv_analysis", 2, "SUCCESS", {"processing_status": "SUCCESS"}, now - timedelta(days=20)),
        (hiring.user_id, "ACCESS_DENIED", "user", None, "DENIED", {"permission": "manage_users"}, now - timedelta(hours=3)),
        (auditor.user_id, "AUDIT_VIEW", "audit_logs", None, "SUCCESS", {"filter": "all"}, now - timedelta(hours=2)),
        (hr.user_id, "APPLICATION_STATUS_CHANGE", "application", applications[0].application_id, "SUCCESS", {"new_status": "HIRED"}, now - timedelta(days=43)),
    ]
    for user_id, action, resource_type, resource_id, result, metadata, created_at in audit_specs:
        session.add(
            AuditLog(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id is not None else None,
                result=result,
                log_metadata=metadata,
                created_at=created_at,
            )
        )

    session.commit()
    config.ensure_directories()
