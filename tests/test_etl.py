from __future__ import annotations

from datetime import timezone

import pandas as pd
from sqlalchemy import func, select

from src.database.models import Application, Candidate, ETLRowError, Job
from src.database.sample_data import write_sample_files
from src.etl.extract import detect_column_mapping, read_excel_bytes, read_tabular_bytes
from src.etl.load import run_etl
from src.etl.transform import (
    normalize_email,
    normalize_phone,
    normalize_stage,
    normalize_status,
    parse_datetime,
)


def test_normalization_helpers():
    assert normalize_email("  An.Nguyen@Example.COM ") == "an.nguyen@example.com"
    assert normalize_status("Đã tuyển") == "HIRED"
    assert normalize_status("từ chối") == "REJECTED"
    assert normalize_stage("cv", ["CV Screening", "Online Test"]) == "CV Screening"
    parsed, error = parse_datetime("05/10/2026")
    assert error is None and parsed.month == 10 and parsed.day == 5
    assert parsed.tzinfo == timezone.utc
    _, error = parse_datetime("ngày mai")
    assert error == "INVALID_DATE"
    assert normalize_phone("+84 (90) 123-4567") == "+84901234567"


def test_sample_csv_etl_is_idempotent(clean_session):
    paths = write_sample_files()
    data = paths["csv"].read_bytes()
    frame = read_tabular_bytes(data, "candidates_sample.csv")
    assert len(frame) == 18
    mapping = detect_column_mapping(list(frame.columns))
    assert mapping["full_name"] == "Họ tên"
    assert mapping["email"] == "Email"
    assert mapping["job_title"] == "Vị trí"
    assert mapping["applied_at"] == "Ngày ứng tuyển"

    run = run_etl(
        clean_session,
        frame,
        source_name="candidates_sample.csv",
        source_type="CSV",
        user_id=None,
        column_mapping=mapping,
    )
    assert run.status == "PARTIAL_SUCCESS"
    assert run.rows_read == 18
    assert run.rows_valid == 13
    assert run.rows_rejected == 5
    assert run.rows_inserted == 12
    assert run.rows_duplicate == 1
    assert run.rows_updated == 0

    applications = clean_session.scalar(select(func.count()).select_from(Application))
    assert applications == 12
    candidates = clean_session.scalar(select(func.count()).select_from(Candidate))
    assert candidates == 11
    jobs = clean_session.scalar(select(func.count()).select_from(Job))
    assert jobs == 4

    errors = list(clean_session.scalars(select(ETLRowError).where(ETLRowError.etl_run_id == run.etl_run_id)))
    assert len(errors) >= 5
    assert len({error.source_row_number for error in errors}) == 5
    assert {error.error_code for error in errors} >= {"INVALID_EMAIL", "REQUIRED_FIELD", "INVALID_DATE"}

    # Re-running skips rows with a normalized email that already exist. Records
    # without any email cannot be safely merged (README rule) and are inserted.
    rerun = run_etl(
        clean_session,
        frame,
        source_name="candidates_sample.csv",
        source_type="CSV",
        user_id=None,
        column_mapping=mapping,
    )
    assert rerun.rows_inserted == 1
    assert rerun.rows_duplicate == 12
    assert rerun.rows_rejected == 5
    apps_after = clean_session.scalar(select(func.count()).select_from(Application))
    assert apps_after == 13
    assert rerun.status == "PARTIAL_SUCCESS"

    # Without the no-email row, a rerun is fully idempotent.
    with_email = frame[frame["Email"].str.strip() != ""]
    idempotent = run_etl(
        clean_session,
        with_email,
        source_name="candidates_with_email.csv",
        source_type="CSV",
        user_id=None,
        column_mapping=mapping,
    )
    assert idempotent.rows_inserted == 0


def test_sample_excel_etl(clean_session):
    paths = write_sample_files()
    frame = read_excel_bytes(paths["xlsx"].read_bytes())
    assert len(frame) == 18
    run = run_etl(
        clean_session,
        frame,
        source_name="candidates_sample.xlsx",
        source_type="EXCEL",
        user_id=None,
    )
    assert run.rows_read == 18
    assert run.status in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert run.rows_inserted > 0


def test_missing_required_mapping_marks_failed(clean_session):
    frame = pd.DataFrame([{"Email": "a@example.com", "Ghi chú": "x"}])
    run = run_etl(
        clean_session,
        frame,
        source_name="bad.csv",
        source_type="CSV",
        user_id=None,
    )
    assert run.status == "FAILED"
    assert "cấu trúc" in (run.error_summary or "").lower() or "thiếu cột" in (run.error_summary or "").lower()
    errors = list(clean_session.scalars(select(ETLRowError).where(ETLRowError.etl_run_id == run.etl_run_id)))
    assert any(error.error_code == "MISSING_REQUIRED_COLUMN" for error in errors)


def test_run_status_failed_when_all_rows_invalid(clean_session):
    frame = pd.DataFrame([{"Họ tên": "", "Vị trí": "", "Email": "bad-email"}])
    run = run_etl(
        clean_session,
        frame,
        source_name="all-invalid.csv",
        source_type="CSV",
        user_id=None,
    )
    assert run.status == "FAILED"
    assert run.rows_rejected == 1
