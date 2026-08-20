from __future__ import annotations

from pathlib import Path

import pandas as pd

from .constants import (
    CHOLERA_DATA_PATH,
    CHOLERA_REQUIRED_COLUMNS,
    CLIMATE_COLUMNS,
    CLIMATE_WEEKLY_PATH,
    DISPLACEMENT_COLUMNS,
    DISPLACEMENT_PATH,
    FLOOD_COLUMNS,
    FLOOD_WEEKLY_PATH,
    HEALTH_FACILITY_COLUMNS,
    HEALTH_FACILITY_PATH,
    MODELING_DATASET_PATH,
    STATE_WASH_PATH,
    WASH_COLUMNS,
    WDI_WASH_PATH,
    ensure_directories,
)
from .features import build_features, parse_epi_week_bounds


def canonical_column_name(column: str) -> str:
    normalized = column.strip().lower().replace(" ", "_")
    aliases = {
        "state": "state",
        "cases": "cases",
        "case": "cases",
        "suspected_cases": "suspected_cases",
        "suspected": "suspected_cases",
        "cfr": "cfr",
        "case_fatality_ratio": "cfr",
        "case_fatality_rate": "cfr",
        "deaths": "deaths",
        "death": "deaths",
    }
    return aliases.get(normalized, normalized)


def normalize_state_name(value: object) -> str:
    state = str(value).strip()
    replacements = {
        "Akwa-Ibom": "Akwa Ibom",
        "Cross-River": "Cross River",
        "Nassarawa": "Nasarawa",
        "Federal Capital Territory": "FCT",
    }
    return replacements.get(state, state.replace("-", " "))


