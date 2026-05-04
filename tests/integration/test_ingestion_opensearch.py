"""Integration tests — ingestion pipeline ↔ OpenSearch.

These tests exercise the real HTTP round-trip between seed()/sync() and a
live OpenSearch node.  They are automatically skipped when OpenSearch is not
reachable (see conftest.py).

Test isolation
--------------
Every test uses a unique index prefix (``test-ingestion-<8-hex-chars>``).
No index template is applied, so tests work against a plain OpenSearch node
without the full bootstrap (no ML model required).

Scenarios covered
-----------------
Seed:
  - Creates an index and populates it with the correct document count
  - Returns correct SeedResult metadata (index_name, docs_indexed)
  - Documents are retrievable by _id after seed
  - Second seed run reuses the existing index (already_exists handled gracefully)
  - Running seed on an empty Parquet creates an empty index

Sync:
  - New documents (no prior index) are fully upserted
  - Re-syncing the same unchanged Parquet skips all documents
  - Syncing a modified document upserts only the changed document
  - Syncing a Parquet with additional documents upserts only the new ones
  - soft_delete=True marks documents absent from the Parquet as deleted
  - Soft-deleted documents are not re-deleted on subsequent sync runs
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from opensearchpy import OpenSearch, TransportError

from app.ingestion.seed import make_client, seed
from app.ingestion.sync import content_hash, sync

from .conftest import make_parquet, sample_doc

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.integration


def _refresh(client: OpenSearch, index: str) -> None:
    """Force a segment refresh so newly indexed docs are searchable."""
    client.indices.refresh(index=index)


def _count(client: OpenSearch, index: str) -> int:
    """Return the total document count for *index*."""
    _refresh(client, index)
    return client.count(index=index)["count"]


def _get_doc(client: OpenSearch, index: str, doc_id: str) -> dict | None:
    """Fetch a document by ID; return None if not found."""
    try:
        return client.get(index=index, id=doc_id)["_source"]
    except TransportError:
        return None


def _alias_indices(client: OpenSearch, alias: str) -> list[str]:
    """Return index names currently behind *alias*; empty list if alias absent."""
    try:
        state = client.indices.get_alias(name=alias)
        return list(state.keys())
    except TransportError:
        return []


# ===========================================================================
# Seed integration tests
# ===========================================================================


class TestSeedIntegration:
    def test_seed_creates_index(self, os_client, test_prefix, tmp_path):
        rows = [sample_doc(0), sample_doc(1)]
        parquet = make_parquet(tmp_path, rows)
        index_name = f"{test_prefix}-001"

        seed(parquet, client=os_client, index_name=index_name)

        assert os_client.indices.exists(index=index_name)

    def test_seed_indexes_correct_doc_count(self, os_client, test_prefix, tmp_path):
        rows = [sample_doc(i) for i in range(3)]
        parquet = make_parquet(tmp_path, rows)
        index_name = f"{test_prefix}-001"

        result = seed(parquet, client=os_client, index_name=index_name)

        assert result.docs_indexed == 3
        assert result.bulk_errors == 0
        assert _count(os_client, index_name) == 3

    def test_seed_result_metadata(self, os_client, test_prefix, tmp_path):
        rows = [sample_doc(0)]
        parquet = make_parquet(tmp_path, rows)
        index_name = f"{test_prefix}-001"

        result = seed(parquet, client=os_client, index_name=index_name)

        assert result.index_name == index_name

    def test_seed_docs_are_retrievable_by_id(self, os_client, test_prefix, tmp_path):
        doc = sample_doc(0)
        parquet = make_parquet(tmp_path, [doc])
        index_name = f"{test_prefix}-001"

        seed(parquet, client=os_client, index_name=index_name)
        _refresh(os_client, index_name)

        stored = _get_doc(os_client, index_name, doc["company_id"])
        assert stored is not None
        assert stored["name"] == doc["name"]

    def test_second_seed_reuses_existing_index(self, os_client, test_prefix, tmp_path):
        rows = [sample_doc(0)]
        parquet = make_parquet(tmp_path, rows)
        index_name = f"{test_prefix}-001"

        # First seed creates the index
        seed(parquet, client=os_client, index_name=index_name)
        # Second seed should not raise — index_already_exists handled gracefully
        result = seed(parquet, client=os_client, index_name=index_name)
        assert result.index_name == index_name

    def test_seed_empty_parquet_creates_empty_index(self, os_client, test_prefix, tmp_path):
        parquet = make_parquet(tmp_path, [])
        index_name = f"{test_prefix}-001"

        result = seed(parquet, client=os_client, index_name=index_name)

        assert result.docs_indexed == 0
        assert os_client.indices.exists(index=index_name)
        assert _count(os_client, index_name) == 0


# ===========================================================================
# Sync integration tests
# ===========================================================================


class TestSyncIntegration:
    def _seed_first(
        self,
        client: OpenSearch,
        tmp_path: Path,
        rows: list[dict],
        prefix: str,
    ) -> str:
        """Seed initial data; return index_name."""
        seed_dir = tmp_path / "seed"
        seed_dir.mkdir(parents=True, exist_ok=True)
        parquet = make_parquet(seed_dir, rows)
        index_name = f"{prefix}-idx"
        seed(parquet, client=client, index_name=index_name)
        _refresh(client, index_name)
        return index_name

    def test_sync_new_docs_are_upserted(self, os_client, test_prefix, tmp_path):
        rows = [sample_doc(0)]
        index_name = self._seed_first(os_client, tmp_path, rows, test_prefix)

        new_doc = sample_doc(99)
        sync_parquet = make_parquet(tmp_path / "sync", [new_doc])
        result = sync(sync_parquet, client=os_client, index_name=index_name)

        assert result.docs_upserted == 1
        _refresh(os_client, index_name)
        assert _get_doc(os_client, index_name, new_doc["company_id"]) is not None

    def test_sync_unchanged_docs_are_skipped(self, os_client, test_prefix, tmp_path):
        rows = [sample_doc(0)]
        index_name = self._seed_first(os_client, tmp_path, rows, test_prefix)

        sync_parquet = make_parquet(tmp_path / "sync1", rows)
        sync(sync_parquet, client=os_client, index_name=index_name)  # attaches hash

        sync_parquet2 = make_parquet(tmp_path / "sync2", rows)
        result = sync(sync_parquet2, client=os_client, index_name=index_name)

        assert result.docs_skipped == len(rows)
        assert result.docs_upserted == 0

    def test_sync_changed_doc_is_upserted(self, os_client, test_prefix, tmp_path):
        original = sample_doc(0, name="original name")
        index_name = self._seed_first(os_client, tmp_path, [original], test_prefix)

        sync(make_parquet(tmp_path / "sync1", [original]), client=os_client, index_name=index_name)

        modified = {**original, "name": "modified name"}
        result = sync(
            make_parquet(tmp_path / "sync2", [modified]),
            client=os_client,
            index_name=index_name,
        )

        assert result.docs_upserted == 1
        assert result.docs_skipped == 0

    def test_sync_updated_field_is_stored(self, os_client, test_prefix, tmp_path):
        original = sample_doc(0, name="original name")
        index_name = self._seed_first(os_client, tmp_path, [original], test_prefix)

        modified = {**original, "name": "new name"}
        sync(make_parquet(tmp_path / "sync", [modified]), client=os_client, index_name=index_name)
        _refresh(os_client, index_name)

        stored = _get_doc(os_client, index_name, original["company_id"])
        assert stored["name"] == "new name"

    def test_sync_stores_content_hash_on_upserted_doc(self, os_client, test_prefix, tmp_path):
        doc = sample_doc(0)
        index_name = self._seed_first(os_client, tmp_path, [doc], test_prefix)

        sync(make_parquet(tmp_path / "sync", [doc]), client=os_client, index_name=index_name)
        _refresh(os_client, index_name)

        stored = _get_doc(os_client, index_name, doc["company_id"])
        assert stored is not None
        assert "content_hash" in stored
        assert stored["content_hash"] == content_hash(doc)

    def test_sync_soft_delete_marks_missing_docs(self, os_client, test_prefix, tmp_path):
        doc_keep = sample_doc(0)
        doc_delete = sample_doc(1)
        index_name = self._seed_first(os_client, tmp_path, [doc_keep, doc_delete], test_prefix)

        result = sync(
            make_parquet(tmp_path / "sync", [doc_keep]),
            client=os_client,
            index_name=index_name,
            soft_delete=True,
        )

        assert result.docs_soft_deleted == 1
        _refresh(os_client, index_name)
        stored = _get_doc(os_client, index_name, doc_delete["company_id"])
        assert stored is not None
        assert stored.get("is_deleted") is True
        assert "deleted_at" in stored

    def test_sync_soft_delete_does_not_touch_kept_docs(self, os_client, test_prefix, tmp_path):
        doc_keep = sample_doc(0)
        doc_delete = sample_doc(1)
        index_name = self._seed_first(os_client, tmp_path, [doc_keep, doc_delete], test_prefix)

        sync(
            make_parquet(tmp_path / "sync", [doc_keep]),
            client=os_client,
            index_name=index_name,
            soft_delete=True,
        )
        _refresh(os_client, index_name)

        stored_keep = _get_doc(os_client, index_name, doc_keep["company_id"])
        assert stored_keep.get("is_deleted") is not True

    def test_sync_already_soft_deleted_not_re_deleted(self, os_client, test_prefix, tmp_path):
        doc_keep = sample_doc(0)
        doc_delete = sample_doc(1)
        index_name = self._seed_first(os_client, tmp_path, [doc_keep, doc_delete], test_prefix)

        sync(
            make_parquet(tmp_path / "sync1", [doc_keep]),
            client=os_client,
            index_name=index_name,
            soft_delete=True,
        )
        _refresh(os_client, index_name)

        result = sync(
            make_parquet(tmp_path / "sync2", [doc_keep]),
            client=os_client,
            index_name=index_name,
            soft_delete=True,
        )

        assert result.docs_soft_deleted == 0

    def test_sync_bulk_errors_zero_for_clean_run(self, os_client, test_prefix, tmp_path):
        rows = [sample_doc(0), sample_doc(1)]
        index_name = self._seed_first(os_client, tmp_path, rows, test_prefix)

        result = sync(
            make_parquet(tmp_path / "sync", [sample_doc(2)]),
            client=os_client,
            index_name=index_name,
        )

        assert result.bulk_errors == 0
