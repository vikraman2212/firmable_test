# Firmable Search System — Architecture

## Overview

Firmable is a staged company-search system over the People Data Labs company dataset. The current delivery path is deterministic search first: the browser submits an explicit search request to the FastAPI service, the API normalizes free text plus filters into a stable search plan, and OpenSearch executes named search or aggregation templates using those normalized parameters.

This repository already has the ingestion, OpenSearch bootstrap, and static UI foundation in place. Phase 3 is the primary delivery target for the API search surface. Phase 5 remains an enhancement lane for intelligent search with Ollama. Based on the current feasibility review, the recommended Phase 5 approach is LangChain plus ChatOllama on top of the deterministic search layer, not OpenSearch-native agentic search.

Two rules keep the architecture aligned with the take-home scope:

- The UI path must succeed without Ollama.
- OpenSearch query execution should use stored runtime templates created during bootstrap or API initialization rather than assembling ad hoc DSL bodies inside request handlers.

---

## Component Map

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENT LAYER                                  │
│                                                                         │
│  Browser (web/index.html + web/app.js)                                  │
│  ─ explicit submit only: Enter or Apply Filters                         │
│  ─ no debounce, no live-search-as-you-type                              │
│  ─ current UI path calls POST /search                                   │
│  ─ facet wiring is planned for POST /facets                             │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ HTTP
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          API LAYER (FastAPI)                            │
│                                                                         │
│  app/api/main.py                                                        │
│  ─ GET  /health        process liveness                                 │
│  ─ GET  /readiness     OpenSearch connectivity                          │
│  ─ POST /search        deterministic search lane                        │
│  ─ POST /facets        deterministic aggregation lane (planned P3)      │
│  ─ POST /agent/search  optional intelligent lane (candidate P5)         │
│                                                                         │
│  Search lane responsibilities                                           │
│  ─ validate request payload                                             │
│  ─ normalize query + filters into template parameters                   │
│  ─ execute named OpenSearch templates via SearchService                 │
│  ─ shape results into API-safe response models                          │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ OpenSearch HTTP
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    SEARCH BACKEND (OpenSearch 3.1)                      │
│                                                                         │
│  Companies index template                                               │
│  ─ strict mappings                                                      │
│  ─ synonym analyzer on industry                                         │
│  ─ knn_vector field for company_vector                                  │
│  ─ default ingest pipeline for embeddings                               │
│                                                                         │
│  Bootstrap-managed runtime artifacts                                    │
│  ─ ingest pipeline: firmable-description-embedding-pipeline             │
│  ─ search pipeline: hybrid-search-pipeline                              │
│  ─ search templates: deterministic search + facets (planned extension)  │
│                                                                         │
│  ML Commons                                                             │
│  ─ local model registration and deployment                              │
│  ─ all-MiniLM-L12-v2 embeddings for company_semantic_text               │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                       INTELLIGENCE LANE (PHASE 5)                       │
│                                                                         │
│  Recommended path: LangChain + ChatOllama                               │
│  ─ wraps deterministic search and facet tools                           │
│  ─ keeps /agent/search off the critical UI path                         │
│  ─ falls back to deterministic search when Ollama is unavailable        │
│                                                                         │
│  Explicitly not the baseline path                                       │
│  ─ direct Ollama-only orchestration is possible but more brittle        │
│  ─ OpenSearch-native agentic search is not a take-home target because   │
│    it would require a higher-risk platform upgrade and extra setup      │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                          INGESTION LAYER                                │
│                                                                         │
│  Seed flow                                                              │
│  ─ CSV read and normalization                                           │
│  ─ deterministic company_id generation                                  │
│  ─ semantic-text derivation from normalized attributes                  │
│  ─ staged Parquet output + dead-letter artifacts                        │
│  ─ bulk indexing through the default ingest pipeline                    │
│                                                                         │
│  Sync flow                                                              │
│  ─ idempotent upserts by company_id                                     │
│  ─ optional soft-delete handling                                        │
│  ─ reuse of staged, validated document contract                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Request Flow

### Deterministic UI search (current baseline)

