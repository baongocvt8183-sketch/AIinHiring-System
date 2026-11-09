"""Funnel and stage-duration calculations from stage history (not current status)."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def _days(series: pd.Series) -> pd.Series:
    return series.dt.total_seconds() / 86400.0


def build_funnel(app_df: pd.DataFrame, history_df: pd.DataFrame, stages: list[tuple[str, int, bool]]) -> pd.DataFrame:
    """Return stage funnel metrics.

    ``apps_entered`` counts distinct applications that entered each stage in the
    filtered cohort. Conversion is computed from the previous stage's entered
    count, exactly as described in the README.
    """
    if app_df.empty:
        cohort = set()
    else:
        cohort = set(app_df["application_id"].astype(int).tolist())

    rows: list[dict] = []
    previous_entered: int | None = None
    now = datetime.now(timezone.utc)

    for stage_name, stage_order, is_terminal in stages:
        if history_df.empty:
            stage_rows = history_df
        else:
            stage_rows = history_df[
                (history_df["stage_name"] == stage_name)
                & (history_df["application_id"].isin(cohort))
            ]
        entered = int(stage_rows["application_id"].nunique()) if not stage_rows.empty else 0
        completed = stage_rows[stage_rows["exited_at"].notna()] if not stage_rows.empty else stage_rows
        open_rows = stage_rows[stage_rows["exited_at"].isna()] if not stage_rows.empty else stage_rows

        avg_completed = None
        if not completed.empty:
            duration = _days(completed["exited_at"] - completed["entered_at"])
            duration = duration[duration >= 0]
            avg_completed = round(float(duration.mean()), 2) if not duration.empty else None

        avg_waiting = None
        if not open_rows.empty:
            waiting = _days(pd.Timestamp(now) - open_rows["entered_at"])
            waiting = waiting[waiting >= 0]
            avg_waiting = round(float(waiting.mean()), 2) if not waiting.empty else None

        conversion = None
        if previous_entered is not None:
            conversion = round(entered / previous_entered * 100, 2) if previous_entered > 0 else None

        rows.append(
            {
                "stage_name": stage_name,
                "stage_order": stage_order,
                "is_terminal": bool(is_terminal),
                "apps_entered": entered,
                "completed_count": int(completed["application_id"].nunique()) if not completed.empty else 0,
                "open_count": int(open_rows["application_id"].nunique()) if not open_rows.empty else 0,
                "conversion_from_previous": conversion,
                "avg_days_completed": avg_completed,
                "avg_days_waiting": avg_waiting,
            }
        )
        previous_entered = entered

    return pd.DataFrame(rows)


def stage_duration_table(funnel_df: pd.DataFrame) -> pd.DataFrame:
    if funnel_df.empty:
        return pd.DataFrame(
            columns=["stage_name", "avg_days_completed", "completed_count", "avg_days_waiting", "open_count"]
        )
    return funnel_df[
        ["stage_name", "stage_order", "avg_days_completed", "completed_count", "avg_days_waiting", "open_count"]
    ].sort_values("stage_order")


def overall_conversion(funnel_df: pd.DataFrame) -> float | None:
    if funnel_df.empty:
        return None
    entered = funnel_df[funnel_df["apps_entered"] > 0]
    if entered.empty:
        return None
    first = int(entered.iloc[0]["apps_entered"])
    last = int(funnel_df.iloc[-1]["apps_entered"])
    return round(last / first * 100, 2) if first else None
