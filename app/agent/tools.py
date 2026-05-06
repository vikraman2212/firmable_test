"""LangChain tool set for the Firmable search agent.

Four tools:
    - hybrid_search  : BM25 + neural retrieval (primary for natural language queries)
    - lexical_search : BM25-only (for exact name/domain lookups)
    - get_facets     : aggregation counts for filter exploration
    - web_search     : Tavily-backed external search with DuckDuckGo fallback
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, field_validator

from app.api.schemas import FacetsRequest, SearchRequest
from app.search.service import SearchService

logger = logging.getLogger(__name__)

_LOW_RESULT_THRESHOLD = 3


_VALID_SIZE_RANGES = [
    "1 - 10", "11 - 50", "51 - 200", "201 - 500",
    "501 - 1000", "1001 - 5000", "5001 - 10000", "10001+",
]


class _SearchInput(BaseModel):
    query: str = Field(description="Natural language search query")
    industry: Optional[list[str]] = Field(
        default=None, description="Filter by industry list (e.g. ['Information Technology'])"
    )
    size_range: Optional[list[str]] = Field(
        default=None,
        description=(
            "Filter by company size range. Must be a list of exact strings from: "
            + ", ".join(f"'{v}'" for v in _VALID_SIZE_RANGES)
        ),
    )
    country: Optional[str] = Field(
        default=None,
        description=(
            "Filter by country name only (e.g. 'united states', 'australia'). "
            "Do NOT use this for US states, provinces, or cities. "
            "If the query says 'California', use region='california' and leave country unset unless a country is explicitly mentioned."
        ),
    )
    region: Optional[str] = Field(
        default=None,
        description="Filter by state/province/region (e.g. 'california', 'new york', 'ontario'). "
                    "Use this for US states and provinces — NOT city or country.",
    )
    city: Optional[str] = Field(
        default=None,
        description="Filter by city name only (e.g. 'san francisco', 'austin'). "
                    "Do NOT use this for states or countries.",
    )
    year_founded_gte: Optional[int] = Field(default=None, description="Minimum founding year")
    year_founded_lte: Optional[int] = Field(default=None, description="Maximum founding year")

    @field_validator("country", "region", "city", mode="before")
    @classmethod
    def normalize_blank_text(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("industry", "size_range", mode="before")
    @classmethod
    def normalize_blank_list_or_string(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip("[] ")
            return [stripped] if stripped else None
        return value

    @field_validator("size_range", mode="before")
    @classmethod
    def coerce_size_range(cls, v: object) -> object:
        """Accept a bare string or a JSON-encoded list from the LLM."""
        if isinstance(v, str):
            s = v.strip("[] ")
            return [s] if s else None
        return v


class _FacetsInput(BaseModel):
    industry: Optional[list[str]] = Field(default=None, description="Filter by industry")
    size_range: Optional[list[str]] = Field(
        default=None,
        description="Filter by size range (valid values: " + ", ".join(f"'{v}'" for v in _VALID_SIZE_RANGES) + ")",
    )
    country: Optional[str] = Field(default=None, description="Filter by country")
    region: Optional[str] = Field(default=None, description="Filter by state/province/region")
    city: Optional[str] = Field(default=None, description="Filter by city")


class _WebSearchInput(BaseModel):
    query: str = Field(description="Search query for external web information about companies")


def _search_response_to_json(resp, low_threshold: int = _LOW_RESULT_THRESHOLD) -> str:
    hits = [
        {
            "company_id": item.company_id,
            "name": item.name,
            "domain": item.domain,
            "industry": item.industry,
            "country": item.country,
            "city": item.city,
            "region": item.region,
            "size_range": item.size_range,
            "year_founded": item.year_founded,
            "current_employee_estimate": item.current_employee_estimate,
        }
        for item in resp.items
    ]
    result: dict = {"hits": hits, "total": resp.total, "took_ms": resp.took_ms}
    if resp.total < low_threshold:
        result["note"] = (
            f"Only {resp.total} result(s) found — consider web_search if external data is needed"
        )
    return json.dumps(result)


def make_search_tools(service: SearchService, tavily_api_key: str = "") -> list[BaseTool]:
    """Build the agent tool set with the SearchService injected via closure."""

    def hybrid_search_fn(
        query: str,
        industry: Optional[list[str]] = None,
        size_range: Optional[list[str]] = None,
        country: Optional[str] = None,
        region: Optional[str] = None,
        city: Optional[str] = None,
        year_founded_gte: Optional[int] = None,
        year_founded_lte: Optional[int] = None,
    ) -> str:
        try:
            req = SearchRequest(
                query=query,
                industry=industry,
                size_range=size_range,
                country=country,
                region=region,
                city=city,
                year_founded_gte=year_founded_gte,
                year_founded_lte=year_founded_lte,
                page=1,
                page_size=10,
            )
            return _search_response_to_json(service.search(req))
        except Exception as exc:
            logger.warning("hybrid_search tool error: %s", exc)
            return json.dumps({"error": str(exc), "hits": [], "total": 0})

    def lexical_search_fn(
        query: str,
        industry: Optional[list[str]] = None,
        size_range: Optional[list[str]] = None,
        country: Optional[str] = None,
        region: Optional[str] = None,
        city: Optional[str] = None,
        year_founded_gte: Optional[int] = None,
        year_founded_lte: Optional[int] = None,
    ) -> str:
        try:
            req = SearchRequest(
                query=query,
                industry=industry,
                size_range=size_range,
                country=country,
                region=region,
                city=city,
                year_founded_gte=year_founded_gte,
                year_founded_lte=year_founded_lte,
                page=1,
                page_size=10,
            )
            return _search_response_to_json(service.search_lexical(req))
        except Exception as exc:
            logger.warning("lexical_search tool error: %s", exc)
            return json.dumps({"error": str(exc), "hits": [], "total": 0})

    def get_facets_fn(
        industry: Optional[list[str]] = None,
        size_range: Optional[list[str]] = None,
        country: Optional[str] = None,
        region: Optional[str] = None,
        city: Optional[str] = None,
    ) -> str:
        try:
            req = FacetsRequest(
                industry=industry,
                size_range=size_range,
                country=country,
                region=region,
                city=city,
            )
            resp = service.facets(req)
            return json.dumps(
                {
                    "industry": [{"key": b.key, "count": b.count} for b in resp.industry],
                    "size_range": [{"key": b.key, "count": b.count} for b in resp.size_range],
                    "country": [{"key": b.key, "count": b.count} for b in resp.country],
                    "city": [{"key": b.key, "count": b.count} for b in resp.city],
                }
            )
        except Exception as exc:
            logger.warning("get_facets tool error: %s", exc)
            return json.dumps({"error": str(exc)})

    def web_search_fn(query: str) -> str:
        try:
            if tavily_api_key:
                from tavily import TavilyClient  # lazy import — only needed when key is set

                client = TavilyClient(api_key=tavily_api_key)
                response = client.search(query, max_results=5, search_depth="basic")
                results = [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "content": r.get("content", "")[:500],
                    }
                    for r in response.get("results", [])
                ]
                return json.dumps(
                    {
                        "results": results,
                        "total": len(results),
                        "provider": "tavily",
                    }
                )

            from ddgs import DDGS  # lazy import — only needed when no Tavily key is set

            with DDGS() as client:
                response = list(client.text(query, max_results=5))
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", "") or r.get("url", ""),
                    "content": (
                        r.get("body", "") or r.get("snippet", "") or r.get("content", "")
                    )[:500],
                }
                for r in response
            ]
            return json.dumps(
                {
                    "results": results,
                    "total": len(results),
                    "provider": "duckduckgo",
                }
            )
        except ImportError as exc:
            logger.warning("web_search provider import error: %s", exc)
            return json.dumps(
                {
                    "error": "web search provider unavailable",
                    "results": [],
                }
            )
        except Exception as exc:
            logger.warning("web_search tool error: %s", exc)
            return json.dumps({"error": str(exc), "results": []})

    return [
        StructuredTool.from_function(
            func=hybrid_search_fn,
            name="hybrid_search",
            description=(
                "Search companies using hybrid BM25 + neural retrieval. "
                "Best for natural language queries like 'tech companies in California'. "
                "Returns up to 10 company records with a total count. "
                "If total < 3, consider using web_search for external data."
            ),
            args_schema=_SearchInput,
        ),
        StructuredTool.from_function(
            func=lexical_search_fn,
            name="lexical_search",
            description=(
                "Search companies using exact keyword (BM25-only) matching. "
                "Best for exact company name or domain lookups (e.g. from web search results). "
                "Returns up to 10 company records with a total count."
            ),
            args_schema=_SearchInput,
        ),
        StructuredTool.from_function(
            func=get_facets_fn,
            name="get_facets",
            description=(
                "Get aggregated counts for industry, company size, country, and city. "
                "Use this to understand what categories or locations are available in the dataset."
            ),
            args_schema=_FacetsInput,
        ),
        StructuredTool.from_function(
            func=web_search_fn,
            name="web_search",
            description=(
                "Search the web for external company information (e.g. recent funding rounds, news). "
                "Uses Tavily when configured, otherwise falls back to DuckDuckGo. "
                "ONLY use this when hybrid_search returns fewer than 3 results. "
                "Returns web article excerpts, not structured company records."
            ),
            args_schema=_WebSearchInput,
        ),
    ]
