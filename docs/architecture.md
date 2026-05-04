# Firmable Search System — Architecture

## Overview

The system is a company search platform over the People Data Labs 7M company dataset. Search is powered by OpenSearch with ML Commons for semantic vectorization. Every query is routed through a LangChain agent backed by a local Ollama LLM; a deterministic query planner acts as fallback when Ollama is unreachable. The UI is a static HTML/JS interface that calls only the deterministic endpoints.

---

## Component Map

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          CLIENT LAYER                                   │
│                                                                         │
│   Browser (web/index.html + web/app.js)                                 │
│   ─ debounced search input, filter controls, pagination, sort           │
│   ─ calls POST /search and POST /facets only (never /agent/search)      │
│                                                                         │
│   API Caller / Demo Client                                              │
│   ─ calls POST /agent/search for agent-routed intelligent search        │
└─────────────────────┬───────────────────────────┬───────────────────────┘
                      │ HTTP                       │ HTTP
                      ▼                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          API LAYER  (FastAPI)                           │
│                   app/api/routes/search.py                              │
│                                                                         │
│  POST /search ──────► query_planner.py ──────────────────────────────┐  │
│  POST /facets ──────► query_planner.py ──────────────────────────────┤  │
│                                                                       │  │
│  POST /agent/search ─► Ollama probe ─► search_agent.py               │  │
│                              │               │                        │  │
│                              │ down          │ tools                  │  │
│                              ▼               ▼                        │  │
│                        query_planner.py  tools.py                     │  │
│                              │               │                        │  │
│                              └───────────────┘                        │  │
│                                      │                                │  │
│  GET  /health   ◄── Ollama + OpenSearch reachability check            │  │
│  GET  /readiness                                                       │  │
└──────────────────────────────────────┬────────────────────────────────┘
                                       │ OpenSearch HTTP (9200)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     SEARCH BACKEND  (OpenSearch)                        │
