"""Audit log viewer for Admin and Auditor roles (read-only)."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.audit.audit_logger import safe_log_action
from src.constants import PERM_VIEW_AUDIT
from src.database.models import AuditLog
from src.ui.common import format_datetime, page_header, page_setup

user, db = page_setup("Audit log", "🧾", PERM_VIEW_AUDIT)
page_header(
    "Nhật ký kiểm toán",
    "Bản ghi chỉ đọc cho các hành động quan trọng. Không lưu mật khẩu, token, toàn văn CV hay dữ liệu nhạy cảm.",
    "🧾",
)


def _day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _day_end(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


try:
    today = date.today()
    actions = sorted(
        value for value in db.scalars(select(AuditLog.action).distinct()) if value
    )
    with st.sidebar:
        st.markdown("### 🔎 Lọc audit")
        selected_dates = st.date_input(
            "Khoảng thời gian",
            value=(today - timedelta(days=30), today),
            max_value=today,
            key="audit_dates",
        )
        if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
            date_from, date_to = selected_dates
        else:
            date_from = date_to = selected_dates if isinstance(selected_dates, date) else today
        selected_actions = st.multiselect("Hành động", actions, key="audit_actions")
        selected_results = st.multiselect(
            "Kết quả",
            ["SUCCESS", "FAILURE", "DENIED"],
            key="audit_results",
        )
        actor_search = st.text_input("Người thực hiện (username/họ tên)", key="audit_actor")

    stmt = (
        select(AuditLog)
        .options(joinedload(AuditLog.user))
        .where(AuditLog.created_at >= _day_start(date_from), AuditLog.created_at <= _day_end(date_to))
        .order_by(AuditLog.created_at.desc())
        .limit(2000)
    )
    if selected_actions:
        stmt = stmt.where(AuditLog.action.in_(selected_actions))
    if selected_results:
        stmt = stmt.where(AuditLog.result.in_(selected_results))

    logs = list(db.scalars(stmt))
    if actor_search:
        needle = actor_search.strip().lower()
        logs = [
            log
            for log in logs
            if log.user
            and (needle in log.user.username.lower() or needle in log.user.full_name.lower())
        ]

    log_key = "audit_view_logged"
    if log_key not in st.session_state:
        safe_log_action(
            db,
            user_id=user.user_id,
            action="AUDIT_VIEW",
            resource_type="audit_logs",
            metadata={"filters": True},
        )
        db.commit()
        st.session_state[log_key] = True

    counts = {
        "total": len(logs),
        "success": sum(1 for log in logs if log.result == "SUCCESS"),
        "failure": sum(1 for log in logs if log.result == "FAILURE"),
        "denied": sum(1 for log in logs if log.result == "DENIED"),
    }
    metrics = st.columns(4)
    metrics[0].metric("Sự kiện", f"{counts['total']:,}")
    metrics[1].metric("Thành công", f"{counts['success']:,}")
    metrics[2].metric("Thất bại", f"{counts['failure']:,}")
    metrics[3].metric("Bị từ chối", f"{counts['denied']:,}")

    if not logs:
        st.info("Không có sự kiện audit phù hợp bộ lọc.")
        st.stop()

    table = pd.DataFrame(
        [
            {
                "ID": log.audit_id,
                "Thời điểm": format_datetime(log.created_at),
                "Người thực hiện": log.user.username if log.user else "—",
                "Hành động": log.action,
                "Tài nguyên": f"{log.resource_type or '—'}{('/' + log.resource_id) if log.resource_id else ''}",
                "Kết quả": log.result,
                "IP": log.ip_address or "—",
            }
            for log in logs
        ]
    )
    st.subheader("Sự kiện gần nhất")
    st.dataframe(table, hide_index=True, width="stretch", height=340)

    selected_id = st.selectbox(
        "Xem chi tiết sự kiện",
        [log.audit_id for log in logs],
        format_func=lambda audit_id: next(
            f"#{audit_id} · {log.action} · {format_datetime(log.created_at)}"
            for log in logs
            if log.audit_id == audit_id
        ),
        key="audit_selected",
    )
    log = next(log for log in logs if log.audit_id == selected_id)
    st.markdown("#### Chi tiết")
    detail_cols = st.columns(4)
    detail_cols[0].markdown(f"**Người thực hiện:** {log.user.username if log.user else '—'}")
    detail_cols[1].markdown(f"**Kết quả:** `{log.result}`")
    detail_cols[2].markdown(f"**Tài nguyên:** `{log.resource_type or '—'}` / `{log.resource_id or '—'}`")
    detail_cols[3].markdown(f"**IP:** {log.ip_address or '—'}")
    st.json(log.log_metadata or {}, expanded=True)
    st.caption("Metadata đã được lọc bỏ mật khẩu, token và dữ liệu nhận dạng trước khi ghi.")

    csv_bytes = table.to_csv(index=False).encode("utf-8-sig")
    if st.download_button(
        "⬇️ Xuất audit CSV",
        data=csv_bytes,
        file_name="audit_logs.csv",
        mime="text/csv",
        key="audit_export",
    ):
        safe_log_action(
            db,
            user_id=user.user_id,
            action="AUDIT_EXPORT",
            resource_type="audit_logs",
            metadata={"rows": len(table)},
        )
        db.commit()
        st.toast("Đã ghi nhật ký xuất audit.")
finally:
    db.close()
