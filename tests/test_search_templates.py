"""Validate template DSL content by reading the canonical shell script."""

import re
from pathlib import Path

_SCRIPT_PATH = Path(__file__).parent.parent / "infra/opensearch/bootstrap/04-create-search-templates.sh"
_SCRIPT_SOURCE = _SCRIPT_PATH.read_text()

# Each template is assigned via: VAR=$(cat << 'TEMPLATE' ... TEMPLATE\n)
# Pattern: VARNAME=$(cat << 'TEMPLATE'\nBODY\nTEMPLATE\n)
_TEMPLATE_BLOCKS = re.findall(
    r"^(\w+)=\$\(cat << 'TEMPLATE'\n([\s\S]+?)\nTEMPLATE\n\)",
    _SCRIPT_SOURCE,
    re.MULTILINE,
)
_TEMPLATE_MAP = {name: body for name, body in _TEMPLATE_BLOCKS}

_SEARCH_V1_SOURCE = _TEMPLATE_MAP.get("SEARCH_TEMPLATE", "")
_SEARCH_HYBRID_V1_SOURCE = _TEMPLATE_MAP.get("HYBRID_SEARCH_TEMPLATE", "")
_FACETS_V1_SOURCE = _TEMPLATE_MAP.get("FACETS_TEMPLATE", "")


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