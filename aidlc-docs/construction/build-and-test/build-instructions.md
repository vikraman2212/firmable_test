# Build Instructions

## Prerequisites

- **Build Tool**: `uv` for Python dependency management, Docker Compose for container builds
- **Dependencies**: Docker, Docker Compose, Python 3.11+, `uv`, `bash`, `curl`, `jq`, Node.js (used for static JS syntax validation)
- **Python package workflow**: use `uv` commands for environment sync and execution; do not use ad hoc `pip install` steps for this repository
- **Environment Variables**:
  - `OPENSEARCH_URL` defaults to `http://localhost:9200`
  - `ENV_FILE` defaults to `.env`
  - `EMBEDDING_MODEL_ID` is written into `.env` by `make infra-up` or `make bootstrap-model`
  - `TAG_INDEX_NAME` defaults to `company_tags`
- **System Requirements**:
  - macOS or Linux with Docker Desktop or Docker Engine
  - At least 8 GB RAM available to Docker because OpenSearch is configured with a 4 GB heap
  - Enough disk for the OpenSearch data volume, Ollama model cache, and staged company data

## Build Steps

### 1. Install Dependencies

```bash
uv sync --dev
```

Use `uv sync --dev` as the canonical dependency-install step for this repo.

### 2. Configure Environment

```bash
cp .env.example .env 2>/dev/null || true
make compose-config
```

If `.env` does not already contain `EMBEDDING_MODEL_ID`, run `make infra-up` once so the bootstrap flow writes it automatically.

### 3. Build All Units

```bash
docker compose -f infra/docker-compose.yml build api
make script-check
```

For a full local stack build plus bootstrap:

```bash
make infra-up
```

### 4. Verify Build Success

- **Expected Output**:
  - `docker compose ... build api` completes without Docker build failures
  - `make script-check` returns exit code `0`
  - `make infra-up` starts OpenSearch, Dashboards, Ollama, and the API service and creates the search and tag runtime artifacts
- **Build Artifacts**:
  - Python virtual environment under `.venv/`
  - Docker image for `firmable-api`
  - OpenSearch runtime artifacts created by bootstrap scripts
  - Tag index `company_tags` in the local OpenSearch cluster
- **Common Warnings**:
  - Large OpenSearch startup time on cold Docker boots is expected
  - `file:///` loading of the static page will fail the `/facets` request because the API is not serving the page in that mode

## Troubleshooting

### Build Fails with Dependency Errors

- **Cause**: `uv` lockfile drift, missing local tools, or Docker not running
- **Solution**:
  1. Confirm `uv --version` and `docker --version`
  2. Re-run `uv sync --dev`
  3. Start Docker Desktop or Docker Engine
  4. Retry `make compose-config` and `docker compose -f infra/docker-compose.yml build api`

### Build Fails with Bootstrap Errors

- **Cause**: OpenSearch not healthy yet, missing `jq` or `curl`, or stale Docker volumes
- **Solution**:
  1. Run `make check-tools`
  2. Check `make infra-logs`
  3. Retry `make infra-up`
  4. If the cluster is corrupted locally, run `make infra-reset` and then `make infra-up`