```
Browser
  │
  ▼
POST /search  {query, filters}
  │
  ▼
Deterministic request normalization
  ├─ extract structured filters from request payload
  ├─ expand configured industry synonyms where needed
  └─ produce stable template parameters
  │
  ▼
Named OpenSearch search template
  ├─ search free text across the supported fields
  ├─ give the strongest semantic weighting to company_semantic_text
  ├─ boost exact or near-exact company-name and domain matches
  └─ apply structured filters as filter clauses
  │
  ▼
OpenSearch companies-read alias
  │
  ▼
SearchResponse {items, total, took_ms}
```

### Deterministic facets (planned Phase 3 companion lane)

```
Browser or API caller
  │
  ▼
POST /facets  {query, filters}
  │
  ▼
Deterministic request normalization
  │
  ▼
Named OpenSearch aggregation template
  ├─ reuses the same active query and filters
  ├─ returns industry, size, geography, and year coverage
  └─ leaves tag aggregation pluggable until Phase 6 decides storage
  │
  ▼
FacetResponse {counts only, no hits}
```

### Intelligent search (candidate Phase 5 lane)

```
API caller
  │
  ▼
POST /agent/search  {query, filters}
  │
  ▼
Ollama readiness probe
  │
  ├─ unavailable ───────────────► deterministic /search path
  │
  ▼
LangChain + ChatOllama agent
  ├─ decides whether to call lexical search, hybrid search, or facets
  ├─ delegates to deterministic OpenSearch execution tools
  └─ returns the same result envelope plus agent_path / fallback_used
```

### Ingestion flow

```
Kaggle CSV
  │
  ▼
Normalization
  ├─ null and malformed value handling
  ├─ employee and year normalization
  ├─ locality parsing → city, region, country
  ├─ company_id = SHA-256(source first-column id + normalized company name)
  └─ company_semantic_text = name + industry + city + region + country
                              + optional "founded YEAR"
  │
  ▼
Validation + staged Parquet output
  ├─ valid rows   → staged artifact
  └─ invalid rows → dead-letter artifact
  │
  ▼
Bulk indexing via companies-write alias
  │
  ▼
firmable-description-embedding-pipeline
  └─ company_semantic_text → company_vector
```

---

## Data Model

### Canonical company document

| Field                       | Type           | Notes                                                          |
| --------------------------- | -------------- | -------------------------------------------------------------- |
| `company_id`                | keyword        | deterministic SHA-256 digest of source id plus normalized name |
| `name`                      | text + keyword | full-text search plus exact match support                      |
| `domain`                    | keyword        | exact filter and exact-match boost                             |
| `industry`                  | text + keyword | synonym-aware text field plus exact facet field                |
| `size_range`                | keyword        | faceting and filtering                                         |
| `city`                      | keyword        | normalized from locality parsing                               |
| `region`                    | keyword        | normalized from locality parsing                               |
| `country`                   | keyword        | normalized country                                             |
| `year_founded`              | integer        | optional, omitted when unavailable                             |
| `current_employee_estimate` | integer        | current company size signal                                    |
| `total_employee_estimate`   | integer        | broader company size signal                                    |
| `linkedin_url`              | keyword        | exact value storage                                            |
| `company_semantic_text`     | text           | deterministic embedding source text                            |
| `company_vector`            | knn_vector     | 384-dimensional vector populated by ingest pipeline            |

### Tagging status

Tags are intentionally not part of the current base company schema. Phase 6 will finalize the storage strategy. The latest working preference is to evaluate whether tags should live in the existing company index template and participate in facets and aggregations, but that is not yet a committed architectural decision.

---

## Search Lanes and Latency Budgets

| Lane                    | Path                                                   | Ollama dependency | Target p99 |
| ----------------------- | ------------------------------------------------------ | ----------------- | ---------- |
| UI search               | POST /search → deterministic planner → stored template | None              | < 200 ms   |
| UI facets               | POST /facets → deterministic planner → stored template | None              | < 100 ms   |
| Agent search (primary)  | POST /agent/search → LangChain + ChatOllama → tools    | Required          | < 3 s      |
| Agent search (fallback) | POST /agent/search → deterministic planner → template  | None              | < 200 ms   |

