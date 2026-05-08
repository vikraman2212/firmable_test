#!/bin/bash

set -euo pipefail

# Registers the named Mustache search templates used by the Firmable search API.
#
# Templates registered:
#   firmable-search-v1          — BM25-only scored search
#   firmable-search-hybrid-v1   — hybrid BM25 + neural scored search
#   firmable-facets-v1          — aggregation-only facet counts
# This script is idempotent — re-running overwrites templates with the same DSL.

OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9200}"
SEARCH_TEMPLATE_NAME="${SEARCH_TEMPLATE_NAME:-firmable-search-v1}"
HYBRID_SEARCH_TEMPLATE_NAME="${HYBRID_SEARCH_TEMPLATE_NAME:-firmable-search-hybrid-v1}"
FACETS_TEMPLATE_NAME="${FACETS_TEMPLATE_NAME:-firmable-facets-v1}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command '$1' is not installed"
    exit 1
  fi
}

require_command curl
require_command jq

echo "Waiting for OpenSearch to be ready at ${OPENSEARCH_URL}..."
until curl -fsS "${OPENSEARCH_URL}/_cluster/health" | grep -q '"status":"'; do
  echo "Waiting for OpenSearch..."
  sleep 5
done
echo "OpenSearch is ready"


# ---------------------------------------------------------------------------
# firmable-search-v1 — BM25 scored search template
#
# Query structure:
#   bool.should  — scored clauses, only rendered when query_text is present
#     1. multi_match across semantic text, name, industry, location fields
#     2. match on industry with synonym_analyzer for synonym expansion
#     3. match on name (text field) with fuzziness AUTO
#     4. fuzzy on domain (keyword field) — match+fuzziness is invalid on keywords
#     5. term on name.keyword with high exact-match boost
#     6. term on domain with high exact-match boost
#   bool.filter  — structured filter clauses, not score-driving
#     {"match_all": {}} sentinel at the end absorbs trailing commas from
#     conditional blocks, keeping the JSON valid in all filter combinations.
#   minimum_should_match — 1 when query_text present, 0 (match-all) otherwise
# ---------------------------------------------------------------------------
SEARCH_TEMPLATE=$(cat << 'TEMPLATE'
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
            "type": "best_fields"
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
TEMPLATE
)

echo "Registering search template '${SEARCH_TEMPLATE_NAME}'..."
search_payload=$(jq -n --arg source "${SEARCH_TEMPLATE}" \
  '{"script": {"lang": "mustache", "source": $source}}')

search_response=$(curl -fsS -X PUT "${OPENSEARCH_URL}/_scripts/${SEARCH_TEMPLATE_NAME}" \
  -H "Content-Type: application/json" \
  -d "${search_payload}")

echo "Search template response: ${search_response}"

if ! echo "${search_response}" | jq -e '.acknowledged == true' >/dev/null 2>&1; then
  echo "Error: Failed to register search template. Response: ${search_response}"
  exit 1
fi

echo "Search template '${SEARCH_TEMPLATE_NAME}' registered"

# ---------------------------------------------------------------------------
# firmable-search-hybrid-v1 — hybrid BM25 + neural search template
#
# Query structure:
#   query.hybrid.queries[0] — existing BM25 clauses
#   query.hybrid.queries[1] — neural query against company_vector
#   query.hybrid.filter     — structured filters applied across both subqueries
#   search_pipeline         — hybrid-search-pipeline for score normalization
# ---------------------------------------------------------------------------
HYBRID_SEARCH_TEMPLATE=$(cat << 'TEMPLATE'
{
  "_source": {
    "excludes": ["company_vector"]
  },
  "explain": {{#explain}}true{{/explain}}{{^explain}}false{{/explain}},
  "from": {{from}},
  "size": {{size}},
  "query": {
    "hybrid": {
      "pagination_depth": {{pagination_depth}},
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
TEMPLATE
)

echo "Registering hybrid search template '${HYBRID_SEARCH_TEMPLATE_NAME}'..."
hybrid_search_payload=$(jq -n --arg source "${HYBRID_SEARCH_TEMPLATE}" \
  '{"script": {"lang": "mustache", "source": $source}}')

hybrid_search_response=$(curl -fsS -X PUT "${OPENSEARCH_URL}/_scripts/${HYBRID_SEARCH_TEMPLATE_NAME}" \
  -H "Content-Type: application/json" \
  -d "${hybrid_search_payload}")

echo "Hybrid search template response: ${hybrid_search_response}"

if ! echo "${hybrid_search_response}" | jq -e '.acknowledged == true' >/dev/null 2>&1; then
  echo "Error: Failed to register hybrid search template. Response: ${hybrid_search_response}"
  exit 1
fi

echo "Hybrid search template '${HYBRID_SEARCH_TEMPLATE_NAME}' registered"

# ---------------------------------------------------------------------------
# firmable-facets-v1 — aggregation-only template (size=0, no scored hits)
#
# Uses the same filter clause pattern as firmable-search-v1.
# Aggregations:
#   by_industry     — top 20 terms on industry.keyword
#   by_size_range   — top 20 terms on size_range
#   by_country      — top 30 terms on country
#   by_city         — top 30 terms on city
#   by_year_founded — top 50 terms on year_founded (integer)
# ---------------------------------------------------------------------------
FACETS_TEMPLATE=$(cat << 'TEMPLATE'
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
    "by_industry": {
      "terms": {"field": "industry.keyword", "size": 20}
    },
    "by_size_range": {
      "terms": {"field": "size_range", "size": 20}
    },
    "by_country": {
      "terms": {"field": "country", "size": 30}
    },
    "by_city": {
      "terms": {"field": "city", "size": 30}
    },
    "by_year_founded": {
      "terms": {"field": "year_founded", "size": 50}
    }
  }
}
TEMPLATE
)

echo "Registering facets template '${FACETS_TEMPLATE_NAME}'..."
facets_payload=$(jq -n --arg source "${FACETS_TEMPLATE}" \
  '{"script": {"lang": "mustache", "source": $source}}')

facets_response=$(curl -fsS -X PUT "${OPENSEARCH_URL}/_scripts/${FACETS_TEMPLATE_NAME}" \
  -H "Content-Type: application/json" \
  -d "${facets_payload}")

echo "Facets template response: ${facets_response}"

if ! echo "${facets_response}" | jq -e '.acknowledged == true' >/dev/null 2>&1; then
  echo "Error: Failed to register facets template. Response: ${facets_response}"
  exit 1
fi

echo "Facets template '${FACETS_TEMPLATE_NAME}' registered"
echo "Search templates bootstrap complete"
