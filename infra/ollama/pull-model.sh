#!/bin/bash

set -euo pipefail

# Pulls the configured Ollama model into the running Ollama container.
# Model name is configurable via OLLAMA_MODEL (default: gemma3:4b).
# Container name is configurable via OLLAMA_CONTAINER (default: firmable-ollama).

OLLAMA_MODEL="${OLLAMA_MODEL:-gemma3:4b}"
OLLAMA_CONTAINER="${OLLAMA_CONTAINER:-firmable-ollama}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command '$1' is not installed"
    exit 1
  fi
}

require_command docker

echo "Pulling Ollama model '${OLLAMA_MODEL}' into container '${OLLAMA_CONTAINER}'..."

if ! docker ps --format '{{.Names}}' | grep -q "^${OLLAMA_CONTAINER}$"; then
  echo "Error: container '${OLLAMA_CONTAINER}' is not running"
  exit 1
fi

docker exec "${OLLAMA_CONTAINER}" ollama pull "${OLLAMA_MODEL}"

echo "Model '${OLLAMA_MODEL}' pulled successfully"
