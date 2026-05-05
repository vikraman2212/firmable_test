"""Pure query planning functions — no I/O, no side effects.

Translates API request objects into parameter dicts that are forwarded
to the named OpenSearch search templates (firmable-search-v1 and
firmable-facets-v1).  Synonym expansion is intentionally NOT done here;
it is delegated to the synonym_analyzer configured on the OpenSearch index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.api.schemas import FacetsRequest, SearchRequest
from app.ingestion.normalizers import normalize_country, normalize_industry, normalize_size_range, normalize_text_field

# Words that express search intent but carry no domain meaning.
# "companies in bengaluru" → "bengaluru"; "find tech firms" → "tech"
# These are not Lucene stop words, so they aren't caught by analyzer="stop".
_QUERY_META_WORDS = frozenset({
    "companies", "company", "businesses", "business",
    "firms", "firm", "organizations", "organisations",
    "find", "list", "show", "get", "search", "all", "top", "best",
})

_FOUNDED_YEAR_PATTERN = re.compile(
    r"\b(?:founded|started|established|formed|launched)\s+(?:(?:in|during|around|circa)\s+)?(\d{4})\b",
    re.IGNORECASE,
)


def _clean_query(text: str) -> str | None:
    """Strip meta-words from query; return None if nothing meaningful remains."""
    tokens = re.split(r"\s+", text.strip())
    meaningful = [t for t in tokens if t and t.lower() not in _QUERY_META_WORDS]
    return " ".join(meaningful) if meaningful else None


def _extract_founded_year(text: str) -> tuple[str, int | None]:
    """Extract simple founded-year phrases and remove them from the free-text query."""
    match = _FOUNDED_YEAR_PATTERN.search(text)
    if not match:
        return text, None
    remaining = _FOUNDED_YEAR_PATTERN.sub(" ", text, count=1)
    return remaining, int(match.group(1))


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
    - Strips blank filter values so they produce no clauses in the template
    - Computes from_ for cursor-style pagination
    - Industry synonym expansion is handled at query time by synonym_analyzer on the index
    """
    raw_query = (request.query or "").strip()
    extracted_year = None
    if raw_query:
        raw_query, extracted_year = _extract_founded_year(raw_query)
    query_text = _clean_query(raw_query) if raw_query else None
    filters = _extract_filters(
        industry=request.industry,
        size_range=request.size_range,
        country=request.country,
        region=getattr(request, "region", None),
        city=request.city,
        year_founded_gte=request.year_founded_gte,
        year_founded_lte=request.year_founded_lte,
    )
    if extracted_year is not None and "year_founded_gte" not in filters and "year_founded_lte" not in filters:
        filters["year_founded_gte"] = extracted_year
        filters["year_founded_lte"] = extracted_year
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