def load_cholera_data(path: Path = CHOLERA_DATA_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Expected raw cholera data at {path}. Put your cleaned NCDC state-week CSV there."
        )
    frame = pd.read_csv(path)
    frame = frame.rename(columns={column: canonical_column_name(column) for column in frame.columns})
    missing = CHOLERA_REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

    frame["state"] = frame["state"].map(normalize_state_name)

    if "suspected_cases" not in frame.columns:
        if "cases" not in frame.columns:
            raise ValueError(f"{path} must contain either 'cases' or 'suspected_cases'.")
        frame["suspected_cases"] = frame["cases"]

    if "confirmed_cases" not in frame.columns:
        frame["confirmed_cases"] = pd.NA

    if "deaths" not in frame.columns:
        frame["deaths"] = 0

    for column in ["year", "suspected_cases", "confirmed_cases", "deaths", "cases", "cfr"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    if "cfr" not in frame.columns:
        frame["cfr"] = pd.NA
    computed_cfr = frame["deaths"] / frame["suspected_cases"].replace({0: pd.NA})
    frame["cfr"] = frame["cfr"].fillna(computed_cfr).fillna(0)
    return frame


def load_climate_data(path: Path = CLIMATE_WEEKLY_PATH) -> pd.DataFrame | None:
    if not path.exists():
        return None
    climate = pd.read_csv(path)
    required = {"state", "year", "epi_week", *CLIMATE_COLUMNS}
    missing = required.difference(climate.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    return climate


def load_wash_data(path: Path = WDI_WASH_PATH) -> pd.DataFrame | None:
    if not path.exists():
        return None
    wash = pd.read_csv(path)
    required = {"year", *WASH_COLUMNS}
    missing = required.difference(wash.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    wash["year"] = pd.to_numeric(wash["year"], errors="coerce")
    for column in WASH_COLUMNS:
        wash[column] = pd.to_numeric(wash[column], errors="coerce")
    return wash[["year", *WASH_COLUMNS]].drop_duplicates(subset=["year"])


def load_state_wash_data(path: Path = STATE_WASH_PATH) -> pd.DataFrame | None:
    if not path.exists():
        return None
    wash = pd.read_csv(path)
    required = {"state", "year", *WASH_COLUMNS}
    missing = required.difference(wash.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    wash["state"] = wash["state"].map(normalize_state_name)
    wash["year"] = pd.to_numeric(wash["year"], errors="coerce")
    for column in WASH_COLUMNS:
        wash[column] = pd.to_numeric(wash[column], errors="coerce")
    return wash[["state", "year", *WASH_COLUMNS]].drop_duplicates(subset=["state", "year"])


def load_flood_data(path: Path = FLOOD_WEEKLY_PATH) -> pd.DataFrame | None:
    if not path.exists():
        return None
    flood = pd.read_csv(path)
    required = {"state", "year", "epi_week", *FLOOD_COLUMNS}
    missing = required.difference(flood.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    flood["state"] = flood["state"].map(normalize_state_name)
    for column in ["year", "epi_week", *FLOOD_COLUMNS]:
        flood[column] = pd.to_numeric(flood[column], errors="coerce")
    return flood


def load_displacement_data(path: Path = DISPLACEMENT_PATH) -> pd.DataFrame | None:
    if not path.exists():
        return None
    displacement = pd.read_csv(path)
    required = {"state", "year", *DISPLACEMENT_COLUMNS}
    missing = required.difference(displacement.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    displacement["state"] = displacement["state"].map(normalize_state_name)
    for column in ["year", *DISPLACEMENT_COLUMNS]:
        displacement[column] = pd.to_numeric(displacement[column], errors="coerce")
    return displacement[["state", "year", *DISPLACEMENT_COLUMNS]].drop_duplicates(subset=["state", "year"])


def load_health_facility_data(path: Path = HEALTH_FACILITY_PATH) -> pd.DataFrame | None:
    if not path.exists():
        return None
    health = pd.read_csv(path)
    required = {"state", *HEALTH_FACILITY_COLUMNS}
    missing = required.difference(health.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    health["state"] = health["state"].map(normalize_state_name)
    for column in HEALTH_FACILITY_COLUMNS:
        health[column] = pd.to_numeric(health[column], errors="coerce")
    return health[["state", *HEALTH_FACILITY_COLUMNS]].drop_duplicates(subset=["state"])


def merge_climate(cholera: pd.DataFrame, climate: pd.DataFrame | None) -> pd.DataFrame:
    frame = cholera.copy()
    if climate is None:
        return frame

    source = frame.drop(columns=[column for column in CLIMATE_COLUMNS if column in frame.columns])
    bounds = source["epi_week"].apply(parse_epi_week_bounds)
    source["_epi_week_start"] = bounds.apply(lambda pair: pair[0]).astype(int)
    source["_epi_week_end"] = bounds.apply(lambda pair: pair[1]).astype(int)
    climate_frame = climate.copy()
    climate_frame["epi_week"] = pd.to_numeric(climate_frame["epi_week"], errors="coerce")

    rows = []
    for record in source.to_dict("records"):
        climate_slice = climate_frame[
            (climate_frame["state"] == record["state"])
            & (climate_frame["year"] == record["year"])
            & (climate_frame["epi_week"] >= record["_epi_week_start"])
            & (climate_frame["epi_week"] <= record["_epi_week_end"])
        ]
        enriched = {key: value for key, value in record.items() if not key.startswith("_")}
        if not climate_slice.empty:
            enriched["rainfall_mm"] = climate_slice["rainfall_mm"].sum()
            enriched["temperature_c"] = climate_slice["temperature_c"].mean()
            enriched["humidity_pct"] = climate_slice["humidity_pct"].mean()
        rows.append(enriched)
    return pd.DataFrame(rows)


def merge_flood(cholera: pd.DataFrame, flood: pd.DataFrame | None) -> pd.DataFrame:
    frame = cholera.copy()
    if flood is None:
        return frame

    source = frame.drop(columns=[column for column in FLOOD_COLUMNS if column in frame.columns])
    bounds = source["epi_week"].apply(parse_epi_week_bounds)
    source["_epi_week_start"] = bounds.apply(lambda pair: pair[0]).astype(int)
    source["_epi_week_end"] = bounds.apply(lambda pair: pair[1]).astype(int)
    flood_frame = flood.copy()

    rows = []
    for record in source.to_dict("records"):
        flood_slice = flood_frame[
            (flood_frame["state"] == record["state"])
            & (flood_frame["year"] == record["year"])
            & (flood_frame["epi_week"] >= record["_epi_week_start"])
            & (flood_frame["epi_week"] <= record["_epi_week_end"])
        ]
        enriched = {key: value for key, value in record.items() if not key.startswith("_")}
        if not flood_slice.empty:
            for column in FLOOD_COLUMNS:
                reducer = "sum" if column.endswith("_flag") or column == "reliefweb_flood_reports" else "mean"
                value = getattr(flood_slice[column], reducer)()
                enriched[column] = min(value, 1) if column.endswith("_flag") else value
        rows.append(enriched)
    return pd.DataFrame(rows)


def merge_wash(cholera: pd.DataFrame, wash: pd.DataFrame | None) -> pd.DataFrame:
    frame = cholera.copy()
    if wash is None:
        return frame
    source = frame.merge(wash, on="year", how="left", suffixes=("", "_national"))
    for column in WASH_COLUMNS:
        national_column = f"{column}_national"
        if national_column in source.columns:
            if column in source.columns:
                source[column] = source[column].fillna(source[national_column])
            else:
                source[column] = source[national_column]
            source = source.drop(columns=[national_column])
    return source


def merge_state_wash(cholera: pd.DataFrame, wash: pd.DataFrame | None) -> pd.DataFrame:
    frame = cholera.copy()
    if wash is None:
        return frame
    return frame.merge(wash, on=["state", "year"], how="left", suffixes=("", "_state"))


def merge_displacement(cholera: pd.DataFrame, displacement: pd.DataFrame | None) -> pd.DataFrame:
    frame = cholera.copy()
    if displacement is None:
        return frame
    source = frame.drop(columns=[column for column in DISPLACEMENT_COLUMNS if column in frame.columns])
    return source.merge(displacement, on=["state", "year"], how="left")


def merge_health_facilities(cholera: pd.DataFrame, health: pd.DataFrame | None) -> pd.DataFrame:
    frame = cholera.copy()
    if health is None:
        return frame
    source = frame.drop(columns=[column for column in HEALTH_FACILITY_COLUMNS if column in frame.columns])
    return source.merge(health, on="state", how="left")


def build_dataset(
    cholera_path: Path = CHOLERA_DATA_PATH,
    climate_path: Path = CLIMATE_WEEKLY_PATH,
    wash_path: Path = WDI_WASH_PATH,
    state_wash_path: Path = STATE_WASH_PATH,
    flood_path: Path = FLOOD_WEEKLY_PATH,
    displacement_path: Path = DISPLACEMENT_PATH,
    health_facility_path: Path = HEALTH_FACILITY_PATH,
    output_path: Path = MODELING_DATASET_PATH,
) -> pd.DataFrame:
    ensure_directories()
    cholera = load_cholera_data(cholera_path)
    climate = load_climate_data(climate_path)
    wash = load_wash_data(wash_path)
    state_wash = load_state_wash_data(state_wash_path)
    flood = load_flood_data(flood_path)
    displacement = load_displacement_data(displacement_path)
    health = load_health_facility_data(health_facility_path)
    merged = merge_climate(cholera, climate)
    merged = merge_flood(merged, flood)
    merged = merge_state_wash(merged, state_wash)
    merged = merge_wash(merged, wash)
    merged = merge_displacement(merged, displacement)
    merged = merge_health_facilities(merged, health)
    modeled = build_features(merged)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    modeled.to_csv(output_path, index=False)
    return modeled
