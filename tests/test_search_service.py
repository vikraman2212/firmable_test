"""Unit tests for app.search.service.SearchService — OpenSearch client is mocked."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from app.api.schemas import FacetsRequest, SearchRequest
from app.search.service import SearchService


def _make_service():
    client = MagicMock()
    return SearchService(client=client, index_name="companies"), client


# ---------------------------------------------------------------------------
# SearchService.search()
# ---------------------------------------------------------------------------

def _search_response(hits=None, total=0, took=5):
    return {
        "took": took,
        "hits": {
            "total": {"value": total, "relation": "eq"},
            "hits": hits or [],
        },
    }


def _make_hit(id_="abc123", **source_fields):
    base = {
        "name": "Acme Corp",
        "domain": "acme.com",
        "industry": "software",
        "size_range": "11-50",
        "city": "Austin",
        "region": "TX",
        "country": "US",
        "year_founded": 2010,
        "current_employee_estimate": 30,
    }
    base.update(source_fields)
    return {"_id": id_, "_score": 1.5, "_source": base}


def test_search_calls_correct_template():
    svc, client = _make_service()
    client.search_template.return_value = _search_response()

    with patch("app.settings.Settings.effective_embedding_model_id", new_callable=PropertyMock, return_value="model-123"):
        svc.search(SearchRequest(query="acme"))

    args, kwargs = client.search_template.call_args
    body = kwargs.get("body") or args[0]
    assert body["id"] == "firmable-search-hybrid-v1"
    assert body["params"]["query_text"] == "acme"
    assert body["params"]["model_id"] == "model-123"
    assert kwargs["params"]["search_pipeline"] == "hybrid-search-pipeline"
    assert body["params"]["explain"] is False


def test_search_passes_filter_params():
    svc, client = _make_service()
    client.search_template.return_value = _search_response()

    svc.search(SearchRequest(country="United States", city="New York", industry=["Fintech"]))

    body = client.search_template.call_args.kwargs.get("body") or client.search_template.call_args[0][0]
    assert body["params"]["country"] == "united states"
    assert body["params"]["city"] == "new york"
    assert body["params"]["industry"] == ["fintech"]


def test_search_uses_keyword_template_when_query_missing():
    svc, client = _make_service()
    client.search_template.return_value = _search_response()

    svc.search(SearchRequest(country="United States"))

    body = client.search_template.call_args.kwargs.get("body") or client.search_template.call_args[0][0]
    assert body["id"] == "firmable-search-v1"
    assert client.search_template.call_args.kwargs.get("params") is None


def test_search_passes_explain_override():
    svc, client = _make_service()
    client.search_template.return_value = _search_response(
        hits=[{"_id": "id1", "_score": 1.5, "_source": {"name": "Acme Corp"}, "_explanation": {"value": 1.5}}],
        total=1,
    )

    resp = svc.search(SearchRequest(query="acme", explain=True))

    body = client.search_template.call_args.kwargs.get("body") or client.search_template.call_args[0][0]
    assert body["params"]["explain"] is True
    assert resp.items[0].explanation == {"value": 1.5}


def test_search_maps_hits_to_company_results():
    svc, client = _make_service()
    client.search_template.return_value = _search_response(
        hits=[_make_hit("id1", name="Acme Corp", domain="acme.com")],
        total=1,
    )

    resp = svc.search(SearchRequest(query="acme"))

    assert len(resp.items) == 1
    assert resp.items[0].company_id == "id1"
    assert resp.items[0].name == "Acme Corp"
    assert resp.items[0].domain == "acme.com"


def test_search_assembles_correct_pagination():
    svc, client = _make_service()
    client.search_template.return_value = _search_response(total=42)

    resp = svc.search(SearchRequest(page=3, page_size=10))

    assert resp.total == 42
    assert resp.page == 3
    assert resp.page_size == 10


def test_search_took_ms_populated():
    svc, client = _make_service()
    client.search_template.return_value = _search_response()

    resp = svc.search(SearchRequest())

    assert isinstance(resp.took_ms, int)
    assert resp.took_ms >= 0


def test_search_handles_missing_optional_source_fields():
    svc, client = _make_service()
    hit = {"_id": "x", "_score": 1.0, "_source": {"name": "Minimal Co"}}
    client.search_template.return_value = _search_response(hits=[hit], total=1)

    resp = svc.search(SearchRequest())

    item = resp.items[0]
    assert item.name == "Minimal Co"
    assert item.domain is None
    assert item.industry is None
    assert item.country is None


# ---------------------------------------------------------------------------
# SearchService.facets()
# ---------------------------------------------------------------------------

def _facets_response(aggs=None):
    return {
        "took": 2,
        "hits": {"total": {"value": 0, "relation": "eq"}, "hits": []},
        "aggregations": aggs or {},
    }


def test_facets_calls_correct_template():
    svc, client = _make_service()
    client.search_template.return_value = _facets_response()

    svc.facets(FacetsRequest())

    body = client.search_template.call_args.kwargs.get("body") or client.search_template.call_args[0][0]
    assert body["id"] == "firmable-facets-v1"


def test_facets_maps_aggregation_buckets():
    svc, client = _make_service()
    aggs = {
        "by_industry": {"buckets": [{"key": "software", "doc_count": 100}]},
        "by_size_range": {"buckets": [{"key": "11-50", "doc_count": 40}]},
        "by_country": {"buckets": [{"key": "US", "doc_count": 300}]},
        "by_city": {"buckets": [{"key": "Austin", "doc_count": 25}]},
        "by_year_founded": {"buckets": [{"key": 2015, "doc_count": 12}]},
    }
    client.search_template.return_value = _facets_response(aggs=aggs)

    resp = svc.facets(FacetsRequest())

    assert resp.industry[0].key == "software"
    assert resp.industry[0].count == 100
    assert resp.size_range[0].key == "11-50"
    assert resp.country[0].key == "US"
    assert resp.city[0].key == "Austin"
    assert resp.year_founded[0].key == "2015"  # int key serialised to str


def test_facets_returns_empty_tags():
    svc, client = _make_service()
    client.search_template.return_value = _facets_response()

    resp = svc.facets(FacetsRequest())

    assert resp.tags == []


def test_facets_handles_missing_aggregations():
    svc, client = _make_service()
    client.search_template.return_value = _facets_response(aggs={})

    resp = svc.facets(FacetsRequest())

    assert resp.industry == []
    assert resp.size_range == []
    assert resp.country == []
    assert resp.city == []
    assert resp.year_founded == []
