# Firmable

Firmable is a company search system built on FastAPI, OpenSearch, a staged ingestion pipeline, and an optional Ollama-backed AI search lane. The UI is served from the API at `/ui`, deterministic search works without Ollama, and the agent path degrades back to normal search when the LLM is unavailable.

## What This Repo Runs

- OpenSearch for indexing, filtering, facets, and hybrid retrieval.
- A FastAPI service for `/search`, `/facets`, `/agent/search`, tagging, health, readiness, and the static UI.
- An Ollama container for local AI-assisted search.
- A seed/sync pipeline that stages CSV data into Parquet and indexes it into OpenSearch.

## Prerequisites

- Docker with Compose support.
- `uv` for local Python execution.
- `curl` and `jq` for health checks and bootstrap scripts.
- Enough memory for OpenSearch. The local compose file sets `OPENSEARCH_JAVA_OPTS=-Xms4g -Xmx4g`, so a machine with less available RAM will struggle.
- The People Data Labs CSV extracted locally as `data/companies_sorted.csv`, or another CSV/Parquet path you pass to the seed commands.

If you need the dataset zip, the repo includes `download_dataset.sh`, but it only downloads the archive. You still need to extract the CSV and place it at `data/companies_sorted.csv` or point the seed command at the extracted file explicitly.

## Quick Start

```bash
uv sync --dev
make infra-up
OLLAMA_MODEL=llama3.2:3b make ollama-pull
make seed
```

Then open `http://127.0.0.1:8000/ui`.

Use these checks if something looks off:

```bash
make infra-ps
make opensearch-health
curl -fsS http://127.0.0.1:8000/health | jq .
curl -fsS http://127.0.0.1:8000/readiness | jq .
```

## 1. Infrastructure

Bring up the full local stack:

```bash
make infra-up
```

That target does more than `docker compose up`:

- Starts `opensearch`, `opensearch-dashboards`, `ollama`, and `api`.
- Registers and deploys the local embedding model in OpenSearch ML Commons.
- Creates the ingest pipeline, search templates, log templates, and tag index.
- Writes the current embedding model ID to `/tmp/firmable-ml/model_id` and syncs it into `.env` as `EMBEDDING_MODEL_ID`.

Useful follow-up commands:

```bash
make infra-ps
make infra-logs
make infra-down
make infra-reset
```

What to look for:

- `make infra-ps` should show healthy `opensearch`, `ollama`, and `api` containers.
- `make opensearch-health` should return a `green` or `yellow` cluster status.
- `http://127.0.0.1:5601` should open OpenSearch Dashboards.
- `http://127.0.0.1:8000/health` should return `{"status":"ok"}`.

Caveats:

- The first `make infra-up` can take a few minutes because model registration and deployment wait on OpenSearch ML tasks.
- The API depends on `/tmp/firmable-ml/model_id` for hybrid search model resolution. If you wipe `/tmp/firmable-ml` or skip bootstrap, hybrid search will not have a valid embedding model.
- `make infra-reset` removes Docker volumes, which means you lose the local OpenSearch data and Ollama model cache.

## 2. API

You have two supported ways to run the API.

### Option A: Use the Docker API started by `make infra-up`

After infrastructure is up, the API is already available at `http://127.0.0.1:8000`.

Smoke checks:

```bash
curl -fsS http://127.0.0.1:8000/health | jq .
curl -fsS http://127.0.0.1:8000/readiness | jq .
```

### Option B: Run the API locally with hot reload

```bash
uv sync --dev
make dev
```

`make dev` intentionally stops the Docker `api` container first, then runs:

```bash
uv run python -m uvicorn app.api.main:app --reload --port 8000
```

What to look for:

- The local API should bind to port `8000` and serve the UI at `http://127.0.0.1:8000/ui`.
- `/readiness` should return `200` only after OpenSearch is up and the `companies` search target exists.

Caveats:

- Local API runs read `.env`; the Docker API container does not rely on your host `.env` file in the same way. Keep that difference in mind when you change runtime settings.
- If port `8000` is already occupied, the local dev server will fail to start.
- Deterministic search does not need Ollama. Agent search does.

## 3. Seeding

The default ingestion config lives in `config/ingestion.toml` and expects this CSV path:

```text
data/companies_sorted.csv
```

Seed using the default config:

```bash
make seed
```

Override the source file if needed:

```bash
make seed CSV=/absolute/path/to/companies_sorted.csv
```

If you already staged data and want to seed from Parquet instead:

```bash
make seed PARQUET=data/staged/latest.parquet
```

For incremental re-indexing from staged Parquet:

