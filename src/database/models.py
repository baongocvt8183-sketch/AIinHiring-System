"""SQLAlchemy ORM models for the recruitment data warehouse.

The same models create a PostgreSQL schema (production) and a SQLite schema
(quick local demo). PostgreSQL-only types are used through ``with_variant``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship

from src.constants import (
    APPLICATION_STATUSES,
    AUDIT_RESULTS,
    ETL_STATUSES,
    PROCESSING_STATUSES,
    REVIEW_DECISIONS,
    REVIEW_STATUSES,
    STAGE_RESULTS,
)

BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")
JSON_VARIANT = JSON().with_variant(JSONB, "postgresql")
INET_VARIANT = INET().with_variant(String(45), "sqlite")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sql_in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Identity and access
# ---------------------------------------------------------------------------
class Role(Base):
    __tablename__ = "roles"

    role_id = Column(BIGINT_PK, primary_key=True, autoincrement=True)
    role_name = Column(String(50), nullable=False, unique=True)
    description = Column(Text)

    users = relationship(
        "User",
        secondary="user_roles",
        primaryjoin="Role.role_id == UserRole.role_id",
        secondaryjoin="User.user_id == UserRole.user_id",
        back_populates="roles",
        viewonly=True,
    )


class User(Base):
    __tablename__ = "users"

    user_id = Column(BIGINT_PK, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    full_name = Column(String(200), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    roles = relationship(
        "Role",
        secondary="user_roles",
        primaryjoin="User.user_id == UserRole.user_id",
        secondaryjoin="Role.role_id == UserRole.role_id",
        back_populates="users",
        lazy="selectin",
    )
    job_assignments = relationship(
        "UserJobAssignment",
        foreign_keys="UserJobAssignment.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        CheckConstraint("assigned_by IS NULL OR assigned_by <> user_id", name="ck_user_role_not_self"),
    )

    user_id = Column(BIGINT_PK, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(BIGINT_PK, ForeignKey("roles.role_id", ondelete="RESTRICT"), primary_key=True)
    assigned_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    assigned_by = Column(BIGINT_PK, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)


class UserJobAssignment(Base):
    """Scope of a Hiring Manager (or any user) to specific recruiting jobs."""

    __tablename__ = "user_job_assignments"

    user_id = Column(BIGINT_PK, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    job_id = Column(BIGINT_PK, ForeignKey("jobs.job_id", ondelete="CASCADE"), primary_key=True)
    assigned_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    assigned_by = Column(BIGINT_PK, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)

    user = relationship("User", foreign_keys=[user_id], back_populates="job_assignments")
    job = relationship("Job", back_populates="assignments")


# ---------------------------------------------------------------------------
# Recruiting data
# ---------------------------------------------------------------------------
class Candidate(Base):
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint("email", name="uq_candidates_email"),
        Index("ix_candidates_full_name", "full_name"),
    )

    candidate_id = Column(BIGINT_PK, primary_key=True, autoincrement=True)
    full_name = Column(String(200), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    is_archived = Column(Boolean, nullable=False, default=False)

    applications = relationship("Application", back_populates="candidate", cascade="all, delete-orphan")
    documents = relationship("CandidateDocument", back_populates="candidate", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_title_department", "job_title", "department"),)

    job_id = Column(BIGINT_PK, primary_key=True, autoincrement=True)
    job_title = Column(String(200), nullable=False)
    department = Column(String(150))
    job_description = Column(Text)
    source_name = Column(String(100))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    applications = relationship("Application", back_populates="job")
    required_skills = relationship("JobRequiredSkill", back_populates="job", cascade="all, delete-orphan")
    assignments = relationship("UserJobAssignment", back_populates="job", cascade="all, delete-orphan")


class Stage(Base):
    __tablename__ = "stages"

    stage_id = Column(BIGINT_PK, primary_key=True, autoincrement=True)
    stage_name = Column(String(100), nullable=False, unique=True)
    stage_order = Column(Integer, nullable=False, unique=True)
    is_terminal = Column(Boolean, nullable=False, default=False)

    histories = relationship("ApplicationStageHistory", back_populates="stage")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_application_candidate_job"),
        CheckConstraint(f"current_status IN ({sql_in(APPLICATION_STATUSES)})", name="ck_application_status"),
        Index("ix_applications_candidate_id", "candidate_id"),
        Index("ix_applications_job_id", "job_id"),
        Index("ix_applications_current_status", "current_status"),
        Index("ix_applications_applied_at", "applied_at"),
    )

    application_id = Column(BIGINT_PK, primary_key=True, autoincrement=True)
    candidate_id = Column(BIGINT_PK, ForeignKey("candidates.candidate_id", ondelete="RESTRICT"), nullable=False)
    job_id = Column(BIGINT_PK, ForeignKey("jobs.job_id", ondelete="RESTRICT"), nullable=False)
    applied_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    current_stage_id = Column(BIGINT_PK, ForeignKey("stages.stage_id", ondelete="SET NULL"))
    current_status = Column(String(30), nullable=False, default="IN_PROGRESS")
    source_name = Column(String(100))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    candidate = relationship("Candidate", back_populates="applications")
    job = relationship("Job", back_populates="applications")
    current_stage = relationship("Stage", foreign_keys=[current_stage_id])
    stage_history = relationship(
        "ApplicationStageHistory",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationStageHistory.entered_at",
    )
    analyses = relationship("AICVAnalysis", back_populates="application", cascade="all, delete-orphan")
    notes = relationship("ApplicationNote", back_populates="application", cascade="all, delete-orphan")
    documents = relationship("CandidateDocument", back_populates="application")


class ApplicationStageHistory(Base):
    __tablename__ = "application_stage_history"
    __table_args__ = (
        CheckConstraint("exited_at IS NULL OR exited_at >= entered_at", name="ck_stage_history_time"),
        CheckConstraint(f"result IS NULL OR result IN ({sql_in(STAGE_RESULTS)})", name="ck_stage_history_result"),
        Index("ix_stage_history_application_entered", "application_id", "entered_at"),
        Index("ix_stage_history_stage_entered", "stage_id", "entered_at"),
        # Partial unique index: an application may have only one open stage.
        Index(
            "uq_open_stage_history",
            "application_id",
            unique=True,
            sqlite_where=text("exited_at IS NULL"),
            postgresql_where=text("exited_at IS NULL"),
        ),
    )

    history_id = Column(BIGINT_PK, primary_key=True, autoincrement=True)
    application_id = Column(BIGINT_PK, ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False)
    stage_id = Column(BIGINT_PK, ForeignKey("stages.stage_id", ondelete="RESTRICT"), nullable=False)
    entered_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    exited_at = Column(DateTime(timezone=True), nullable=True)
    result = Column(String(30), nullable=True)
    notes = Column(Text)

    application = relationship("Application", back_populates="stage_history")
    stage = relationship("Stage", back_populates="histories")


class JobRequiredSkill(Base):
    __tablename__ = "job_required_skills"
    __table_args__ = (
        CheckConstraint("importance >= 0 AND importance <= 1", name="ck_required_skill_importance"),
    )

    job_id = Column(BIGINT_PK, ForeignKey("jobs.job_id", ondelete="CASCADE"), primary_key=True)
    skill_name = Column(String(100), primary_key=True)
    importance = Column(Numeric(4, 3), nullable=False, default=Decimal("1.000"))
    is_required = Column(Boolean, nullable=False, default=True)

    job = relationship("Job", back_populates="required_skills")


class CandidateDocument(Base):
    __tablename__ = "candidate_documents"

    document_id = Column(BIGINT_PK, primary_key=True, autoincrement=True)
    candidate_id = Column(BIGINT_PK, ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False)
    application_id = Column(BIGINT_PK, ForeignKey("applications.application_id", ondelete="SET NULL"))
    storage_key = Column(Text, nullable=False, unique=True)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    sha256_hash = Column(String(64))
    uploaded_by = Column(BIGINT_PK, ForeignKey("users.user_id", ondelete="SET NULL"))
    uploaded_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    candidate = relationship("Candidate", back_populates="documents")
    application = relationship("Application", back_populates="documents")
    uploader = relationship("User")
    analyses = relationship("AICVAnalysis", back_populates="document")


class AICVAnalysis(Base):
    __tablename__ = "ai_cv_analysis"
    __table_args__ = (
        CheckConstraint(
            "skill_match_score IS NULL OR (skill_match_score >= 0 AND skill_match_score <= 100)",
            name="ck_ai_skill_score",
        ),
        CheckConstraint(f"processing_status IN ({sql_in(PROCESSING_STATUSES)})", name="ck_ai_processing_status"),
        CheckConstraint(f"review_status IN ({sql_in(REVIEW_STATUSES)})", name="ck_ai_review_status"),
        Index("ix_ai_analysis_application_created", "application_id", "created_at"),
    )

    analysis_id = Column(BIGINT_PK, primary_key=True, autoincrement=True)
    application_id = Column(BIGINT_PK, ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False)
    document_id = Column(BIGINT_PK, ForeignKey("candidate_documents.document_id", ondelete="SET NULL"))
    skills_extracted = Column(JSON_VARIANT, nullable=False, default=list)
    missing_skills = Column(JSON_VARIANT, nullable=False, default=list)
    experience_summary = Column(Text)
    projects_summary = Column(Text)
    extracted_text = Column(Text)
    skill_match_score = Column(Numeric(5, 2))
    processing_status = Column(String(30), nullable=False, default="PENDING")
    review_status = Column(String(30), nullable=False, default="PENDING_REVIEW")
    processing_error = Column(Text)
    method_version = Column(String(100))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    application = relationship("Application", back_populates="analyses")
    document = relationship("CandidateDocument", back_populates="analyses")
    reviews = relationship(
        "AIAnalysisReview", back_populates="analysis", cascade="all, delete-orphan", order_by="AIAnalysisReview.created_at"
    )


class AIAnalysisReview(Base):
    __tablename__ = "ai_analysis_reviews"
    __table_args__ = (
        CheckConstraint(f"decision IN ({sql_in(REVIEW_DECISIONS)})", name="ck_ai_review_decision"),
    )

    review_id = Column(BIGINT_PK, primary_key=True, autoincrement=True)
    analysis_id = Column(BIGINT_PK, ForeignKey("ai_cv_analysis.analysis_id", ondelete="CASCADE"), nullable=False)
    reviewer_id = Column(BIGINT_PK, ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    decision = Column(String(30), nullable=False)
    review_note = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    analysis = relationship("AICVAnalysis", back_populates="reviews")
    reviewer = relationship("User")


class ApplicationNote(Base):
    __tablename__ = "application_notes"

    note_id = Column(BIGINT_PK, primary_key=True, autoincrement=True)
    application_id = Column(BIGINT_PK, ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False)
    author_id = Column(BIGINT_PK, ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    note_type = Column(String(30), nullable=False, default="GENERAL")
    note_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    application = relationship("Application", back_populates="notes")
    author = relationship("User")


# ---------------------------------------------------------------------------
# ETL and audit
# ---------------------------------------------------------------------------
class ETLRun(Base):
    __tablename__ = "etl_runs"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in(ETL_STATUSES)})", name="ck_etl_status"),
        Index("ix_etl_runs_started_status", "started_at", "status"),
    )

    etl_run_id = Column(BIGINT_PK, primary_key=True, autoincrement=True)
    source_name = Column(String(255), nullable=False)
    source_type = Column(String(30), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at = Column(DateTime(timezone=True))
    rows_read = Column(BigInteger, nullable=False, default=0)
    rows_valid = Column(BigInteger, nullable=False, default=0)
    rows_inserted = Column(BigInteger, nullable=False, default=0)
    rows_updated = Column(BigInteger, nullable=False, default=0)
    rows_duplicate = Column(BigInteger, nullable=False, default=0)
    rows_rejected = Column(BigInteger, nullable=False, default=0)
    status = Column(String(30), nullable=False, default="FAILED")
    error_summary = Column(Text)

    errors = relationship("ETLRowError", back_populates="run", cascade="all, delete-orphan")


class ETLRowError(Base):
    __tablename__ = "etl_row_errors"

    etl_error_id = Column(BIGINT_PK, primary_key=True, autoincrement=True)
    etl_run_id = Column(BIGINT_PK, ForeignKey("etl_runs.etl_run_id", ondelete="CASCADE"), nullable=False)
    source_row_number = Column(BigInteger)
    field_name = Column(String(100))
    error_code = Column(String(100), nullable=False)
    error_message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    run = relationship("ETLRun", back_populates="errors")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(f"result IN ({sql_in(AUDIT_RESULTS)})", name="ck_audit_result"),
        Index("ix_audit_logs_created", "created_at"),
        Index("ix_audit_logs_action", "action"),
    )

    audit_id = Column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id = Column(BIGINT_PK, ForeignKey("users.user_id", ondelete="SET NULL"))
    action = Column(String(100), nullable=False)
    resource_type = Column(String(100))
    resource_id = Column(String(100))
    result = Column(String(30), nullable=False, default="SUCCESS")
    ip_address = Column(INET_VARIANT)
    log_metadata = Column("metadata", JSON_VARIANT, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    user = relationship("User")
