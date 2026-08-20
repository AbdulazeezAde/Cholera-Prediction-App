from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import requests

from .constants import HEALTH_FACILITY_PATH, ensure_directories
from .data_pipeline import normalize_state_name

GRID3_HEALTH_FACILITY_URL = (
    "https://services3.arcgis.com/BU6Aadhn6tbBEdyk/arcgis/rest/services/"
    "GRID3_NGA_health_facilities_v2_0/FeatureServer/0/query"
)


def fetch_grid3_health_facilities(page_size: int = 2000) -> pd.DataFrame:
    rows = []
    offset = 0
    while True:
        response = requests.get(
            GRID3_HEALTH_FACILITY_URL,
            params={
                "where": "1=1",
                "outFields": "*",
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "returnGeometry": "false",
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        features = payload.get("features", [])
        rows.extend(feature.get("attributes", {}) for feature in features)
        if not payload.get("exceededTransferLimit") or not features:
            break
        offset += page_size
    return pd.DataFrame(rows)


def first_existing_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    normalized = {column.lower(): column for column in frame.columns}
    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]
    return None


def summarize_health_facilities(facilities: pd.DataFrame) -> pd.DataFrame:
    if facilities.empty:
        return pd.DataFrame(columns=["state", "health_facility_count", "hospital_count", "phc_count"])

    state_column = first_existing_column(
        facilities,
        ["state", "state_name", "admin1", "admin1_name", "adm1_name", "StateName"],
    )
    if state_column is None:
        raise ValueError("Could not find a state/admin1 column in the health facility feed.")

    type_column = first_existing_column(
        facilities,
        ["facility_level_option", "facility_level", "facility_type", "type", "facility_typology", "category", "level"],
    )

    frame = facilities.copy()
    frame["state"] = frame[state_column].map(normalize_state_name)
    frame["health_facility_count"] = 1
    if type_column:
        type_text = frame[type_column].fillna("").astype(str).str.lower()
        frame["hospital_count"] = type_text.str.contains("hospital|secondary|tertiary|medical centre|medical center").astype(int)
        frame["phc_count"] = type_text.str.contains("primary|phc|health post|clinic|health center|health centre").astype(int)
    else:
        frame["hospital_count"] = 0
        frame["phc_count"] = 0

    return (
        frame.groupby("state", as_index=False)[["health_facility_count", "hospital_count", "phc_count"]]
        .sum()
        .sort_values("state")
    )


def collect_health_facility_features(output_path: Path = HEALTH_FACILITY_PATH) -> pd.DataFrame:
    ensure_directories()
    facilities = fetch_grid3_health_facilities()
    summary = summarize_health_facilities(facilities)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_path, index=False)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Nigeria state-level health facility counts from GRID3 ArcGIS.")
    parser.add_argument("--output", type=Path, default=HEALTH_FACILITY_PATH)
    args = parser.parse_args()
    frame = collect_health_facility_features(output_path=args.output)
    print(f"Wrote {len(frame)} health facility state rows to {args.output}.")


if __name__ == "__main__":
    main()
