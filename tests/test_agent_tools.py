"""Unit tests for app.agent.tools — SearchService and web providers are mocked."""

import json
import sys
import types
from unittest.mock import MagicMock

import pytest

from app.agent.tools import _LOW_RESULT_THRESHOLD, _search_response_to_json, make_search_tools
from app.api.schemas import CompanyResult, FacetBucket, FacetsResponse, SearchResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_service():
    svc = MagicMock()
    return svc


def _make_search_response(items=None, total=None):
    items = items or [
        CompanyResult(
            company_id="c1",
            name="Acme Corp",
            domain="acme.com",
            industry="Information Technology",
            country="United States",
            city="San Francisco",
            size_range="51 - 200",
            year_founded=2010,
        )
    ]
    return SearchResponse(
        items=items,
        total=total if total is not None else len(items),
        page=1,
        page_size=10,
        took_ms=12,
    )


def _make_facets_response():
    return FacetsResponse(
        industry=[FacetBucket(key="Information Technology", count=500)],
        size_range=[FacetBucket(key="51 - 200", count=200)],
        country=[FacetBucket(key="United States", count=1000)],
        city=[FacetBucket(key="San Francisco", count=100)],
    )


# ---------------------------------------------------------------------------
# make_search_tools
# ---------------------------------------------------------------------------

def test_make_search_tools_returns_four_tools():
    tools = make_search_tools(_mock_service())
    assert len(tools) == 4
    names = {t.name for t in tools}
    assert names == {"hybrid_search", "lexical_search", "get_facets", "web_search"}


def test_make_search_tools_descriptions_are_nonempty():
    tools = make_search_tools(_mock_service())
    for tool in tools:
        assert tool.description.strip()


# ---------------------------------------------------------------------------
# hybrid_search
# ---------------------------------------------------------------------------

def test_hybrid_search_returns_json_with_hits():
    svc = _mock_service()
    svc.search.return_value = _make_search_response()
    tools = {t.name: t for t in make_search_tools(svc)}

    result = json.loads(tools["hybrid_search"].run({"query": "tech companies"}))

    assert result["total"] == 1
    assert result["hits"][0]["name"] == "Acme Corp"
    svc.search.assert_called_once()


def test_hybrid_search_adds_note_when_few_results():
    svc = _mock_service()
    svc.search.return_value = _make_search_response(total=1)
    tools = {t.name: t for t in make_search_tools(svc)}

    result = json.loads(tools["hybrid_search"].run({"query": "very rare company"}))

    assert "note" in result
    assert result["total"] < _LOW_RESULT_THRESHOLD


def test_hybrid_search_returns_error_on_exception():
    svc = _mock_service()
    svc.search.side_effect = RuntimeError("OpenSearch down")
    tools = {t.name: t for t in make_search_tools(svc)}

    result = json.loads(tools["hybrid_search"].run({"query": "any"}))

    assert "error" in result
    assert result["total"] == 0


def test_hybrid_search_normalizes_blank_string_filters_to_none():
    svc = _mock_service()
    svc.search.return_value = _make_search_response()
    tools = {t.name: t for t in make_search_tools(svc)}

    result = json.loads(
        tools["hybrid_search"].run(
            {
                "query": "companies in melbourne",
                "city": "melbourne",
                "country": "",
                "industry": "",
                "region": "",
                "size_range": "",
            }
        )
    )

    assert result["total"] == 1
    req = svc.search.call_args.args[0]
    assert req.city == "melbourne"
    assert req.country is None
    assert req.industry is None
    assert req.region is None
    assert req.size_range is None


# ---------------------------------------------------------------------------
# lexical_search
# ---------------------------------------------------------------------------

def test_lexical_search_calls_search_lexical():
    svc = _mock_service()
    svc.search_lexical.return_value = _make_search_response()
    tools = {t.name: t for t in make_search_tools(svc)}

    result = json.loads(tools["lexical_search"].run({"query": "Stripe"}))

    assert result["total"] == 1
    svc.search_lexical.assert_called_once()
    svc.search.assert_not_called()


# ---------------------------------------------------------------------------
# get_facets
# ---------------------------------------------------------------------------

def test_get_facets_returns_aggregations():
    svc = _mock_service()
    svc.facets.return_value = _make_facets_response()
    tools = {t.name: t for t in make_search_tools(svc)}

    result = json.loads(tools["get_facets"].run({}))

    assert "industry" in result
    assert result["industry"][0]["key"] == "Information Technology"


def test_get_facets_returns_error_on_exception():
    svc = _mock_service()
    svc.facets.side_effect = RuntimeError("boom")
    tools = {t.name: t for t in make_search_tools(svc)}

    result = json.loads(tools["get_facets"].run({}))

    assert "error" in result


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------

def test_web_search_uses_duckduckgo_when_no_key(monkeypatch):
    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query, max_results):
            assert query == "Stripe fundraising"
            assert max_results == 5
            return [
                {
                    "title": "Stripe closes new funding round",
                    "href": "https://example.com/stripe",
                    "body": "Stripe raised new capital from investors.",
                }
            ]

    monkeypatch.setitem(sys.modules, "duckduckgo_search", types.SimpleNamespace(DDGS=FakeDDGS))

    tools = {t.name: t for t in make_search_tools(_mock_service(), tavily_api_key="")}

    result = json.loads(tools["web_search"].run({"query": "Stripe fundraising"}))

    assert result["provider"] == "duckduckgo"
    assert result["total"] == 1
    assert result["results"][0]["url"] == "https://example.com/stripe"


def test_web_search_uses_tavily_when_key_present(monkeypatch):
    class FakeTavilyClient:
        def __init__(self, api_key):
            assert api_key == "test-key"

        def search(self, query, max_results, search_depth):
            assert query == "Stripe fundraising"
            assert max_results == 5
            assert search_depth == "basic"
            return {
                "results": [
                    {
                        "title": "Stripe funding news",
                        "url": "https://example.com/tavily-stripe",
                        "content": "Tavily content",
                    }
                ]
            }

    monkeypatch.setitem(sys.modules, "tavily", types.SimpleNamespace(TavilyClient=FakeTavilyClient))

    tools = {t.name: t for t in make_search_tools(_mock_service(), tavily_api_key="test-key")}

    result = json.loads(tools["web_search"].run({"query": "Stripe fundraising"}))

    assert result["provider"] == "tavily"
    assert result["total"] == 1
    assert result["results"][0]["url"] == "https://example.com/tavily-stripe"


# ---------------------------------------------------------------------------
# _search_response_to_json
# ---------------------------------------------------------------------------

def test_search_response_to_json_no_note_above_threshold():
    resp = _make_search_response(total=10)
    data = json.loads(_search_response_to_json(resp))
    assert "note" not in data


def test_search_response_to_json_has_note_below_threshold():
    resp = _make_search_response(total=0)
    data = json.loads(_search_response_to_json(resp))
    assert "note" in data
