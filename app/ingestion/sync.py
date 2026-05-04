"""Incremental sync flow for company data (P2-T08).

Sequence
--------
1. Read a staged Parquet file produced by ``stage_companies``.
2. For each batch, fetch existing ``content_hash`` values from the write alias
   via ``_mget`` so unchanged documents can be skipped without re-indexing.
3. Upsert documents whose hash differs (or that are absent from the index).
   ``doc_as_upsert: true`` makes every operation idempotent — running the same
   Parquet twice produces the same index state.
4. Optionally soft-delete documents that are present in the write alias but
   absent from the incoming Parquet by setting ``is_deleted = true`` and
   recording a ``deleted_at`` timestamp.

Public API
----------
content_hash(doc)
    Compute a stable SHA-256 content fingerprint for a document dict.

build_upsert_bulk_body(docs, index_name)
    Build NDJSON for a batch of upsert operations.

build_soft_delete_bulk_body(ids, index_name)
    Build NDJSON to mark a list of IDs as soft-deleted.

SyncResult
    Returned by ``sync()``.

sync(parquet_path, *, client, index_name, batch_size, soft_delete)
    Main incremental sync function.

CLI usage (driven by ``make sync``)::

    python -m app.ingestion.sync --config config/ingestion.toml
    python -m app.ingestion.sync --config config/ingestion.toml --parquet data/staged/latest.parquet
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
from opensearchpy import OpenSearch, TransportError

from app.ingestion.config import DEFAULT_CONFIG_PATH, load_ingestion_config
from app.ingestion.seed import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_INDEX_NAME,
    OpenSearchError,
    _count_bulk_errors,
    make_client,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Content hash
# ---------------------------------------------------------------------------


def content_hash(doc: dict) -> str:
    """Return a stable SHA-256 hex digest for *doc*.

    Keys are sorted so field ordering does not affect the hash.  Fields
    injected by OpenSearch pipelines (``company_vector``, ``is_deleted``,
    ``deleted_at``) are not present in a Parquet row, so hashes computed from
    Parquet rows are comparable to hashes stored at upsert time.

    Args:
        doc: Document dictionary containing core company fields.

    Returns:
        64-character lowercase hex digest.
    """
    serialised = json.dumps(doc, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class SyncResult:
    """Outcome of an incremental sync run.

    Attributes:
        docs_examined: Total documents in the Parquet file.
        docs_upserted: Documents sent to OpenSearch (new or content-changed).
        docs_skipped: Unchanged documents skipped (hash matched existing).
        docs_soft_deleted: Documents marked deleted (only when soft_delete=True).
        bulk_errors: Total document-level failures reported by the bulk API.
        batches_sent: Number of bulk requests sent to the bulk API.
    """

    docs_examined: int
    docs_upserted: int
    docs_skipped: int
    docs_soft_deleted: int
    bulk_errors: int
    batches_sent: int = 0


# ---------------------------------------------------------------------------
# Bulk body helpers
# ---------------------------------------------------------------------------


def build_upsert_bulk_body(docs: list[dict], index_name: str) -> str:
    """Return NDJSON bulk body for upsert operations.

    Each document generates two lines:
    - Action line: ``{"update": {"_index": "<index>", "_id": "<company_id>"}}``
    - Payload line: ``{"doc": {..., "content_hash": "<hash>"}, "doc_as_upsert": true}``

    The stored ``content_hash`` lets future sync runs skip unchanged documents
    without reading the full source document.

    Args:
        docs: List of document dicts, each containing ``company_id``.
        index_name: Target OpenSearch index or write alias name.

    Returns:
        NDJSON string ending with a trailing newline.
    """
    lines: list[str] = []
    for doc in docs:
        action = {"update": {"_index": index_name, "_id": doc["company_id"]}}
        payload = {
            "doc": {**doc, "content_hash": content_hash(doc)},
            "doc_as_upsert": True,
        }
        lines.append(json.dumps(action, ensure_ascii=False))
        lines.append(json.dumps(payload, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def build_soft_delete_bulk_body(ids: list[str], index_name: str) -> str:
    """Return NDJSON bulk body to mark the given document IDs as soft-deleted.

    Args:
        ids: Document IDs (``company_id`` values) to mark as deleted.
        index_name: Target OpenSearch index or write alias name.

    Returns:
        NDJSON string ending with a trailing newline.
    """
    now = datetime.now(timezone.utc).isoformat()
    lines: list[str] = []
    for doc_id in ids:
        action = {"update": {"_index": index_name, "_id": doc_id}}
        payload = {"doc": {"is_deleted": True, "deleted_at": now}}
        lines.append(json.dumps(action, ensure_ascii=False))
        lines.append(json.dumps(payload, ensure_ascii=False))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_existing_hashes(
    client: OpenSearch,
    index: str,
    ids: list[str],
) -> dict[str, str]:
    """Return ``{company_id: content_hash}`` for documents already in *index*.

    Uses ``_mget`` and fetches only the ``content_hash`` source field.  Missing
    documents are omitted from the result so callers treat them as new.

    Returns an empty dict when *ids* is empty or the index/alias does not yet
    exist (404 TransportError is treated as "nothing stored yet").
    """
    if not ids:
        return {}
    try:
        response = client.mget(
            body={"ids": ids},
            index=index,
            _source_includes=["content_hash"],
        )
    except TransportError as exc:
        if getattr(exc, "status_code", None) == 404:
            return {}
        raise OpenSearchError(f"mget failed: {exc}") from exc

    result: dict[str, str] = {}
    for doc in response.get("docs", []):
        if doc.get("found"):
            h = doc.get("_source", {}).get("content_hash")
            if h:
                result[doc["_id"]] = h
    return result


def _find_stale_ids(
    client: OpenSearch,
    index: str,
    incoming_ids: set[str],
) -> list[str]:
    """Return IDs present in *index* but absent from *incoming_ids*.

    Iterates with the scroll API to handle large indices.  Only non-deleted
    documents are considered (``is_deleted`` absent or ``false``).
    """
    query: dict = {
        "size": 1000,
        "_source": False,
        "query": {
            "bool": {
                "must_not": [{"term": {"is_deleted": True}}],
            }
        },
    }
    stale: list[str] = []
    scroll_id: str | None = None
    try:
        page = client.search(index=index, body=query, scroll="1m")
        scroll_id = page.get("_scroll_id")
        hits = page["hits"]["hits"]
        while hits:
            for h in hits:
                if h["_id"] not in incoming_ids:
                    stale.append(h["_id"])
            if not scroll_id:
                break
            page = client.scroll(scroll_id=scroll_id, scroll="1m")
            scroll_id = page.get("_scroll_id")
            hits = page["hits"]["hits"]
    except TransportError as exc:
        raise OpenSearchError(f"scroll for stale IDs failed: {exc}") from exc
    finally:
        if scroll_id:
            try:
                client.clear_scroll(scroll_id=scroll_id)
            except TransportError:
                pass
    return stale


# ---------------------------------------------------------------------------
# Main sync pipeline
# ---------------------------------------------------------------------------


def sync(
    parquet_path: Path,
    *,
    client: OpenSearch,
    index_name: str = DEFAULT_INDEX_NAME,
    batch_size: int = DEFAULT_BATCH_SIZE,
    soft_delete: bool = False,
) -> SyncResult:
    """Incrementally upsert changed company documents into the index.

    Args:
        parquet_path: Path to a Parquet file produced by ``stage_companies``.
        client: ``opensearch-py`` ``OpenSearch`` instance.
        index_name: Target OpenSearch index (default: ``companies``).
        batch_size: Documents per bulk request (default: 500).
        soft_delete: When True, documents present in the index but absent from
            the Parquet are marked with ``is_deleted=true`` and ``deleted_at``.

    Returns:
        SyncResult with per-category document counts and error totals.

    Raises:
        FileNotFoundError: If *parquet_path* does not exist.
        OpenSearchError: On HTTP/transport failures from OpenSearch.
    """
    parquet_path = Path(parquet_path)
    logger.info("Sync start", extra={"parquet_path": str(parquet_path)})
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

    # 1. Load all records from Parquet
    logger.info("Reading staged parquet", extra={"parquet_path": str(parquet_path)})
    table = pq.read_table(parquet_path)
    docs: list[dict] = []
    for batch in table.to_batches():
        for row in range(batch.num_rows):
            doc = {col: batch.column(col)[row].as_py() for col in table.schema.names}
            doc = {k: v for k, v in doc.items() if v is not None}
            docs.append(doc)

    total = len(docs)
    incoming_ids: set[str] = {d["company_id"] for d in docs}
    logger.info("Loaded staged parquet", extra={"docs": total, "index_name": index_name})

    docs_upserted = 0
    docs_skipped = 0
    bulk_errors = 0
    batches_sent = 0

    # 2. Process in batches: compare hashes, upsert only changed or new docs
    for offset in range(0, max(total, 1), batch_size):
        chunk = docs[offset : offset + batch_size]
        if not chunk:
            break

        ids = [d["company_id"] for d in chunk]
        logger.info(
            "Fetching existing hashes",
            extra={
                "index_name": index_name,
                "batch_number": (offset // batch_size) + 1,
                "batch_docs": len(chunk),
            },
        )
        existing_hashes = _fetch_existing_hashes(client, index_name, ids)

        to_upsert = [
            d for d in chunk
            if existing_hashes.get(d["company_id"]) != content_hash(d)
        ]
        docs_skipped += len(chunk) - len(to_upsert)

        if to_upsert:
            ndjson = build_upsert_bulk_body(to_upsert, index_name)
            try:
                logger.info(
                    "Sending upsert batch",
                    extra={
                        "index_name": index_name,
                        "batch_number": batches_sent + 1,
                        "batch_docs": len(to_upsert),
                    },
                )
                response = client.bulk(body=ndjson)
            except TransportError as exc:
                raise OpenSearchError(f"bulk upsert failed: {exc}") from exc
            bulk_errors += _count_bulk_errors(response)
            batches_sent += 1

        docs_upserted += len(to_upsert)

    # 3. Optional soft-delete for stale documents
    docs_soft_deleted = 0
    if soft_delete and incoming_ids:
        logger.info("Scanning for stale documents", extra={"index_name": index_name})
        stale_ids = _find_stale_ids(client, index_name, incoming_ids)
        if stale_ids:
            ndjson = build_soft_delete_bulk_body(stale_ids, index_name)
            try:
                logger.info(
                    "Sending soft-delete batch",
                    extra={"index_name": index_name, "docs": len(stale_ids)},
                )
                response = client.bulk(body=ndjson)
            except TransportError as exc:
                raise OpenSearchError(f"bulk soft-delete failed: {exc}") from exc
            bulk_errors += _count_bulk_errors(response)
            docs_soft_deleted = len(stale_ids)
            batches_sent += 1

    return SyncResult(
        docs_examined=total,
        docs_upserted=docs_upserted,
        docs_skipped=docs_skipped,
        docs_soft_deleted=docs_soft_deleted,
        bulk_errors=bulk_errors,
        batches_sent=batches_sent,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Incrementally sync staged company data into OpenSearch."
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help=f"Optional ingestion config TOML (default lookup: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--parquet",
        metavar="PATH",
        default=None,
        help="Pre-staged Parquet artifact from stage_companies().",
    )
    parser.add_argument(
        "--opensearch-url",
        default=None,
        metavar="URL",
        help="Override the configured OpenSearch base URL.",
    )
    parser.add_argument(
        "--opensearch-timeout",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Override the configured OpenSearch client timeout.",
    )
    parser.add_argument(
        "--index-name",
        default=None,
        metavar="INDEX",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        metavar="N",
    )
    parser.add_argument(
        "--soft-delete",
        action="store_true",
        default=None,
        help="Mark documents missing from the input parquet as soft-deleted.",
    )
    return parser.parse_args()


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def _resolve_cli_config(args: argparse.Namespace) -> dict[str, object]:
    runtime = load_ingestion_config(Path(args.config) if args.config else None)
    return {
        "config_path": runtime.source_path,
        "parquet_path": Path(args.parquet) if args.parquet else runtime.sync.parquet_path,
        "opensearch_url": args.opensearch_url or runtime.opensearch.url,
        "opensearch_timeout": args.opensearch_timeout or runtime.opensearch.timeout,
        "index_name": args.index_name or runtime.sync.index_name,
        "batch_size": args.batch_size or runtime.sync.batch_size,
        "soft_delete": args.soft_delete if args.soft_delete is not None else runtime.sync.soft_delete,
    }


def main() -> None:
    _configure_logging()
    args = _parse_args()
    resolved = _resolve_cli_config(args)

    logger.info(
        "Loaded sync runtime config",
        extra={
            "config_path": str(resolved["config_path"]) if resolved["config_path"] else "<defaults>",
            "parquet_path": str(resolved["parquet_path"]),
            "index_name": resolved["index_name"],
            "batch_size": resolved["batch_size"],
            "soft_delete": resolved["soft_delete"],
        },
    )

    client = make_client(
        str(resolved["opensearch_url"]),
        timeout=int(resolved["opensearch_timeout"]),
    )
    result = sync(
        Path(resolved["parquet_path"]),
        client=client,
        index_name=str(resolved["index_name"]),
        batch_size=int(resolved["batch_size"]),
        soft_delete=bool(resolved["soft_delete"]),
    )

    print(f"Docs examined    : {result.docs_examined}")
    print(f"Docs upserted    : {result.docs_upserted}")
    print(f"Docs skipped     : {result.docs_skipped}")
    print(f"Docs soft deleted: {result.docs_soft_deleted}")
    print(f"Bulk errors      : {result.bulk_errors}")
    print(f"Batches sent     : {result.batches_sent}")


if __name__ == "__main__":
    main()
