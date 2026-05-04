"""Staged Parquet output pipeline (P2-T05/P2-T06).

Wires the CSV reader, field normalizers, and identity helpers into a single
pass that produces three artifacts per run:

  data/staged/companies_<timestamp>.parquet          — valid normalized records
  data/staged/dead_letter_<timestamp>.jsonl          — rejected rows with reasons
  data/staged/validation_summary_<timestamp>.json    — machine-readable run stats
  data/staged/latest.parquet                         — symlink to most recent run

Each run is self-contained and deterministic for the same input slice so
downstream seed and sync commands can replay without re-reading the CSV.

Public API
----------
stage_companies(csv_path, output_dir, row_limit) -> StagingResult
    Run the normalization pipeline and write all artifacts.

StagingResult
    Metadata struct returned by stage_companies.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pyarrow as pa
import pyarrow.parquet as pq

from app.ingestion.identity import build_company_id, build_semantic_text
from app.ingestion.normalize import read_csv_rows
from app.ingestion.normalizers import (
    normalize_domain,
    normalize_industry,
    normalize_linkedin_url,
    normalize_name,
    normalize_size_range,
    parse_employee_estimate,
    parse_locality,
    parse_year_founded,
)

# ---------------------------------------------------------------------------
# Parquet schema
# ---------------------------------------------------------------------------

PARQUET_SCHEMA = pa.schema(
    [
        pa.field("company_id", pa.string(), nullable=False),
        pa.field("name", pa.string(), nullable=False),
        pa.field("domain", pa.string(), nullable=True),
        pa.field("industry", pa.string(), nullable=True),
        pa.field("size_range", pa.string(), nullable=True),
        pa.field("city", pa.string(), nullable=True),
        pa.field("region", pa.string(), nullable=True),
        pa.field("country", pa.string(), nullable=True),
        pa.field("year_founded", pa.int32(), nullable=True),
        pa.field("current_employee_estimate", pa.int32(), nullable=True),
        pa.field("total_employee_estimate", pa.int32(), nullable=True),
        pa.field("linkedin_url", pa.string(), nullable=True),
        pa.field("company_semantic_text", pa.string(), nullable=False),
    ]
)

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class StagingResult:
    """Metadata produced by a staging run.

    Attributes:
        parquet_path: Absolute path to the written Parquet file.
        dead_letter_path: Absolute path to the JSONL dead-letter file.
        validation_summary_path: Absolute path to the JSON validation summary.
        total_rows_read: Number of source rows consumed from the CSV.
        valid_rows_written: Number of rows successfully written.
        skipped_rows: Number of rows skipped (blank name after normalization).
        run_timestamp: UTC timestamp when the run started.
        skip_reasons: Per-row rejection details (source_id, raw_name, reason).
    """

    parquet_path: Path
    dead_letter_path: Path
    validation_summary_path: Path
    total_rows_read: int
    valid_rows_written: int
    skipped_rows: int
    run_timestamp: datetime
    skip_reasons: list[dict] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_rows_read == 0:
            return 0.0
        return self.valid_rows_written / self.total_rows_read


# ---------------------------------------------------------------------------
# Normalization helper — one raw row → canonical dict or None
# ---------------------------------------------------------------------------

def _normalize_row(raw) -> Optional[dict]:
    """Normalize a single RawCompanyRow into a canonical dict.

    Returns None if the row cannot produce a valid record (e.g. blank name
    after normalization).  The caller is responsible for counting skips.
    """
    name = normalize_name(raw.name)
    if not name:
        return None  # cannot build a valid record without a name

    city, region, country_from_locality = parse_locality(raw.locality_raw)

    # Prefer locality-derived country; fall back to the source country field
    country_raw_fallback = raw.country_raw
    country = country_from_locality or (
        country_raw_fallback.strip().lower() if country_raw_fallback.strip() else None
    )

    year_founded = parse_year_founded(raw.year_founded_raw)
    current_emp = parse_employee_estimate(raw.current_employee_estimate_raw)
    total_emp = parse_employee_estimate(raw.total_employee_estimate_raw)
    industry = normalize_industry(raw.industry)
    size_range = normalize_size_range(raw.size_range)
    domain = normalize_domain(raw.domain)
    linkedin_url = normalize_linkedin_url(raw.linkedin_url)
    company_id = build_company_id(raw.source_id, name)
    semantic_text = build_semantic_text(
        name,
        industry=industry,
        city=city,
        region=region,
        country=country,
        year_founded=year_founded,
    )

    return {
        "company_id": company_id,
        "name": name,
        "domain": domain,
        "industry": industry,
        "size_range": size_range,
        "city": city,
        "region": region,
        "country": country,
        "year_founded": year_founded,
        "current_employee_estimate": current_emp,
        "total_employee_estimate": total_emp,
        "linkedin_url": linkedin_url,
        "company_semantic_text": semantic_text,
    }


# ---------------------------------------------------------------------------
# Public pipeline entry point
# ---------------------------------------------------------------------------

def stage_companies(
    csv_path: Path,
    output_dir: Path,
    *,
    row_limit: Optional[int] = None,
) -> StagingResult:
    """Normalize and write a staged Parquet artifact from the source CSV.

    Args:
        csv_path: Path to the source companies CSV.
        output_dir: Directory where the Parquet file will be written.
            Created automatically if it does not exist.
        row_limit: Optional cap on the number of source rows to process.
            Useful for local subset runs and tests.

    Returns:
        StagingResult with artifact path and run statistics.

    Raises:
        FileNotFoundError: If csv_path does not exist.
        ValueError: If any required CSV column is missing.
    """
    csv_path = Path(csv_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_ts = datetime.now(timezone.utc)
    ts_str = run_ts.strftime("%Y%m%dT%H%M%SZ")
    parquet_path = output_dir / f"companies_{ts_str}.parquet"

    records: list[dict] = []
    total_read = 0
    skip_reasons: list[dict] = []

    for raw in read_csv_rows(csv_path, row_limit=row_limit):
        total_read += 1
        normalized = _normalize_row(raw)
        if normalized is None:
            skip_reasons.append(
                {
                    "source_id": raw.source_id,
                    "raw_name": raw.name,
                    "reason": "blank name after normalization",
                }
            )
        else:
            records.append(normalized)

    # Build columnar arrays aligned to PARQUET_SCHEMA
    columns: dict[str, list] = {f.name: [] for f in PARQUET_SCHEMA}
    for rec in records:
        for col_name in columns:
            columns[col_name].append(rec.get(col_name))

    arrays = []
    for schema_field in PARQUET_SCHEMA:
        col = columns[schema_field.name]
        arrays.append(pa.array(col, type=schema_field.type))

    table = pa.Table.from_arrays(arrays, schema=PARQUET_SCHEMA)
    pq.write_table(table, parquet_path, compression="snappy")

    # ------------------------------------------------------------------
    # Dead-letter artifact — one JSON line per rejected row
    # ------------------------------------------------------------------
    dead_letter_path = output_dir / f"dead_letter_{ts_str}.jsonl"
    with dead_letter_path.open("w", encoding="utf-8") as dl_file:
        for entry in skip_reasons:
            dl_file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Validation summary artifact — machine-readable run statistics
    # ------------------------------------------------------------------
    valid_count = len(records)
    skipped_count = len(skip_reasons)
    skip_reason_counts: dict[str, int] = {}
    for entry in skip_reasons:
        reason = entry.get("reason", "unknown")
        skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1

    summary = {
        "run_timestamp": run_ts.isoformat(),
        "csv_path": str(csv_path),
        "parquet_path": str(parquet_path),
        "dead_letter_path": str(dead_letter_path),
        "total_rows_read": total_read,
        "valid_rows_written": valid_count,
        "skipped_rows": skipped_count,
        "success_rate": valid_count / total_read if total_read else 0.0,
        "skip_reason_counts": skip_reason_counts,
    }
    validation_summary_path = output_dir / f"validation_summary_{ts_str}.json"
    with validation_summary_path.open("w", encoding="utf-8") as vs_file:
        json.dump(summary, vs_file, indent=2)

    # ------------------------------------------------------------------
    # Update the 'latest' symlink atomically
    # ------------------------------------------------------------------
    latest_link = output_dir / "latest.parquet"
    tmp_link = output_dir / f"latest.parquet.tmp_{os.getpid()}"
    tmp_link.symlink_to(parquet_path.name)
    tmp_link.replace(latest_link)

    return StagingResult(
        parquet_path=parquet_path,
        dead_letter_path=dead_letter_path,
        validation_summary_path=validation_summary_path,
        total_rows_read=total_read,
        valid_rows_written=valid_count,
        skipped_rows=skipped_count,
        run_timestamp=run_ts,
        skip_reasons=skip_reasons,
    )
