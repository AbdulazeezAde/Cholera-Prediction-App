from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
import pdfplumber

from .constants import NCDC_CHOLERA_URL, NCDC_REPORT_DIR, PDF_EXTRACTION_PATH, ensure_directories


def discover_ncdc_pdf_links(source_url: str = NCDC_CHOLERA_URL) -> list[str]:
    response = requests.get(source_url, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        text = anchor.get_text(" ", strip=True).lower()
        absolute_url = urljoin(source_url, href)
        if ".pdf" in href.lower() or ("download" in href.lower() and "cholera" in text):
            links.append(absolute_url)
    return sorted(set(links))


def download_ncdc_reports(limit: int = 5, output_dir: Path = NCDC_REPORT_DIR) -> list[Path]:
    ensure_directories()
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    for index, url in enumerate(discover_ncdc_pdf_links()[:limit], start=1):
        filename = Path(url.split("?")[0]).name or f"ncdc_cholera_report_{index}.pdf"
        if not filename.lower().endswith(".pdf"):
            filename = f"ncdc_cholera_report_{index}.pdf"
        output_path = output_dir / filename
        if not output_path.exists():
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            output_path.write_bytes(response.content)
        downloaded.append(output_path)
    return downloaded


def extract_pdf_tables(
    pdf_dir: Path = NCDC_REPORT_DIR,
    output_path: Path = PDF_EXTRACTION_PATH,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                for table_index, table in enumerate(page.extract_tables() or [], start=1):
                    for row_index, row in enumerate(table):
                        rows.append(
                            {
                                "source_file": pdf_path.name,
                                "page": page_num,
                                "table": table_index,
                                "row": row_index,
                                "cells": [cell.strip() if isinstance(cell, str) else cell for cell in row],
                            }
                        )
    extracted = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    extracted.to_csv(output_path, index=False)
    return extracted


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and extract NCDC cholera PDF tables.")
    parser.add_argument("--download", action="store_true", help="Download NCDC report PDFs before extraction.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum reports to download.")
    args = parser.parse_args()

    if args.download:
        downloaded = download_ncdc_reports(limit=args.limit)
        print(f"Downloaded or found {len(downloaded)} report PDFs.")
    extracted = extract_pdf_tables()
    print(f"Extracted {len(extracted)} raw PDF table rows to {PDF_EXTRACTION_PATH}.")


if __name__ == "__main__":
    main()
