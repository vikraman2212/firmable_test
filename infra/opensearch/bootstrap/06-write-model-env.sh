#!/bin/bash

set -euo pipefail

# Sync the current OpenSearch embedding model ID into the local .env file so
# the API keeps using the same deployed model after restarts.

STATE_DIR="${STATE_DIR:-/tmp/firmable-ml}"
STATE_FILE="${STATE_DIR}/model_id"
ENV_FILE="${ENV_FILE:-.env}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command '$1' is not installed"
    exit 1
  fi
}

require_command awk
require_command mktemp

if [[ ! -f "${STATE_FILE}" ]]; then
  echo "Error: state file not found at ${STATE_FILE}"
  echo "Run 01-register-model.sh first"
  exit 1
fi

MODEL_ID="$(tr -d '[:space:]' < "${STATE_FILE}")"
if [[ -z "${MODEL_ID}" ]]; then
  echo "Error: MODEL_ID in ${STATE_FILE} is empty"
  exit 1
fi

touch "${ENV_FILE}"

tmp_file="$(mktemp)"
awk -v line="EMBEDDING_MODEL_ID=${MODEL_ID}" '
  BEGIN { updated = 0 }
  /^EMBEDDING_MODEL_ID=/ {
    if (!updated) {
      print line
      updated = 1
    }
    next
  }
  { print }
  END {
    if (!updated) {
      print line
    }
  }
' "${ENV_FILE}" > "${tmp_file}"

mv "${tmp_file}" "${ENV_FILE}"
echo "EMBEDDING_MODEL_ID written to ${ENV_FILE}"