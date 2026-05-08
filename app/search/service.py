"""Search service — translates SearchRequest into OpenSearch queries and maps results back."""

from __future__ import annotations

import time

from opensearchpy import OpenSearch

from app.api.schemas import (
    CompanyResult,
    FacetBucket,
    FacetsRequest,
    FacetsResponse,
    SearchRequest,
    SearchResponse,
)
from app.search.query_planner import build_facets_plan, build_search_plan
from app.settings import settings


class SearchService:
    def __init__(self, client: OpenSearch, index_name: str) -> None:
        self._client = client
        self._index = index_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, request: SearchRequest) -> SearchResponse:
        """Execute a search request using the default template for query searches."""
        plan = build_search_plan(request)
        params = plan.to_params()
        pagination_depth = max(settings.hybrid_neural_k, plan.from_ + plan.size)
        params.update(
            {
                "model_id": settings.effective_embedding_model_id,
                "neural_k": pagination_depth,
                "pagination_depth": pagination_depth,
            }
        )
        pipeline = settings.hybrid_search_pipeline if plan.query_text else None
        return self._execute_template(
            request,
            template_id=self._resolve_search_template_id(plan.query_text),
            params=params,
            pipeline=pipeline,
        )

    def search_lexical(self, request: SearchRequest) -> SearchResponse:
        """Execute a keyword-only (BM25) search, bypassing the neural hybrid pipeline."""
        plan = build_search_plan(request)
        return self._execute_template(
            request,
            template_id=settings.keyword_search_template_id,
            params=plan.to_params(),
        )

    def facets(self, request: FacetsRequest) -> FacetsResponse:
        """Execute an aggregation request using the firmable-facets-v1 named template."""
        plan = build_facets_plan(request)
        response = self._client.search_template(
            body={"id": "firmable-facets-v1", "params": plan.to_params()},
            index=self._index,
        )
        aggs = response.get("aggregations", {})
        return FacetsResponse(
            industry=self._map_buckets(aggs.get("by_industry", {})),
            size_range=self._map_buckets(aggs.get("by_size_range", {})),
            country=self._map_buckets(aggs.get("by_country", {})),
            city=self._map_buckets(aggs.get("by_city", {})),
            year_founded=self._map_buckets(aggs.get("by_year_founded", {})),
            tags=[],
        )

    def get_companies_by_ids(self, company_ids: list[str]) -> list[CompanyResult]:
        """Resolve company documents by company_id without going through ranked search."""
        if not company_ids:
            return []

        unique_ids = list(dict.fromkeys(company_ids))
        response = self._client.mget(index=self._index, body={"ids": unique_ids})
        return [
            self._map_document(doc)
            for doc in response.get("docs", [])
            if doc.get("found")
        ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _execute_template(
        self,
        request: SearchRequest,
        *,
        template_id: str,
        params: dict,
        pipeline: str | None = None,
    ) -> SearchResponse:
        t0 = time.monotonic()
        response = self._client.search_template(
            body={"id": template_id, "params": params},
            index=self._index,
            params={"search_pipeline": pipeline} if pipeline else None,
        )
        took_ms = int((time.monotonic() - t0) * 1000)
        hits = response.get("hits", {})
        total_value = hits.get("total", {})
        total = total_value.get("value", 0) if isinstance(total_value, dict) else int(total_value)
        return SearchResponse(
            items=[self._map_hit(h) for h in hits.get("hits", [])],
            total=total,
            page=request.page,
            page_size=request.page_size,
            took_ms=took_ms,
        )

    @staticmethod
    def _resolve_search_template_id(query_text: str | None) -> str:
        if query_text:
            return settings.search_template_id
        return settings.keyword_search_template_id

    def _map_hit(self, hit: dict) -> CompanyResult:
        return self._map_document(hit)

    def _map_document(self, document: dict) -> CompanyResult:
        src = document.get("_source", {})
        return CompanyResult(
            company_id=document.get("_id", src.get("company_id", "")),
            name=src.get("name", ""),
            domain=src.get("domain"),
            industry=src.get("industry"),
            size_range=src.get("size_range"),
            city=src.get("city"),
            region=src.get("region"),
            country=src.get("country"),
            year_founded=src.get("year_founded"),
            current_employee_estimate=src.get("current_employee_estimate"),
            explanation=document.get("_explanation"),
        )

    @staticmethod
    def _map_buckets(agg: dict) -> list[FacetBucket]:
        return [
            FacetBucket(key=str(b["key"]), count=b["doc_count"])
            for b in agg.get("buckets", [])
        ]

