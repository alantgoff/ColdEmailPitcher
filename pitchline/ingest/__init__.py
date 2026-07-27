"""Module 1 — the investor universe.

CSV import plus pluggable public-source scrapers, resolved to partner-level records with
provenance (R1.4, R5.3).
"""

from pitchline.ingest.csv_import import ImportReport, import_investors_csv, parse_role
from pitchline.ingest.scrapers import (
    Scraper,
    ScrapeResult,
    FundSiteScraper,
    FormDScraper,
    available_scrapers,
)

__all__ = [
    "ImportReport",
    "import_investors_csv",
    "parse_role",
    "Scraper",
    "ScrapeResult",
    "FundSiteScraper",
    "FormDScraper",
    "available_scrapers",
]
