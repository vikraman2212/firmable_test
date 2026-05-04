"""Unit tests for app/ingestion/sync.py.

All tests use a mock client — no live OpenSearch required.

Coverage:
  - content_hash: stability, sort-key independence, sensitivity to field changes
  - build_upsert_bulk_body: NDJSON format, doc_as_upsert, hash stored
  - build_soft_delete_bulk_body: NDJSON format, is_deleted, deleted_at fields
  - sync() orchestration: mget → compare → upsert changed only
  - sync() batching: multiple batches, per-batch mget
  - sync() soft_delete=False default: no scroll calls
  - sync() soft_delete=True: stale IDs marked deleted
  - sync() edge cases: empty parquet, all unchanged, all new
  - SyncResult fields
  - Error propagation: mget failure, bulk failure
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, call

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from opensearchpy import TransportError

from app.ingestion.seed import OpenSearchError
from app.ingestion.stage import PARQUET_SCHEMA
from app.ingestion.sync import (
    SyncResult,
    build_soft_delete_bulk_body,
    build_upsert_bulk_body,
    content_hash,
    main,
    sync,
)

# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------


def _make_parquet(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a minimal Parquet artifact from the given row dicts."""
    columns: dict[str, list] = {f.name: [] for f in PARQUET_SCHEMA}
    for row in rows:
        for col in columns:
            columns[col].append(row.get(col))
    arrays = [pa.array(columns[f.name], type=f.type) for f in PARQUET_SCHEMA]
    table = pa.Table.from_arrays(arrays, schema=PARQUET_SCHEMA)
    path = tmp_path / "test.parquet"
    pq.write_table(table, path)
    return path


def _doc(**overrides) -> dict:
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
    existing_hashes: dict[str, str] | None = None,
    bulk_errors: bool = False,
    stale_ids: list[str] | None = None,
) -> MagicMock:
    """Return a MagicMock shaped like an opensearch-py OpenSearch client."""
    client = MagicMock()

    # mget — returns found docs for IDs present in existing_hashes
    def _mget(body, index, _source_includes=None, **kwargs):
        hashes = existing_hashes or {}
        docs = []
        for doc_id in body.get("ids", []):
            if doc_id in hashes:
                docs.append({
                    "_id": doc_id,
                    "found": True,
                    "_source": {"content_hash": hashes[doc_id]},
                })
            else:
                docs.append({"_id": doc_id, "found": False})
        return {"docs": docs}

    client.mget.side_effect = _mget

    # bulk
    bulk_resp = {"errors": bulk_errors, "items": []}
    if bulk_errors:
        bulk_resp["items"] = [
            {"update": {"_id": "x" * 64, "error": {"reason": "simulated"}}}
        ]
    client.bulk.return_value = bulk_resp

    # search / scroll / clear_scroll for soft-delete
    _stale = stale_ids or []
    client.search.return_value = {
        "_scroll_id": None,
        "hits": {
            "hits": [{"_id": sid} for sid in _stale],
        },
    }
    client.scroll.return_value = {"_scroll_id": None, "hits": {"hits": []}}
    client.clear_scroll.return_value = {}

    return client


# ---------------------------------------------------------------------------
# TestContentHash
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_returns_64_char_hex_string(self):
        h = content_hash(_doc())
        assert isinstance(h, str)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_doc_produces_same_hash(self):
        d = _doc()
        assert content_hash(d) == content_hash(d)

    def test_key_order_does_not_affect_hash(self):
        d1 = {"a": 1, "b": 2, "company_id": "x" * 64}
        d2 = {"b": 2, "company_id": "x" * 64, "a": 1}
        assert content_hash(d1) == content_hash(d2)

    def test_different_name_produces_different_hash(self):
        assert content_hash(_doc(name="alpha")) != content_hash(_doc(name="beta"))

    def test_different_id_produces_different_hash(self):
        assert content_hash(_doc(company_id="a" * 64)) != content_hash(_doc(company_id="b" * 64))

    def test_added_field_changes_hash(self):
        base = _doc()
        extra = {**base, "city": "paris"}
        assert content_hash(base) != content_hash(extra)


# ---------------------------------------------------------------------------
# TestBuildUpsertBulkBody
# ---------------------------------------------------------------------------


