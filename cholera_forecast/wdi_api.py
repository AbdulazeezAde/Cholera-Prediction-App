from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import requests

from .constants import WDI_WASH_PATH, ensure_directories

WORLD_BANK_API = "https://api.worldbank.org/v2"

WDI_WASH_INDICATORS = {
    "basic_water_pct": "SH.H2O.BASW.ZS",
    "safely_managed_water_pct": "SH.H2O.SMDW.ZS",
    "basic_sanitation_pct": "SH.STA.BASS.ZS",
    "safely_managed_sanitation_pct": "SH.STA.SMSS.ZS",
    "open_defecation_pct": "SH.STA.ODFC.ZS",
}


def fetch_indicator(
    indicator: str,
    start_year: int,
    end_year: int,
    country: str = "NGA",
    timeout: int = 30,
) -> pd.DataFrame:
    url = f"{WORLD_BANK_API}/country/{country}/indicator/{indicator}"
    response = requests.get(
        url,
        params={
            "format": "json",
            "date": f"{start_year}:{end_year}",
            "per_page": 200,
            "source": 2,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        return pd.DataFrame(columns=["year", "value"])

    rows = []
    for item in payload[1]:
        rows.append(
            {
                "year": int(item["date"]),
                "value": item.get("value"),
                "indicator_code": indicator,
                "indicator_name": item.get("indicator", {}).get("value"),
                "country": item.get("country", {}).get("value"),
            }
        )
    return pd.DataFrame(rows)


def collect_wdi_wash(
    start_year: int,
    end_year: int,
    country: str = "NGA",
    output_path: Path = WDI_WASH_PATH,
) -> pd.DataFrame:
    ensure_directories()
    years = pd.DataFrame({"year": list(range(start_year, end_year + 1))})
    merged = years.copy()
    metadata_rows = []

    for column, indicator in WDI_WASH_INDICATORS.items():
        indicator_frame = fetch_indicator(indicator, start_year, end_year, country=country)
        if indicator_frame.empty:
            merged[column] = pd.NA
            continue
        values = indicator_frame[["year", "value"]].rename(columns={"value": column})
        merged = merged.merge(values, on="year", how="left")
        metadata_rows.extend(
            indicator_frame[["indicator_code", "indicator_name", "country"]]
            .drop_duplicates()
            .to_dict("records")
        )

    value_columns = [column for column in WDI_WASH_INDICATORS if column in merged.columns]
    merged = merged.sort_values("year").reset_index(drop=True)
    merged[value_columns] = merged[value_columns].apply(pd.to_numeric, errors="coerce")
    merged[value_columns] = merged[value_columns].ffill().bfill()
    merged["source"] = "World Bank WDI"
    merged["source_note"] = "National annual WASH proxy repeated across state-week cholera rows."

    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)

    metadata_path = output_path.with_suffix(".metadata.csv")
    pd.DataFrame(metadata_rows).drop_duplicates().to_csv(metadata_path, index=False)
    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Nigeria WASH indicators from World Bank WDI.")
    parser.add_argument("--start-year", type=int, default=2021)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--country", default="NGA", help="World Bank country code, default: NGA.")
    parser.add_argument("--output", type=Path, default=WDI_WASH_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frame = collect_wdi_wash(
        start_year=args.start_year,
        end_year=args.end_year,
        country=args.country,
        output_path=args.output,
    )
    print(f"Wrote {len(frame)} WDI WASH rows to {args.output}.")


if __name__ == "__main__":
    main()
