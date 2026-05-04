#!/bin/bash

set -euo pipefail

# Creates the ingest pipeline, applies the index template, and registers the
# search pipeline for hybrid BM25+kNN score blending.
#
# Depends on MODEL_ID written by 01-register-model.sh to the state file.
# The index template is loaded from app/search/index_template.json (relative to REPO_ROOT).
# The search pipeline payload is inlined below.

OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9200}"
INGEST_PIPELINE_NAME="${INGEST_PIPELINE_NAME:-firmable-description-embedding-pipeline}"
SEARCH_PIPELINE_NAME="${SEARCH_PIPELINE_NAME:-hybrid-search-pipeline}"
INDEX_TEMPLATE_NAME="${INDEX_TEMPLATE_NAME:-companies-template}"
SOURCE_FIELD="${SOURCE_FIELD:-company_semantic_text}"
TARGET_FIELD="${TARGET_FIELD:-company_vector}"
STATE_DIR="${STATE_DIR:-/tmp/firmable-ml}"
REPO_ROOT="${REPO_ROOT:-$PWD}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command '$1' is not installed"
    exit 1
  fi
}

require_command curl
require_command jq

# ---------------------------------------------------------------------------
# Read MODEL_ID from state file
# ---------------------------------------------------------------------------
STATE_FILE="${STATE_DIR}/model_id"
if [[ ! -f "${STATE_FILE}" ]]; then
  echo "Error: state file not found at ${STATE_FILE}"
  echo "Run 01-register-model.sh first"
  exit 1
fi

MODEL_ID=$(cat "${STATE_FILE}")
if [[ -z "${MODEL_ID}" ]]; then
  echo "Error: MODEL_ID in ${STATE_FILE} is empty"
  exit 1
fi

echo "Using MODEL_ID: ${MODEL_ID}"

# ---------------------------------------------------------------------------
# Verify JSON artifacts exist
# ---------------------------------------------------------------------------
INDEX_TEMPLATE_FILE="${REPO_ROOT}/app/search/index_template.json"

if [[ ! -f "${INDEX_TEMPLATE_FILE}" ]]; then
  echo "Error: required file not found: ${INDEX_TEMPLATE_FILE}"
  exit 1
fi

# ---------------------------------------------------------------------------
# Create ingest pipeline (text_embedding processor)
# ---------------------------------------------------------------------------
echo "Creating ingest pipeline '${INGEST_PIPELINE_NAME}'..."

ingest_payload=$(jq -n \
  --arg model_id "${MODEL_ID}" \
  --arg source_field "${SOURCE_FIELD}" \
  --arg target_field "${TARGET_FIELD}" \
  '{
    description: "Text embedding pipeline for company semantic text",
    processors: [
      {
        text_embedding: {
          model_id: $model_id,
          field_map: {
            ($source_field): $target_field
          }
        }
      }
    ]
  }')

ingest_response=$(curl -fsS -X PUT "${OPENSEARCH_URL}/_ingest/pipeline/${INGEST_PIPELINE_NAME}" \
  -H "Content-Type: application/json" \
  -d "${ingest_payload}")

echo "Ingest pipeline response: ${ingest_response}"

if ! echo "${ingest_response}" | jq -e '.acknowledged == true' >/dev/null 2>&1; then
  echo "Error: Failed to create ingest pipeline. Response: ${ingest_response}"
  exit 1
fi

echo "Ingest pipeline '${INGEST_PIPELINE_NAME}' created"

# ---------------------------------------------------------------------------
# Apply index template (strict mappings, knn_vector, synonym analyzer)
# ---------------------------------------------------------------------------
echo "Applying index template '${INDEX_TEMPLATE_NAME}'..."

template_response=$(curl -fsS -X PUT "${OPENSEARCH_URL}/_index_template/${INDEX_TEMPLATE_NAME}" \
  -H "Content-Type: application/json" \
  -d "@${INDEX_TEMPLATE_FILE}")

echo "Index template response: ${template_response}"

if ! echo "${template_response}" | jq -e '.acknowledged == true' >/dev/null 2>&1; then
  echo "Error: Failed to apply index template. Response: ${template_response}"
  exit 1
fi

echo "Index template '${INDEX_TEMPLATE_NAME}' applied"

# ---------------------------------------------------------------------------
# Create search pipeline (hybrid BM25+kNN normalization)
# ---------------------------------------------------------------------------
echo "Creating search pipeline '${SEARCH_PIPELINE_NAME}'..."

search_payload=$(jq -n '{
  "phase_results_processors": [
    {
      "normalization-processor": {
        "normalization": { "technique": "min_max" },
        "combination": {
          "technique": "arithmetic_mean",
          "parameters": { "weights": [0.3, 0.7] }
        }
      }
    }
  ]
}')

search_response=$(curl -fsS -X PUT "${OPENSEARCH_URL}/_search/pipeline/${SEARCH_PIPELINE_NAME}" \
  -H "Content-Type: application/json" \
  -d "${search_payload}")

echo "Search pipeline response: ${search_response}"

if ! echo "${search_response}" | jq -e '.acknowledged == true' >/dev/null 2>&1; then
  echo "Error: Failed to create search pipeline. Response: ${search_response}"
  exit 1
fi

echo "Search pipeline '${SEARCH_PIPELINE_NAME}' created"
echo "Bootstrap complete"