│                                                                         │
│  Index: companies-v1  (alias: companies-read, companies-write)          │
│  ─ strict dynamic mappings                                              │
│  ─ multi-fields: .keyword for filters/facets, .text for full-text       │
│  ─ synonym_graph analyzer on industry + category fields                 │
│  ─ knn_vector field populated by ingest pipeline                        │
│  ─ default_pipeline: text_embedding                                     │
│                                                                         │
│  Ingest Pipeline: text_embedding                                        │
│  ─ text_embedding processor: company_semantic_text → company_vector     │
│                                                                         │
│  Search Pipeline: hybrid-pipeline                                       │
│  ─ normalization + score blending (BM25 + neural kNN)                  │
│                                                                         │
│  ML Commons (local node, no dedicated ML node)                          │
│  ─ model group: firmable-embeddings                                     │
│  ─ model: all-MiniLM-L12-v2 (sentence-transformers)                    │
│  ─ plugins.ml_commons.only_run_on_ml_node: false                        │
│  ─ plugins.ml_commons.local_model.enabled: true                         │
│                                                                         │
│  OpenSearch Dashboards (port 5601)  — local dev only                   │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                    INTELLIGENCE LAYER  (LangChain + Ollama)             │
│                                                                         │
│  search_agent.py                                                        │
│  ─ ChatOllama → http://ollama:11434, model: configurable via OLLAMA_MODEL (default: gemma3:4b) │
│  ─ create_agent (LangChain v1.0)                                        │
│  ─ system prompt: extract filters, route to correct tool                │
│  ─ @wrap_tool_call middleware: structured ToolMessage errors            │
│  ─ Ollama health probe (GET /api/tags) before each /agent/search call   │
│  ─ fallback: httpx.ConnectError / TimeoutException → query_planner      │
│                                                                         │
│  tools.py (@tool functions)                                             │
│  ─ search_companies(query, filters, page, page_size)  → BM25 lexical   │
│  ─ hybrid_search(query, filters, page, page_size)     → BM25 + neural  │
│  ─ get_facets(query, filters, facet_fields)           → aggregations    │
│  ─ each tool delegates to query_templates.py                            │
│                                                                         │
│  query_planner.py  (deterministic fallback)                             │
│  ─ regex entity extraction: location, founding year, size, industry     │
│  ─ industry synonym expansion                                           │
│  ─ used by /search + /facets always; /agent/search when Ollama is down  │
│                                                                         │
│  query_templates.py                                                     │
│  ─ filtered match, exact-boost multi_match, neural kNN, hybrid queries  │
│  ─ used by all tools and the deterministic path                         │
│                                                                         │
│  Ollama service  (ollama/ollama, port 11434)                            │
│  ─ model: configurable via OLLAMA_MODEL env var (default: gemma3:4b)   │
│  ─ swap to any Ollama-supported model; set OLLAMA_MODEL before make    │
│  ─ model cache persists in named Docker volume                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                       INGESTION LAYER                                   │
│                                                                         │
│  Seed flow  (app/ingestion/seed.py)                                     │
│  ─ reads CSV subset (configurable row limit)                            │
│  ─ normalize.py: null handling, year/employee normalization,            │
│       locality parsing, company_semantic_text derivation                │
│  ─ Pydantic validation (app/models/company.py)                          │
│  ─ writes staged Parquet artifact (auditable, replayable)               │
│  ─ dead-letter artifact for rejected rows                               │
│  ─ bulk indexes from Parquet → companies-write alias                    │
│  ─ OpenSearch ingest pipeline generates embeddings automatically        │
│  ─ alias swap on success                                                │
│                                                                         │
│  Sync flow  (app/ingestion/sync.py)                                     │
│  ─ idempotent upserts by company_id                                     │
│  ─ optional soft-delete for missing records                             │
│  ─ skip_existing behavior via ingest pipeline                           │
│                                                                         │
│  Source: Kaggle PDL 7M company CSV                                      │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         TAGS LAYER                                      │
│                                                                         │
│  Separate OpenSearch index: company-tags                                │
│  ─ keyed by (company_id, user_id)  — user-scoped metadata               │
│  ─ fields: company_id (keyword), user_id (keyword), tags (keyword[])    │
│  ─ no coupling to the companies index lifecycle                         │
│  ─ tag suggestions generated offline from normalized industry,          │
│       location, and semantic cluster labels during ingestion            │
│  ─ PUT /tags/{company_id}  and  GET /tags/{company_id}  endpoints       │
│                                                                         │
│  Not part of the search ranking pipeline — tags are user annotations,   │
│  not document features. Querying by tag is a simple term filter.        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Request Flow

### UI search request (POST /search)

```
Browser
  │
  ▼
POST /search  {query, filters, page, sort}
  │
  ▼
query_planner.py
  ├─ regex entity extraction (location, year, size, industry)
  ├─ synonym expansion (e.g. "tech" → "information technology and services")
  └─ builds structured filter set
  │
  ▼
query_templates.py  →  BM25 filtered match query body
  │
  ▼
OpenSearch  companies-read alias
  ├─ BM25 scoring + explicit filters
  └─ synonym_graph analyzer on industry/category
  │
  ▼
SearchResponse  {items, total, page, took_ms}
```

### Agent search request (POST /agent/search)

```
API caller
  │
  ▼
POST /agent/search  {query, filters, page, sort}
  │
  ▼
Ollama health probe  GET http://ollama:11434/api/tags
  │
  ├─ unreachable ──────────────────────────────────────────────────────┐
  │                                                                     │
  ▼                                                                     │
search_agent.py  (ChatOllama — model from OLLAMA_MODEL env var)        │
  │                                                                     │
  ▼  ReAct loop                                                         │
tools.py                                                                │
  ├─ search_companies  → query_templates BM25                          │
  ├─ hybrid_search     → query_templates hybrid (BM25 + neural kNN)    │
  └─ get_facets        → query_templates aggregation                   │
  │                      │                                             │
  │                      ▼                                             │
  │               OpenSearch + hybrid search pipeline                  │
  │                      │                                             │
  ◄──────────────────────┘                                             │
  │                                                                     │
  ▼                                                                     │
AgentSearchResponse  {items, total, agent_path: true,                  │
                      fallback_used: false, took_ms}                   │
                                                                        │
  ◄──────────────────────── query_planner fallback ───────────────────┘
  │
  ▼
AgentSearchResponse  {items, total, agent_path: true,
                      fallback_used: true, took_ms}
```

