from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .constants import CLIMATE_COLUMNS, DISPLACEMENT_COLUMNS, FLOOD_COLUMNS, HEALTH_FACILITY_COLUMNS, WASH_COLUMNS


def parse_epi_week_bounds(value: object) -> tuple[int, int]:
    numbers = [int(number) for number in re.findall(r"\d+", str(value))]
    if not numbers:
        raise ValueError(f"Could not parse epi_week value: {value!r}")
    start = numbers[0]
    end = numbers[-1]
    if end < start:
        start, end = end, start
    start = max(1, min(start, 53))
    end = max(1, min(end, 53))
    return start, end


def add_epi_week_bounds(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    bounds = frame["epi_week"].apply(parse_epi_week_bounds)
    frame["epi_week_label"] = frame["epi_week"].astype(str)
    frame["epi_week_start"] = bounds.apply(lambda pair: pair[0]).astype(int)
    frame["epi_week_end"] = bounds.apply(lambda pair: pair[1]).astype(int)
    frame["period_weeks"] = (frame["epi_week_end"] - frame["epi_week_start"] + 1).astype(int)
    frame["epi_week"] = frame["epi_week_end"]
    return frame


def add_reporting_features(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.sort_values(["state", "year", "epi_week_start", "epi_week_end"]).reset_index(drop=True).copy()
    state_categories = {state: index for index, state in enumerate(sorted(frame["state"].dropna().unique()))}
    frame["state_code"] = frame["state"].map(state_categories).astype(int)
    previous_end = frame.groupby(["state", "year"])["epi_week_end"].shift(1)
    frame["report_gap_weeks"] = (frame["epi_week_start"] - previous_end - 1).clip(lower=0).fillna(0).astype(int)
    return frame


def add_missing_dates(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    if "date" not in frame.columns:
        frame["date"] = [
            pd.Timestamp.fromisocalendar(int(year), int(week), 1)
            for year, week in zip(frame["year"], frame["epi_week_end"])
        ]
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def fill_environmental_gaps(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    context_columns = [*CLIMATE_COLUMNS, *WASH_COLUMNS, *FLOOD_COLUMNS, *DISPLACEMENT_COLUMNS, *HEALTH_FACILITY_COLUMNS]
    for column in context_columns:
        if column not in frame.columns:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if column in CLIMATE_COLUMNS:
            frame[column] = frame.groupby("state")[column].transform(
                lambda series: series.interpolate().ffill().bfill()
            )
        elif column in WASH_COLUMNS or column in DISPLACEMENT_COLUMNS:
            frame[column] = frame.sort_values("year").groupby("state")[column].transform(
                lambda series: series.ffill().bfill()
            )
        elif column in HEALTH_FACILITY_COLUMNS:
            frame[column] = frame.groupby("state")[column].transform(lambda series: series.ffill().bfill())
        frame[column] = frame[column].fillna(frame[column].median()).fillna(0)
    return frame


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    frame = add_missing_dates(df)
    frame["month"] = frame["date"].dt.month
    frame["quarter"] = frame["date"].dt.quarter
    frame["rainy_season"] = frame["month"].isin([4, 5, 6, 7, 8, 9, 10]).astype(int)
    return frame


def add_lag_features(df: pd.DataFrame, target: str = "suspected_cases") -> pd.DataFrame:
    frame = df.sort_values(["state", "year", "epi_week_end"]).reset_index(drop=True).copy()
    for lag in [1, 2, 4, 8]:
        frame[f"lag_{lag}_cases"] = frame.groupby("state")[target].shift(lag)
    if "deaths" not in frame.columns:
        frame["deaths"] = 0
    if "cfr" not in frame.columns:
        frame["cfr"] = 0
    for lag in [1, 2, 4]:
        frame[f"lag_{lag}_deaths"] = frame.groupby("state")["deaths"].shift(lag)
        frame[f"lag_{lag}_cfr"] = frame.groupby("state")["cfr"].shift(lag)
    shifted_cases = frame.groupby("state")[target].shift(1)
    shifted_deaths = frame.groupby("state")["deaths"].shift(1)
    shifted_cfr = frame.groupby("state")["cfr"].shift(1)
    frame["rolling_4_cases"] = (
        shifted_cases.groupby(frame["state"])
        .rolling(window=4, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    frame["rolling_8_cases"] = (
        shifted_cases.groupby(frame["state"])
        .rolling(window=8, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    frame["rolling_4_deaths"] = (
        shifted_deaths.groupby(frame["state"])
        .rolling(window=4, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    frame["rolling_4_cfr"] = (
        shifted_cfr.groupby(frame["state"])
        .rolling(window=4, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    return frame


def add_risk_labels(df: pd.DataFrame, target: str = "suspected_cases") -> pd.DataFrame:
    frame = df.copy()
    q1 = frame[target].quantile(0.25)
    q3 = frame[target].quantile(0.75)
    iqr = q3 - q1
    upper_fence = q3 + (1.5 * iqr)
    threshold_source = frame.loc[frame[target] <= upper_fence, target]
    if threshold_source.empty:
        threshold_source = frame[target]
    q50 = threshold_source.quantile(0.50)
    q75 = threshold_source.quantile(0.75)
    if pd.isna(q50) or pd.isna(q75) or q50 == q75:
        q50, q75 = 5, 25
    frame["risk_threshold_basis"] = "iqr_trimmed_quantiles"
    frame["risk_low_threshold"] = float(q50)
    frame["risk_high_threshold"] = float(q75)
    frame["risk_level"] = np.select(
        [frame[target] < q50, frame[target] < q75],
        ["Low", "Medium"],
        default="High",
    )
    return frame


def build_features(df: pd.DataFrame, target: str = "suspected_cases") -> pd.DataFrame:
    frame = df.copy()
    frame[target] = pd.to_numeric(frame[target], errors="coerce")
    if "deaths" in frame.columns:
        frame["deaths"] = pd.to_numeric(frame["deaths"], errors="coerce").fillna(0)
    if "cfr" not in frame.columns:
        frame["cfr"] = pd.NA
    frame["cfr"] = pd.to_numeric(frame["cfr"], errors="coerce")
    if "deaths" in frame.columns:
        computed_cfr = frame["deaths"] / frame[target].replace({0: pd.NA})
        frame["cfr"] = frame["cfr"].fillna(computed_cfr)
    frame["cfr"] = frame["cfr"].fillna(0)
    frame = frame.dropna(subset=["state", "year", "epi_week", target])
    frame = add_epi_week_bounds(frame)
    frame = add_reporting_features(frame)
    frame = add_time_features(frame)
    frame = fill_environmental_gaps(frame)
    frame = add_lag_features(frame, target=target)
    frame = add_risk_labels(frame, target=target)
    return frame
