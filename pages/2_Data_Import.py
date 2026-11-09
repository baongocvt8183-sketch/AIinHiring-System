"""Data import: CSV/Excel/API → transform → validate → load, with run history."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st
from sqlalchemy import select

from src.constants import CANONICAL_ETL_COLUMNS, ETL_COLUMN_ALIASES, PERM_IMPORT_DATA
from src.database.models import ETLRun
from src.database.sample_data import write_sample_files
from src.etl.extract import (
    ExtractionError,
    detect_column_mapping,
    fetch_api_json,
    preview_frame,
    read_api_payload,
    read_tabular_bytes,
)
from src.etl.load import run_etl
from src.ui.common import format_datetime, page_header, page_setup

user, db = page_setup("Nhập dữ liệu ETL", "📥", PERM_IMPORT_DATA)

FIELD_LABELS = {
    "full_name": "Họ tên *",
    "email": "Email",
    "phone": "Điện thoại",
    "job_title": "Vị trí *",
    "department": "Phòng ban",
    "source_name": "Nguồn",
    "applied_at": "Ngày ứng tuyển",
    "current_status": "Trạng thái",
    "stage": "Vòng tuyển",
    "job_description": "Mô tả công việc",
    "job_skills": "Kỹ năng yêu cầu",
}


def render_mapping_and_import(frame: pd.DataFrame, *, source_name: str, source_type: str, key_prefix: str) -> None:
    st.markdown("#### Xem trước dữ liệu nguồn")
    st.caption(f"{len(frame):,} dòng · {len(frame.columns)} cột nguồn")
    st.dataframe(preview_frame(frame, 8), hide_index=True, width="stretch")

    detected = detect_column_mapping(list(frame.columns))
    columns = list(frame.columns)
    options = ["— Không ánh xạ —"] + columns
    mapping: dict[str, str | None] = {}
    with st.expander("🔗 Ánh xạ cột nguồn → schema chuẩn", expanded=True):
        st.caption("Hệ thống tự nhận diện tên cột tiếng Việt/tiếng Anh. Có thể chỉnh lại trước khi nạp.")
        for target in CANONICAL_ETL_COLUMNS:
            default_source = detected.get(target)
            default_index = options.index(default_source) if default_source in options else 0
            selected = st.selectbox(
                FIELD_LABELS.get(target, target),
                options,
                index=default_index,
                key=f"{key_prefix}_map_{target}",
            )
            mapping[target] = None if selected == options[0] else selected

    if st.button("🚀 Nạp dữ liệu", type="primary", key=f"{key_prefix}_import"):
        with st.spinner("Đang validate, chống trùng và nạp dữ liệu..."):
            run = run_etl(
                db,
                frame,
                source_name=source_name,
                source_type=source_type,
                user_id=user.user_id,
                column_mapping=mapping,
            )
        st.session_state["last_etl_run"] = run.etl_run_id
        if run.status == "SUCCESS":
            st.success(f"ETL hoàn tất: {run.rows_inserted} hồ sơ mới, {run.rows_duplicate} dòng trùng bị bỏ qua.")
        elif run.status == "PARTIAL_SUCCESS":
            st.warning("ETL hoàn tất một phần. Một số dòng bị từ chối — xem chi tiết bên dưới.")
        else:
            st.error("ETL thất bại. Kiểm tra ánh xạ và lỗi chi tiết bên dưới.")
        render_run_summary(run.etl_run_id)


def render_run_summary(run_id: int) -> None:
    db.expire_all()
    run = db.get(ETLRun, run_id)
    if run is None:
        return
    st.markdown(f"#### Kết quả lần nạp #{run.etl_run_id} · `{run.status}`")
    columns = st.columns(7)
    columns[0].metric("Dòng đọc", f"{run.rows_read:,}")
    columns[1].metric("Hợp lệ", f"{run.rows_valid:,}")
    columns[2].metric("Tạo mới", f"{run.rows_inserted:,}")
    columns[3].metric("Cập nhật", f"{run.rows_updated:,}")
    columns[4].metric("Trùng", f"{run.rows_duplicate:,}")
    columns[5].metric("Từ chối", f"{run.rows_rejected:,}")
    columns[6].metric("Trạng thái", run.status)
    st.caption(
        f"Nguồn: {run.source_name} · {run.source_type} · "
        f"{format_datetime(run.started_at)} → {format_datetime(run.finished_at)}"
    )
    if run.error_summary:
        st.info(run.error_summary)
    if run.errors:
        errors = pd.DataFrame(
            [
                {
                    "Dòng nguồn": error.source_row_number,
                    "Trường": error.field_name or "—",
                    "Mã lỗi": error.error_code,
                    "Mô tả": error.error_message,
                }
                for error in run.errors
            ]
        )
        st.dataframe(errors, hide_index=True, width="stretch")
    if run.status != "FAILED":
        st.caption("Chạy lại cùng tệp sẽ không tạo trùng hồ sơ ứng tuyển theo quy tắc (ứng viên, vị trí).")


page_header(
    "Nhập dữ liệu & ETL",
    "Extract → Transform → Validate → Deduplicate → Load. Mọi lần chạy được lưu trong etl_runs.",
    "📥",
)

sample_paths = write_sample_files()
with st.sidebar:
    st.markdown("### 📎 Tệp mẫu")
    st.download_button(
        "⬇️ CSV mẫu",
        data=sample_paths["csv"].read_bytes(),
        file_name="candidates_sample.csv",
        mime="text/csv",
        width="stretch",
    )
    st.download_button(
        "⬇️ Excel mẫu",
        data=sample_paths["xlsx"].read_bytes(),
        file_name="candidates_sample.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
    st.caption("Tệp mẫu chứa cả dòng hợp lệ, dòng trùng và dòng lỗi để minh họa ETL.")

last_run_id = st.session_state.get("last_etl_run")
if last_run_id:
    with st.expander("Kết quả lần nạp gần nhất", expanded=True):
        render_run_summary(int(last_run_id))

tab_file, tab_api, tab_history = st.tabs(["📄 CSV / Excel", "🔌 API JSON", "🧾 Lịch sử ETL"])

with tab_file:
    uploaded = st.file_uploader("Chọn tệp CSV hoặc Excel (.xlsx)", type=["csv", "xlsx"], key="etl_file")
    if uploaded is None:
        st.info("Tải tệp lên hoặc dùng tệp mẫu ở thanh bên. Hỗ trợ tối đa 8 MB.")
    else:
        try:
            data = uploaded.getvalue()
            frame = read_tabular_bytes(data, uploaded.name)
        except ExtractionError as exc:
            st.error(str(exc))
        else:
            source_type = "EXCEL" if uploaded.name.lower().endswith(".xlsx") else "CSV"
            render_mapping_and_import(frame, source_name=uploaded.name, source_type=source_type, key_prefix="file")

with tab_api:
    st.caption("Phần mở rộng: lấy JSON từ API tuyển dụng hoặc dán trực tiếp mảng JSON. Không lưu token/URL vào audit log.")
    api_url = st.text_input("URL API", placeholder="https://example.com/api/candidates.json", key="etl_api_url")
    col_url, col_paste = st.columns([1, 1])
    if col_url.button("🌐 Tải từ URL", key="etl_api_fetch"):
        try:
            st.session_state["api_frame"] = fetch_api_json(api_url)
            st.session_state["api_source"] = api_url
            st.success("Đã tải dữ liệu API.")
        except ExtractionError as exc:
            st.error(str(exc))
    pasted = col_paste.text_area("Hoặc dán JSON", height=120, placeholder='[{"Họ tên": "...", "Email": "..."}]', key="etl_api_paste")
    if col_paste.button("📋 Dùng JSON dán", key="etl_api_paste_btn"):
        try:
            st.session_state["api_frame"] = read_api_payload(json.loads(pasted))
            st.session_state["api_source"] = "api-pasted-json"
            st.success("Đã đọc JSON.")
        except (json.JSONDecodeError, ExtractionError) as exc:
            st.error(f"JSON không hợp lệ: {exc}")

    api_frame = st.session_state.get("api_frame")
    if isinstance(api_frame, pd.DataFrame) and not api_frame.empty:
        render_mapping_and_import(
            api_frame,
            source_name=st.session_state.get("api_source", "api"),
            source_type="API",
            key_prefix="api",
        )

with tab_history:
    runs = list(db.scalars(select(ETLRun).order_by(ETLRun.started_at.desc()).limit(100)))
    st.subheader("100 lần chạy gần nhất")
    if not runs:
        st.info("Chưa có lần chạy ETL nào.")
    else:
        table = pd.DataFrame(
            [
                {
                    "ID": run.etl_run_id,
                    "Nguồn": run.source_name,
                    "Loại": run.source_type,
                    "Bắt đầu": format_datetime(run.started_at),
                    "Đọc": run.rows_read,
                    "Hợp lệ": run.rows_valid,
                    "Tạo mới": run.rows_inserted,
                    "Cập nhật": run.rows_updated,
                    "Trùng": run.rows_duplicate,
                    "Từ chối": run.rows_rejected,
                    "Trạng thái": run.status,
                }
                for run in runs
            ]
        )
        st.dataframe(table, hide_index=True, width="stretch")
        selected = st.selectbox(
            "Xem chi tiết lần chạy",
            options=[run.etl_run_id for run in runs],
            format_func=lambda run_id: f"#{run_id} · {next(r.source_name for r in runs if r.etl_run_id == run_id)}",
            key="etl_history_select",
        )
        if selected:
            render_run_summary(int(selected))

db.close()