### Ingestion flow

```
Kaggle CSV  (7M rows)
  │
  ▼
normalize.py  (pandas)
  ├─ null / malformed year handling
  ├─ employee count normalization
  ├─ locality parsing  →  city, region, country
  └─ company_semantic_text  =  name + industry + locality + country + domain
  │
  ▼
Pydantic validation  (CompanyDocument)
  ├─ valid rows   → staged Parquet artifact
  └─ invalid rows → dead-letter Parquet artifact
  │
  ▼
OpenSearch bulk index  (companies-write alias)
  │
  ▼
text_embedding ingest pipeline
  └─ company_semantic_text → company_vector  (all-MiniLM-L12-v2, 384d)
  │
  ▼
alias swap  companies-write → companies-read
```

---

## Data Model

### Canonical company document

| Field                       | Type           | Notes                                |
| --------------------------- | -------------- | ------------------------------------ |
| `company_id`                | keyword        | stable PDL identifier                |
| `name`                      | text + keyword | full-text + exact filter             |
| `domain`                    | keyword        | deduplicated on ingest               |
| `industry`                  | text + keyword | synonym_graph search analyzer        |
| `category`                  | text + keyword | synonym_graph search analyzer        |
| `size_range`                | keyword        | e.g. `10001+`                        |
| `year_founded`              | integer        | null → omitted                       |
| `city`                      | keyword        | parsed from locality string          |
| `region`                    | keyword        | parsed from locality string          |
| `country`                   | keyword        | normalized                           |
| `current_employee_estimate` | integer        |                                      |
| `total_employee_estimate`   | integer        |                                      |
| `linkedin_url`              | keyword        |                                      |
| `company_vector`            | knn_vector     | 384d, populated by ingest pipeline   |
| `company_semantic_text`     | text           | source field for embedding processor |

### Tag document (company-tags index)

| Field        | Type      | Notes                            |
| ------------ | --------- | -------------------------------- |
| `company_id` | keyword   | foreign key into companies index |
| `user_id`    | keyword   | user or team scope               |
| `tags`       | keyword[] | free-form user labels            |

---

## Search Lanes and Latency Budgets

| Lane                    | Path                                             | Ollama dependency | Target p99 |
| ----------------------- | ------------------------------------------------ | ----------------- | ---------- |
| UI search               | POST /search → query_planner → BM25              | None              | < 200 ms   |
| UI facets               | POST /facets → query_planner → aggregations      | None              | < 100 ms   |
| Agent search (agent)    | POST /agent/search → ChatOllama → tools → hybrid | Required          | < 3 s      |
| Agent search (fallback) | POST /agent/search → query_planner → BM25        | None              | < 200 ms   |

---

## API Surface

```
POST /search              # deterministic, UI-facing
POST /facets              # deterministic aggregations, UI filter dropdowns
POST /agent/search        # LangChain agent, identical response shape
GET  /health              # OpenSearch + Ollama reachability
GET  /readiness           # service ready to accept traffic
PUT  /tags/{company_id}   # upsert user tags for a company
GET  /tags/{company_id}   # retrieve user tags for a company
```

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

`/agent/search` adds two observable fields:

```json
{ "agent_path": true, "fallback_used": false }
```

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
│  LLM           (hosted provider: OpenAI / Anthropic)             │
│  ─ swap OLLAMA_BASE_URL + OLLAMA_MODEL env vars                  │
│  ─ no Ollama container in production                             │
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
  ├─ 03-create-pipelines.sh   text_embedding ingest + hybrid search pipeline
  └─ infra/ollama/pull-model.sh
        ├─ ollama serve (background)
        ├─ wait :11434 ready
        └─ ollama pull $OLLAMA_MODEL  (default: gemma3:4b, persists in ollama-models volume)

make seed CSV=data/sample.csv
  └─ runs app/ingestion/seed.py against companies-write alias
