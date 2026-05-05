"""Unit tests for app.search.query_planner — pure functions, no I/O."""

import pytest

from app.api.schemas import FacetsRequest, SearchRequest
from app.search.query_planner import SearchPlan, build_facets_plan, build_search_plan


# ---------------------------------------------------------------------------
# build_search_plan
# ---------------------------------------------------------------------------

def test_empty_request_defaults():
    req = SearchRequest()
    plan = build_search_plan(req)
    assert plan.query_text is None
    assert plan.filters == {}
    assert plan.from_ == 0
    assert plan.size == 20
    assert plan.explain is False


def test_query_text_trimmed():
    req = SearchRequest(query="  acme corp  ")
    plan = build_search_plan(req)
    assert plan.query_text == "acme corp"


def test_blank_query_becomes_none():
    req = SearchRequest(query="   ")
    plan = build_search_plan(req)
    assert plan.query_text is None


def test_founded_year_phrase_becomes_exact_year_filter():
    req = SearchRequest(query="insurance companies started during 1980")
    plan = build_search_plan(req)
    assert plan.query_text == "insurance"
    assert plan.filters["year_founded_gte"] == 1980
    assert plan.filters["year_founded_lte"] == 1980


def test_explicit_year_filters_override_query_extraction():
    req = SearchRequest(
        query="insurance companies started during 1980",
        year_founded_gte=1975,
        year_founded_lte=1985,
    )
    plan = build_search_plan(req)
    assert plan.query_text == "insurance"
    assert plan.filters["year_founded_gte"] == 1975
    assert plan.filters["year_founded_lte"] == 1985


def test_filters_extracted_correctly():
    req = SearchRequest(
        industry=["Software", "Fintech"],
        size_range=[" 51 - 200 "],
        country="United States",
        city="San Francisco",
        year_founded_gte=2010,
        year_founded_lte=2020,
    )
    plan = build_search_plan(req)
    assert plan.filters["industry"] == ["software", "fintech"]
    assert plan.filters["size_range"] == ["51 - 200"]
    assert plan.filters["country"] == "united states"
    assert plan.filters["city"] == "san francisco"
    assert plan.filters["year_founded_gte"] == 2010
    assert plan.filters["year_founded_lte"] == 2020


def test_industry_passed_through_raw():
    """Synonym expansion is delegated to synonym_analyzer at query time — no Python expansion."""
    req = SearchRequest(industry=["Information Technology"])
    plan = build_search_plan(req)
    assert plan.filters["industry"] == ["information technology"]


def test_blank_filter_values_omitted():
    req = SearchRequest(industry=["", "  ", "Software"], country="  ", city="Austin")
    plan = build_search_plan(req)
    # blank industry entries stripped; normalized industry kept
    assert plan.filters["industry"] == ["software"]
    # blank country omitted entirely
    assert "country" not in plan.filters
    # valid city normalized
    assert plan.filters["city"] == "austin"


def test_pagination_from_calculation():
    req = SearchRequest(page=3, page_size=10)
    plan = build_search_plan(req)
    assert plan.from_ == 20
    assert plan.size == 10


def test_to_params_includes_pagination():
    req = SearchRequest(query="test", page=2, page_size=5)
    params = build_search_plan(req).to_params()
    assert params["from"] == 5
    assert params["size"] == 5
    assert params["query_text"] == "test"
    assert params["explain"] is False


def test_to_params_omits_query_text_when_none():
    req = SearchRequest()
    params = build_search_plan(req).to_params()
    assert "query_text" not in params


def test_to_params_includes_filters():
    req = SearchRequest(country="Germany")
    params = build_search_plan(req).to_params()
    assert params["country"] == "germany"


def test_to_params_allows_explain_override():
    req = SearchRequest(query="test", explain=True)
    params = build_search_plan(req).to_params()
    assert params["explain"] is True


# ---------------------------------------------------------------------------
# build_facets_plan
# ---------------------------------------------------------------------------

def test_facets_plan_size_zero():
    req = FacetsRequest()
    plan = build_facets_plan(req)
    assert plan.size == 0
    assert plan.from_ == 0
    assert plan.query_text is None


def test_facets_plan_filters_extracted():
    req = FacetsRequest(country="United Kingdom", size_range=[" 51 - 200 "])
    plan = build_facets_plan(req)
    assert plan.filters["country"] == "united kingdom"
    assert plan.filters["size_range"] == ["51 - 200"]


def test_facets_plan_to_params_size_zero():
    req = FacetsRequest()
    params = build_facets_plan(req).to_params()
    assert params["size"] == 0
    assert params["from"] == 0
