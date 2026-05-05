#!/bin/bash

set -euo pipefail

# Deploys the embedding model registered by 01-register-model.sh.
# Pipeline and index template creation is handled by 03-create-pipelines.sh.
#
# Reads MODEL_ID from ${STATE_DIR}/model_id (written by 01-register-model.sh).

OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9200}"
STATE_DIR="${STATE_DIR:-/tmp/firmable-ml}"

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
# Deploy model (idempotent — skip if already DEPLOYED)
# ---------------------------------------------------------------------------
echo "Checking model state for ${MODEL_ID}..."

model_info=$(curl -fsS "${OPENSEARCH_URL}/_plugins/_ml/models/${MODEL_ID}")
model_state=$(echo "${model_info}" | jq -r '.model_state // empty')

if [[ "${model_state}" == "DEPLOYED" ]]; then
  echo "Model ${MODEL_ID} is already DEPLOYED — skipping deploy step"
else
  echo "Deploying model ${MODEL_ID} (current state: ${model_state:-unknown})..."

  deploy_response=$(curl -fsS -X POST "${OPENSEARCH_URL}/_plugins/_ml/models/${MODEL_ID}/_deploy" \
    -H "Content-Type: application/json")

  echo "Deploy response: ${deploy_response}"

  DEPLOY_TASK_ID=$(echo "${deploy_response}" | jq -r '.task_id')
  if [[ "${DEPLOY_TASK_ID}" == "null" || -z "${DEPLOY_TASK_ID}" ]]; then
    echo "Error: Could not get deploy task ID. Response: ${deploy_response}"
    exit 1
  fi

  echo "Waiting for deploy task ${DEPLOY_TASK_ID}..."
  while true; do
    task_response=$(curl -fsS "${OPENSEARCH_URL}/_plugins/_ml/tasks/${DEPLOY_TASK_ID}")
    state=$(echo "${task_response}" | jq -r '.state')

    if [[ "${state}" == "COMPLETED" ]]; then
      echo "Model deployed successfully"
      break
    elif [[ "${state}" == "FAILED" ]]; then
      echo "Error: Model deployment failed. Response: ${task_response}"
      exit 1
    fi

    echo "  State: ${state} — waiting..."
    sleep 2
  done
fi

echo "Model deployment complete — run 03-create-pipelines.sh next"
