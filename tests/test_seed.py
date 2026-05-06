"""Tests for app/ingestion/seed.py — seed flow.

All tests use a mock client so no live OpenSearch is required.
The test surface covers:
  - bulk NDJSON body construction (pure unit tests)
  - index name format
  - seed() orchestration: create_index → bulk batches
  - SeedResult fields
  - edge cases: empty Parquet, batching boundaries, bulk errors
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from opensearchpy import TransportError

from app.ingestion.seed import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_INDEX_NAME,
    OpenSearchError,
    SeedResult,
    build_bulk_body,
    main,
    make_index_name,
    seed,
)
from app.ingestion.stage import PARQUET_SCHEMA, StagingResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CSV = Path(__file__).parent / "fixtures" / "companies_sample.csv"


def _make_parquet(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a minimal Parquet artifact from the given row dicts."""
    columns: dict[str, list] = {f.name: [] for f in PARQUET_SCHEMA}
    for row in rows:
        for col in columns:
            columns[col].append(row.get(col))
    arrays = [
        pa.array(columns[f.name], type=f.type) for f in PARQUET_SCHEMA
    ]
    table = pa.Table.from_arrays(arrays, schema=PARQUET_SCHEMA)
    path = tmp_path / "test.parquet"
    pq.write_table(table, path)
    return path


def _sample_doc(**overrides) -> dict:
    base = {
        "company_id": "a" * 64,
        "name": "acme corp",
        "domain": "acme.com",
        "industry": "technology",
        "size_range": "11-50",
        "city": "london",
        "region": "england",
        "country": "united kingdom",
        "year_founded": 2000,
        "current_employee_estimate": 30,
        "total_employee_estimate": 35,
        "linkedin_url": "linkedin.com/company/acme",
        "company_semantic_text": "acme corp technology london",
    }
    base.update(overrides)
    return base


def _make_mock_client(
    *,
    bulk_errors: bool = False,
) -> MagicMock:
    """Return a MagicMock shaped like an opensearch-py OpenSearch client."""
    client = MagicMock()
    client.indices.create.return_value = {"acknowledged": True}
    bulk_resp = {"errors": bulk_errors, "items": []}
    if bulk_errors:
        bulk_resp["items"] = [
            {"index": {"_id": "x" * 64, "error": {"reason": "simulated error"}}}
        ]
    client.bulk.return_value = bulk_resp
    return client


def _make_full_sample_parquet(tmp_path: Path) -> Path:
    """Stage the sample CSV and return the Parquet path."""
    from app.ingestion.stage import stage_companies
    result = stage_companies(SAMPLE_CSV, tmp_path)
    return result.parquet_path


# ---------------------------------------------------------------------------
# build_bulk_body — pure unit tests
# ---------------------------------------------------------------------------


class TestBuildBulkBody:
    def test_returns_string(self):
        body = build_bulk_body([_sample_doc()], "companies-test")
        assert isinstance(body, str)

    def test_ends_with_newline(self):
        body = build_bulk_body([_sample_doc()], "companies-test")
        assert body.endswith("\n")

    def test_two_lines_per_document(self):
        docs = [_sample_doc(), _sample_doc(company_id="b" * 64, name="beta")]
        body = build_bulk_body(docs, "companies-test")
        lines = [l for l in body.splitlines() if l.strip()]
        assert len(lines) == 4  # 2 docs × 2 lines each

    def test_action_line_has_index_key(self):
        body = build_bulk_body([_sample_doc()], "companies-test")
        action = json.loads(body.splitlines()[0])
        assert "index" in action

    def test_action_line_contains_index_name(self):
        body = build_bulk_body([_sample_doc()], "companies-test")
        action = json.loads(body.splitlines()[0])
        assert action["index"]["_index"] == "companies-test"

    def test_action_line_uses_company_id_as_doc_id(self):
        doc = _sample_doc(company_id="c" * 64)
        body = build_bulk_body([doc], "companies-test")
        action = json.loads(body.splitlines()[0])
        assert action["index"]["_id"] == "c" * 64

    def test_source_line_contains_company_id(self):
        doc = _sample_doc(company_id="d" * 64)
        body = build_bulk_body([doc], "companies-test")
        source = json.loads(body.splitlines()[1])
        assert source["company_id"] == "d" * 64

    def test_source_line_contains_name(self):
        doc = _sample_doc(name="widgetco")
        body = build_bulk_body([doc], "companies-test")
        source = json.loads(body.splitlines()[1])
        assert source["name"] == "widgetco"

    def test_empty_docs_returns_only_newline(self):
        body = build_bulk_body([], "companies-test")
        assert body == "\n"

    def test_multiple_docs_interleaved_correctly(self):
        docs = [_sample_doc(company_id="a" * 64), _sample_doc(company_id="b" * 64)]
        lines = [l for l in build_bulk_body(docs, "idx").splitlines() if l]
        # lines[0] = action for doc0, lines[1] = source for doc0
        # lines[2] = action for doc1, lines[3] = source for doc1
        assert json.loads(lines[0])["index"]["_id"] == "a" * 64
        assert json.loads(lines[2])["index"]["_id"] == "b" * 64