```bash
make sync
```

What to look for:

- The seed flow stages data into Parquet, creates or reuses the `companies` index, and bulk-indexes documents in batches.
- `data/staged/latest.parquet` should point to the most recent staged artifact.
- `data/staged/dead_letter_<timestamp>.jsonl` contains rejected rows if normalization or validation skipped any records.
- `curl -fsS http://127.0.0.1:8000/readiness | jq .` should return a ready search target after a successful seed.

Caveats:

- `make seed` assumes OpenSearch is already running.
- Full dataset runs are materially slower than local subset experiments and will use real disk space under `data/staged/`.
- If the CSV is missing or extracted to a different filename, the seed command fails fast.
- Dead-letter output is expected when the source dataset contains malformed rows. Check the validation summary before assuming the run is bad.

## 4. Run AI Search

The agent endpoint is `POST /agent/search` and streams SSE events.

Before using it, pull the same Ollama model the API expects. The safest current command is:

```bash
OLLAMA_MODEL=llama3.2:3b make ollama-pull
```

Then test the AI path directly:

```bash
curl -N -X POST http://127.0.0.1:8000/agent/search \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"query": "tech companies in california"}'
```

You can also use the browser UI at `http://127.0.0.1:8000/ui` and enable the agent search mode there.

What to look for:

- SSE output should include `tool_call`, `tool_result`, `result`, and `done` events.
- A healthy agent run usually returns `fallback_used: false`.
- If Ollama is unavailable, the endpoint should still answer with a deterministic fallback path instead of failing the whole request.

Caveats:

- There is currently a model-name mismatch between the API defaults and the Ollama pull script defaults. The API defaults to `llama3.2:3b`, while `infra/ollama/pull-model.sh` defaults to `gemma3:4b`. If you do not override `OLLAMA_MODEL`, you can pull a model the API is not asking for.
- For local `make dev`, the repo `.env` currently points `OLLAMA_BASE_URL` at `http://localhost:11434`, which is correct for the host machine talking to the Docker Ollama container.
- Tavily-backed web search is optional. If `TAVILY_API_KEY` is unset, the agent falls back to DuckDuckGo for external lookups.

## Development Settings

Runtime configuration is defined in `app/settings.py`. The most relevant values during local development are:

| Variable                 | Purpose                                         | Typical local value                                                       |
| ------------------------ | ----------------------------------------------- | ------------------------------------------------------------------------- |
| `OPENSEARCH_URL`         | OpenSearch endpoint for the API                 | `http://localhost:9200` for local dev, `http://opensearch:9200` in Docker |
| `EMBEDDING_MODEL_ID`     | Explicit embedding model ID for hybrid search   | Written automatically into `.env` by `make infra-up`                      |
| `OLLAMA_BASE_URL`        | Ollama endpoint used by the agent               | `http://localhost:11434` for local dev                                    |
| `OLLAMA_MODEL`           | Ollama model name used by the agent             | `llama3.2:3b` unless you standardize on another model                     |
| `TAVILY_API_KEY`         | Optional key for external web search enrichment | Empty unless configured                                                   |
| `LOG_OPENSEARCH_ENABLED` | Send structured logs to OpenSearch              | `true` in the Docker API service                                          |
| `LOG_LEVEL`              | API log verbosity                               | `INFO` by default                                                         |

Recommended local workflow:

1. Run `make infra-up` once to bootstrap OpenSearch and write `EMBEDDING_MODEL_ID`.
2. Run `OLLAMA_MODEL=llama3.2:3b make ollama-pull` so the LLM runtime and API agree on the model.
3. Use `make dev` for normal API iteration and keep the rest of the stack in Docker.

## Common Issues

### `/readiness` returns 503

Usually one of these is true:

- OpenSearch is not healthy yet.
- The `companies` index has not been seeded.
- The API is pointed at the wrong OpenSearch URL for the current run mode.

### AI search falls back unexpectedly

Check:

- `docker compose -f infra/docker-compose.yml logs ollama --tail=100`
- Whether the pulled Ollama model matches the API model setting.
- Whether you are running the API in Docker or locally, because the expected Ollama base URL differs.

### Hybrid search behaves oddly after cleanup

Check that `/tmp/firmable-ml/model_id` exists and that `.env` still contains a current `EMBEDDING_MODEL_ID`. Re-running `make infra-up` or `make bootstrap-model` repairs that state.

## Useful Commands

```bash
make help
make test
make infra-logs
make opensearch-health
make seed CSV=/absolute/path/to/companies_sorted.csv
make sync SOFT_DELETE=true
```
