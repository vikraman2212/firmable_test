"""Shared runtime config for ingestion CLI entrypoints.

Configuration is loaded from a TOML file so seed and sync can share one
OpenSearch section plus operation-specific defaults.  Command-line flags still
win over file values.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import tomllib

DEFAULT_CONFIG_PATH = Path("config/ingestion.toml")
DEFAULT_OPENSEARCH_URL = "http://localhost:9200"
DEFAULT_OPENSEARCH_TIMEOUT = 60
DEFAULT_INDEX_NAME = "companies"
DEFAULT_BATCH_SIZE = 500
DEFAULT_BULK_REQUEST_DELAY = 0
DEFAULT_SEED_CSV_PATH = Path("data/companies_sorted.csv")
DEFAULT_SYNC_PARQUET_PATH = Path("data/staged/latest.parquet")


@dataclass(frozen=True)
class OpenSearchRuntimeConfig:
    url: str = DEFAULT_OPENSEARCH_URL
    timeout: int = DEFAULT_OPENSEARCH_TIMEOUT


@dataclass(frozen=True)
class SeedRuntimeConfig:
    csv_path: Optional[Path] = DEFAULT_SEED_CSV_PATH
    parquet_path: Optional[Path] = None
    index_name: str = DEFAULT_INDEX_NAME
    batch_size: int = DEFAULT_BATCH_SIZE
    row_offset: int = 0
    row_limit: Optional[int] = None
    bulk_request_delay: float = DEFAULT_BULK_REQUEST_DELAY


@dataclass(frozen=True)
class SyncRuntimeConfig:
    parquet_path: Path = DEFAULT_SYNC_PARQUET_PATH
    index_name: str = DEFAULT_INDEX_NAME
    batch_size: int = DEFAULT_BATCH_SIZE
    soft_delete: bool = False


@dataclass(frozen=True)
class IngestionRuntimeConfig:
    source_path: Optional[Path]
    opensearch: OpenSearchRuntimeConfig
    seed: SeedRuntimeConfig
    sync: SyncRuntimeConfig


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_path(value: Any) -> Optional[Path]:
    if value in (None, ""):
        return None
    return Path(str(value))


def _as_int(value: Any, default: int) -> int:
    return int(value) if value is not None else default


def _as_bool(value: Any, default: bool) -> bool:
    return bool(value) if value is not None else default


def load_ingestion_config(path: Path | None = None) -> IngestionRuntimeConfig:
    """Load seed/sync runtime config from TOML.

    If *path* is omitted and the default file is absent, built-in defaults are
    returned.  If *path* is provided explicitly, absence is an error so callers
    fail fast on a mistyped config path.
    """
    if path is None:
        source_path = DEFAULT_CONFIG_PATH if DEFAULT_CONFIG_PATH.exists() else None
    else:
        source_path = Path(path)
        if not source_path.exists():
            raise FileNotFoundError(f"Config file not found: {source_path}")

    raw: dict[str, Any] = {}
    if source_path is not None:
        with source_path.open("rb") as handle:
            raw = tomllib.load(handle)

    opensearch_raw = _as_dict(raw.get("opensearch"))
    seed_raw = _as_dict(raw.get("seed"))
    sync_raw = _as_dict(raw.get("sync"))

    return IngestionRuntimeConfig(
        source_path=source_path,
        opensearch=OpenSearchRuntimeConfig(
            url=str(opensearch_raw.get("url", DEFAULT_OPENSEARCH_URL)),
            timeout=_as_int(opensearch_raw.get("timeout"), DEFAULT_OPENSEARCH_TIMEOUT),
        ),
        seed=SeedRuntimeConfig(
            csv_path=_as_path(seed_raw.get("csv_path", str(DEFAULT_SEED_CSV_PATH))),
            parquet_path=_as_path(seed_raw.get("parquet_path")),
            index_name=str(seed_raw.get("index_name", DEFAULT_INDEX_NAME)),
            batch_size=_as_int(seed_raw.get("batch_size"), DEFAULT_BATCH_SIZE),
            row_offset=_as_int(seed_raw.get("row_offset"), 0),
            row_limit=(int(seed_raw["row_limit"]) if seed_raw.get("row_limit") is not None else None),
            bulk_request_delay=float(seed_raw.get("bulk_request_delay", DEFAULT_BULK_REQUEST_DELAY)),
        ),
        sync=SyncRuntimeConfig(
            parquet_path=_as_path(sync_raw.get("parquet_path", str(DEFAULT_SYNC_PARQUET_PATH))) or DEFAULT_SYNC_PARQUET_PATH,
            index_name=str(sync_raw.get("index_name", DEFAULT_INDEX_NAME)),
            batch_size=_as_int(sync_raw.get("batch_size"), DEFAULT_BATCH_SIZE),
            soft_delete=_as_bool(sync_raw.get("soft_delete"), False),
        ),
    )
