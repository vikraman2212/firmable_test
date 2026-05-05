"""Startup verification and registration of named OpenSearch search templates.

Ensures the named Mustache templates required by Phase 3 exist in OpenSearch.
If they are missing (e.g., bootstrap script was not run), they are created inline
using the same DSL as 04-create-search-templates.sh.  This lets the API start
and serve requests even in environments where the bootstrap script has not run.

Templates managed here:
  firmable-search-v1  — BM25 scored search with fuzzy, synonym, and exact-boost clauses
  firmable-search-hybrid-v1 — hybrid BM25 + neural search using the search pipeline
  firmable-facets-v1  — aggregation-only (size=0) for facet count queries
"""

from __future__ import annotations

import logging

from opensearchpy import OpenSearch

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template source strings (Mustache)
#
# These are kept in sync with 04-create-search-templates.sh.
# See that script for detailed comments on query structure and design decisions.
# ---------------------------------------------------------------------------

_SEARCH_V1_SOURCE = """\
{
  "_source": {
    "excludes": ["company_vector"]
  },
  "explain": {{#explain}}true{{/explain}}{{^explain}}false{{/explain}},
  "from": {{from}},
  "size": {{size}},
  "query": {
    "bool": {
      "should": [
        {{#query_text}}
        {
          "multi_match": {
            "query": "{{query_text}}",
            "fields": [
              "company_semantic_text^5",
              "name^3",
              "industry^2",
              "city",
              "region",
              "country"
            ],
            "type": "best_fields",
            "analyzer": "stop"
          }
        },
        {
          "match": {
            "industry": {
              "query": "{{query_text}}",
              "analyzer": "synonym_analyzer",
              "boost": 3
            }
          }
        },
        {
          "match": {
            "name": {
              "query": "{{query_text}}",
              "analyzer": "stop",
              "fuzziness": "AUTO",
              "prefix_length": 2,
              "boost": 4
            }
          }
        },
        {
          "fuzzy": {
            "domain": {
              "value": "{{query_text}}",
              "fuzziness": 1,
              "prefix_length": 3,
              "boost": 3
            }
          }
        },
        {
          "term": {
            "name.keyword": {
              "value": "{{query_text}}",
              "boost": 6
            }
          }
        },
        {
          "term": {
            "domain": {
              "value": "{{query_text}}",
              "boost": 5
            }
          }
        }
        {{/query_text}}
      ],
      "filter": [
        {{#industry}}{"bool": {"should": [{{#industry}}{"match_phrase": {"industry": "{{.}}"}},{{/industry}}{"match_none": {}}], "minimum_should_match": 1}},{{/industry}}
        {{#size_range}}{"terms": {"size_range": {{#toJson}}size_range{{/toJson}}}},{{/size_range}}
        {{#country}}{"term": {"country": "{{country}}"}},{{/country}}
        {{#region}}{"term": {"region": "{{region}}"}},{{/region}}
        {{#city}}{"term": {"city": "{{city}}"}},{{/city}}
        {{#year_founded_gte}}{"range": {"year_founded": {"gte": {{year_founded_gte}}}}},{{/year_founded_gte}}
        {{#year_founded_lte}}{"range": {"year_founded": {"lte": {{year_founded_lte}}}}},{{/year_founded_lte}}
        {"match_all": {}}
      ],
      "minimum_should_match": {{#query_text}}1{{/query_text}}{{^query_text}}0{{/query_text}}
    }
  },
  "sort": [
    {{#query_text}}{"_score": {"order": "desc"}},{{/query_text}}
    {"name.keyword": {"order": "asc"}}
  ]
}
"""

