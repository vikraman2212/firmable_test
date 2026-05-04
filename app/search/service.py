"""Search service — translates SearchRequest into OpenSearch queries and maps results back.

This is a skeleton. Each method raises NotImplementedError until implemented in P3.
"""

from opensearchpy import OpenSearch

from app.api.schemas import CompanyResult, SearchRequest, SearchResponse


class SearchService:
    def __init__(self, client: OpenSearch, index_name: str) -> None:
        self._client = client
        self._index = index_name

    def search(self, request: SearchRequest) -> SearchResponse:
        """Execute a search request and return shaped results."""
        raise NotImplementedError("search() not yet implemented — coming in P3")

    # ------------------------------------------------------------------
    # Private helpers (to be filled in during P3)
    # ------------------------------------------------------------------

    def _build_query(self, request: SearchRequest) -> dict:
        """Build the OpenSearch query DSL from a SearchRequest."""
        raise NotImplementedError

    def _map_hit(self, hit: dict) -> CompanyResult:
        """Map a raw OpenSearch hit to a CompanyResult."""
        raise NotImplementedError