# ---------------------------------------------------------------------------
# make_index_name — unit tests
# ---------------------------------------------------------------------------


class TestMakeIndexName:
    def test_starts_with_companies_prefix(self):
        assert make_index_name().startswith("companies-")

    def test_contains_only_lowercase(self):
        name = make_index_name()
        assert name == name.lower()

    def test_is_reproducible_for_same_timestamp(self):
        from datetime import datetime, timezone
        ts = datetime(2026, 5, 4, 8, 30, 12, tzinfo=timezone.utc)
        assert make_index_name(ts) == "companies-20260504t083012z"

    def test_different_timestamps_produce_different_names(self):
        from datetime import datetime, timezone
        ts1 = datetime(2026, 5, 4, 8, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 5, 4, 9, 0, 0, tzinfo=timezone.utc)
        assert make_index_name(ts1) != make_index_name(ts2)


# ---------------------------------------------------------------------------
# TestSwapAliases removed — alias swapping is no longer part of the seed flow.
# The seed() function now creates/reuses the fixed "companies" index directly.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# seed() — orchestration tests
# ---------------------------------------------------------------------------


class TestSeedOrchestration:
    def test_returns_seed_result(self, tmp_path):
        parquet = _make_full_sample_parquet(tmp_path)
        client = _make_mock_client()
        result = seed(parquet, client=client, index_name="companies-test")
        assert isinstance(result, SeedResult)

    def test_create_index_called_once(self, tmp_path):
        parquet = _make_full_sample_parquet(tmp_path)
        client = _make_mock_client()
        seed(parquet, client=client, index_name="companies-test")
        client.indices.create.assert_called_once_with(index="companies-test")

    def test_create_index_called_before_bulk(self, tmp_path):
        call_order = []
        client = _make_mock_client()
        client.indices.create.side_effect = lambda *a, **kw: call_order.append("create_index")
        client.bulk.side_effect = lambda *a, **kw: (call_order.append("bulk"), {"errors": False, "items": []})[1]
        parquet = _make_full_sample_parquet(tmp_path)
        seed(parquet, client=client, index_name="companies-test")
        assert call_order.index("create_index") < call_order.index("bulk")

    def test_bulk_called_at_least_once_for_non_empty_parquet(self, tmp_path):
        parquet = _make_full_sample_parquet(tmp_path)
        client = _make_mock_client()
        seed(parquet, client=client, index_name="companies-test")
        assert client.bulk.call_count >= 1

    def test_result_index_name_matches_argument(self, tmp_path):
        parquet = _make_full_sample_parquet(tmp_path)
        client = _make_mock_client()
        result = seed(parquet, client=client, index_name="companies-specific")
        assert result.index_name == "companies-specific"

    def test_result_uses_default_index_name_when_not_specified(self, tmp_path):
        parquet = _make_full_sample_parquet(tmp_path)
        client = _make_mock_client()
        result = seed(parquet, client=client)
        assert result.index_name == DEFAULT_INDEX_NAME

    def test_result_docs_indexed_equals_parquet_row_count(self, tmp_path):
        parquet = _make_full_sample_parquet(tmp_path)
        table = pq.read_table(parquet)
        client = _make_mock_client()
        result = seed(parquet, client=client, index_name="companies-test")
        assert result.docs_indexed == len(table)

    def test_result_bulk_errors_zero_when_no_errors(self, tmp_path):
        parquet = _make_full_sample_parquet(tmp_path)
        client = _make_mock_client(bulk_errors=False)
        result = seed(parquet, client=client, index_name="companies-test")
        assert result.bulk_errors == 0

    def test_result_bulk_errors_positive_when_errors(self, tmp_path):
        parquet = _make_full_sample_parquet(tmp_path)
        client = _make_mock_client(bulk_errors=True)
        result = seed(parquet, client=client, index_name="companies-test")
        assert result.bulk_errors >= 1


# ---------------------------------------------------------------------------
# seed() — batching tests
# ---------------------------------------------------------------------------


class TestSeedBatching:
    def _parquet_with_n_rows(self, tmp_path: Path, n: int) -> Path:
        rows = [
            _sample_doc(
                company_id=hex(i)[2:].zfill(64),
                name=f"company {i}",
                company_semantic_text=f"company {i} text",
            )
            for i in range(n)
        ]
        return _make_parquet(tmp_path, rows)

    def test_single_batch_when_rows_lte_batch_size(self, tmp_path):
        parquet = self._parquet_with_n_rows(tmp_path, 3)
        client = _make_mock_client()
        result = seed(parquet, client=client, index_name="companies-test", batch_size=10)
        assert client.bulk.call_count == 1
        assert result.batches_sent == 1

    def test_two_batches_when_rows_exceed_batch_size(self, tmp_path):
        parquet = self._parquet_with_n_rows(tmp_path, 5)
        client = _make_mock_client()
        result = seed(parquet, client=client, index_name="companies-test", batch_size=3)
        assert client.bulk.call_count == 2
        assert result.batches_sent == 2

    def test_each_batch_ndjson_is_valid(self, tmp_path):
        parquet = self._parquet_with_n_rows(tmp_path, 4)
        client = _make_mock_client()
        seed(parquet, client=client, index_name="companies-test", batch_size=2)
        for call_args in client.bulk.call_args_list:
            ndjson = call_args.kwargs.get("body") or call_args.args[0]
            for line in ndjson.splitlines():
                if line.strip():
                    json.loads(line)  # must not raise

    def test_batch_documents_reference_correct_index(self, tmp_path):
        parquet = self._parquet_with_n_rows(tmp_path, 2)
        client = _make_mock_client()
        seed(parquet, client=client, index_name="companies-myidx", batch_size=10)
        call_args = client.bulk.call_args
        ndjson = call_args.kwargs.get("body") or call_args.args[0]
        action = json.loads(ndjson.splitlines()[0])
        assert action["index"]["_index"] == "companies-myidx"


