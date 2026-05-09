SHELL := /bin/bash

.DEFAULT_GOAL := help

COMPOSE_FILE ?= infra/docker-compose.yml
DOCKER_COMPOSE ?= docker compose -f $(COMPOSE_FILE)
REGISTER_MODEL_SCRIPT ?= infra/opensearch/bootstrap/01-register-model.sh
DEPLOY_MODEL_SCRIPT ?= infra/opensearch/bootstrap/02-deploy-model.sh
CREATE_PIPELINES_SCRIPT ?= infra/opensearch/bootstrap/03-create-pipelines.sh
CREATE_SEARCH_TEMPLATES_SCRIPT ?= infra/opensearch/bootstrap/04-create-search-templates.sh
CREATE_LOG_TEMPLATES_SCRIPT ?= infra/opensearch/bootstrap/05-create-log-templates.sh
WRITE_MODEL_ENV_SCRIPT ?= infra/opensearch/bootstrap/06-write-model-env.sh
CREATE_TAG_INDEX_SCRIPT ?= infra/opensearch/bootstrap/07-create-tag-index.sh
OLLAMA_PULL_SCRIPT ?= infra/ollama/pull-model.sh
OPENSEARCH_URL ?= http://localhost:9200
OLLAMA_CONTAINER ?= firmable-ollama
INGESTION_CONFIG ?= config/ingestion.toml
ENV_FILE ?= .env
CSV ?=
PARQUET ?=
SOFT_DELETE ?= false
PYTHON ?= uv run python

.PHONY: help check-tools compose-config infra-up infra-down infra-reset infra-ps infra-logs opensearch-health script-check bootstrap-model bootstrap validate ci-validate ollama-pull seed sync test dev-setup

help: ## Show available developer and CI targets
	@awk 'BEGIN {FS = ":.*## "; printf "Available targets:\n"} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

check-tools: ## Verify required local tooling is installed
	@command -v docker >/dev/null 2>&1 || { echo "docker is required"; exit 1; }
	@command -v bash >/dev/null 2>&1 || { echo "bash is required"; exit 1; }
	@command -v curl >/dev/null 2>&1 || { echo "curl is required"; exit 1; }
	@command -v jq >/dev/null 2>&1 || { echo "jq is required"; exit 1; }

compose-config: ## Validate the Docker Compose configuration
	@$(DOCKER_COMPOSE) config >/dev/null

infra-up: ## Start the local OpenSearch infrastructure and run ML bootstrap (model, pipelines, index template)
	@$(DOCKER_COMPOSE) up -d --build
	@bash $(REGISTER_MODEL_SCRIPT)
	@bash $(DEPLOY_MODEL_SCRIPT)
	@bash $(CREATE_PIPELINES_SCRIPT)
	@bash $(CREATE_SEARCH_TEMPLATES_SCRIPT)
	@bash $(CREATE_TAG_INDEX_SCRIPT)
	@bash $(CREATE_LOG_TEMPLATES_SCRIPT)
	@ENV_FILE=$(ENV_FILE) bash $(WRITE_MODEL_ENV_SCRIPT)

infra-down: ## Stop the local infrastructure and keep volumes
	@$(DOCKER_COMPOSE) down --remove-orphans

infra-reset: ## Stop the local infrastructure and remove volumes
	@$(DOCKER_COMPOSE) down -v --remove-orphans

infra-ps: ## List running services in the local infrastructure stack
	@$(DOCKER_COMPOSE) ps

infra-logs: ## Tail logs from the local infrastructure stack
	@$(DOCKER_COMPOSE) logs -f --tail=200

opensearch-health: ## Print the current OpenSearch cluster health payload
	@curl -fsS $(OPENSEARCH_URL)/_cluster/health | jq .

script-check: ## Validate the OpenSearch bootstrap script syntax
	@bash -n $(REGISTER_MODEL_SCRIPT)
	@bash -n $(DEPLOY_MODEL_SCRIPT)
	@bash -n $(CREATE_PIPELINES_SCRIPT)
	@bash -n $(CREATE_SEARCH_TEMPLATES_SCRIPT)
	@bash -n $(CREATE_LOG_TEMPLATES_SCRIPT)
	@bash -n $(WRITE_MODEL_ENV_SCRIPT)
	@bash -n $(CREATE_TAG_INDEX_SCRIPT)
	@bash -n $(OLLAMA_PULL_SCRIPT)

bootstrap-model: ## Register and deploy the embedding model, create pipelines and index template
	@bash $(REGISTER_MODEL_SCRIPT)
	@bash $(DEPLOY_MODEL_SCRIPT)
	@bash $(CREATE_PIPELINES_SCRIPT)
	@bash $(CREATE_SEARCH_TEMPLATES_SCRIPT)
	@bash $(CREATE_TAG_INDEX_SCRIPT)
	@ENV_FILE=$(ENV_FILE) bash $(WRITE_MODEL_ENV_SCRIPT)

bootstrap: check-tools compose-config infra-up ## Start infra and run the OpenSearch ML bootstrap flow

validate: compose-config script-check ## Run local validation checks for infra automation artifacts

ci-validate: compose-config script-check ## Run non-interactive checks suitable for GitHub Actions

ollama-pull: ## Pull the Ollama LLM model into the running container
	@bash $(OLLAMA_PULL_SCRIPT)

seed: ## Index companies using config/ingestion.toml (override with CSV=path or PARQUET=path)
	$(PYTHON) -m app.ingestion.seed --config $(INGESTION_CONFIG) $(if $(CSV),--csv $(CSV),) $(if $(PARQUET),--parquet $(PARQUET),)

sync: ## Incrementally re-sync companies using config/ingestion.toml
	$(PYTHON) -m app.ingestion.sync --config $(INGESTION_CONFIG) $(if $(PARQUET),--parquet $(PARQUET),) $(if $(filter true TRUE 1 yes YES,$(SOFT_DELETE)),--soft-delete,)

test: ## Run the test suite with pytest
	uv run pytest tests/ -v

dev-setup: infra-up ollama-pull ## One-shot local onboarding: start stack, pull model, run ML bootstrap

dev: ## Run the API locally with hot-reload — stops the docker API container first (UI at http://localhost:8000/ui)
	@$(DOCKER_COMPOSE) stop api 2>/dev/null || true
	$(PYTHON) -m uvicorn app.api.main:app --host 0.0.0.0 --reload --port 8000