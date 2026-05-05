"""Structured JSON logging with an async-buffered OpenSearch sink.

Usage
-----
Call ``setup_logging(service="api")`` once at process startup.  All subsequent
``logging.getLogger(__name__)`` calls in any module will emit JSON records and,
when ``LOG_OPENSEARCH_ENABLED=true``, ship them to the daily rolling index:

  api       → logs-api-MMDD       (e.g. logs-api-0505)
  ingestion → logs-ingestion-MMDD

The OpenSearch handler is fire-and-forget via a background thread queue so it
never blocks the request path.  Log records that cannot be delivered are
silently dropped after a short timeout so a dead log cluster never takes down
the application.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import traceback
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "@timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", "unknown"),
        }

        # Merge any extra= kwargs the caller passed
        for key, value in record.__dict__.items():
            if key not in _LOGGING_RESERVED and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str)


_LOGGING_RESERVED = frozenset(logging.LogRecord(
    "", 0, "", 0, "", (), None
).__dict__.keys()) | {"service", "message", "asctime"}


# ---------------------------------------------------------------------------
# OpenSearch HTTP handler (background thread, non-blocking)
# ---------------------------------------------------------------------------

class _OpenSearchHandler(logging.Handler):
    """Ships log records to a daily OpenSearch index via a background thread.

    Records are placed on an in-process queue; a daemon thread drains the
    queue and bulk-indexes into ``<prefix>-MMDD``.  When the queue is full or
    the thread cannot reach OpenSearch the record is silently dropped so the
    application is never blocked by the logging sink.
    """

    _QUEUE_MAXSIZE = 2000
    _BATCH_SIZE = 50
    _FLUSH_INTERVAL_S = 5.0
    _ENQUEUE_TIMEOUT_S = 0.05   # never block the caller for more than 50ms

    def __init__(self, opensearch_url: str, index_prefix: str) -> None:
        super().__init__()
        self._url = opensearch_url.rstrip("/")
        self._prefix = index_prefix
        self._queue: queue.Queue[logging.LogRecord | None] = queue.Queue(
            maxsize=self._QUEUE_MAXSIZE
        )
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"os-log-{index_prefix}")
        self._thread.start()

    # -- logging.Handler interface --

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            pass  # drop — never block

    def close(self) -> None:
        try:
            self._queue.put(None, timeout=1)  # sentinel to stop thread
        except queue.Full:
            pass
        self._thread.join(timeout=3)
        super().close()

    # -- background thread --

    def _run(self) -> None:
        import urllib.request
        import urllib.error

        batch: list[str] = []

        while True:
            try:
                record = self._queue.get(timeout=self._FLUSH_INTERVAL_S)
            except queue.Empty:
                if batch:
                    self._flush(batch, urllib)
                    batch = []
                continue

            if record is None:  # shutdown sentinel
                if batch:
                    self._flush(batch, urllib)
                break

            try:
                doc = self.format(record)
                index = self._index_name()
                meta = json.dumps({"index": {"_index": index}})
                batch.append(meta)
                batch.append(doc)
            except Exception:
                pass

            if len(batch) >= self._BATCH_SIZE * 2:
                self._flush(batch, urllib)
                batch = []

    def _flush(self, batch: list[str], urllib: Any) -> None:
        if not batch:
            return
        body = "\n".join(batch) + "\n"
        try:
            req = urllib.request.Request(
                f"{self._url}/_bulk",
                data=body.encode(),
                headers={"Content-Type": "application/x-ndjson"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception:
            pass  # drop on error — never raise from a log handler
        batch.clear()

    def _index_name(self) -> str:
        mmdd = datetime.now(tz=timezone.utc).strftime("%m%d")
        return f"{self._prefix}-{mmdd}"


# ---------------------------------------------------------------------------
# ServiceLogFilter — injects service name into every record
# ---------------------------------------------------------------------------

class _ServiceFilter(logging.Filter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._service
        return True


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def setup_logging(
    service: str,
    *,
    level: int = logging.INFO,
    opensearch_url: str | None = None,
    opensearch_enabled: bool = False,
) -> None:
    """Configure root logger with JSON output + optional OpenSearch sink.

    Call once at process startup before any log records are emitted.

    Parameters
    ----------
    service:
        Short service identifier embedded in every record (``"api"`` or
        ``"ingestion"``).  Determines the OpenSearch index prefix:
        ``logs-<service>-MMDD``.
    level:
        Root log level (default INFO).
    opensearch_url:
        Base URL of the OpenSearch cluster (e.g. ``http://localhost:9200``).
        Required when ``opensearch_enabled=True``.
    opensearch_enabled:
        When ``True`` a background-thread handler ships records to OpenSearch.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Remove any handlers added by earlier basicConfig calls
    for h in list(root.handlers):
        root.removeHandler(h)

    service_filter = _ServiceFilter(service)
    formatter = JsonFormatter()

    # Always add a stdout handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(service_filter)
    root.addHandler(stream_handler)

    if opensearch_enabled and opensearch_url:
        os_handler = _OpenSearchHandler(
            opensearch_url=opensearch_url,
            index_prefix=f"logs-{service}",
        )
        os_handler.setFormatter(formatter)
        os_handler.addFilter(service_filter)
        root.addHandler(os_handler)
        logging.getLogger(__name__).info(
            "OpenSearch log sink enabled",
            extra={"index_prefix": f"logs-{service}-MMDD", "url": opensearch_url},
        )
