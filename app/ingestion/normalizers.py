"""Pure field normalizer functions for company CSV data.

All functions accept a raw string (possibly blank or None-ish) and return
a normalized value or None.  No I/O, no external dependencies.
"""

from __future__ import annotations

from typing import Optional


def normalize_text_field(raw: str) -> Optional[str]:
    """Strip and lowercase. Return None if blank after stripping."""
    if not raw:
        return None
    stripped = raw.strip().lower()
    return stripped if stripped else None


def normalize_name(raw: str) -> Optional[str]:
    """Strip and lowercase. Return None if blank."""
    return normalize_text_field(raw)


def normalize_domain(raw: str) -> Optional[str]:
    """Strip and lowercase. Return None if blank."""
    return normalize_text_field(raw)


def normalize_industry(raw: str) -> Optional[str]:
    """Strip and lowercase. Return None if blank."""
    return normalize_text_field(raw)


def normalize_size_range(raw: str) -> Optional[str]:
    """Strip only (preserve original casing like '10001+'). Return None if blank."""
    if not raw:
        return None
    stripped = raw.strip()
    return stripped if stripped else None


def normalize_linkedin_url(raw: str) -> Optional[str]:
    """Strip only. Return None if blank."""
    if not raw:
        return None
    stripped = raw.strip()
    return stripped if stripped else None


def normalize_country(raw: str) -> Optional[str]:
    """Strip and lowercase. Return None if blank."""
    return normalize_text_field(raw)


def parse_locality(raw: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse a raw locality string into (city, region, country).

    Splits on ', ' (comma+space):
    - 3+ parts: city=parts[0].lower, region=parts[1].lower, country=parts[2:].lower
    - 2 parts:  city=parts[0].lower, region=None, country=parts[1].lower
    - 1 part:   city=None, region=None, country=parts[0].lower (if non-blank)
    - blank:    return (None, None, None)
    All returned values are strip+lowercased; blank after strip → None.
    """
    if not raw or not raw.strip():
        return (None, None, None)

    parts = raw.split(", ")

    def clean(s: str) -> Optional[str]:
        v = s.strip().lower()
        return v if v else None

    if len(parts) >= 3:
        city = clean(parts[0])
        region = clean(parts[1])
        country = clean(", ".join(parts[2:]))
        return (city, region, country)
    elif len(parts) == 2:
        city = clean(parts[0])
        country = clean(parts[1])
        return (city, None, country)
    else:
        country = clean(parts[0])
        return (None, None, country)


def parse_year_founded(raw: str) -> Optional[int]:
    """Parse raw year string to int.

    Handles:
    - "1911.0" → 1911  (float string → truncate decimal)
    - "1989"   → 1989
    - blank    → None
    - non-numeric garbage → None (does NOT raise)
    """
    if not raw or not raw.strip():
        return None
    try:
        return int(float(raw.strip()))
    except (ValueError, OverflowError):
        return None


def parse_employee_estimate(raw: str) -> Optional[int]:
    """Parse raw employee count string to int.

    Handles:
    - "274047"   → 274047
    - "274047.0" → 274047
    - blank      → None
    - non-numeric → None (does NOT raise)
    """
    if not raw or not raw.strip():
        return None
    try:
        return int(float(raw.strip()))
    except (ValueError, OverflowError):
        return None
