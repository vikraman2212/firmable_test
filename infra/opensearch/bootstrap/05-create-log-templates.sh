#!/bin/bash

set -euo pipefail

# Creates OpenSearch index templates for structured log indices.
#
# Templates registered:
#   logs-api-template       → matches logs-api-*
#   logs-ingestion-template → matches logs-ingestion-*
#
# Indices are created daily by the application logging handler:
#   logs-api-MMDD       (e.g. logs-api-0505)
#   logs-ingestion-MMDD
#
# Settings:
#   - 1 shard, 0 replicas (single-node dev)
#   - dynamic mapping enabled (log fields vary)
#   - @timestamp mapped as date for Dashboards time filters
#   - level, service, logger mapped as keywords for aggregations

OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9200}"

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
# Shared template body factory
# ---------------------------------------------------------------------------
log_template_body() {
  local pattern="$1"
  jq -n --arg pattern "$pattern" '{
    "index_patterns": [$pattern],
    "template": {
      "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "index.refresh_interval": "10s"
      },
      "mappings": {
        "dynamic": true,
        "properties": {
          "@timestamp":  { "type": "date" },
          "level":       { "type": "keyword" },
          "service":     { "type": "keyword" },
          "logger":      { "type": "keyword" },
          "message":     { "type": "text" },
          "path":        { "type": "keyword" },
          "method":      { "type": "keyword" },
          "status_code": { "type": "integer" },
          "duration_ms": { "type": "integer" },
          "took_ms":     { "type": "integer" },
          "total":       { "type": "long" },
          "query":       { "type": "text" },
          "request_id":  { "type": "keyword" },
          "exception":   { "type": "text" }
        }
      }
    }
  }'
}

# ---------------------------------------------------------------------------
# Register logs-api-template
# ---------------------------------------------------------------------------
echo "Registering index template 'logs-api-template'..."
api_body=$(log_template_body "logs-api-*")
api_response=$(curl -fsS -X PUT "${OPENSEARCH_URL}/_index_template/logs-api-template" \
  -H "Content-Type: application/json" \
  -d "${api_body}")
echo "Response: ${api_response}"
if ! echo "${api_response}" | jq -e '.acknowledged == true' >/dev/null 2>&1; then
  echo "Error: Failed to register logs-api-template"
  exit 1
fi
echo "logs-api-template registered"

# ---------------------------------------------------------------------------
# Register logs-ingestion-template
# ---------------------------------------------------------------------------
echo "Registering index template 'logs-ingestion-template'..."
ingestion_body=$(log_template_body "logs-ingestion-*")
ingestion_response=$(curl -fsS -X PUT "${OPENSEARCH_URL}/_index_template/logs-ingestion-template" \
  -H "Content-Type: application/json" \
  -d "${ingestion_body}")
echo "Response: ${ingestion_response}"
if ! echo "${ingestion_response}" | jq -e '.acknowledged == true' >/dev/null 2>&1; then
  echo "Error: Failed to register logs-ingestion-template"
  exit 1
fi
echo "logs-ingestion-template registered"

echo "Log index templates bootstrap complete"
