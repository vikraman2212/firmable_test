#!/bin/bash

set -euo pipefail

# This script sets up the OpenSearch ML pipeline for the Firmable local stack.

OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9200}"
MODEL_GROUP_NAME="${MODEL_GROUP_NAME:-huggingface/sentence-transformers/all-MiniLM-L12-v2}"
MODEL_VERSION="${MODEL_VERSION:-1.0.2}"
MODEL_DESCRIPTION="${MODEL_DESCRIPTION:-Sentence transformer model for generating text embeddings.}"
PIPELINE_NAME="${PIPELINE_NAME:-rfp-description-embedding-pipeline}"
SOURCE_FIELD="${SOURCE_FIELD:-description}"
TARGET_FIELD="${TARGET_FIELD:-description_vector}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command '$1' is not installed"
    exit 1
  fi
}

require_command curl
require_command jq

echo "Waiting for OpenSearch to be ready at ${OPENSEARCH_URL}..."
until curl -fsS "${OPENSEARCH_URL}/_cluster/health" | grep -q '"status":"green"'; do
  echo "Waiting for OpenSearch cluster to be ready..."
  sleep 5
done
echo "OpenSearch is ready"

echo "Registering model group..."
register_response=$(curl -fsS -X POST "${OPENSEARCH_URL}/_plugins/_ml/model_groups/_register" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"${MODEL_GROUP_NAME}\",
    \"description\": \"A model group for local models\"
  }")

echo "Model group registration response: ${register_response}"

if echo "${register_response}" | grep -q "already being used by a model group with ID"; then
  MODEL_GROUP_ID=$(echo "${register_response}" | sed -n 's/.*ID: \([^.]*\)\..*/\1/p')
  echo "Using existing model group with ID: ${MODEL_GROUP_ID}"
else
  MODEL_GROUP_ID=$(echo "${register_response}" | jq -r '.model_group_id')
  if [[ "${MODEL_GROUP_ID}" == "null" || -z "${MODEL_GROUP_ID}" ]]; then
    echo "Error: Could not get model group ID. Response was: ${register_response}"
    exit 1
  fi
  echo "Got new model group ID: ${MODEL_GROUP_ID}"
fi

if [[ -z "${MODEL_GROUP_ID}" ]]; then
  echo "Error: Could not obtain a valid model group ID"
  exit 1
fi

echo "Verifying model group ${MODEL_GROUP_ID} exists..."
verify_response=$(curl -fsS "${OPENSEARCH_URL}/_plugins/_ml/model_groups/${MODEL_GROUP_ID}")
if echo "${verify_response}" | grep -q "resource_not_found_exception"; then
  echo "Error: Model group ${MODEL_GROUP_ID} not found. Attempting to register a new model group..."

  register_response=$(curl -fsS -X POST "${OPENSEARCH_URL}/_plugins/_ml/model_groups/_register" \
    -H "Content-Type: application/json" \
    -d "{
      \"name\": \"${MODEL_GROUP_NAME}-new\",
      \"description\": \"A model group for local models\"
    }")

  MODEL_GROUP_ID=$(echo "${register_response}" | jq -r '.model_group_id')
  if [[ "${MODEL_GROUP_ID}" == "null" || -z "${MODEL_GROUP_ID}" ]]; then
    echo "Error: Failed to register new model group. Response was: ${register_response}"
    exit 1
  fi
  echo "Successfully registered new model group with ID: ${MODEL_GROUP_ID}"

  verify_response=$(curl -fsS "${OPENSEARCH_URL}/_plugins/_ml/model_groups/${MODEL_GROUP_ID}")
fi
echo "Model group verification response: ${verify_response}"

echo "Proceeding with model registration using model group ID: ${MODEL_GROUP_ID}"

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

echo "Registering model with payload: ${model_payload}"

model_response=$(curl -fsS -X POST "${OPENSEARCH_URL}/_plugins/_ml/models/_register" \
  -H "Content-Type: application/json" \
  -d "${model_payload}")

echo "Model registration response: ${model_response}"

MODEL_TASK_ID=$(echo "${model_response}" | jq -r '.task_id')
if [[ "${MODEL_TASK_ID}" == "null" || -z "${MODEL_TASK_ID}" ]]; then
  echo "Failed to get model registration task ID. Response was: ${model_response}"
  exit 1
fi

echo "Model registration task ID: ${MODEL_TASK_ID}"

echo "Waiting for model registration to complete..."
while true; do
  task_response=$(curl -fsS "${OPENSEARCH_URL}/_plugins/_ml/tasks/${MODEL_TASK_ID}")
  state=$(echo "${task_response}" | jq -r '.state')

  if [[ "${state}" == "COMPLETED" ]]; then
    MODEL_ID=$(echo "${task_response}" | jq -r '.model_id')
    echo "Model registration completed successfully with ID: ${MODEL_ID}"
    break
  elif [[ "${state}" == "FAILED" ]]; then
    echo "Model registration failed. Response was: ${task_response}"
    exit 1
  fi

  echo "Model registration state: ${state}. Waiting..."
  sleep 2
done

if [[ -z "${MODEL_ID:-}" ]]; then
  echo "Error: Could not obtain a valid model ID"
  exit 1
fi

echo "Deploying model with ID: ${MODEL_ID}"

deploy_response=$(curl -fsS -X POST "${OPENSEARCH_URL}/_plugins/_ml/models/${MODEL_ID}/_deploy" \
  -H "Content-Type: application/json")

echo "Model deployment response: ${deploy_response}"

DEPLOY_TASK_ID=$(echo "${deploy_response}" | jq -r '.task_id')
if [[ "${DEPLOY_TASK_ID}" == "null" || -z "${DEPLOY_TASK_ID}" ]]; then
  echo "Failed to get model deployment task ID. Response was: ${deploy_response}"
  exit 1
fi

echo "Waiting for model deployment to complete..."
while true; do
  task_response=$(curl -fsS "${OPENSEARCH_URL}/_plugins/_ml/tasks/${DEPLOY_TASK_ID}")
  state=$(echo "${task_response}" | jq -r '.state')

  if [[ "${state}" == "COMPLETED" ]]; then
    echo "Model deployment completed successfully"
    break
  elif [[ "${state}" == "FAILED" ]]; then
    echo "Model deployment failed. Response was: ${task_response}"
    exit 1
  fi

  echo "Model deployment state: ${state}. Waiting..."
  sleep 2
done

echo "Creating ingest pipeline..."

pipeline_payload=$(jq -n \
  --arg model_id "${MODEL_ID}" \
  --arg source_field "${SOURCE_FIELD}" \
  --arg target_field "${TARGET_FIELD}" \
  '{
    description: "Text embedding pipeline for RFP documents",
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

echo "Creating pipeline with payload: ${pipeline_payload}"

pipeline_response=$(curl -fsS -X PUT "${OPENSEARCH_URL}/_ingest/pipeline/${PIPELINE_NAME}" \
  -H "Content-Type: application/json" \
  -d "${pipeline_payload}")

echo "Pipeline creation response: ${pipeline_response}"

if echo "${pipeline_response}" | grep -q '"acknowledged":true'; then
  echo "Pipeline created successfully"
else
  echo "Failed to create pipeline. Response was: ${pipeline_response}"
  exit 1
fi

if [[ -f "${SCRIPT_DIR}/07-create-tag-index.sh" ]]; then
  OPENSEARCH_URL="${OPENSEARCH_URL}" TAG_INDEX_NAME="${TAG_INDEX_NAME:-company_tags}" bash "${SCRIPT_DIR}/07-create-tag-index.sh"
fi