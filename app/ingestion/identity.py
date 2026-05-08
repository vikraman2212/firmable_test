"""Stable identifier and semantic text generation for company records.

These are pure functions with no I/O side effects, usable independently of
the CSV reader or normalizer pipeline.
"""
from __future__ import annotations

from typing import Optional

from app.models.company import make_company_id


def build_company_id(source_id: str, raw_name: str) -> str:
    """Return a deterministic company_id by normalizing name then calling make_company_id.

    Normalization: strip + lowercase.
    Delegates to make_company_id(source_id, normalized_name).

    Args:
        source_id: Raw value from the first CSV column (e.g. "5872184").
        raw_name: Raw company name before normalization (e.g. "IBM" or "ibm").

    Returns:
        64-character lowercase hex SHA-256 digest.
    """
    normalized_name = raw_name.strip().lower()
    return make_company_id(source_id, normalized_name)


def build_semantic_text(
    name: str,
    *,
    industry: Optional[str] = None,
    city: Optional[str] = None,
    region: Optional[str] = None,
    country: Optional[str] = None,
    year_founded: Optional[int] = None,
    size_range: Optional[str] = None,
    employee_estimate: Optional[int] = None,
) -> str:
    """Build the company_semantic_text string used as embedding input.

    Composition order: name, industry, city, region, country, "founded YEAR",
    "employees N", size_range label.
    Only non-None, non-blank parts are included.
    Parts are joined with a single space.
    name is required and must be non-blank (raises ValueError if blank).

    Args:
        name: Normalized company name (required).
        industry: Normalized industry string (optional).
        city: Normalized city (optional).
        region: Normalized region (optional).
        country: Normalized country (optional).
        year_founded: Integer year (optional).
        size_range: Size bucket string, e.g. "1001 - 5000" (optional).
        employee_estimate: Current employee headcount integer (optional).

    Returns:
        Space-joined semantic text string.

    Raises:
        ValueError: If name is blank after stripping.
    """
    if not name or not name.strip():
        raise ValueError("name must be a non-blank string")

    parts: list[str] = [name]

    if industry is not None and industry.strip():
        parts.append(industry)
    if city is not None and city.strip():
        parts.append(city)
    if region is not None and region.strip():
        parts.append(region)
    if country is not None and country.strip():
        parts.append(country)
    if year_founded is not None:
        parts.append(f"founded {year_founded}")
    if employee_estimate is not None:
        parts.append(f"employees {employee_estimate}")
    if size_range is not None and size_range.strip():
        parts.append(size_range)

    return " ".join(parts)
