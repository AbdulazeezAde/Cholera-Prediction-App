from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

from .constants import STATE_BOUNDARIES_PATH

DEFAULT_BOUNDARY_URL = "https://gist.githubusercontent.com/sdwfrost/6c0ccf457e30963292522dc57ed1fe7a/raw/nigeria_states.geojson"


def download_state_boundaries(
    url: str = DEFAULT_BOUNDARY_URL,
    output_path: Path = STATE_BOUNDARIES_PATH,
) -> dict:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    data = response.json()
    if data.get("type") != "FeatureCollection" or not data.get("features"):
        raise ValueError("Downloaded boundary file is not a non-empty GeoJSON FeatureCollection.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data), encoding="utf-8")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Nigeria state boundary GeoJSON.")
    parser.add_argument("--url", default=DEFAULT_BOUNDARY_URL, help="GeoJSON URL to download.")
    parser.add_argument("--output", type=Path, default=STATE_BOUNDARIES_PATH, help="Output GeoJSON path.")
    args = parser.parse_args()
    data = download_state_boundaries(url=args.url, output_path=args.output)
    print(f"Wrote {len(data['features'])} features to {args.output}.")


if __name__ == "__main__":
    main()
