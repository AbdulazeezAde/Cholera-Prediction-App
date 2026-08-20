from __future__ import annotations

import argparse
import re
import warnings
from pathlib import Path

import pandas as pd
import requests

from .constants import CLIMATE_WEEKLY_PATH, FLOOD_COLUMNS, FLOOD_WEEKLY_PATH, ensure_directories
from .data_pipeline import normalize_state_name

RELIEFWEB_API = "https://api.reliefweb.int/v2/reports"

NIGERIA_STATES = [
    "Abia",
    "Adamawa",
    "Akwa Ibom",
    "Anambra",
    "Bauchi",
    "Bayelsa",
    "Benue",
    "Borno",
    "Cross River",
    "Delta",
    "Ebonyi",
    "Edo",
    "Ekiti",
    "Enugu",
    "FCT",
    "Gombe",
    "Imo",
    "Jigawa",
    "Kaduna",
    "Kano",
    "Katsina",
    "Kebbi",
    "Kogi",
    "Kwara",
    "Lagos",
    "Nasarawa",
    "Niger",
    "Ogun",
    "Ondo",
    "Osun",
    "Oyo",
    "Plateau",
    "Rivers",
    "Sokoto",
    "Taraba",
    "Yobe",
    "Zamfara",
]


def load_weekly_climate(path: Path = CLIMATE_WEEKLY_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Expected weekly climate data at {path}. Run cholera_forecast.climate_api first.")
    frame = pd.read_csv(path)
    required = {"state", "year", "epi_week", "rainfall_mm"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    frame["state"] = frame["state"].map(normalize_state_name)
    for column in ["year", "epi_week", "rainfall_mm"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["state", "year", "epi_week"])


def build_rainfall_flood_proxies(climate: pd.DataFrame) -> pd.DataFrame:
    frame = climate.sort_values(["state", "year", "epi_week"]).copy()
    stats = (
        frame.groupby(["state", "epi_week"])["rainfall_mm"]
        .agg(["mean", "std"])
        .rename(columns={"mean": "_rainfall_mean", "std": "_rainfall_std"})
        .reset_index()
    )
    frame = frame.merge(stats, on=["state", "epi_week"], how="left")
    state_p90 = frame.groupby("state")["rainfall_mm"].transform(lambda series: series.quantile(0.90))
    state_p95 = frame.groupby("state")["rainfall_mm"].transform(lambda series: series.quantile(0.95))
    frame["rainfall_anomaly_mm"] = frame["rainfall_mm"] - frame["_rainfall_mean"]
    frame["rainfall_zscore"] = frame["rainfall_anomaly_mm"] / frame["_rainfall_std"].replace({0: pd.NA})
    frame["heavy_rain_flag"] = (frame["rainfall_mm"] >= state_p90).astype(int)
    frame["extreme_rain_flag"] = (frame["rainfall_mm"] >= state_p95).astype(int)
    frame["rolling_4_rainfall_mm"] = (
        frame.groupby("state")["rainfall_mm"]
        .rolling(window=4, min_periods=1)
        .sum()
        .reset_index(level=0, drop=True)
    )
    frame["reliefweb_flood_reports"] = 0
    frame["rainfall_zscore"] = frame["rainfall_zscore"].fillna(0)
    return frame[["state", "year", "epi_week", *FLOOD_COLUMNS]]


def state_mentions(text: str) -> list[str]:
    found = []
    normalized = text.replace("-", " ")
    for state in NIGERIA_STATES:
        pattern = r"\b(?:FCT|Federal Capital Territory)\b" if state == "FCT" else rf"\b{re.escape(state)}\b"
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            found.append(state)
    return found


def fetch_reliefweb_flood_reports(start_date: str, end_date: str, appname: str, limit: int = 1000) -> pd.DataFrame:
    payload = {
        "limit": limit,
        "query": {"value": "Nigeria flood flooding"},
        "filter": {"field": "country.name", "value": "Nigeria"},
        "fields": {"include": ["title", "date.created", "body"]},
        "sort": ["date.created:asc"],
    }
    response = requests.post(RELIEFWEB_API, params={"appname": appname}, json=payload, timeout=60)
    if response.status_code == 400:
        payload.pop("sort", None)
        response = requests.post(RELIEFWEB_API, params={"appname": appname}, json=payload, timeout=60)
    response.raise_for_status()
    rows = []
    for item in response.json().get("data", []):
        fields = item.get("fields", {})
        created = pd.to_datetime(fields.get("date", {}).get("created"), errors="coerce")
        if pd.isna(created):
            continue
        if not (pd.Timestamp(start_date) <= created.tz_localize(None) <= pd.Timestamp(end_date)):
            continue
        text = f"{fields.get('title', '')} {fields.get('body', '')}"
        mentions = state_mentions(text)
        if not mentions:
            mentions = ["Nigeria"]
        iso = created.isocalendar()
        for state in mentions:
            if state != "Nigeria":
                rows.append({"state": state, "year": int(iso.year), "epi_week": int(iso.week), "reliefweb_flood_reports": 1})
    if not rows:
        return pd.DataFrame(columns=["state", "year", "epi_week", "reliefweb_flood_reports"])
    return pd.DataFrame(rows).groupby(["state", "year", "epi_week"], as_index=False)["reliefweb_flood_reports"].sum()


def collect_flood_features(
    start_date: str,
    end_date: str,
    appname: str = "cholera-risk-platform",
    climate_path: Path = CLIMATE_WEEKLY_PATH,
    output_path: Path = FLOOD_WEEKLY_PATH,
    include_reliefweb: bool = True,
) -> pd.DataFrame:
    ensure_directories()
    flood = build_rainfall_flood_proxies(load_weekly_climate(climate_path))
    if include_reliefweb:
        try:
            reports = fetch_reliefweb_flood_reports(start_date, end_date, appname=appname)
            if not reports.empty:
                flood = flood.drop(columns=["reliefweb_flood_reports"]).merge(
                    reports, on=["state", "year", "epi_week"], how="left"
                )
                flood["reliefweb_flood_reports"] = flood["reliefweb_flood_reports"].fillna(0)
        except requests.HTTPError as exc:
            warnings.warn(f"ReliefWeb flood report query failed; keeping rainfall-only flood proxies. {exc}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    flood.to_csv(output_path, index=False)
    return flood


def main() -> None:
    parser = argparse.ArgumentParser(description="Build state-week flood proxies from rainfall and ReliefWeb flood reports.")
    parser.add_argument("--start-date", default="2021-01-01")
    parser.add_argument("--end-date", default="2025-12-31")
    parser.add_argument("--appname", default="cholera-risk-platform")
    parser.add_argument("--climate-path", type=Path, default=CLIMATE_WEEKLY_PATH)
    parser.add_argument("--output", type=Path, default=FLOOD_WEEKLY_PATH)
    parser.add_argument("--skip-reliefweb", action="store_true")
    args = parser.parse_args()
    frame = collect_flood_features(
        start_date=args.start_date,
        end_date=args.end_date,
        appname=args.appname,
        climate_path=args.climate_path,
        output_path=args.output,
        include_reliefweb=not args.skip_reliefweb,
    )
    print(f"Wrote {len(frame)} flood feature rows to {args.output}.")


if __name__ == "__main__":
    main()