---

## API Surface

| Endpoint             | Status                                      | Purpose                                             |
| -------------------- | ------------------------------------------- | --------------------------------------------------- |
| `GET /health`        | implemented                                 | process liveness                                    |
| `GET /readiness`     | implemented                                 | OpenSearch readiness                                |
| `POST /search`       | implemented scaffold, Phase 3 logic pending | deterministic search lane                           |
| `POST /facets`       | planned for Phase 3                         | deterministic facet lane                            |
| `POST /agent/search` | candidate for Phase 5                       | intelligent search wrapper over deterministic tools |
| tag endpoints        | deferred to Phase 6                         | storage and contract intentionally undecided        |

All search endpoints share the same response envelope:

```json
{
  "items": [
    {
      "company_id": "...",
      "name": "...",
      "score": 12.34,
      "match_reasons": ["name_match", "industry_synonym"]
    }
  ],
  "total": 1247,
  "page": 1,
  "page_size": 20,
  "took_ms": 42
}
```

If `/agent/search` is added in Phase 5, it should extend the same response shape with two observable fields:

```json
{ "agent_path": true, "fallback_used": false }
```

### Pagination strategy

The current API contract uses page-number pagination via `page` and `page_size`, which the deterministic search path should translate to OpenSearch `from` and `size`.

This is an intentional take-home tradeoff, not a production pagination design:

- `from` + `size` keeps the API and browser UI simple and matches the existing request schema.
- It is suitable for shallow browsing of result sets and straightforward numbered pagination.
- It is not suitable for deep pagination across thousands of hits because offset cost grows with page depth and page contents can drift while the index changes.
- The production upgrade path is Point in Time plus `search_after`, which would require a cursor-style API instead of relying only on page numbers.

For this repository, treat `from` + `size` as a demo-safe default and document it as a non-production limitation alongside search scalability notes.

---

## Infrastructure Topology

### Local (Docker Compose)

```
┌──────────────────────────────────────────────────────────────────┐
│  Docker network: firmable                                        │
│                                                                  │
│  opensearch        :9200/:9300   (custom image, ML Commons)      │
│  opensearch-dash   :5601         (dev visibility only)           │
│  ollama            :11434        (ollama/ollama, named volume)   │
│  api               :8000         (FastAPI, hot reload)           │
│  web               :3000         (static file server)            │
│                                                                  │
│  Volumes:  opensearch-data, ollama-models                        │
└──────────────────────────────────────────────────────────────────┘
```

### Production (target topology)

```
┌──────────────────────────────────────────────────────────────────┐
│  OpenSearch cluster                                              │
│  ├─ data nodes (n ≥ 3, shards + replicas)                        │
│  └─ ML nodes   (dedicated, GPU optional)                         │
│                                                                  │
│  API service   (horizontally scaled, load balanced)              │
│                                                                  │
│  Optional LLM lane                                                │
│  ─ Ollama-compatible local runtime or hosted model provider       │
│  ─ only required for /agent/search                               │
│  ─ deterministic /search and /facets stay independent            │
│                                                                  │
│  Observability (structured logs, metrics, LangSmith traces)      │
└──────────────────────────────────────────────────────────────────┘
```

---

## Bootstrap Sequence

```
make infra-up
  └─ docker compose up -d (opensearch, dashboards, ollama)

make bootstrap
  ├─ 00-cluster-settings.sh   apply ML Commons cluster settings
  ├─ 01-register-model.sh     register model group + embedding model
  ├─ 02-deploy-model.sh       deploy model, poll task to COMPLETED
  ├─ 03-create-pipelines.sh   apply index template + ingest/search pipelines
  ├─ 04-create-search-templates.sh   install named search and facets templates
  ├─ 05-create-log-templates.sh      install observability index templates
  ├─ 06-write-model-env.sh           persist EMBEDDING_MODEL_ID into .env
  └─ infra/ollama/pull-model.sh
        ├─ wait for Ollama readiness
        └─ pull $OLLAMA_MODEL for the optional agent path

make seed CSV=data/sample.csv
  └─ runs app/ingestion/seed.py against companies-write alias
```

