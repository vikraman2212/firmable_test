"""Tests for app/ingestion/stage.py — staged Parquet output pipeline."""

from __future__ import annotations

import csv
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from app.ingestion.stage import PARQUET_SCHEMA, StagingResult, stage_companies

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CSV = Path(__file__).parent / "fixtures" / "companies_sample.csv"
EDGE_CASES_CSV = Path(__file__).parent / "fixtures" / "companies_edge_cases.csv"


def _row_count(path: Path) -> int:
    table = pq.read_table(path)
    return len(table)


def _read_table(path: Path):
    return pq.read_table(path)


# ---------------------------------------------------------------------------
# stage_companies: happy-path
# ---------------------------------------------------------------------------

class TestStageCompaniesBasic:
    def test_returns_staging_result(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path)
        assert isinstance(result, StagingResult)

    def test_parquet_file_created(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path)
        assert result.parquet_path.exists()
        assert result.parquet_path.suffix == ".parquet"

    def test_parquet_file_is_within_output_dir(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path)
        assert result.parquet_path.parent == tmp_path

    def test_row_count_matches_valid_input(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path)
        # sample CSV has 3 rows, all valid
        assert result.valid_rows_written == 3
        assert result.total_rows_read == 3
        assert result.skipped_rows == 0

    def test_parquet_row_count_matches_result(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path)
        assert _row_count(result.parquet_path) == result.valid_rows_written

    def test_schema_columns_match(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path)
        table = _read_table(result.parquet_path)
        expected_names = [f.name for f in PARQUET_SCHEMA]
        assert list(table.schema.names) == expected_names


# ---------------------------------------------------------------------------
# stage_companies: field-level spot checks
# ---------------------------------------------------------------------------

class TestStageCompaniesFieldValues:
    def test_company_id_is_hex_string(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path)
        table = _read_table(result.parquet_path)
        ids = table.column("company_id").to_pylist()
        for cid in ids:
            assert isinstance(cid, str) and len(cid) == 64

    def test_name_is_lowercase(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path)
        table = _read_table(result.parquet_path)
        names = table.column("name").to_pylist()
        assert "ibm" in names
        assert "tata consultancy services" in names
        assert "accenture" in names

    def test_semantic_text_is_present(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path)
        table = _read_table(result.parquet_path)
        texts = table.column("company_semantic_text").to_pylist()
        assert all(isinstance(t, str) and t for t in texts)

    def test_year_founded_parsed(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path)
        table = _read_table(result.parquet_path)
        years = sorted(table.column("year_founded").to_pylist())
        assert 1911 in years
        assert 1968 in years
        assert 1989 in years

    def test_country_extracted_from_locality(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path)
        table = _read_table(result.parquet_path)
        countries = set(table.column("country").to_pylist())
        # IBM row locality: "new york, new york, united states"
        assert "united states" in countries

    def test_employee_estimate_is_int_or_null(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path)
        table = _read_table(result.parquet_path)
        estimates = table.column("current_employee_estimate").to_pylist()
        for e in estimates:
            assert e is None or isinstance(e, int)


# ---------------------------------------------------------------------------
# stage_companies: row_limit
# ---------------------------------------------------------------------------

class TestStageCompaniesRowLimit:
    def test_row_limit_restricts_output(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path, row_limit=1)
        assert result.total_rows_read == 1
        assert result.valid_rows_written <= 1

    def test_row_limit_0_produces_empty_parquet(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path, row_limit=0)
        assert result.valid_rows_written == 0
        assert _row_count(result.parquet_path) == 0

    def test_row_limit_2_returns_2_rows(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path, row_limit=2)
        assert result.total_rows_read == 2
        assert result.valid_rows_written == 2


# ---------------------------------------------------------------------------
# stage_companies: skip counting
# ---------------------------------------------------------------------------