# ---------------------------------------------------------------------------
# seed() — empty Parquet
# ---------------------------------------------------------------------------


class TestSeedEmpty:
    def test_empty_parquet_creates_index(self, tmp_path):
        parquet = _make_parquet(tmp_path, [])
        client = _make_mock_client()
        seed(parquet, client=client, index_name="companies-test")
        client.indices.create.assert_called_once()

    def test_empty_parquet_does_not_call_bulk(self, tmp_path):
        parquet = _make_parquet(tmp_path, [])
        client = _make_mock_client()
        seed(parquet, client=client, index_name="companies-test")
        client.bulk.assert_not_called()

    def test_empty_parquet_docs_indexed_zero(self, tmp_path):
        parquet = _make_parquet(tmp_path, [])
        client = _make_mock_client()
        result = seed(parquet, client=client, index_name="companies-test")
        assert result.docs_indexed == 0


# ---------------------------------------------------------------------------
# seed() — error handling
# ---------------------------------------------------------------------------


class TestSeedErrors:
    def test_missing_parquet_raises_file_not_found(self, tmp_path):
        client = _make_mock_client()
        with pytest.raises(FileNotFoundError):
            seed(tmp_path / "nonexistent.parquet", client=client)

    def test_existing_index_error_is_treated_as_reusable(self, tmp_path):
        from opensearchpy import RequestError

        parquet = _make_parquet(tmp_path, [_sample_doc()])
        client = _make_mock_client()
        client.indices.create.side_effect = RequestError(
            400,
            "resource_already_exists_exception",
            {"error": {"type": "resource_already_exists_exception"}},
        )

        result = seed(parquet, client=client, index_name="companies-test")

        assert result.index_name == "companies-test"
        assert client.bulk.called

    def test_opensearch_error_on_create_index_propagates(self, tmp_path):
        from opensearchpy import RequestError
        parquet = _make_parquet(tmp_path, [_sample_doc()])
        client = _make_mock_client()
        client.indices.create.side_effect = RequestError(500, "internal_server_error", {})
        with pytest.raises(OpenSearchError):
            seed(parquet, client=client, index_name="companies-test")


# ---------------------------------------------------------------------------
# SeedResult properties
# ---------------------------------------------------------------------------


class TestSeedResult:
    def test_default_batches_sent_zero(self):
        r = SeedResult(
            index_name="companies",
            docs_indexed=0,
            bulk_errors=0,
        )
        assert r.batches_sent == 0


# ---------------------------------------------------------------------------
# main() — CSV staging lifecycle regression test
# ---------------------------------------------------------------------------


class TestSeedCliMain:
    def test_csv_mode_keeps_staged_parquet_alive_until_seed_runs(self, monkeypatch):
        import app.ingestion.stage as stage_module

        args = argparse.Namespace(
            config=None,
            csv=str(SAMPLE_CSV),
            parquet=None,
            opensearch_url="http://localhost:9200",
            opensearch_timeout=None,
            batch_size=DEFAULT_BATCH_SIZE,
            row_limit=1,
        )
        observed: dict[str, bool] = {}

        def fake_stage_companies(csv_path, output_dir, *, row_limit=None):
            parquet_path = output_dir / "staged.parquet"
            parquet_path.write_text("placeholder", encoding="utf-8")
            return StagingResult(
                parquet_path=parquet_path,
                dead_letter_path=output_dir / "dead_letter.jsonl",
                validation_summary_path=output_dir / "validation_summary.json",
                total_rows_read=1,
                valid_rows_written=1,
                skipped_rows=0,
                run_timestamp=datetime.now(timezone.utc),
                skip_reasons=[],
            )

        def fake_seed(parquet_path, **kwargs):
            observed["exists_at_call"] = Path(parquet_path).exists()
            return SeedResult(
                index_name="companies",
                docs_indexed=1,
                bulk_errors=0,
            )

        monkeypatch.setattr("app.ingestion.seed._configure_logging", lambda: None)
        monkeypatch.setattr("app.ingestion.seed._parse_args", lambda: args)
        monkeypatch.setattr(stage_module, "stage_companies", fake_stage_companies)
        monkeypatch.setattr("app.ingestion.seed.make_client", lambda host, timeout=60: object())
        monkeypatch.setattr("app.ingestion.seed.seed", fake_seed)

        main()

        assert observed["exists_at_call"] is True
