# AI-DLC State Tracking

## Project Information

- **Project Type**: Greenfield
- **Start Date**: 2026-05-03T12:57:03Z
- **Current Stage**: OPERATIONS - Placeholder

## Workspace State

- **Existing Code**: Yes
- **Programming Languages**: Python, JavaScript, HTML/CSS
- **Build System**: `uv`, `pytest`, `Makefile`, Docker Compose
- **Project Structure**: Greenfield repository bootstrap
- **Reverse Engineering Needed**: No
- **Workspace Root**: /Users/viknarasimhan/Documents/firmable

## Code Location Rules

- **Application Code**: Workspace root (NEVER in aidlc-docs/)
- **Documentation**: aidlc-docs/ only
- **Structure patterns**: Greenfield repository with app/, web/, infra/, docs/, and tests/

## Stage Progress

### 🔵 INCEPTION PHASE

- [x] Workspace Detection
- [ ] Reverse Engineering (not applicable)
- [x] Requirements Analysis
- [x] User Stories
- [x] Workflow Planning
- [ ] Application Design (skipped)
- [ ] Units Generation (skipped)

### 🟢 CONSTRUCTION PHASE

- [ ] Functional Design (skipped)
- [ ] NFR Requirements (skipped)
- [ ] NFR Design (skipped)
- [ ] Infrastructure Design (skipped)
- [x] Code Generation - Planning
- [x] Code Generation - Generation
- [x] Build and Test

### 🟡 OPERATIONS PHASE

- [ ] Operations

## Extension Configuration

| Extension              | Enabled | Decided At            |
| ---------------------- | ------- | --------------------- |
| Security Baseline      | No      | Requirements Analysis |
| Property-Based Testing | No      | Requirements Analysis |

## Current Status

- **Working Unit**: Operations placeholder
- **Last Completed Step**: Build and Test stage approved. The instruction pack is complete and the current workflow has advanced into the placeholder Operations stage.
- **Next Step**: No additional automated Operations work is defined in the current AIDLC ruleset.

## Completed Tasks

- P1-T01: Repository skeleton
- P1-T02: Docker Compose stack (full 5-service shape)
- P1-T03: OpenSearch ML Commons environment variables
- P1-T04: Service health checks and startup ordering
- P1-T05: Makefile workflow commands
- P1-T06: Cluster settings bootstrap (moved to docker-compose env vars; no script needed)
- P1-T07: Embedding model registration and deployment scripts (01-register-model.sh, 02-deploy-model.sh, infra/ollama/pull-model.sh)
- P1-T08: Ingest pipeline, search pipeline, strict index template, synonyms (03-create-pipelines.sh, app/search/)
- P2-T08: Incremental sync flow with content-hash skipping, idempotent upserts, and optional soft deletes (app/ingestion/sync.py)
- P3-T01: FastAPI scaffold and runtime settings
- P3-T02: API request/response schemas (SearchRequest, SearchResponse, FacetsRequest, FacetsResponse)
- P3-T03: Deterministic query planner (app/search/query_planner.py)
- P3-T04: Named OpenSearch search templates — firmable-search-v1, firmable-search-hybrid-v1, and firmable-facets-v1 (04-create-search-templates.sh, app/search/templates.py)
- P3-T05: SearchService.search() with template routing for BM25 fallback and hybrid default for query-bearing searches
- P3-T06: POST /search endpoint
- P3-T07: POST /facets endpoint + SearchService.facets() using firmable-facets-v1 template
- P3-T08: /health (liveness) and /readiness (OpenSearch + index alias check) endpoints
- P4-T01: Static UI shell in web/index.html
- P4-T02: Client-side search state in web/app.js (query/filter DOM state, agentic mode persistence, current page state)
- P4-T04: Result cards, error state, and empty state rendering in web/app.js
- P4-T06: Static UI served locally from /ui through the API service
- P5-T01: Ollama runtime configuration in app/settings.py and docker-compose wiring
- P5-T02: Automated Ollama model pull script in infra/ollama/pull-model.sh and Makefile workflow
- P5-T03: LangChain search agent with ChatOllama, system prompt, and SSE event streaming in app/agent/search_agent.py
- P5-T04: Agent tool set for hybrid search, lexical search, facets, and optional web search in app/agent/tools.py
- P5-T05: Structured tool-call error handling across agent tools and streamed error events
- P5-T06: Ollama reachability probe and deterministic fallback gate in app/agent/search_agent.py
- P5-T07: POST /agent/search endpoint with SSE streaming and agent metadata in app/api/main.py
- P5-T08: Stable semantic embedding field built from normalized company attributes and indexed through the ingest pipeline
- P5-T09: Hybrid BM25 + neural retrieval with request-parameter search pipeline normalization
- P5-T10: Structured zero-result agent responses with query-refinement guidance
- P5-T11: Search and agent observability with request IDs, latency logging, fallback/tool-call logging, and optional LangSmith hooks
