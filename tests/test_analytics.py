from __future__ import annotations

from datetime import date, timedelta

from src.analytics.funnel import overall_conversion
from src.analytics.kpi import (
    DashboardFilters,
    applications_by_job,
    applications_by_status,
    compute_kpis,
    funnel_dataframe,
    load_applications,
    load_history,
)
from src.database.models import Candidate, Job, User
from src.auth.permissions import scoped_job_ids
from sqlalchemy import select


def _hr(session):
    return session.scalar(select(User).where(User.username == "hr"))


def _hm(session):
    return session.scalar(select(User).where(User.username == "hiring"))


def test_kpi_and_funnel_for_hr(demo_session):
    hr = _hr(demo_session)
    scope = scoped_job_ids(demo_session, hr)
    assert scope is None
    filters = DashboardFilters()
    apps = load_applications(demo_session, filters, scope)
    history = load_history(demo_session, filters, scope)
    assert len(apps) == 15
    assert len(history) == 46

    kpis = compute_kpis(apps, history)
    assert kpis["total_applications"] == 15
    assert kpis["hired"] == 3
    assert kpis["in_progress"] == 7
    assert kpis["hire_rate"] == 20.0
    assert kpis["avg_time_to_hire_days"] is not None

    funnel = funnel_dataframe(demo_session, filters, scope, apps, history)
    assert list(funnel["stage_name"])[:2] == ["CV Screening", "Online Test"]
    assert funnel.iloc[0]["apps_entered"] == 15
    assert funnel.iloc[-1]["apps_entered"] == 3
    assert funnel.iloc[1]["conversion_from_previous"] == round(10 / 15 * 100, 2)
    assert overall_conversion(funnel) == 20.0


def test_hiring_manager_scope_and_kpis(demo_session):
    hm = _hm(demo_session)
    scope = scoped_job_ids(demo_session, hm)
    assert scope is not None

    filters = DashboardFilters()
    apps = load_applications(demo_session, filters, scope)
    history = load_history(demo_session, filters, scope)
    assert len(apps) == 11
    assert set(apps["job_title"]) == {"AI Engineer", "Data Analyst"}
    kpis = compute_kpis(apps, history)
    assert kpis["total_applications"] == 11
    assert kpis["hired"] == 2


def test_filters_by_job_status_and_date(demo_session):
    hr = _hr(demo_session)
    filters = DashboardFilters(statuses=("HIRED",))
    apps = load_applications(demo_session, filters, None)
    assert len(apps) == 3

    ai_job = demo_session.scalar(select(Job).where(Job.job_title == "AI Engineer"))
    filters = DashboardFilters(job_ids=(ai_job.job_id,))
    assert len(load_applications(demo_session, filters, None)) == 5

    filters = DashboardFilters(applied_from=date.today() - timedelta(days=20), applied_to=date.today())
    apps = load_applications(demo_session, filters, None)
    assert len(apps) == 5

    assert not applications_by_status(apps).empty
    assert not applications_by_job(load_applications(demo_session, DashboardFilters(), None)).empty


def test_not_scorable_when_job_has_no_skills(demo_session):
    from src.cv_analysis.resume_matcher import match_skills

    result = match_skills(["Python"], [])
    assert result.score is None
    assert result.status == "NOT_SCORABLE"
    assert "không thể chấm điểm" in result.explanation.lower()
