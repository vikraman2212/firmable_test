#!/bin/bash

set -euo pipefail

# Registers the embedding model group and model in OpenSearch ML Commons.
# Writes the resulting MODEL_ID to a state file so that 02-deploy-model.sh
# can deploy it without re-registering.
#
# State file location: ${STATE_DIR}/model_id  (default: /tmp/firmable-ml)

OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9200}"
MODEL_GROUP_NAME="${MODEL_GROUP_NAME:-huggingface/sentence-transformers/all-MiniLM-L12-v2}"
MODEL_VERSION="${MODEL_VERSION:-1.0.2}"
MODEL_DESCRIPTION="${MODEL_DESCRIPTION:-Sentence transformer model for generating text embeddings.}"
STATE_DIR="${STATE_DIR:-/tmp/firmable-ml}"
MAX_WAIT="${MAX_WAIT:-120}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command '$1' is not installed"
    exit 1
  fi
}

require_command curl
require_command jq

mkdir -p "${STATE_DIR}"

# ---------------------------------------------------------------------------
# Wait for cluster health (green or yellow)
# ---------------------------------------------------------------------------
echo "Waiting for OpenSearch cluster health at ${OPENSEARCH_URL} (max ${MAX_WAIT}s)..."

elapsed=0
interval=5
until curl -fsS "${OPENSEARCH_URL}/_cluster/health" \
      | jq -e '.status == "green" or .status == "yellow"' >/dev/null 2>&1; do
  if [[ $elapsed -ge $MAX_WAIT ]]; then
    echo "Error: OpenSearch did not become healthy within ${MAX_WAIT}s"
    exit 1
  fi
  echo "  Not ready yet (${elapsed}s elapsed), retrying in ${interval}s..."
  sleep $interval
  elapsed=$((elapsed + interval))
done

echo "OpenSearch cluster is healthy"

# ---------------------------------------------------------------------------
# Register model group (idempotent — search before creating)
# ---------------------------------------------------------------------------
echo "Checking for existing model group '${MODEL_GROUP_NAME}'..."

existing_group=$(curl -fsS -X POST "${OPENSEARCH_URL}/_plugins/_ml/model_groups/_search" \
  -H "Content-Type: application/json" \
  -d "{\"query\":{\"term\":{\"name.keyword\":\"${MODEL_GROUP_NAME}\"}},\"size\":1}")

MODEL_GROUP_ID=$(echo "${existing_group}" | jq -r '.hits.hits[0]._id // empty')

if [[ -n "${MODEL_GROUP_ID}" ]]; then
  echo "Reusing existing model group: ${MODEL_GROUP_ID}"
else
  echo "Registering new model group '${MODEL_GROUP_NAME}'..."
  register_response=$(curl -fsS -X POST "${OPENSEARCH_URL}/_plugins/_ml/model_groups/_register" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"${MODEL_GROUP_NAME}\",\"description\":\"A model group for local embedding models\"}")
  echo "Model group response: ${register_response}"
  MODEL_GROUP_ID=$(echo "${register_response}" | jq -r '.model_group_id')
  if [[ "${MODEL_GROUP_ID}" == "null" || -z "${MODEL_GROUP_ID}" ]]; then
    echo "Error: Could not obtain model group ID. Response: ${register_response}"
    exit 1
  fi
  echo "Registered new model group: ${MODEL_GROUP_ID}"
fi

# ---------------------------------------------------------------------------
# Register model (idempotent — check state file, then verify liveness)
# ---------------------------------------------------------------------------
echo "Checking for existing model '${MODEL_GROUP_NAME}' v${MODEL_VERSION}..."

MODEL_ID=""
STATE_FILE="${STATE_DIR}/model_id"

if [[ -f "${STATE_FILE}" ]]; then
  cached_id=$(cat "${STATE_FILE}")
  if [[ -n "${cached_id}" ]]; then
    # Verify the model still exists in OpenSearch
    http_code=$(curl -o /dev/null -w "%{http_code}" -sS \
      "${OPENSEARCH_URL}/_plugins/_ml/models/${cached_id}")
    if [[ "${http_code}" == "200" ]]; then
      MODEL_ID="${cached_id}"
      echo "Reusing existing model: ${MODEL_ID}"
    else
      echo "Cached model ${cached_id} is gone (HTTP ${http_code}) — registering fresh"
    fi
  fi
fi

if [[ -z "${MODEL_ID}" ]]; then
  echo "Registering model '${MODEL_GROUP_NAME}' v${MODEL_VERSION}..."

  model_payload=$(jq -n \
    --arg name "${MODEL_GROUP_NAME}" \
    --arg version "${MODEL_VERSION}" \
    --arg model_group_id "${MODEL_GROUP_ID}" \
    --arg desc "${MODEL_DESCRIPTION}" \
    '{
      name: $name,
      version: $version,
      model_group_id: $model_group_id,
      description: $desc,
      model_format: "TORCH_SCRIPT",
      model_config: {
        model_type: "bert",
        embedding_dimension: 384,
        framework_type: "sentence_transformers",
        pooling_mode: "MEAN",
        normalize_results: true
      }
    }')

  model_response=$(curl -fsS -X POST "${OPENSEARCH_URL}/_plugins/_ml/models/_register" \
    -H "Content-Type: application/json" \
    -d "${model_payload}")

  echo "Model registration response: ${model_response}"

  MODEL_TASK_ID=$(echo "${model_response}" | jq -r '.task_id')
  if [[ "${MODEL_TASK_ID}" == "null" || -z "${MODEL_TASK_ID}" ]]; then
    echo "Error: Could not get model registration task ID. Response: ${model_response}"
    exit 1
  fi

  echo "Waiting for model registration task ${MODEL_TASK_ID}..."
  while true; do
    task_response=$(curl -fsS "${OPENSEARCH_URL}/_plugins/_ml/tasks/${MODEL_TASK_ID}")
    state=$(echo "${task_response}" | jq -r '.state')

    if [[ "${state}" == "COMPLETED" ]]; then
      MODEL_ID=$(echo "${task_response}" | jq -r '.model_id')
      echo "Model registered with ID: ${MODEL_ID}"
      break
    elif [[ "${state}" == "FAILED" ]]; then
      echo "Error: Model registration failed. Response: ${task_response}"
      exit 1
    fi

    echo "  State: ${state} — waiting..."
    sleep 2
  done

  if [[ -z "${MODEL_ID:-}" ]]; then
    echo "Error: Could not obtain model ID"
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# Write MODEL_ID to state file
# ---------------------------------------------------------------------------
echo "${MODEL_ID}" > "${STATE_DIR}/model_id"
echo "MODEL_ID written to ${STATE_DIR}/model_id"
