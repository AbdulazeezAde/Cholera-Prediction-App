from __future__ import annotations

import argparse
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from .constants import DISPLACEMENT_PATH, STATE_COORDINATES_PATH, ensure_directories
from .data_pipeline import normalize_state_name

UNHCR_NIGERIA_IDP_CSV = (
    "https://data.unhcr.org/population/?export=csv&geo_id=699&population_group=4601%2C5266&widget_id=690705"
)


def load_states(path: Path = STATE_COORDINATES_PATH) -> list[str]:
    if path.exists():
        frame = pd.read_csv(path)
        if "state" in frame.columns:
            return sorted(frame["state"].dropna().map(normalize_state_name).unique())
    return []


def first_existing_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    normalized = {str(column).lower().strip().replace(" ", "_"): column for column in frame.columns}
    for candidate in candidates:
        key = candidate.lower().strip().replace(" ", "_")
        if key in normalized:
            return normalized[key]
    return None


def normalize_dtm_admin1(frame: pd.DataFrame) -> pd.DataFrame:
    state_column = first_existing_column(frame, ["Admin1Name", "admin1_name", "admin1", "state"])
    date_column = first_existing_column(frame, ["ReportingDate", "reporting_date", "date", "assessment_date"])
    idp_column = first_existing_column(frame, ["IDPIndividuals", "idp_individuals", "idp_population", "idps"])
    returnee_column = first_existing_column(frame, ["ReturneeIndividuals", "returnee_individuals", "returnee_population"])
    round_column = first_existing_column(frame, ["RoundNumber", "round_number", "round"])

    if state_column is None or date_column is None or idp_column is None:
        raise ValueError("DTM data did not include recognizable state, date, and IDP columns.")

    result = pd.DataFrame(
        {
            "state": frame[state_column].map(normalize_state_name),
            "date": pd.to_datetime(frame[date_column], errors="coerce"),
            "idp_population": pd.to_numeric(frame[idp_column], errors="coerce"),
            "returnee_population": pd.to_numeric(frame[returnee_column], errors="coerce") if returnee_column else 0,
            "displacement_round": pd.to_numeric(frame[round_column], errors="coerce") if round_column else 0,
        }
    ).dropna(subset=["state", "date"])
    result["year"] = result["date"].dt.year.astype(int)
    result["displacement_data_age_days"] = 0
    return (
        result.sort_values("date")
        .groupby(["state", "year"], as_index=False)
        .tail(1)[["state", "year", "idp_population", "returnee_population", "displacement_round", "displacement_data_age_days"]]
    )


def fetch_dtm_admin1(subscription_key: str, country: str = "Nigeria") -> pd.DataFrame:
    try:
        from dtmapi import DTMApi
    except ImportError as exc:
        raise RuntimeError("Install dtmapi or use the UNHCR fallback. Example: uv pip install dtmapi") from exc

    api = DTMApi(subscription_key=subscription_key)
    frame = api.get_idp_admin1_data(CountryName=country)
    return normalize_dtm_admin1(frame)


def fetch_unhcr_national_idp(csv_url: str = UNHCR_NIGERIA_IDP_CSV) -> pd.DataFrame:
    response = requests.get(csv_url, timeout=60)
    response.raise_for_status()
    if response.text.lstrip().startswith("{"):
        payload = response.json()
        frame = pd.DataFrame(payload.get("data", []))
    else:
        frame = pd.read_csv(StringIO(response.text))
    date_column = first_existing_column(frame, ["date", "year", "updated_at", "reference_date"])
    value_column = first_existing_column(frame, ["individuals", "value", "population", "total"])
    if date_column is None or value_column is None:
        numeric_columns = [column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])]
        if not numeric_columns:
            raise ValueError("UNHCR CSV did not include recognizable date/year and population columns.")
        value_column = numeric_columns[-1]
        date_column = frame.columns[0]

    result = frame.copy()
    result["_date"] = pd.to_datetime(result[date_column], errors="coerce")
    result["_year"] = pd.to_numeric(result[date_column], errors="coerce")
    result["year"] = result["_date"].dt.year.fillna(result["_year"]).astype("Int64")
    result["idp_population"] = pd.to_numeric(result[value_column], errors="coerce")
    result = result.dropna(subset=["year", "idp_population"])
    return result.groupby("year", as_index=False)["idp_population"].max()


def expand_national_to_states(national: pd.DataFrame, states: list[str], start_year: int, end_year: int) -> pd.DataFrame:
    if national.empty:
        return pd.DataFrame(
            columns=["state", "year", "idp_population", "returnee_population", "displacement_round", "displacement_data_age_days"]
        )
    years = pd.DataFrame({"year": range(start_year, end_year + 1)})
    annual = years.merge(national, on="year", how="left").sort_values("year")
    annual["idp_population"] = annual["idp_population"].ffill().bfill()
    annual["returnee_population"] = 0
    annual["displacement_round"] = 0
    annual["displacement_data_age_days"] = 365
    rows = []
    for state in states:
        state_frame = annual.copy()
        state_frame["state"] = state
        rows.append(state_frame)
    return pd.concat(rows, ignore_index=True)[
        ["state", "year", "idp_population", "returnee_population", "displacement_round", "displacement_data_age_days"]
    ]


def collect_displacement_features(
    start_year: int,
    end_year: int,
    output_path: Path = DISPLACEMENT_PATH,
    dtm_subscription_key: str | None = None,
    use_unhcr_fallback: bool = True,
) -> pd.DataFrame:
    ensure_directories()
    states = load_states()
    if dtm_subscription_key:
        displacement = fetch_dtm_admin1(dtm_subscription_key)
    elif use_unhcr_fallback:
        displacement = expand_national_to_states(fetch_unhcr_national_idp(), states, start_year, end_year)
    else:
        raise ValueError("No DTM subscription key supplied and UNHCR fallback is disabled.")

    displacement = displacement[
        (pd.to_numeric(displacement["year"], errors="coerce") >= start_year)
        & (pd.to_numeric(displacement["year"], errors="coerce") <= end_year)
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    displacement.to_csv(output_path, index=False)
    return displacement


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect displacement features from DTM or UNHCR fallback data.")
    parser.add_argument("--start-year", type=int, default=2021)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--dtm-subscription-key")
    parser.add_argument("--output", type=Path, default=DISPLACEMENT_PATH)
    parser.add_argument("--no-unhcr-fallback", action="store_true")
    args = parser.parse_args()
    frame = collect_displacement_features(
        start_year=args.start_year,
        end_year=args.end_year,
        output_path=args.output,
        dtm_subscription_key=args.dtm_subscription_key,
        use_unhcr_fallback=not args.no_unhcr_fallback,
    )
    print(f"Wrote {len(frame)} displacement rows to {args.output}.")


if __name__ == "__main__":
    main()