_SEARCH_HYBRID_V1_SOURCE = """\
{
  "_source": {
    "excludes": ["company_vector"]
  },
  "explain": {{#explain}}true{{/explain}}{{^explain}}false{{/explain}},
  "from": {{from}},
  "size": {{size}},
  "query": {
    "hybrid": {
      "queries": [
        {
          "bool": {
            "should": [
              {
                "multi_match": {
                  "query": "{{query_text}}",
                  "fields": [
                    "company_semantic_text^5",
                    "name^3",
                    "industry^2",
                    "city",
                    "region",
                    "country"
                  ],
                  "type": "best_fields",
                  "analyzer": "stop"
                }
              },
              {
                "match": {
                  "industry": {
                    "query": "{{query_text}}",
                    "analyzer": "synonym_analyzer",
                    "boost": 3
                  }
                }
              },
              {
                "match": {
                  "name": {
                    "query": "{{query_text}}",
                    "analyzer": "stop",
                    "fuzziness": "AUTO",
                    "prefix_length": 2,
                    "boost": 4
                  }
                }
              },
              {
                "fuzzy": {
                  "domain": {
                    "value": "{{query_text}}",
                    "fuzziness": 1,
                    "prefix_length": 3,
                    "boost": 3
                  }
                }
              },
              {
                "term": {
                  "name.keyword": {
                    "value": "{{query_text}}",
                    "boost": 6
                  }
                }
              },
              {
                "term": {
                  "domain": {
                    "value": "{{query_text}}",
                    "boost": 5
                  }
                }
              }
            ],
            "minimum_should_match": 1
          }
        },
        {
          "neural": {
            "company_vector": {
              "query_text": "{{query_text}}",
              "model_id": "{{model_id}}",
              "k": {{neural_k}}
            }
          }
        }
      ],
      "filter": {
        "bool": {
          "must": [
            {{#industry}}{"bool": {"should": [{{#industry}}{"match_phrase": {"industry": "{{.}}"}},{{/industry}}{"match_none": {}}], "minimum_should_match": 1}},{{/industry}}
            {{#size_range}}{"terms": {"size_range": {{#toJson}}size_range{{/toJson}}}},{{/size_range}}
            {{#country}}{"term": {"country": "{{country}}"}},{{/country}}
            {{#region}}{"term": {"region": "{{region}}"}},{{/region}}
            {{#city}}{"term": {"city": "{{city}}"}},{{/city}}
            {{#year_founded_gte}}{"range": {"year_founded": {"gte": {{year_founded_gte}}}}},{{/year_founded_gte}}
            {{#year_founded_lte}}{"range": {"year_founded": {"lte": {{year_founded_lte}}}}},{{/year_founded_lte}}
            {"match_all": {}}
          ]
        }
      }
    }
  },
  "sort": [
    {"_score": {"order": "desc"}}
  ]
}
"""

_FACETS_V1_SOURCE = """\
{
  "_source": {
    "excludes": ["company_vector"]
  },
  "explain": false,
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        {{#industry}}{"bool": {"should": [{{#industry}}{"match_phrase": {"industry": "{{.}}"}},{{/industry}}{"match_none": {}}], "minimum_should_match": 1}},{{/industry}}
        {{#size_range}}{"terms": {"size_range": {{#toJson}}size_range{{/toJson}}}},{{/size_range}}
        {{#country}}{"term": {"country": "{{country}}"}},{{/country}}
        {{#region}}{"term": {"region": "{{region}}"}},{{/region}}
        {{#city}}{"term": {"city": "{{city}}"}},{{/city}}
        {{#year_founded_gte}}{"range": {"year_founded": {"gte": {{year_founded_gte}}}}},{{/year_founded_gte}}
        {{#year_founded_lte}}{"range": {"year_founded": {"lte": {{year_founded_lte}}}}},{{/year_founded_lte}}
        {"match_all": {}}
      ]
    }
  },
  "aggs": {
    "by_industry":     {"terms": {"field": "industry.keyword", "size": 20}},
    "by_size_range":   {"terms": {"field": "size_range",       "size": 20}},
    "by_country":      {"terms": {"field": "country",          "size": 30}},
    "by_city":         {"terms": {"field": "city",             "size": 30}},
    "by_year_founded": {"terms": {"field": "year_founded",     "size": 50}}
  }
}
"""

_TEMPLATES: dict[str, str] = {
    "firmable-search-v1": _SEARCH_V1_SOURCE,
    "firmable-search-hybrid-v1": _SEARCH_HYBRID_V1_SOURCE,
    "firmable-facets-v1": _FACETS_V1_SOURCE,
}


def _template_exists(client: OpenSearch, name: str) -> bool:
    try:
        client.get_script(id=name)
        return True
    except Exception:
        return False


def _register_template(client: OpenSearch, name: str, source: str) -> None:
    client.put_script(
        id=name,
        body={"script": {"lang": "mustache", "source": source}},
    )


def ensure_search_templates(client: OpenSearch) -> None:
    """Verify named search templates exist in OpenSearch; create any that are missing.

    Called once during API lifespan startup.  Logs a warning (does NOT raise)
    on connectivity failures so the process can start and serve /health even
    when OpenSearch is temporarily unreachable.  The /readiness probe will
    surface the connectivity problem.
    """
    from opensearchpy.exceptions import TransportError

    for name, source in _TEMPLATES.items():
        try:
            existed = _template_exists(client, name)
            _register_template(client, name, source)
            if existed:
                logger.debug("Search template '%s' updated", name)
            else:
                logger.info("Search template '%s' registered", name)
        except (TransportError, Exception) as exc:
            logger.warning(
                "Could not verify/register template '%s' (OpenSearch unavailable at startup): %s",
                name,
                exc,
            )
