#!/bin/bash

set -euo pipefail

OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9200}"
TAG_INDEX_NAME="${TAG_INDEX_NAME:-company_tags}"

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

if curl -fsS "${OPENSEARCH_URL}/${TAG_INDEX_NAME}" >/dev/null 2>&1; then
  echo "Tag index '${TAG_INDEX_NAME}' already exists"
  exit 0
fi

payload=$(cat <<JSON
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "tag_name_display": {"type": "keyword"},
      "tag_name_normalized": {"type": "keyword"},
      "company_id": {"type": "keyword"},
      "user_id": {"type": "keyword"},
      "created_at": {"type": "date"}
    }
  }
}
JSON
)

echo "Creating tag index '${TAG_INDEX_NAME}'..."
response=$(curl -fsS -X PUT "${OPENSEARCH_URL}/${TAG_INDEX_NAME}" \
  -H "Content-Type: application/json" \
  -d "${payload}")

echo "Tag index response: ${response}"
if ! echo "${response}" | jq -e '.acknowledged == true' >/dev/null 2>&1; then
  echo "Error: failed to create tag index '${TAG_INDEX_NAME}'"
  exit 1
fi

echo "Tag index '${TAG_INDEX_NAME}' created"