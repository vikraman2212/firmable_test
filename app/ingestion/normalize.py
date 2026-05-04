"""Ingestion normalization pipeline — CSV reader, field normalizers, ID/semantic
text generation, and staged Parquet output.

Each public function is a pure transformation step so individual stages remain
independently testable without I/O side effects.

CSV column → canonical field mapping
-------------------------------------
  (unnamed first col)  → source_id   (str, the raw integer key)
  name                 → name
  domain               → domain
  year founded         → year_founded
  industry             → industry
  size range           → size_range
  locality             → locality (intermediate), then → city / region / country
  country              → country  (source country field, cross-check with locality)
  linkedin url         → linkedin_url
  current employee estimate → current_employee_estimate
  total employee estimate   → total_employee_estimate
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator, Optional

# Re-export normalizers and identity helpers so callers can import from this
# single module without needing to know the internal file split.
from app.ingestion.normalizers import (  # noqa: F401
    normalize_country,
    normalize_domain,
    normalize_industry,
    normalize_linkedin_url,
    normalize_name,
    normalize_size_range,
    normalize_text_field,
    parse_employee_estimate,
    parse_locality,
    parse_year_founded,
)
from app.ingestion.identity import build_company_id, build_semantic_text  # noqa: F401

# ---------------------------------------------------------------------------
# Source column names (match the Kaggle CSV header exactly)
# ---------------------------------------------------------------------------

_SOURCE_ID_COL = ""                         # unnamed first column
_SOURCE_COLUMNS = {
    "source_id": _SOURCE_ID_COL,
    "name": "name",
    "domain": "domain",
    "year_founded_raw": "year founded",
    "industry": "industry",
    "size_range": "size range",
    "locality_raw": "locality",
    "country_raw": "country",
    "linkedin_url": "linkedin url",
    "current_employee_estimate_raw": "current employee estimate",
    "total_employee_estimate_raw": "total employee estimate",
}

# All source column names that must be present for the reader to proceed
REQUIRED_SOURCE_COLUMNS: frozenset[str] = frozenset(_SOURCE_COLUMNS.values())


# ---------------------------------------------------------------------------
# Raw row type — intermediate shape before validation / normalization
# ---------------------------------------------------------------------------

class RawCompanyRow:
    """Holds values mapped directly from one CSV row with no conversion applied.

    Using a plain class (rather than a dataclass) keeps the representation
    explicit and avoids any implicit coercion at read time.
    """

    __slots__ = (
        "source_id",
        "name",
        "domain",
        "year_founded_raw",
        "industry",
        "size_range",
        "locality_raw",
        "country_raw",
        "linkedin_url",
        "current_employee_estimate_raw",
        "total_employee_estimate_raw",
    )

    def __init__(
        self,
        source_id: str,
        name: str,
        domain: str,
        year_founded_raw: str,
        industry: str,
        size_range: str,
        locality_raw: str,
        country_raw: str,
        linkedin_url: str,
        current_employee_estimate_raw: str,
        total_employee_estimate_raw: str,
    ) -> None:
        self.source_id = source_id
        self.name = name
        self.domain = domain
        self.year_founded_raw = year_founded_raw
        self.industry = industry
        self.size_range = size_range
        self.locality_raw = locality_raw
        self.country_raw = country_raw
        self.linkedin_url = linkedin_url
        self.current_employee_estimate_raw = current_employee_estimate_raw
        self.total_employee_estimate_raw = total_employee_estimate_raw


# ---------------------------------------------------------------------------
# CSV reader
# ---------------------------------------------------------------------------

def _blank(value: str) -> bool:
    return not value or not value.strip()


def _strip_or_none(value: str) -> Optional[str]:
    stripped = value.strip() if value else ""
    return stripped if stripped else None


def validate_csv_columns(fieldnames: list[str]) -> None:
    """Raise ValueError if any required source column is absent from the header.

    Args:
        fieldnames: The list of column names returned by csv.DictReader.

    Raises:
        ValueError: With a message listing all missing column names.
    """
    missing = REQUIRED_SOURCE_COLUMNS - set(fieldnames)
    if missing:
        formatted = ", ".join(sorted(repr(c) for c in missing))
        raise ValueError(f"CSV is missing required columns: {formatted}")


def read_csv_rows(
    csv_path: Path,
    *,
    row_limit: Optional[int] = None,
) -> Iterator[RawCompanyRow]:
    """Yield raw, unmapped rows from the companies CSV.

    Performs column validation on the first read and then streams rows one at a
    time so callers can process large files without loading everything into
    memory.

    Args:
        csv_path: Absolute or relative path to the source CSV file.
        row_limit: If provided, stops after yielding this many data rows (not
            counting the header).  Useful for local subset runs and tests.

    Yields:
        RawCompanyRow for each data row up to row_limit.

    Raises:
        FileNotFoundError: If csv_path does not exist.
        ValueError: If any required column is absent from the header.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        validate_csv_columns(list(reader.fieldnames or []))

        count = 0
        for raw in reader:
            if row_limit is not None and count >= row_limit:
                break
            yield RawCompanyRow(
                source_id=raw[_SOURCE_ID_COL].strip(),
                name=raw["name"].strip(),
                domain=raw["domain"].strip(),
                year_founded_raw=raw["year founded"].strip(),
                industry=raw["industry"].strip(),
                size_range=raw["size range"].strip(),
                locality_raw=raw["locality"].strip(),
                country_raw=raw["country"].strip(),
                linkedin_url=raw["linkedin url"].strip(),
                current_employee_estimate_raw=raw["current employee estimate"].strip(),
                total_employee_estimate_raw=raw["total employee estimate"].strip(),
            )
            count += 1