class TestBuildUpsertBulkBody:
    def test_returns_string(self):
        body = build_upsert_bulk_body([_doc()], "companies-write")
        assert isinstance(body, str)

    def test_ends_with_newline(self):
        body = build_upsert_bulk_body([_doc()], "companies-write")
        assert body.endswith("\n")

    def test_two_lines_per_document(self):
        body = build_upsert_bulk_body([_doc(), _doc(company_id="b" * 64)], "companies-write")
        lines = [l for l in body.splitlines() if l.strip()]
        assert len(lines) == 4

    def test_action_line_uses_update(self):
        body = build_upsert_bulk_body([_doc()], "companies-write")
        action = json.loads(body.splitlines()[0])
        assert "update" in action

    def test_action_line_contains_index_name(self):
        body = build_upsert_bulk_body([_doc()], "companies-write")
        action = json.loads(body.splitlines()[0])
        assert action["update"]["_index"] == "companies-write"

    def test_action_line_uses_company_id_as_doc_id(self):
        d = _doc(company_id="c" * 64)
        body = build_upsert_bulk_body([d], "companies-write")
        action = json.loads(body.splitlines()[0])
        assert action["update"]["_id"] == "c" * 64

    def test_payload_has_doc_as_upsert_true(self):
        body = build_upsert_bulk_body([_doc()], "companies-write")
        payload = json.loads(body.splitlines()[1])
        assert payload.get("doc_as_upsert") is True

    def test_payload_doc_contains_content_hash(self):
        d = _doc()
        body = build_upsert_bulk_body([d], "companies-write")
        payload = json.loads(body.splitlines()[1])
        assert "content_hash" in payload["doc"]
        assert payload["doc"]["content_hash"] == content_hash(d)

    def test_payload_doc_contains_company_fields(self):
        d = _doc(name="test corp")
        body = build_upsert_bulk_body([d], "companies-write")
        payload = json.loads(body.splitlines()[1])
        assert payload["doc"]["name"] == "test corp"


# ---------------------------------------------------------------------------
# TestBuildSoftDeleteBulkBody
# ---------------------------------------------------------------------------


class TestBuildSoftDeleteBulkBody:
    def test_returns_string(self):
        body = build_soft_delete_bulk_body(["a" * 64], "companies-write")
        assert isinstance(body, str)

    def test_ends_with_newline(self):
        body = build_soft_delete_bulk_body(["a" * 64], "companies-write")
        assert body.endswith("\n")

    def test_two_lines_per_id(self):
        body = build_soft_delete_bulk_body(["a" * 64, "b" * 64], "companies-write")
        lines = [l for l in body.splitlines() if l.strip()]
        assert len(lines) == 4

    def test_action_line_uses_update(self):
        body = build_soft_delete_bulk_body(["a" * 64], "companies-write")
        action = json.loads(body.splitlines()[0])
        assert "update" in action

    def test_payload_sets_is_deleted_true(self):
        body = build_soft_delete_bulk_body(["a" * 64], "companies-write")
        payload = json.loads(body.splitlines()[1])
        assert payload["doc"]["is_deleted"] is True

    def test_payload_has_deleted_at_field(self):
        body = build_soft_delete_bulk_body(["a" * 64], "companies-write")
        payload = json.loads(body.splitlines()[1])
        assert "deleted_at" in payload["doc"]

    def test_payload_does_not_set_doc_as_upsert(self):
        body = build_soft_delete_bulk_body(["a" * 64], "companies-write")
        payload = json.loads(body.splitlines()[1])
        assert "doc_as_upsert" not in payload


# ---------------------------------------------------------------------------
# TestSyncOrchestration
# ---------------------------------------------------------------------------


