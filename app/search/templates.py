"""Startup health check for named OpenSearch search templates.

Verifies the Mustache templates required by the search API exist in OpenSearch.
Templates are registered by the bootstrap script 04-create-search-templates.sh,
which is the single source of truth for the template DSL.

Templates expected:
  firmable-search-v1            — BM25 scored search with fuzzy, synonym, and exact-boost clauses
  firmable-search-hybrid-v1     — hybrid BM25 + neural search using the search pipeline
  firmable-facets-v1            — aggregation-only (size=0) for facet count queries
"""

from __future__ import annotations

import logging

from opensearchpy import OpenSearch

logger = logging.getLogger(__name__)

_REQUIRED_TEMPLATES = [
    "firmable-search-v1",
    "firmable-search-hybrid-v1",
    "firmable-facets-v1",
]


def ensure_search_templates(client: OpenSearch) -> None:
    """Verify named search templates exist in OpenSearch.

    Called once during API lifespan startup. Logs a warning (does NOT raise)
    on missing templates or connectivity failures so the API can still start.
    Run the bootstrap script 04-create-search-templates.sh to register them.
    The /readiness probe will surface missing templates as a health failure.
    """
    from opensearchpy.exceptions import TransportError

    for name in _REQUIRED_TEMPLATES:
        try:
            client.get_script(id=name)
            logger.debug("Search template '%s' verified", name)
        except TransportError as exc:
            logger.warning(
                "Search template '%s' not found — run 04-create-search-templates.sh to register it. Error: %s",
                name,
                exc,
            )
        except Exception as exc:
            logger.warning(
                "Could not verify template '%s' (OpenSearch unavailable at startup): %s",
                name,
                exc,
            )