```

---

## Observability

| Signal                    | What is measured                                      |
| ------------------------- | ----------------------------------------------------- |
| Structured logs           | request id, endpoint, latency, status                 |
| Request counters          | per-endpoint request and error counts                 |
| Search outcome counters   | total results, zero-result rate                       |
| OpenSearch query timings  | `took` field forwarded as metric                      |
| Ollama reachability       | probe result logged per /agent/search call            |
| Agent tool call counts    | tool name + invocation count per request              |
| Fallback activation count | times query_planner used instead of agent             |
| ML ingest failures        | text_embedding processor error counts                 |
| LangSmith traces          | enabled via `LANGSMITH_TRACING=true` (off by default) |

---

## Key Architectural Decisions

| Decision                                              | Rationale                                                    |
| ----------------------------------------------------- | ------------------------------------------------------------ |
| Agent is primary path for /agent/search               | natural language understanding without hand-coded parsers    |
| query_planner is primary path for /search and /facets | UI reliability; never blocked by Ollama state                |
| Ollama health probe before agent routing              | avoids per-request timeout cost when Ollama is down          |
| OpenSearch-native vectorization (ML Commons)          | no external embedding service; vectors colocated with index  |
| Staged Parquet artifact                               | ingestion failures are auditable; reruns are deterministic   |
| Strict dynamic:strict index mapping                   | prevents schema drift from unexpected CSV columns            |
| Alias-based indexing (read + write)                   | zero-downtime reindex; write alias decouples seed from reads |
| Tags in a separate index                              | decouples user annotations from company index lifecycle      |
| LangChain v1.0 + langchain-ollama                     | stable agent API; easy LLM swap via env vars                 |
| Static HTML/JS UI                                     | keeps UI independent of API framework; easy to host anywhere |
| Tags as separate concern                              | avoids coupling user metadata lifecycle to company index     |

---

## File Map

```
firmable/
├── app/
│   ├── settings.py                   runtime config (OPENSEARCH_URL, OLLAMA_*)
│   ├── api/routes/search.py          /search  /facets  /agent/search  /health
│   ├── agent/
│   │   ├── search_agent.py           LangChain agent, Ollama probe, fallback
│   │   └── tools.py                  @tool: search_companies, hybrid_search, get_facets
│   ├── search/
│   │   ├── query_planner.py          deterministic regex + synonym fallback
│   │   ├── query_templates.py        OpenSearch query body builders
│   │   ├── index_template.json       strict mappings, analyzers, vector field
│   │   ├── synonyms.txt              industry synonym rules
│   │   └── search_pipeline.json     hybrid score normalization pipeline
│   ├── ingestion/
│   │   ├── normalize.py              CSV cleanup, locality parsing, semantic text
│   │   ├── seed.py                   one-time bulk index from CSV
│   │   └── sync.py                   incremental upsert / soft-delete
│   ├── models/company.py             Pydantic CompanyDocument schema
│   └── api/routes/tags.py            PUT/GET /tags/{company_id}
├── web/
│   ├── index.html                    search UI shell
│   └── app.js                        debounced fetch, filters, pagination
├── infra/
│   ├── docker-compose.yml            all local services
│   ├── opensearch/
│   │   ├── Dockerfile                ML Commons enabled image
│   │   ├── index.json                index config artifact
│   │   └── bootstrap/
│   │       ├── 00-cluster-settings.sh
│   │       ├── 01-register-model.sh
│   │       ├── 02-deploy-model.sh
│   │       └── 03-create-pipelines.sh
│   └── ollama/pull-model.sh          model pull + volume persistence
├── tests/
│   ├── test_normalize.py
│   ├── test_query_planner.py
│   ├── test_query_templates.py
│   ├── test_agent_tools.py
│   └── test_hybrid_search.py
├── docs/
│   ├── architecture.md               ← this file
│   ├── ingestion.md                  seed + sync operational details
│   ├── agent-search.md               agent design, fallback, latency budgets
│   ├── opensearch-ml.md              ML Commons bootstrap, production topology
│   └── scaling.md                    10x scale strategy, LLM swap, ML-node split
├── Makefile
└── README.md
```
