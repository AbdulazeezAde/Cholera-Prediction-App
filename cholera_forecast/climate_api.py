from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import requests

from .constants import (
    CLIMATE_DAILY_PATH,
    CLIMATE_WEEKLY_PATH,
    STATE_COORDINATES_PATH,
    ensure_directories,
)

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
NASA_PARAMETERS = "T2M,RH2M,PRECTOTCORR"


def load_state_coordinates(path: Path = STATE_COORDINATES_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Expected state coordinates at {path}. Create this dataset with state, latitude, and longitude columns."
        )
    coordinates = pd.read_csv(path)
    required = {"state", "latitude", "longitude"}
    missing = required.difference(coordinates.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    return coordinates


def fetch_nasa_power(lat: float, lon: float, start_date: str, end_date: str) -> pd.DataFrame:
    params = {
        "parameters": NASA_PARAMETERS,
        "community": "AG",
        "longitude": lon,
        "latitude": lat,
        "start": start_date,
        "end": end_date,
        "format": "JSON",
    }
    response = requests.get(NASA_POWER_URL, params=params, timeout=60)
    response.raise_for_status()
    parameter_data = response.json()["properties"]["parameter"]
    frame = pd.DataFrame(parameter_data)
    frame.index = pd.to_datetime(frame.index, format="%Y%m%d")
    return frame.reset_index(names="date")


def collect_state_climate(
    start_date: str,
    end_date: str,
    coordinates_path: Path = STATE_COORDINATES_PATH,
    output_path: Path = CLIMATE_DAILY_PATH,
) -> pd.DataFrame:
    ensure_directories()
    coordinates = load_state_coordinates(coordinates_path)

    rows: list[pd.DataFrame] = []
    for state_row in coordinates.itertuples(index=False):
        state_climate = fetch_nasa_power(
            lat=float(state_row.latitude),
            lon=float(state_row.longitude),
            start_date=start_date,
            end_date=end_date,
        )
        state_climate["state"] = state_row.state
        rows.append(state_climate)

    daily = pd.concat(rows, ignore_index=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    daily.to_csv(output_path, index=False)
    return daily


def aggregate_daily_to_weekly(
    daily: pd.DataFrame,
    output_path: Path = CLIMATE_WEEKLY_PATH,
) -> pd.DataFrame:
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    iso = frame["date"].dt.isocalendar()
    frame["year"] = iso.year.astype(int)
    frame["epi_week"] = iso.week.astype(int)
    weekly = (
        frame.groupby(["state", "year", "epi_week"], as_index=False)
        .agg({"PRECTOTCORR": "sum", "T2M": "mean", "RH2M": "mean"})
        .rename(
            columns={
                "PRECTOTCORR": "rainfall_mm",
                "T2M": "temperature_c",
                "RH2M": "humidity_pct",
            }
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    weekly.to_csv(output_path, index=False)
    return weekly


def collect_weekly_climate(start_date: str, end_date: str) -> pd.DataFrame:
    daily = collect_state_climate(start_date=start_date, end_date=end_date)
    return aggregate_daily_to_weekly(daily)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect NASA POWER climate data for Nigerian state centroids.")
    parser.add_argument("--start", required=True, help="Start date in YYYYMMDD format.")
    parser.add_argument("--end", required=True, help="End date in YYYYMMDD format.")
    args = parser.parse_args()
    weekly = collect_weekly_climate(start_date=args.start, end_date=args.end)
    print(f"Wrote {len(weekly)} weekly climate rows to {CLIMATE_WEEKLY_PATH}.")


if __name__ == "__main__":
    main()