The API startup path may also verify or idempotently create the named search templates if bootstrap was skipped. Either way, the API should execute templates by name rather than constructing raw request bodies inline.

---

## Observability

| Signal                    | What is measured                                        |
| ------------------------- | ------------------------------------------------------- |
| Structured logs           | request id, endpoint, latency, status                   |
| Request counters          | per-endpoint request and error counts                   |
| Search outcome counters   | total results, zero-result rate                         |
| OpenSearch query timings  | `took` field forwarded as metric                        |
| Ollama reachability       | probe result logged for the optional /agent/search lane |
| Agent tool call counts    | tool name + invocation count per intelligent request    |
| Fallback activation count | times deterministic search is used instead of agent     |
| ML ingest failures        | text_embedding processor error counts                   |
| LangSmith traces          | enabled via `LANGSMITH_TRACING=true` (off by default)   |

---

## Key Architectural Decisions

| Decision                                                     | Rationale                                                                                |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| Deterministic search is the primary product path             | the take-home must work without Ollama and remain easy to explain                        |
| Stored OpenSearch templates own query execution              | keeps ranking and aggregation logic versionable and outside ad hoc handler code          |
| `company_semantic_text` is the main semantic text field      | supports hybrid retrieval and intent matching from normalized attributes                 |
| `company_id` is a deterministic hash, not a raw source id    | stable identity survives normalization and avoids trusting raw source identifiers alone  |
| Exact boosts stay available for company name and domain      | precise company lookups must not degrade under semantic search plans                     |
| OpenSearch ML Commons handles embeddings locally             | avoids an external embedding dependency for the core search stack                        |
| Staged Parquet artifacts remain part of ingestion            | keeps ingestion replayable, auditable, and easier to debug                               |
| UI search is explicit-submit only                            | aligns with the current browser implementation and keeps request volume predictable      |
| LangChain + ChatOllama is the recommended Phase 5 agent path | lower delivery risk than direct Ollama orchestration or OpenSearch-native agentic search |
| Tag storage is deferred until Phase 6                        | the current preference exists, but the final backend choice is still open                |

---

## Repository Map

### Current repository surfaces

```
firmable/
├── app/
│   ├── settings.py                   runtime config
│   ├── api/
│   │   ├── main.py                   FastAPI app, /health, /readiness, /search
│   │   └── schemas.py                request and response models
│   ├── ingestion/
│   │   ├── identity.py               company_id and company_semantic_text builders
│   │   ├── normalize.py              CSV cleanup and normalization
│   │   ├── seed.py                   bulk seed path
│   │   └── sync.py                   incremental sync path
│   ├── models/company.py             canonical company schema helpers
│   └── search/
│       ├── service.py                SearchService scaffold
│       ├── index_template.json       strict mappings and analyzers
│       └── synonyms.txt              industry synonym rules
├── infra/
│   ├── docker-compose.yml            local OpenSearch, Dashboards, Ollama, API, web
│   ├── ollama/pull-model.sh          optional agent-model bootstrap
│   └── opensearch/bootstrap/         model, pipeline, and template bootstrap scripts
├── web/
│   ├── index.html                    static UI shell
│   └── app.js                        explicit-submit browser logic
├── tests/                            ingestion and API-adjacent tests
└── docs/architecture.md              this file
```

### Planned additions for upcoming phases

- Phase 3 adds deterministic query planning, stored template registration or verification, and the `/facets` endpoint.
- Phase 5 may add the LangChain plus ChatOllama agent wrapper and `/agent/search`.
- Phase 6 will finalize tag storage, schema, and whether tag facets come from the company index or a separate backend.

---

## Deferred Decisions

- Tag storage remains intentionally undecided until Phase 6. The current preference is to evaluate tags inside the existing index template and facet contract, but the earlier separate-store plan is not yet formally replaced.
- The intelligent-search lane remains optional. For this take-home, the recommended path is LangChain plus ChatOllama over deterministic tools. Direct Ollama orchestration is feasible but more brittle, and OpenSearch-native agentic search is not worth the upgrade risk.