class TestSyncOrchestration:
    def test_returns_sync_result(self, tmp_path):
        parquet = _make_parquet(tmp_path, [_doc()])
        client = _make_mock_client()
        result = sync(parquet, client=client, index_name="companies")
        assert isinstance(result, SyncResult)

    def test_docs_examined_equals_row_count(self, tmp_path):
        rows = [_doc(company_id="a" * 64), _doc(company_id="b" * 64)]
        parquet = _make_parquet(tmp_path, rows)
        client = _make_mock_client()
        result = sync(parquet, client=client, index_name="companies")
        assert result.docs_examined == 2

    def test_all_new_docs_are_upserted(self, tmp_path):
        parquet = _make_parquet(tmp_path, [_doc()])
        client = _make_mock_client(existing_hashes={})
        result = sync(parquet, client=client, index_name="companies")
        assert result.docs_upserted == 1
        assert result.docs_skipped == 0

    def test_mget_called_with_correct_ids(self, tmp_path):
        d = _doc(company_id="d" * 64)
        parquet = _make_parquet(tmp_path, [d])
        client = _make_mock_client()
        sync(parquet, client=client, index_name="companies")
        call_ids = client.mget.call_args.kwargs.get("body", {}).get("ids") or \
                   client.mget.call_args.args[0].get("ids", []) if client.mget.call_args.args else []
        # Accept both positional and keyword call shapes
        if not call_ids:
            call_ids = client.mget.call_args[1].get("body", {}).get("ids", [])
        assert "d" * 64 in call_ids

    def test_bulk_called_for_new_docs(self, tmp_path):
        parquet = _make_parquet(tmp_path, [_doc()])
        client = _make_mock_client(existing_hashes={})
        sync(parquet, client=client, index_name="companies")
        client.bulk.assert_called_once()

    def test_bulk_not_called_when_all_unchanged(self, tmp_path):
        d = _doc()
        parquet = _make_parquet(tmp_path, [d])
        client = _make_mock_client(existing_hashes={d["company_id"]: content_hash(d)})
        sync(parquet, client=client, index_name="companies")
        client.bulk.assert_not_called()

    def test_batches_sent_counts_bulk_calls(self, tmp_path):
        parquet = _make_parquet(tmp_path, [_doc()])
        client = _make_mock_client(existing_hashes={})
        result = sync(parquet, client=client, index_name="companies")
        assert result.batches_sent == 1

    def test_bulk_errors_counted(self, tmp_path):
        parquet = _make_parquet(tmp_path, [_doc()])
        client = _make_mock_client(existing_hashes={}, bulk_errors=True)
        result = sync(parquet, client=client, index_name="companies")
        assert result.bulk_errors == 1


# ---------------------------------------------------------------------------
# TestSyncSkipUnchanged
# ---------------------------------------------------------------------------


class TestSyncSkipUnchanged:
    def test_unchanged_doc_is_skipped(self, tmp_path):
        d = _doc()
        parquet = _make_parquet(tmp_path, [d])
        client = _make_mock_client(existing_hashes={d["company_id"]: content_hash(d)})
        result = sync(parquet, client=client, index_name="companies")
        assert result.docs_skipped == 1
        assert result.docs_upserted == 0

    def test_changed_doc_is_upserted(self, tmp_path):
        d = _doc()
        parquet = _make_parquet(tmp_path, [d])
        # Store a different hash to simulate a changed doc
        client = _make_mock_client(existing_hashes={d["company_id"]: "old_hash_value"})
        result = sync(parquet, client=client, index_name="companies")
        assert result.docs_upserted == 1
        assert result.docs_skipped == 0

    def test_mixed_batch_skips_and_upserts_correctly(self, tmp_path):
        unchanged = _doc(company_id="a" * 64, name="unchanged")
        changed = _doc(company_id="b" * 64, name="changed")
        parquet = _make_parquet(tmp_path, [unchanged, changed])
        client = _make_mock_client(
            existing_hashes={
                unchanged["company_id"]: content_hash(unchanged),
                changed["company_id"]: "stale_hash",
            }
        )
        result = sync(parquet, client=client, index_name="companies")
        assert result.docs_upserted == 1
        assert result.docs_skipped == 1

    def test_examined_equals_upserted_plus_skipped(self, tmp_path):
        rows = [
            _doc(company_id="a" * 64),
            _doc(company_id="b" * 64),
            _doc(company_id="c" * 64),
        ]
        parquet = _make_parquet(tmp_path, rows)
        client = _make_mock_client(
            existing_hashes={rows[0]["company_id"]: content_hash(rows[0])}
        )
        result = sync(parquet, client=client, index_name="companies")
        assert result.docs_examined == result.docs_upserted + result.docs_skipped


# ---------------------------------------------------------------------------
# TestSyncBatching
# ---------------------------------------------------------------------------


