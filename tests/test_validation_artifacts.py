"""Tests for P2-T06: dead-letter JSONL and validation summary JSON artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.ingestion.stage import StagingResult, stage_companies

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CSV = Path(__file__).parent / "fixtures" / "companies_sample.csv"
EDGE_CASES_CSV = Path(__file__).parent / "fixtures" / "companies_edge_cases.csv"


def _run_sample(tmp_path) -> StagingResult:
    return stage_companies(SAMPLE_CSV, tmp_path)


def _run_edge(tmp_path) -> StagingResult:
    return stage_companies(EDGE_CASES_CSV, tmp_path)


def _make_header_only_csv(tmp_path: Path) -> Path:
    p = tmp_path / "empty.csv"
    with p.open("w", newline="") as f:
        csv.writer(f).writerow(
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
    return p


# ---------------------------------------------------------------------------
# StagingResult exposes artifact paths
# ---------------------------------------------------------------------------


class TestStagingResultPaths:
    def test_dead_letter_path_in_result(self, tmp_path):
        result = _run_sample(tmp_path)
        assert hasattr(result, "dead_letter_path")

    def test_validation_summary_path_in_result(self, tmp_path):
        result = _run_sample(tmp_path)
        assert hasattr(result, "validation_summary_path")

    def test_dead_letter_path_is_within_output_dir(self, tmp_path):
        result = _run_sample(tmp_path)
        assert result.dead_letter_path.parent == tmp_path

    def test_validation_summary_path_is_within_output_dir(self, tmp_path):
        result = _run_sample(tmp_path)
        assert result.validation_summary_path.parent == tmp_path

    def test_dead_letter_filename_has_jsonl_suffix(self, tmp_path):
        result = _run_sample(tmp_path)
        assert result.dead_letter_path.suffix == ".jsonl"

    def test_validation_summary_filename_has_json_suffix(self, tmp_path):
        result = _run_sample(tmp_path)
        assert result.validation_summary_path.suffix == ".json"


# ---------------------------------------------------------------------------
# Dead-letter artifact — file creation
# ---------------------------------------------------------------------------


class TestDeadLetterCreation:
    def test_dead_letter_file_created(self, tmp_path):
        result = _run_sample(tmp_path)
        assert result.dead_letter_path.exists()

    def test_dead_letter_created_even_when_no_skips(self, tmp_path):
        # sample CSV has no blank names — dead-letter file is created but empty
        result = _run_sample(tmp_path)
        assert result.dead_letter_path.exists()

    def test_dead_letter_empty_when_no_skips(self, tmp_path):
        result = _run_sample(tmp_path)
        content = result.dead_letter_path.read_text(encoding="utf-8").strip()
        assert content == ""

    def test_dead_letter_created_for_empty_csv(self, tmp_path):
        empty = _make_header_only_csv(tmp_path)
        result = stage_companies(empty, tmp_path)
        assert result.dead_letter_path.exists()


# ---------------------------------------------------------------------------
# Dead-letter artifact — JSONL content
# ---------------------------------------------------------------------------


class TestDeadLetterContent:
    def test_dead_letter_has_one_line_per_skipped_row(self, tmp_path):
        result = _run_edge(tmp_path)
        lines = [
            l for l in result.dead_letter_path.read_text(encoding="utf-8").splitlines() if l.strip()
        ]
        assert len(lines) == result.skipped_rows

    def test_dead_letter_lines_are_valid_json(self, tmp_path):
        result = _run_edge(tmp_path)
        for line in result.dead_letter_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                obj = json.loads(line)
                assert isinstance(obj, dict)

    def test_dead_letter_entries_have_source_id(self, tmp_path):
        result = _run_edge(tmp_path)
        for line in result.dead_letter_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                assert "source_id" in json.loads(line)

    def test_dead_letter_entries_have_raw_name(self, tmp_path):
        result = _run_edge(tmp_path)
        for line in result.dead_letter_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                assert "raw_name" in json.loads(line)

    def test_dead_letter_entries_have_reason(self, tmp_path):
        result = _run_edge(tmp_path)
        for line in result.dead_letter_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                assert "reason" in json.loads(line)

    def test_dead_letter_reason_is_non_empty_string(self, tmp_path):
        result = _run_edge(tmp_path)
        for line in result.dead_letter_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                reason = json.loads(line)["reason"]
                assert isinstance(reason, str) and reason


# ---------------------------------------------------------------------------
# Validation summary — file creation
# ---------------------------------------------------------------------------


class TestValidationSummaryCreation:
    def test_validation_summary_file_created(self, tmp_path):
        result = _run_sample(tmp_path)
        assert result.validation_summary_path.exists()

    def test_validation_summary_created_for_empty_csv(self, tmp_path):
        empty = _make_header_only_csv(tmp_path)
        result = stage_companies(empty, tmp_path)
        assert result.validation_summary_path.exists()


# ---------------------------------------------------------------------------
# Validation summary — JSON schema
# ---------------------------------------------------------------------------


class TestValidationSummaryContent:
    def _load(self, result: StagingResult) -> dict:
        return json.loads(result.validation_summary_path.read_text(encoding="utf-8"))

    def test_summary_is_valid_json(self, tmp_path):
        result = _run_sample(tmp_path)
        doc = self._load(result)
        assert isinstance(doc, dict)

    def test_summary_has_run_timestamp(self, tmp_path):
        result = _run_sample(tmp_path)
        doc = self._load(result)
        assert "run_timestamp" in doc

    def test_summary_has_csv_path(self, tmp_path):
        result = _run_sample(tmp_path)
        doc = self._load(result)
        assert "csv_path" in doc

    def test_summary_has_parquet_path(self, tmp_path):
        result = _run_sample(tmp_path)
        doc = self._load(result)
        assert "parquet_path" in doc

    def test_summary_has_dead_letter_path(self, tmp_path):
        result = _run_sample(tmp_path)
        doc = self._load(result)
        assert "dead_letter_path" in doc

    def test_summary_counts_match_result(self, tmp_path):
        result = _run_sample(tmp_path)
        doc = self._load(result)
        assert doc["total_rows_read"] == result.total_rows_read
        assert doc["valid_rows_written"] == result.valid_rows_written
        assert doc["skipped_rows"] == result.skipped_rows

    def test_summary_success_rate_is_float(self, tmp_path):
        result = _run_sample(tmp_path)
        doc = self._load(result)
        assert isinstance(doc["success_rate"], float)

    def test_summary_success_rate_is_one_for_all_valid(self, tmp_path):
        result = _run_sample(tmp_path)
        doc = self._load(result)
        assert doc["success_rate"] == 1.0

    def test_summary_has_skip_reason_counts(self, tmp_path):
        result = _run_sample(tmp_path)
        doc = self._load(result)
        assert "skip_reason_counts" in doc
        assert isinstance(doc["skip_reason_counts"], dict)

    def test_summary_skip_reason_counts_match_skipped_rows(self, tmp_path):
        result = _run_edge(tmp_path)
        doc = self._load(result)
        total_from_counts = sum(doc["skip_reason_counts"].values())
        assert total_from_counts == result.skipped_rows

    def test_summary_zero_success_rate_for_empty_csv(self, tmp_path):
        empty = _make_header_only_csv(tmp_path)
        result = stage_companies(empty, tmp_path)
        doc = self._load(result)
        assert doc["success_rate"] == 0.0

    def test_summary_parquet_path_matches_result(self, tmp_path):
        result = _run_sample(tmp_path)
        doc = self._load(result)
        assert doc["parquet_path"] == str(result.parquet_path)

    def test_summary_run_timestamp_is_iso8601(self, tmp_path):
        from datetime import datetime
        result = _run_sample(tmp_path)
        doc = self._load(result)
        # Should parse without error
        dt = datetime.fromisoformat(doc["run_timestamp"])
        assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# Timestamp consistency — all three artifacts share the same ts suffix
# ---------------------------------------------------------------------------


class TestTimestampConsistency:
    def test_artifacts_share_timestamp_suffix(self, tmp_path):
        result = _run_sample(tmp_path)
        # Extract the timestamp portion from each filename
        parquet_ts = result.parquet_path.stem.replace("companies_", "")
        dl_ts = result.dead_letter_path.stem.replace("dead_letter_", "")
        vs_ts = result.validation_summary_path.stem.replace("validation_summary_", "")
        assert parquet_ts == dl_ts == vs_ts
