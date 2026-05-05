from app.search.templates import _FACETS_V1_SOURCE, _SEARCH_HYBRID_V1_SOURCE, _SEARCH_V1_SOURCE


_INDUSTRY_FILTER_SNIPPET = '"bool": {"should": [{{#industry}}{"match_phrase": {"industry": "{{.}}"}},{{/industry}}{"match_none": {}}], "minimum_should_match": 1}'


def test_search_templates_use_analyzed_industry_filter():
    assert _INDUSTRY_FILTER_SNIPPET in _SEARCH_V1_SOURCE
    assert _INDUSTRY_FILTER_SNIPPET in _SEARCH_HYBRID_V1_SOURCE
    assert _INDUSTRY_FILTER_SNIPPET in _FACETS_V1_SOURCE
    assert '"industry.keyword"' not in _SEARCH_V1_SOURCE
    assert '"industry.keyword"' not in _SEARCH_HYBRID_V1_SOURCE


def test_search_templates_include_region_filter():
    region_clause = '{{#region}}{"term": {"region": "{{region}}"}},{{/region}}'
    assert region_clause in _SEARCH_V1_SOURCE
    assert region_clause in _SEARCH_HYBRID_V1_SOURCE
    assert region_clause in _FACETS_V1_SOURCE