"""Shared fixtures for ingestion↔OpenSearch integration tests.

Tests in this package connect to a real OpenSearch instance.  If OpenSearch
is not reachable the entire module is skipped automatically — no failures,
no red CI.

Environment variables
---------------------
INTEGRATION_OPENSEARCH_URL
    Base URL of the OpenSearch instance to target.
    Defaults to ``http://localhost:9200``.

Running the tests
-----------------
Start OpenSearch (the project's docker-compose stack is sufficient), then::

    uv run pytest tests/integration/ -v -m integration

or let them run as part of the full suite when OpenSearch is up::

    uv run pytest tests/ -v

Design choices
--------------
* Each test gets a unique index prefix so tests are fully isolated.
* No index template is applied — dynamic mappings are fine for integration
  testing the HTTP mechanics; ML-model dependent mappings are not required.
* All test indices are cleaned up after each test via an autouse fixture.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from opensearchpy import OpenSearch, TransportError

from app.ingestion.stage import PARQUET_SCHEMA

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_URL = "http://localhost:9200"
_INTEGRATION_URL = os.getenv("INTEGRATION_OPENSEARCH_URL", DEFAULT_URL)


# ---------------------------------------------------------------------------
# Session-scoped: single client, skip entire module if unreachable
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def os_client() -> OpenSearch:
    """Return a real OpenSearch client; skip all integration tests if down."""
    client = OpenSearch(hosts=[_INTEGRATION_URL], http_compress=True, timeout=10)
    try:
        info = client.info()
        version = info.get("version", {}).get("number", "unknown")
        print(f"\n[integration] Connected to OpenSearch {version} at {_INTEGRATION_URL}")
    except Exception as exc:
        pytest.skip(f"OpenSearch not reachable at {_INTEGRATION_URL}: {exc}")
    return client


# ---------------------------------------------------------------------------
# Function-scoped: unique prefix + automatic index cleanup
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_prefix() -> str:
    """Return a unique short prefix for this test's indices and aliases."""
    return f"test-ingestion-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def cleanup_test_indices(os_client: OpenSearch, test_prefix: str):
    """Delete all indices whose name starts with *test_prefix* after the test."""
    yield
    try:
        os_client.indices.delete(index=f"{test_prefix}*", ignore_unavailable=True)
    except TransportError:
        pass  # Best-effort cleanup


# ---------------------------------------------------------------------------
# Parquet fixture helpers
# ---------------------------------------------------------------------------


def make_parquet(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a minimal Parquet artifact from the given row dicts."""
    columns: dict[str, list] = {f.name: [] for f in PARQUET_SCHEMA}
    for row in rows:
        for col in columns:
            columns[col].append(row.get(col))
    arrays = [pa.array(columns[f.name], type=f.type) for f in PARQUET_SCHEMA]
    table = pa.Table.from_arrays(arrays, schema=PARQUET_SCHEMA)
    path = tmp_path / "test.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)
    return path


def sample_doc(n: int = 0, **overrides) -> dict:
    """Return a minimal valid company document dict."""
    base = {
        "company_id": f"{'a' * (62 - len(str(n)))}{n:02d}",
        "name": f"company {n}",
        "domain": f"company{n}.com",
        "industry": "technology",
        "size_range": "11-50",
        "city": "london",
        "region": "england",
        "country": "united kingdom",
        "year_founded": 2000 + n,
        "current_employee_estimate": 30,
        "total_employee_estimate": 35,
        "linkedin_url": f"linkedin.com/company/company{n}",
        "company_semantic_text": f"company {n} technology london",
    }
    base.update(overrides)
    return base
