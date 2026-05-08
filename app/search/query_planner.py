"""Pure query planning functions — no I/O, no side effects.

Translates API request objects into parameter dicts that are forwarded
to the named OpenSearch search templates (firmable-search-v1 and
firmable-facets-v1).  Synonym expansion is intentionally NOT done here;
it is delegated to the synonym_analyzer configured on the OpenSearch index.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.api.schemas import FacetsRequest, SearchRequest
from app.ingestion.normalizers import normalize_country, normalize_industry, normalize_size_range, normalize_text_field


@dataclass
class SearchPlan:
    """Resolved parameters ready to pass to a search template."""

    query_text: str | None
    filters: dict[str, Any]
    from_: int
    size: int
    explain: bool = False

    def to_params(self) -> dict[str, Any]:
        """Flatten into the flat params dict expected by OpenSearch search_template."""
        params: dict[str, Any] = {
            "from": self.from_,
            "size": self.size,
            "explain": self.explain,
        }
        if self.query_text:
            params["query_text"] = self.query_text
        params.update(self.filters)
        return params


def _extract_filters(
    industry: list[str] | None,
    size_range: list[str] | None,
    country: str | None,
    region: str | None,
    city: str | None,
    year_founded_gte: int | None,
    year_founded_lte: int | None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if industry:
        clean = [value for value in (normalize_industry(v) for v in industry) if value]
        if clean:
            filters["industry"] = clean
    if size_range:
        clean = [value for value in (normalize_size_range(v) for v in size_range) if value]
        if clean:
            filters["size_range"] = clean
    normalized_country = normalize_country(country) if country else None
    if normalized_country:
        filters["country"] = normalized_country
    normalized_region = normalize_text_field(region) if region else None
    if normalized_region:
        filters["region"] = normalized_region
    normalized_city = normalize_text_field(city) if city else None
    if normalized_city:
        filters["city"] = normalized_city
    if year_founded_gte is not None:
        filters["year_founded_gte"] = year_founded_gte
    if year_founded_lte is not None:
        filters["year_founded_lte"] = year_founded_lte
    return filters


def build_search_plan(request: SearchRequest) -> SearchPlan:
    """Build a SearchPlan from a POST /search request.

    - Trims whitespace from query; treats blank query as None (match-all)
    - Preserves query text exactly (no UI-side token stripping or NLP extraction)
    - Strips blank filter values so they produce no clauses in the template
    - Computes from_ for cursor-style pagination
    - Industry synonym expansion is handled at query time by synonym_analyzer on the index
    """
    raw_query = (request.query or "").strip()
    query_text = raw_query or None
    filters = _extract_filters(
        industry=request.industry,
        size_range=request.size_range,
        country=request.country,
        region=getattr(request, "region", None),
        city=request.city,
        year_founded_gte=request.year_founded_gte,
        year_founded_lte=request.year_founded_lte,
    )
    from_ = (request.page - 1) * request.page_size
    return SearchPlan(
        query_text=query_text,
        filters=filters,
        from_=from_,
        size=request.page_size,
        explain=request.explain,
    )


def build_facets_plan(request: FacetsRequest) -> SearchPlan:
    """Build a SearchPlan for POST /facets (aggregation-only, no hits).

    - size=0 so OpenSearch returns no document hits, only aggregation buckets
    - Same filter extraction as build_search_plan
    """
    filters = _extract_filters(
        industry=request.industry,
        size_range=request.size_range,
        country=request.country,
        region=getattr(request, "region", None),
        city=request.city,
        year_founded_gte=request.year_founded_gte,
        year_founded_lte=request.year_founded_lte,
    )
    return SearchPlan(query_text=None, filters=filters, from_=0, size=0)
