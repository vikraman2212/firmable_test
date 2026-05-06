"""Seed flow for bulk-loading staged Parquet data into OpenSearch (P2-T07).

Sequence
--------
1. Read a staged Parquet file produced by ``stage_companies``.
2. Create (or reuse) the ``companies`` index — the ``companies*`` template
   automatically applies strict mappings, the knn_vector field, and the
   embedding ingest pipeline.  No extra settings are passed on creation.
3. Bulk-index all documents in configurable batches.  The pipeline injects
   ``company_vector`` on ingest; callers do not supply it.

Public API
----------
make_client(host)
    Build an ``OpenSearch`` client from a URL string.

SeedResult
    Returned by ``seed()``.

seed(parquet_path, *, client, batch_size, index_name)
    Main pipeline function.

CLI usage (driven by ``make seed``)::

    python -m app.ingestion.seed --config config/ingestion.toml
    python -m app.ingestion.seed --config config/ingestion.toml --csv data/companies_sorted.csv
    python -m app.ingestion.seed --parquet data/staged/latest.parquet
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pyarrow.parquet as pq
from opensearchpy import OpenSearch, RequestError, TransportError

from app.ingestion.config import DEFAULT_CONFIG_PATH, load_ingestion_config
from app.logging_config import setup_logging

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_INDEX_NAME = "companies"
DEFAULT_BATCH_SIZE = 500
DEFAULT_OPENSEARCH_URL = "http://localhost:9200"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def make_client(host: str = DEFAULT_OPENSEARCH_URL, *, timeout: int = 60) -> OpenSearch:
    """Return a configured ``opensearch-py`` client for the given host URL."""
    logger.info("Connecting to OpenSearch", extra={"host": host, "timeout": timeout})
    return OpenSearch(
        hosts=[host],
        http_compress=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class OpenSearchError(RuntimeError):
    """Raised for OpenSearch HTTP/transport failures in the seed pipeline."""


# ---------------------------------------------------------------------------
# Bulk body construction
# ---------------------------------------------------------------------------


def build_bulk_body(docs: list[dict], index_name: str) -> str:
    """Return NDJSON bulk body for the given documents.

    Each document produces two lines:
    - Action line: ``{"index": {"_index": "<index>", "_id": "<company_id>"}}``
    - Source line: the document as JSON (``company_id`` retained for upserts)

    Args:
        docs: List of document dicts, each containing ``company_id``.
        index_name: Target OpenSearch index name.

    Returns:
        NDJSON string ending with a trailing newline.
    """
    lines: list[str] = []
    for doc in docs:
        action = {"index": {"_index": index_name, "_id": doc["company_id"]}}
        lines.append(json.dumps(action, ensure_ascii=False))
        lines.append(json.dumps(doc, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def _count_bulk_errors(bulk_response: dict) -> int:
    """Return the number of failed items in a bulk response."""
    if not bulk_response.get("errors"):
        return 0
    return sum(
        1
        for item in bulk_response.get("items", [])
        if "error" in next(iter(item.values()))
    )


# ---------------------------------------------------------------------------
# Index name generator
# ---------------------------------------------------------------------------


def make_index_name(ts: Optional[datetime] = None) -> str:
    """Return a timestamped index name, e.g. ``companies-20260504t083012z``."""
    ts = ts or datetime.now(timezone.utc)
    return "companies-" + ts.strftime("%Y%m%dt%H%M%Sz")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class SeedResult:
    """Outcome of a seed run.

    Attributes:
        index_name: The OpenSearch index that was created and populated.
        docs_indexed: Total documents sent to OpenSearch.
        bulk_errors: Total document-level failures reported by the bulk API.
        batches_sent: Number of bulk requests sent.
    """

    index_name: str
    docs_indexed: int
    bulk_errors: int
    batches_sent: int = 0


# ---------------------------------------------------------------------------
# Main seed pipeline
# ---------------------------------------------------------------------------


def seed(
    parquet_path: Path,
    *,
    client: OpenSearch,
    batch_size: int = DEFAULT_BATCH_SIZE,
    index_name: str = DEFAULT_INDEX_NAME,
) -> SeedResult:
    """Bulk-load a staged Parquet artifact into OpenSearch.

    The target index is created if it does not already exist.  Index settings
    and mappings are applied automatically by the ``companies*`` index template;
    no explicit settings body is passed on creation.

    Args:
        parquet_path: Path to a Parquet file produced by ``stage_companies``.
        client: ``opensearch-py`` ``OpenSearch`` instance.
        batch_size: Documents per bulk request (default: 500).
        index_name: Target OpenSearch index (default: ``companies``).

    Returns:
        SeedResult with document counts.

    Raises:
        FileNotFoundError: If *parquet_path* does not exist.
        OpenSearchError: On HTTP/transport failures from OpenSearch.
    """
    parquet_path = Path(parquet_path)
    logger.info("Seed start", extra={"parquet_path": str(parquet_path)})
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

    target_index = index_name
    logger.info("Reading staged parquet", extra={"parquet_path": str(parquet_path)})

    # 1. Read records from Parquet
    table = pq.read_table(parquet_path)
    docs: list[dict] = []
    for batch in table.to_batches():
        for row in range(batch.num_rows):
            doc = {col: batch.column(col)[row].as_py() for col in table.schema.names}
            doc = {k: v for k, v in doc.items() if v is not None}
            docs.append(doc)

    total = len(docs)
    logger.info("Loaded staged parquet", extra={"docs": total, "index_name": target_index})

    # 2. Create the target index if it does not yet exist.
    #    No settings body is passed — the companies* template auto-applies
    #    mappings, analyzers, knn settings, and the embedding pipeline.
    try:
        logger.info("Creating target index", extra={"index_name": target_index})
        client.indices.create(index=target_index)
    except RequestError as exc:
        if exc.error in {"index_already_exists_exception", "resource_already_exists_exception"}:
            logger.warning(
                "Index already exists, skipping creation",
                extra={"index_name": target_index},
            )
        else:
            raise OpenSearchError(f"create_index({target_index}) failed: {exc}") from exc
    except TransportError as exc:
        raise OpenSearchError(f"create_index({target_index}) failed: {exc}") from exc

    # 3. Bulk index in batches
    bulk_errors = 0
    batches_sent = 0
    for offset in range(0, max(total, 1), batch_size):
        chunk = docs[offset: offset + batch_size]
        if not chunk:
            break
        ndjson = build_bulk_body(chunk, target_index)
        try:
            logger.info(
                "Sending bulk batch",
                extra={
                    "index_name": target_index,
                    "batch_number": batches_sent + 1,
                    "batch_docs": len(chunk),
                    "offset": offset,
                },
            )
            response = client.bulk(body=ndjson)
        except TransportError as exc:
            raise OpenSearchError(f"bulk request failed: {exc}") from exc
        bulk_errors += _count_bulk_errors(response)
        batches_sent += 1

    return SeedResult(
        index_name=target_index,
        docs_indexed=total,
        bulk_errors=bulk_errors,
        batches_sent=batches_sent,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed company data into OpenSearch from a CSV or Parquet file."
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help=f"Optional ingestion config TOML (default lookup: {DEFAULT_CONFIG_PATH})",
    )
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument(
        "--csv",
        metavar="PATH",
        help="Source companies CSV.  Staged to a temp Parquet file automatically.",
    )
    source.add_argument(
        "--parquet",
        metavar="PATH",
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
        "--batch-size",
        type=int,
        default=None,
        metavar="N",
    )
    parser.add_argument(
        "--row-limit",
        type=int,
        default=None,
        metavar="N",
        help="Limit CSV rows (useful for local subset runs).",
    )
    return parser.parse_args()


def _resolve_cli_config(args: argparse.Namespace) -> dict[str, object]:
    runtime = load_ingestion_config(Path(args.config) if args.config else None)
    csv_path = Path(args.csv) if args.csv else runtime.seed.csv_path
    parquet_path = Path(args.parquet) if args.parquet else runtime.seed.parquet_path

    if csv_path and parquet_path:
        raise ValueError("Choose exactly one source: csv or parquet")
    if not csv_path and not parquet_path:
        raise ValueError("A csv or parquet source must be provided via CLI or config")

    return {
        "config_path": runtime.source_path,
        "csv_path": csv_path,
        "parquet_path": parquet_path,
        "opensearch_url": args.opensearch_url or runtime.opensearch.url,
        "opensearch_timeout": args.opensearch_timeout or runtime.opensearch.timeout,
        "index_name": runtime.seed.index_name,
        "batch_size": args.batch_size or runtime.seed.batch_size,
        "row_limit": args.row_limit if args.row_limit is not None else runtime.seed.row_limit,
    }


def _configure_logging() -> None:
    from app.settings import settings
    setup_logging(
        service="ingestion",
        opensearch_url=settings.effective_log_opensearch_url,
        opensearch_enabled=settings.log_opensearch_enabled,
    )


def main() -> None:
    _configure_logging()
    args = _parse_args()
    resolved = _resolve_cli_config(args)

    logger.info(
        "Loaded seed runtime config",
        extra={
            "config_path": str(resolved["config_path"]) if resolved["config_path"] else "<defaults>",
            "csv_path": str(resolved["csv_path"]) if resolved["csv_path"] else None,
            "parquet_path": str(resolved["parquet_path"]) if resolved["parquet_path"] else None,
            "index_name": resolved["index_name"],
            "batch_size": resolved["batch_size"],
        },
    )

    if resolved["csv_path"]:
        import tempfile

        from app.ingestion.stage import stage_companies

        with tempfile.TemporaryDirectory() as tmp:
            logger.info("Staging CSV to parquet", extra={"csv_path": str(resolved["csv_path"]), "tmp_dir": tmp})
            staging_result = stage_companies(
                Path(resolved["csv_path"]),
                Path(tmp),
                row_limit=resolved["row_limit"],
            )
            parquet_path = staging_result.parquet_path
            if not parquet_path.exists():
                raise FileNotFoundError(
                    f"Staged parquet missing immediately after staging: {parquet_path}"
                )
            logger.info(
                "Staging complete: %s rows (%s skipped) -> %s",
                staging_result.valid_rows_written,
                staging_result.skipped_rows,
                parquet_path,
                extra={
                    "parquet_path": str(parquet_path),
                    "rows_written": staging_result.valid_rows_written,
                    "skipped_rows": staging_result.skipped_rows,
                },
            )

            client = make_client(
                str(resolved["opensearch_url"]),
                timeout=int(resolved["opensearch_timeout"]),
            )
            result = seed(
                parquet_path,
                client=client,
                index_name=str(resolved["index_name"]),
                batch_size=int(resolved["batch_size"]),
            )
    else:
        parquet_path = Path(resolved["parquet_path"])
        client = make_client(
            str(resolved["opensearch_url"]),
            timeout=int(resolved["opensearch_timeout"]),
        )
        result = seed(
            parquet_path,
            client=client,
            index_name=str(resolved["index_name"]),
            batch_size=int(resolved["batch_size"]),
        )

    print(f"Index created  : {result.index_name}")
    print(f"Docs indexed   : {result.docs_indexed}")
    print(f"Bulk errors    : {result.bulk_errors}")
    print(f"Batches sent   : {result.batches_sent}")


if __name__ == "__main__":
    main()
