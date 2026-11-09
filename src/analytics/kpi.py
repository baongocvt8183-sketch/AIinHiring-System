"""Dashboard queries, KPI calculations and filter options."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

import pandas as pd
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from src.analytics.funnel import build_funnel
from src.auth.permissions import require_permission, scoped_job_ids
from src.constants import APPLICATION_STATUS_LABELS, APPLICATION_STATUSES
from src.database.models import (
    Application,
    ApplicationStageHistory,
    Candidate,
    Job,
    Stage,
    User,
)


@dataclass(frozen=True)
class DashboardFilters:
    applied_from: date | None = None
    applied_to: date | None = None
    job_ids: tuple[int, ...] = field(default_factory=tuple)
    departments: tuple[str, ...] = field(default_factory=tuple)
    sources: tuple[str, ...] = field(default_factory=tuple)
    statuses: tuple[str, ...] = field(default_factory=tuple)


APP_COLUMNS = [
    "application_id",
    "candidate_id",
    "full_name",
    "email",
    "phone",
    "job_id",
    "job_title",
    "department",
    "source_name",
    "current_status",
    "applied_at",
    "updated_at",
    "current_stage",
]

HISTORY_COLUMNS = [
    "history_id",
    "application_id",
    "job_id",
    "stage_id",
    "stage_name",
    "stage_order",
    "entered_at",
    "exited_at",
    "result",
    "current_status",
    "applied_at",
]


def _day_start(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _day_end(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


def _apply_application_filters(
    stmt: Select,
    filters: DashboardFilters,
    job_scope: list[int] | None,
) -> Select:
    if job_scope is not None:
        if not job_scope:
            return stmt.where(Application.application_id == -1)
        stmt = stmt.where(Application.job_id.in_(job_scope))
    if filters.job_ids:
        stmt = stmt.where(Application.job_id.in_(list(filters.job_ids)))
    if filters.departments:
        stmt = stmt.where(Job.department.in_(list(filters.departments)))
    if filters.sources:
        stmt = stmt.where(Application.source_name.in_(list(filters.sources)))
    if filters.statuses:
        stmt = stmt.where(Application.current_status.in_(list(filters.statuses)))
    start = _day_start(filters.applied_from)
    end = _day_end(filters.applied_to)
    if start:
        stmt = stmt.where(Application.applied_at >= start)
    if end:
        stmt = stmt.where(Application.applied_at <= end)
    return stmt


def application_query(filters: DashboardFilters, job_scope: list[int] | None) -> Select:
    stmt = (
        select(
            Application.application_id,
            Application.candidate_id,
            Candidate.full_name,
            Candidate.email,
            Candidate.phone,
            Application.job_id,
            Job.job_title,
            Job.department,
            Application.source_name,
            Application.current_status,
            Application.applied_at,
            Application.updated_at,
            Stage.stage_name.label("current_stage"),
        )
        .join(Candidate, Candidate.candidate_id == Application.candidate_id)
        .join(Job, Job.job_id == Application.job_id)
        .outerjoin(Stage, Stage.stage_id == Application.current_stage_id)
    )
    return _apply_application_filters(stmt, filters, job_scope).order_by(Application.applied_at.desc())


def load_applications(session: Session, filters: DashboardFilters, job_scope: list[int] | None) -> pd.DataFrame:
    rows = session.execute(application_query(filters, job_scope)).all()
    frame = pd.DataFrame([dict(row._mapping) for row in rows], columns=APP_COLUMNS)
    for column in ("applied_at", "updated_at"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    return frame


def load_history(session: Session, filters: DashboardFilters, job_scope: list[int] | None) -> pd.DataFrame:
    stmt = (
        select(
            ApplicationStageHistory.history_id,
            ApplicationStageHistory.application_id,
            Application.job_id,
            ApplicationStageHistory.stage_id,
            Stage.stage_name,
            Stage.stage_order,
            ApplicationStageHistory.entered_at,
            ApplicationStageHistory.exited_at,
            ApplicationStageHistory.result,
            Application.current_status,
            Application.applied_at,
        )
        .join(Application, Application.application_id == ApplicationStageHistory.application_id)
        .join(Stage, Stage.stage_id == ApplicationStageHistory.stage_id)
        .join(Job, Job.job_id == Application.job_id)
    )
    stmt = _apply_application_filters(stmt, filters, job_scope).order_by(
        ApplicationStageHistory.application_id, ApplicationStageHistory.entered_at
    )
    rows = session.execute(stmt).all()
    frame = pd.DataFrame([dict(row._mapping) for row in rows], columns=HISTORY_COLUMNS)
    for column in ("entered_at", "exited_at", "applied_at"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    return frame


def load_stages(session: Session) -> list[tuple[str, int, bool]]:
    rows = session.execute(select(Stage.stage_name, Stage.stage_order, Stage.is_terminal).order_by(Stage.stage_order)).all()
    return [(row.stage_name, int(row.stage_order), bool(row.is_terminal)) for row in rows]


def funnel_dataframe(
    session: Session,
    filters: DashboardFilters,
    job_scope: list[int] | None,
    app_df: pd.DataFrame | None = None,
    history_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    app_df = load_applications(session, filters, job_scope) if app_df is None else app_df
    history_df = load_history(session, filters, job_scope) if history_df is None else history_df
    return build_funnel(app_df, history_df, load_stages(session))


def compute_kpis(app_df: pd.DataFrame, history_df: pd.DataFrame) -> dict:
    """Compute dashboard KPIs. All time windows are defined by ``applied_at``."""
    total = int(len(app_df))
    counts = app_df["current_status"].value_counts().to_dict() if total else {}
    hired = int(counts.get("HIRED", 0))
    in_progress = int(counts.get("IN_PROGRESS", 0))
    on_hold = int(counts.get("ON_HOLD", 0))
    rejected = int(counts.get("REJECTED", 0))
    withdrawn = int(counts.get("WITHDRAWN", 0))
    offer_declined = int(counts.get("OFFER_DECLINED", 0))

    now = pd.Timestamp.now(tz="UTC")
    avg_time_to_hire = None
    if not app_df.empty and not history_df.empty:
        hired_ids = set(app_df.loc[app_df["current_status"] == "HIRED", "application_id"].astype(int))
        hired_history = history_df[
            (history_df["application_id"].isin(hired_ids)) & (history_df["stage_name"] == "Hired")
        ]
        if not hired_history.empty:
            first_hired = hired_history.groupby("application_id", as_index=False)["entered_at"].min()
            applied = app_df[["application_id", "applied_at"]].drop_duplicates("application_id")
            merged = first_hired.merge(applied, on="application_id", how="left")
            duration = (merged["entered_at"] - merged["applied_at"]).dt.total_seconds() / 86400
            duration = duration[duration >= 0]
            if not duration.empty:
                avg_time_to_hire = round(float(duration.mean()), 2)

    avg_completed_stage = None
    avg_current_wait = None
    if not history_df.empty:
        completed = history_df[history_df["exited_at"].notna()]
        if not completed.empty:
            duration = (completed["exited_at"] - completed["entered_at"]).dt.total_seconds() / 86400
            duration = duration[duration >= 0]
            if not duration.empty:
                avg_completed_stage = round(float(duration.mean()), 2)
        open_rows = history_df[history_df["exited_at"].isna()]
        if not open_rows.empty:
            waiting = (now - open_rows["entered_at"]).dt.total_seconds() / 86400
            waiting = waiting[waiting >= 0]
            if not waiting.empty:
                avg_current_wait = round(float(waiting.mean()), 2)

    active = total - hired - rejected - withdrawn - offer_declined
    return {
        "total_applications": total,
        "in_progress": in_progress,
        "on_hold": on_hold,
        "hired": hired,
        "rejected": rejected,
        "withdrawn": withdrawn,
        "offer_declined": offer_declined,
        "active_pipeline": active,
        "hire_rate": round(hired / total * 100, 2) if total else None,
        "avg_time_to_hire_days": avg_time_to_hire,
        "avg_completed_stage_days": avg_completed_stage,
        "avg_current_wait_days": avg_current_wait,
    }


def applications_by_job(app_df: pd.DataFrame) -> pd.DataFrame:
    if app_df.empty:
        return pd.DataFrame(columns=["job_title", "department", "applications", "hired", "in_progress"])
    grouped = (
        app_df.groupby(["job_title", "department"], dropna=False)
        .agg(
            applications=("application_id", "nunique"),
            hired=("current_status", lambda values: int((values == "HIRED").sum())),
            in_progress=("current_status", lambda values: int((values == "IN_PROGRESS").sum())),
        )
        .reset_index()
        .sort_values("applications", ascending=False)
    )
    return grouped


def applications_by_source(app_df: pd.DataFrame) -> pd.DataFrame:
    if app_df.empty:
        return pd.DataFrame(columns=["source_name", "applications", "hired"])
    frame = app_df.copy()
    frame["source_name"] = frame["source_name"].fillna("Không xác định")
    return (
        frame.groupby("source_name")
        .agg(
            applications=("application_id", "nunique"),
            hired=("current_status", lambda values: int((values == "HIRED").sum())),
        )
        .reset_index()
        .sort_values("applications", ascending=False)
    )


def applications_by_status(app_df: pd.DataFrame) -> pd.DataFrame:
    if app_df.empty:
        return pd.DataFrame(columns=["current_status", "label", "applications"])
    counts = app_df.groupby("current_status")["application_id"].nunique().reset_index(name="applications")
    counts["label"] = counts["current_status"].map(APPLICATION_STATUS_LABELS).fillna(counts["current_status"])
    return counts.sort_values("applications", ascending=False)


def monthly_trend(app_df: pd.DataFrame) -> pd.DataFrame:
    if app_df.empty:
        return pd.DataFrame(columns=["month", "applications", "hired"])
    frame = app_df.copy()
    frame["month"] = frame["applied_at"].dt.strftime("%Y-%m")
    trend = (
        frame.groupby("month")
        .agg(
            applications=("application_id", "nunique"),
            hired=("current_status", lambda values: int((values == "HIRED").sum())),
        )
        .reset_index()
        .sort_values("month")
    )
    return trend


def filter_options(session: Session, user: User) -> dict:
    job_scope = scoped_job_ids(session, user)
    jobs_stmt = select(Job.job_id, Job.job_title, Job.department).order_by(Job.job_title)
    if job_scope is not None:
        if not job_scope:
            jobs_stmt = jobs_stmt.where(Job.job_id == -1)
        else:
            jobs_stmt = jobs_stmt.where(Job.job_id.in_(job_scope))
    jobs = session.execute(jobs_stmt).all()

    app_stmt = select(Application.source_name).where(Application.source_name.is_not(None)).distinct()
    if job_scope is not None:
        if job_scope:
            app_stmt = app_stmt.where(Application.job_id.in_(job_scope))
        else:
            app_stmt = app_stmt.where(Application.application_id == -1)
    sources = sorted({row[0] for row in session.execute(app_stmt).all() if row[0]})
    departments = sorted({row.department for row in jobs if row.department})
    return {
        "jobs": [{"job_id": int(row.job_id), "job_title": row.job_title, "department": row.department} for row in jobs],
        "departments": departments,
        "sources": sources,
        "statuses": APPLICATION_STATUSES,
    }


def detail_table(app_df: pd.DataFrame, can_view_pii: bool) -> pd.DataFrame:
    if app_df.empty:
        return pd.DataFrame(
            columns=[
                "application_id",
                "Ứng viên",
                "Vị trí",
                "Phòng ban",
                "Vòng hiện tại",
                "Trạng thái",
                "Nguồn",
                "Ngày ứng tuyển",
            ]
        )
    frame = pd.DataFrame(
        {
            "application_id": app_df["application_id"],
            "Ứng viên": app_df["full_name"],
            "Vị trí": app_df["job_title"],
            "Phòng ban": app_df["department"].fillna("—"),
            "Vòng hiện tại": app_df["current_stage"].fillna("—"),
            "Trạng thái": app_df["current_status"].map(APPLICATION_STATUS_LABELS).fillna(app_df["current_status"]),
            "Nguồn": app_df["source_name"].fillna("—"),
            "Ngày ứng tuyển": app_df["applied_at"].dt.strftime("%d/%m/%Y"),
        }
    )
    if can_view_pii:
        frame["Email"] = app_df["email"].fillna("—")
        frame["Điện thoại"] = app_df["phone"].fillna("—")
    return frame


def paginate(frame: pd.DataFrame, page: int, page_size: int) -> tuple[pd.DataFrame, int, int]:
    total = len(frame)
    pages = max((total + page_size - 1) // page_size, 1)
    page = min(max(page, 1), pages)
    start = (page - 1) * page_size
    return frame.iloc[start : start + page_size], page, pages


def date_range_default(days: int = 365) -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=days), today