class TestStageCompaniesSkipCounting:
    def test_blank_name_rows_are_skipped(self, tmp_path):
        # edge-cases CSV has at least 1 row with a blank name
        result = stage_companies(EDGE_CASES_CSV, tmp_path)
        assert result.skipped_rows >= 1

    def test_total_read_equals_valid_plus_skipped(self, tmp_path):
        result = stage_companies(EDGE_CASES_CSV, tmp_path)
        assert result.total_rows_read == result.valid_rows_written + result.skipped_rows

    def test_skip_reasons_list_length_matches(self, tmp_path):
        result = stage_companies(EDGE_CASES_CSV, tmp_path)
        assert len(result.skip_reasons) == result.skipped_rows

    def test_skip_reasons_have_expected_keys(self, tmp_path):
        result = stage_companies(EDGE_CASES_CSV, tmp_path)
        for entry in result.skip_reasons:
            assert "source_id" in entry
            assert "raw_name" in entry
            assert "reason" in entry


# ---------------------------------------------------------------------------
# stage_companies: empty CSV (header only)
# ---------------------------------------------------------------------------

class TestStageCompaniesEmpty:
    def test_empty_csv_produces_zero_rows(self, tmp_path):
        empty_csv = tmp_path / "empty.csv"
        # Write header only
        with open(empty_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "",
                    "name",
                    "domain",
                    "year founded",
                    "industry",
                    "size range",
                    "locality",
                    "country",
                    "linkedin url",
                    "current employee estimate",
                    "total employee estimate",
                ]
            )
        result = stage_companies(empty_csv, tmp_path)
        assert result.valid_rows_written == 0
        assert result.total_rows_read == 0
        assert _row_count(result.parquet_path) == 0


# ---------------------------------------------------------------------------
# stage_companies: output directory creation
# ---------------------------------------------------------------------------

class TestStageCompaniesOutputDir:
    def test_creates_nested_output_dir(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        result = stage_companies(SAMPLE_CSV, nested)
        assert nested.is_dir()
        assert result.parquet_path.exists()


# ---------------------------------------------------------------------------
# stage_companies: latest symlink
# ---------------------------------------------------------------------------

class TestStageCompaniesSymlink:
    def test_latest_symlink_created(self, tmp_path):
        stage_companies(SAMPLE_CSV, tmp_path)
        latest = tmp_path / "latest.parquet"
        assert latest.is_symlink()

    def test_latest_symlink_points_to_real_file(self, tmp_path):
        stage_companies(SAMPLE_CSV, tmp_path)
        latest = tmp_path / "latest.parquet"
        assert latest.resolve().exists()

    def test_latest_symlink_updated_on_second_run(self, tmp_path):
        stage_companies(SAMPLE_CSV, tmp_path)
        first_target = (tmp_path / "latest.parquet").resolve()
        import time; time.sleep(1)  # ensure different timestamp in filename
        stage_companies(SAMPLE_CSV, tmp_path)
        second_target = (tmp_path / "latest.parquet").resolve()
        # second run should point to a newer file
        assert second_target != first_target


# ---------------------------------------------------------------------------
# StagingResult properties
# ---------------------------------------------------------------------------

class TestStagingResult:
    def test_success_rate_all_valid(self, tmp_path):
        result = stage_companies(SAMPLE_CSV, tmp_path)
        assert result.success_rate == 1.0

    def test_success_rate_zero_when_no_rows(self, tmp_path):
        empty_csv = tmp_path / "empty.csv"
        with open(empty_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "",
                    "name",
                    "domain",
                    "year founded",
                    "industry",
                    "size range",
                    "locality",
                    "country",
                    "linkedin url",
                    "current employee estimate",
                    "total employee estimate",
                ]
            )
        result = stage_companies(empty_csv, tmp_path)
        assert result.success_rate == 0.0

    def test_run_timestamp_is_utc(self, tmp_path):
        import datetime
        result = stage_companies(SAMPLE_CSV, tmp_path)
        assert result.run_timestamp.tzinfo is not None
        assert result.run_timestamp.tzinfo == datetime.timezone.utc


# ---------------------------------------------------------------------------
# stage_companies: error handling
# ---------------------------------------------------------------------------

class TestStageCompaniesErrors:
    def test_missing_csv_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            stage_companies(tmp_path / "nonexistent.csv", tmp_path)
