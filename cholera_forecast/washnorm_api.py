from __future__ import annotations

import argparse
import re
import warnings
from pathlib import Path

import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup

from .constants import RAW_DIR, STATE_WASH_PATH, WASH_COLUMNS, ensure_directories
from .data_pipeline import normalize_state_name

WASHNORM_2021_PAGE = (
    "https://www.unicef.org/nigeria/reports/water-sanitation-and-hygiene-national-outcome-routine-mapping-report-2021"
)
WASHNORM_REPORT_DIR = RAW_DIR / "washnorm"


def find_state_profile_pdf(page_url: str = WASHNORM_2021_PAGE) -> str:
    response = requests.get(page_url, headers={"User-Agent": "cholera-risk-platform/1.0"}, timeout=60)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    for link in soup.find_all("a", href=True):
        text = link.get_text(" ", strip=True).lower()
        href = link["href"]
        if "pdf" in href.lower() or "pdf" in text:
            candidates.append((text, requests.compat.urljoin(page_url, href)))
    for text, href in candidates:
        if "state" in text and "wash" in text:
            return href
    for text, href in candidates:
        if "washnorm" in text or "wash" in text:
            return href
    raise ValueError("Could not find a WASHNORM PDF link on the UNICEF page.")


def download_washnorm_pdf(output_dir: Path = WASHNORM_REPORT_DIR) -> Path:
    ensure_directories()
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_url = find_state_profile_pdf()
    output_path = output_dir / "washnorm_2021_state_profiles.pdf"
    response = requests.get(pdf_url, headers={"User-Agent": "cholera-risk-platform/1.0"}, timeout=120)
    response.raise_for_status()
    output_path.write_bytes(response.content)
    return output_path


def parse_percent(value: object) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def extract_state_wash_from_pdf(pdf_path: Path, year: int = 2021) -> pd.DataFrame:
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            state_match = re.search(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)\s+State\b", text)
            if not state_match:
                continue
            state = normalize_state_name(state_match.group(1))
            lower = text.lower()
            rows.append(
                {
                    "state": state,
                    "year": year,
                    "basic_water_pct": parse_percent(re.search(r"basic water[^\d]*(\d+(?:\.\d+)?)", lower).group(1))
                    if re.search(r"basic water[^\d]*(\d+(?:\.\d+)?)", lower)
                    else None,
                    "safely_managed_water_pct": None,
                    "basic_sanitation_pct": parse_percent(re.search(r"basic sanitation[^\d]*(\d+(?:\.\d+)?)", lower).group(1))
                    if re.search(r"basic sanitation[^\d]*(\d+(?:\.\d+)?)", lower)
                    else None,
                    "safely_managed_sanitation_pct": None,
                    "open_defecation_pct": parse_percent(re.search(r"open defecation[^\d]*(\d+(?:\.\d+)?)", lower).group(1))
                    if re.search(r"open defecation[^\d]*(\d+(?:\.\d+)?)", lower)
                    else None,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["state", "year", *WASH_COLUMNS])
    return frame.drop_duplicates(subset=["state", "year"])[["state", "year", *WASH_COLUMNS]]


def collect_washnorm_state_profiles(
    output_path: Path = STATE_WASH_PATH,
    pdf_path: Path | None = None,
    year: int = 2021,
) -> pd.DataFrame:
    try:
        pdf = pdf_path if pdf_path else download_washnorm_pdf()
        frame = extract_state_wash_from_pdf(pdf, year=year)
    except requests.HTTPError as exc:
        warnings.warn(f"WASHNORM direct download failed; writing empty state WASH file. {exc}")
        frame = pd.DataFrame(columns=["state", "year", *WASH_COLUMNS])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Download/scrape WASHNORM state WASH profiles.")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--year", type=int, default=2021)
    parser.add_argument("--output", type=Path, default=STATE_WASH_PATH)
    args = parser.parse_args()
    frame = collect_washnorm_state_profiles(output_path=args.output, pdf_path=args.pdf, year=args.year)
    print(f"Wrote {len(frame)} state WASH rows to {args.output}.")


if __name__ == "__main__":
    main()
