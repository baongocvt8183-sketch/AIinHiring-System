"""Dashboard: KPI, funnel, processing time and filtered detail."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics.funnel import overall_conversion, stage_duration_table
from src.analytics.kpi import (
    DashboardFilters,
    applications_by_job,
    applications_by_source,
    applications_by_status,
    compute_kpis,
    detail_table,
    filter_options,
    funnel_dataframe,
    load_applications,
    load_history,
    monthly_trend,
    paginate,
)
from src.audit.audit_logger import safe_log_action
from src.auth.permissions import can_view_pii, scoped_job_ids
from src.constants import APPLICATION_STATUS_LABELS, PERM_VIEW_DASHBOARD
from src.ui.common import page_header, page_setup

user, db = page_setup("Tổng quan", "📊", PERM_VIEW_DASHBOARD)

try:
    options = filter_options(db, user)
    scope = scoped_job_ids(db, user)
    page_header(
        "Tổng quan tuyển dụng",
        "KPI và funnel tính từ lịch sử vòng tuyển, không thay thế lịch sử bằng trạng thái hiện tại.",
        "📊",
    )
    if scope is not None:
        st.info(
            f"Phạm vi dữ liệu: {len(scope)} vị trí được giao. "
            "Các vị trí ngoài phạm vi bị lọc ở tầng backend."
        )

    today = date.today()
    with st.sidebar:
        st.markdown("### 🔎 Bộ lọc dashboard")
        selected_dates = st.date_input(
            "Khoảng thời gian (ngày ứng tuyển)",
            value=(today - timedelta(days=365), today),
            max_value=today,
            key="ov_dates",
        )
        if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
            date_from, date_to = selected_dates
        elif isinstance(selected_dates, date):
            date_from, date_to = selected_dates, selected_dates
        else:
            date_from, date_to = today - timedelta(days=365), today

        job_labels = {f"{job['job_title']} · {job['department'] or '—'}": job["job_id"] for job in options["jobs"]}
        selected_jobs = st.multiselect("Vị trí tuyển dụng", list(job_labels), key="ov_jobs")
        selected_departments = st.multiselect("Phòng ban", options["departments"], key="ov_depts")
        selected_sources = st.multiselect("Nguồn ứng viên", options["sources"], key="ov_sources")
        selected_statuses = st.multiselect(
            "Trạng thái hồ sơ",
            options["statuses"],
            format_func=lambda value: APPLICATION_STATUS_LABELS.get(value, value),
            key="ov_statuses",
        )
        st.caption("Bộ lọc áp dụng đồng thời cho KPI, funnel và bảng chi tiết.")

    filters = DashboardFilters(
        applied_from=date_from,
        applied_to=date_to,
        job_ids=tuple(job_labels[label] for label in selected_jobs),
        departments=tuple(selected_departments),
        sources=tuple(selected_sources),
        statuses=tuple(selected_statuses),
    )

    app_df = load_applications(db, filters, scope)
    history_df = load_history(db, filters, scope)
    funnel_df = funnel_dataframe(db, filters, scope, app_df=app_df, history_df=history_df)
    kpis = compute_kpis(app_df, history_df)
    overall = overall_conversion(funnel_df)

    metrics = st.columns(6)
    metrics[0].metric("Tổng hồ sơ", f"{kpis['total_applications']:,}", help="Số hồ sơ trong bộ lọc, tính theo ngày ứng tuyển.")
    metrics[1].metric("Đang xử lý", f"{kpis['in_progress']:,}", help="Hồ sơ có trạng thái IN_PROGRESS (không gồm tạm dừng).")
    metrics[2].metric("Đã tuyển", f"{kpis['hired']:,}", help="Hồ sơ có trạng thái HIRED.")
    metrics[3].metric(
        "Tỷ lệ tuyển",
        "N/A" if kpis["hire_rate"] is None else f"{kpis['hire_rate']:.1f}%",
        help="Số hồ sơ HIRED / tổng hồ sơ trong bộ lọc.",
    )
    metrics[4].metric(
        "TG tuyển TB",
        "N/A" if kpis["avg_time_to_hire_days"] is None else f"{kpis['avg_time_to_hire_days']:.1f} ngày",
        help="Thời gian từ ngày ứng tuyển đến lần đầu vào vòng Hired (chỉ hồ sơ đã tuyển).",
    )
    metrics[5].metric(
        "Chờ hiện tại TB",
        "N/A" if kpis["avg_current_wait_days"] is None else f"{kpis['avg_current_wait_days']:.1f} ngày",
        help="Thời gian chờ trung bình của các vòng đang mở; không trộn với thời gian hoàn tất.",
    )
    if kpis["on_hold"]:
        st.caption(f"⏸️ {kpis['on_hold']} hồ sơ đang tạm dừng; vẫn được tính trong tổng và chờ hiện tại.")

    tab_funnel, tab_breakdown, tab_detail = st.tabs(["🔻 Funnel & thời gian", "📈 Phân bố", "📋 Chi tiết hồ sơ"])

    with tab_funnel:
        left, right = st.columns([1.15, 0.85], gap="large")
        with left:
            st.subheader("Funnel theo vòng tuyển")
            if funnel_df.empty or funnel_df["apps_entered"].sum() == 0:
                st.info("Không có dữ liệu vòng tuyển trong bộ lọc hiện tại.")
            else:
                hover = [
                    f"Vào vòng: {row.apps_entered}<br>"
                    f"Chuyển đổi từ vòng trước: {'N/A' if pd.isna(row.conversion_from_previous) else f'{row.conversion_from_previous:.1f}%'}<br>"
                    f"Hoàn tất: {row.completed_count} · Đang mở: {row.open_count}"
                    for row in funnel_df.itertuples()
                ]
                figure = go.Figure(
                    go.Funnel(
                        y=funnel_df["stage_name"],
                        x=funnel_df["apps_entered"],
                        textinfo="value+percent initial",
                        customdata=hover,
                        hovertemplate="%{y}<br>%{customdata}<extra></extra>",
                        marker={"color": ["#145374", "#1b6b82", "#238497", "#4aa3ad", "#7bbfc2", "#b7dadd"]},
                        connector={"line": {"color": "#94a3b8", "width": 1}},
                    )
                )
                figure.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=380, showlegend=False)
                st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
                st.caption(
                    "Tỷ lệ chuyển đổi = số hồ sơ vào vòng N+1 / số hồ sơ vào vòng N × 100%. "
                    "Hồ sơ chưa rời vòng được báo riêng là thời gian chờ."
                )
        with right:
            st.subheader("Thời gian xử lý")
            timing = stage_duration_table(funnel_df)
            if timing.empty:
                st.info("Chưa có dữ liệu thời gian.")
            else:
                display = pd.DataFrame(
                    {
                        "Vòng": timing["stage_name"],
                        "TB hoàn tất (ngày)": timing["avg_days_completed"].apply(
                            lambda value: "—" if pd.isna(value) else f"{value:.2f}"
                        ),
                        "Đã xong": timing["completed_count"],
                        "Chờ TB (ngày)": timing["avg_days_waiting"].apply(
                            lambda value: "—" if pd.isna(value) else f"{value:.2f}"
                        ),
                        "Đang mở": timing["open_count"],
                    }
                )
                st.dataframe(display, hide_index=True, width="stretch", height=330)
                st.caption(f"Tỷ lệ chuyển đổi tổng thể (vòng đầu → cuối): {('N/A' if overall is None else f'{overall:.1f}%')}")

        st.subheader("Tỷ lệ chuyển đổi từng vòng")
        if not funnel_df.empty:
            conversion = funnel_df.dropna(subset=["conversion_from_previous"]).copy()
            if conversion.empty:
                st.info("Chưa đủ dữ liệu để tính chuyển đổi giữa các vòng.")
            else:
                conversion["label"] = conversion["conversion_from_previous"].map(lambda value: f"{value:.1f}%")
                figure = go.Figure(
                    go.Bar(
                        x=conversion["stage_name"],
                        y=conversion["conversion_from_previous"],
                        text=conversion["label"],
                        textposition="outside",
                        marker_color="#238497",
                        hovertemplate="%{x}<br>Chuyển đổi: %{y:.1f}%<extra></extra>",
                    )
                )
                figure.update_layout(
                    yaxis_title="%",
                    yaxis_range=[0, 110],
                    height=320,
                    margin=dict(l=10, r=10, t=20, b=10),
                )
                st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    with tab_breakdown:
        col_a, col_b = st.columns(2, gap="large")
        with col_a:
            st.subheader("Hồ sơ theo trạng thái")
            status_df = applications_by_status(app_df)
            if status_df.empty:
                st.info("Không có dữ liệu.")
            else:
                figure = go.Figure(
                    go.Bar(
                        x=status_df["applications"],
                        y=status_df["label"],
                        orientation="h",
                        marker_color="#1d7a8c",
                        hovertemplate="%{y}: %{x} hồ sơ<extra></extra>",
                    )
                )
                figure.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

            st.subheader("Hồ sơ theo nguồn")
            source_df = applications_by_source(app_df)
            if source_df.empty:
                st.info("Không có dữ liệu nguồn.")
            else:
                figure = go.Figure(
                    go.Bar(
                        x=source_df["source_name"],
                        y=source_df["applications"],
                        text=source_df["applications"],
                        textposition="outside",
                        marker_color="#4aa3ad",
                    )
                )
                figure.update_layout(height=310, margin=dict(l=10, r=10, t=20, b=10))
                st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

        with col_b:
            st.subheader("Hồ sơ theo vị trí")
            job_df = applications_by_job(app_df)
            if job_df.empty:
                st.info("Không có dữ liệu.")
            else:
                job_df = job_df.copy()
                job_df["label"] = job_df["job_title"] + " · " + job_df["department"].fillna("—")
                figure = go.Figure()
                figure.add_bar(y=job_df["label"], x=job_df["applications"], name="Tổng hồ sơ", marker_color="#145374")
                figure.add_bar(y=job_df["label"], x=job_df["hired"], name="Đã tuyển", marker_color="#54a86b")
                figure.update_layout(
                    barmode="group",
                    height=340,
                    margin=dict(l=10, r=10, t=10, b=10),
                    legend=dict(orientation="h", y=1.08),
                )
                st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

            st.subheader("Xu hướng theo tháng")
            trend = monthly_trend(app_df)
            if trend.empty:
                st.info("Không có dữ liệu.")
            else:
                figure = go.Figure()
                figure.add_trace(go.Scatter(x=trend["month"], y=trend["applications"], mode="lines+markers", name="Hồ sơ"))
                figure.add_trace(go.Scatter(x=trend["month"], y=trend["hired"], mode="lines+markers", name="Đã tuyển"))
                figure.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), legend=dict(orientation="h", y=1.08))
                st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    with tab_detail:
        st.subheader("Bảng chi tiết hồ sơ")
        table = detail_table(app_df, can_view_pii(user))
        if table.empty:
            st.info("Không có hồ sơ phù hợp bộ lọc.")
        else:
            top = st.columns([1, 1, 2])
            page_size = top[0].selectbox("Số dòng/trang", [10, 20, 50, 100], index=1, key="ov_page_size")
            page = top[1].number_input("Trang", min_value=1, value=1, step=1, key="ov_page")
            page_df, current_page, pages = paginate(table, int(page), int(page_size))
            top[2].caption(f"Hiển thị {len(page_df)}/{len(table)} hồ sơ · Trang {current_page}/{pages}")
            st.dataframe(page_df, hide_index=True, width="stretch")

            csv_bytes = table.to_csv(index=False).encode("utf-8-sig")
            if st.download_button(
                "⬇️ Xuất CSV",
                data=csv_bytes,
                file_name="recruitment_dashboard.csv",
                mime="text/csv",
                key="ov_export",
            ):
                safe_log_action(
                    db,
                    user_id=user.user_id,
                    action="DASHBOARD_EXPORT",
                    resource_type="dashboard",
                    metadata={"rows": len(table)},
                )
                db.commit()
                st.toast("Đã ghi nhật ký xuất dữ liệu.")
            st.caption(
                "Email/điện thoại chỉ hiển thị cho vai trò có quyền xem dữ liệu nhận dạng. "
                "Auditor và Hiring Manager nhận dữ liệu đã che theo quyền."
            )
finally:
    db.close()