class TestSyncBatching:
    def _parquet_with_n_rows(self, tmp_path: Path, n: int) -> Path:
        rows = [_doc(company_id=(hex(i)[2:].zfill(64)[:64])) for i in range(n)]
        return _make_parquet(tmp_path, rows)

    def test_single_batch_when_rows_lte_batch_size(self, tmp_path):
        parquet = self._parquet_with_n_rows(tmp_path, 3)
        client = _make_mock_client()
        sync(parquet, client=client, index_name="companies", batch_size=10)
        assert client.mget.call_count == 1

    def test_two_mget_calls_for_two_batches(self, tmp_path):
        parquet = self._parquet_with_n_rows(tmp_path, 4)
        client = _make_mock_client()
        sync(parquet, client=client, index_name="companies", batch_size=2)
        assert client.mget.call_count == 2

    def test_upsert_ndjson_references_index_name(self, tmp_path):
        parquet = self._parquet_with_n_rows(tmp_path, 1)
        client = _make_mock_client(existing_hashes={})
        sync(parquet, client=client, index_name="my-index", batch_size=10)
        ndjson = client.bulk.call_args.kwargs.get("body") or client.bulk.call_args.args[0]
        action = json.loads(ndjson.splitlines()[0])
        assert action["update"]["_index"] == "my-index"


# ---------------------------------------------------------------------------
# TestSyncEmpty
# ---------------------------------------------------------------------------


class TestSyncEmpty:
    def test_empty_parquet_returns_zero_examined(self, tmp_path):
        parquet = _make_parquet(tmp_path, [])
        client = _make_mock_client()
        result = sync(parquet, client=client, index_name="companies")
        assert result.docs_examined == 0

    def test_empty_parquet_does_not_call_bulk(self, tmp_path):
        parquet = _make_parquet(tmp_path, [])
        client = _make_mock_client()
        sync(parquet, client=client, index_name="companies")
        client.bulk.assert_not_called()

    def test_empty_parquet_zero_upserted_and_skipped(self, tmp_path):
        parquet = _make_parquet(tmp_path, [])
        client = _make_mock_client()
        result = sync(parquet, client=client, index_name="companies")
        assert result.docs_upserted == 0
        assert result.docs_skipped == 0


# ---------------------------------------------------------------------------
# TestSyncSoftDelete
# ---------------------------------------------------------------------------


class TestSyncSoftDelete:
    def test_soft_delete_false_does_not_call_search(self, tmp_path):
        parquet = _make_parquet(tmp_path, [_doc()])
        client = _make_mock_client()
        sync(parquet, client=client, index_name="companies", soft_delete=False)
        client.search.assert_not_called()

    def test_soft_delete_true_calls_search(self, tmp_path):
        parquet = _make_parquet(tmp_path, [_doc()])
        client = _make_mock_client(stale_ids=[])
        sync(parquet, client=client, index_name="companies", soft_delete=True)
        client.search.assert_called_once()

    def test_soft_delete_marks_stale_docs(self, tmp_path):
        stale_id = "s" * 64
        parquet = _make_parquet(tmp_path, [_doc()])
        client = _make_mock_client(existing_hashes={}, stale_ids=[stale_id])
        result = sync(parquet, client=client, index_name="companies", soft_delete=True)
        assert result.docs_soft_deleted == 1

    def test_soft_delete_bulk_called_for_stale_ids(self, tmp_path):
        stale_id = "s" * 64
        parquet = _make_parquet(tmp_path, [_doc()])
        client = _make_mock_client(existing_hashes={}, stale_ids=[stale_id])
        sync(parquet, client=client, index_name="companies", soft_delete=True)
        # bulk is called at least once for upserts and once for soft-deletes
        assert client.bulk.call_count >= 1
        all_ndjsons = [
            (ca.kwargs.get("body") or ca.args[0])
            for ca in client.bulk.call_args_list
        ]
        all_actions = []
        for ndjson in all_ndjsons:
            for line in ndjson.splitlines():
                if line.strip():
                    all_actions.append(json.loads(line))
        update_actions = [a for a in all_actions if "update" in a and a["update"]["_id"] == stale_id]
        assert len(update_actions) == 1

    def test_soft_delete_zero_when_no_stale_ids(self, tmp_path):
        parquet = _make_parquet(tmp_path, [_doc()])
        client = _make_mock_client(stale_ids=[])
        result = sync(parquet, client=client, index_name="companies", soft_delete=True)
        assert result.docs_soft_deleted == 0


# ---------------------------------------------------------------------------
# TestSyncErrors
# ---------------------------------------------------------------------------


class TestSyncErrors:
    def test_missing_parquet_raises_file_not_found(self, tmp_path):
        client = _make_mock_client()
        with pytest.raises(FileNotFoundError):
            sync(tmp_path / "nonexistent.parquet", client=client, index_name="companies")

    def test_mget_transport_error_non_404_raises_opensearch_error(self, tmp_path):
        parquet = _make_parquet(tmp_path, [_doc()])
        client = _make_mock_client()
        client.mget.side_effect = TransportError(500, "internal_error", {})
        with pytest.raises(OpenSearchError):
            sync(parquet, client=client, index_name="companies")

    def test_mget_404_treated_as_empty_hashes(self, tmp_path):
        parquet = _make_parquet(tmp_path, [_doc()])
        client = _make_mock_client()
        client.mget.side_effect = TransportError(404, "index_not_found", {})
        # Should not raise — treats all docs as new
        result = sync(parquet, client=client, index_name="companies")
        assert result.docs_upserted == 1

    def test_bulk_transport_error_raises_opensearch_error(self, tmp_path):
        parquet = _make_parquet(tmp_path, [_doc()])
        client = _make_mock_client(existing_hashes={})
        client.bulk.side_effect = TransportError(503, "unavailable", {})
        with pytest.raises(OpenSearchError):
            sync(parquet, client=client, index_name="companies")


# ---------------------------------------------------------------------------
# TestSyncResult
# ---------------------------------------------------------------------------


class TestSyncResult:
    def test_default_batches_sent_zero(self):
        r = SyncResult(
            docs_examined=0,
            docs_upserted=0,
            docs_skipped=0,
            docs_soft_deleted=0,
            bulk_errors=0,
        )
        assert r.batches_sent == 0

    def test_all_fields_accessible(self):
        r = SyncResult(
            docs_examined=10,
            docs_upserted=5,
            docs_skipped=5,
            docs_soft_deleted=2,
            bulk_errors=1,
            batches_sent=2,
        )
        assert r.docs_examined == 10
        assert r.docs_upserted == 5
        assert r.docs_skipped == 5
        assert r.docs_soft_deleted == 2
        assert r.bulk_errors == 1
        assert r.batches_sent == 2


# ---------------------------------------------------------------------------
# main() — config-backed CLI resolution
# ---------------------------------------------------------------------------


class TestSyncCliMain:
    def test_main_uses_config_defaults_when_cli_values_omitted(self, monkeypatch, tmp_path):
        parquet = _make_parquet(tmp_path, [_doc()])
        config_path = tmp_path / "ingestion.toml"
        config_path.write_text(
            f"""
[opensearch]
url = "http://localhost:9200"
timeout = 9

[sync]
parquet_path = "{parquet}"
index_name = "companies-configured"
batch_size = 42
soft_delete = true
""".strip(),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            config=str(config_path),
            parquet=None,
            opensearch_url=None,
            opensearch_timeout=None,
            index_name=None,
            batch_size=None,
            soft_delete=None,
        )
        observed: dict[str, object] = {}

        def fake_sync(parquet_path, **kwargs):
            observed["parquet_path"] = Path(parquet_path)
            observed.update(kwargs)
            return SyncResult(
                docs_examined=1,
                docs_upserted=1,
                docs_skipped=0,
                docs_soft_deleted=0,
                bulk_errors=0,
            )

        monkeypatch.setattr("app.ingestion.sync._configure_logging", lambda: None)
        monkeypatch.setattr("app.ingestion.sync._parse_args", lambda: args)
        monkeypatch.setattr("app.ingestion.sync.make_client", lambda host, timeout=60: object())
        monkeypatch.setattr("app.ingestion.sync.sync", fake_sync)

        main()

        assert observed["parquet_path"] == parquet
        assert observed["index_name"] == "companies-configured"
        assert observed["batch_size"] == 42
        assert observed["soft_delete"] is True
