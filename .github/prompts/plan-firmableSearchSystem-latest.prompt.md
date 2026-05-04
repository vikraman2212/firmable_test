## Plan: Firmable Search System

Build the first end-to-end slice around Python + FastAPI + OpenSearch + LangChain agents backed by a local Ollama model. The agent is the primary search path for every query: it receives the natural language input, reasons about which OpenSearch tool to invoke (lexical, hybrid, or facets), calls the tool with structured parameters, and returns results. Semantic vectorization is handled inside OpenSearch via ML Commons and a text_embedding ingest pipeline. A deterministic query planner acts as the fallback when Ollama is unreachable. Do not spend time on autocomplete or edge-ngram indexing.

**Steps**

1. Phase 1 - Repository foundation. Create a minimal repo layout with app (api, agent, search, ingestion, models), web, infra (opensearch, ollama), docs, and tests. Add Docker Compose and a Makefile to start OpenSearch, OpenSearch Dashboards, Ollama, the API, and a static web server locally. This phase blocks all others.
2. Phase 1 - OpenSearch ML-capable local setup. Configure Docker Compose for a local OpenSearch node with ML Commons enabled, plugins.ml_commons.only_run_on_ml_node false, plugins.ml_commons.local_model.enabled true, and safe resource thresholds for local testing. Add Ollama service using the ollama/ollama image on port 11434 with a named volume for model cache. Document that production moves ML workloads to dedicated OpenSearch ML nodes and replaces Ollama with a hosted LLM API. This depends on step 1.
3. Phase 1 - Cluster bootstrap automation. Add initialization scripts that wait for cluster health, apply ML Commons cluster settings, register the embedding model group and model, poll for task completion, deploy the model, and create the ingest pipeline plus hybrid search pipeline. Add a separate Ollama model pull script (infra/ollama/pull-model.sh) that calls ollama serve in background, waits for readiness on :11434, then runs ollama pull llama3.1:8b; the pulled model persists in the Docker volume so subsequent starts skip the download. This depends on step 2.
4. Phase 2 - Data contract and normalization. Use a staged Python ingestion pipeline built on pandas for CSV processing and transformation, plus Pydantic models for final document validation before indexing. Define a canonical company schema from the Kaggle CSV with strict validation, normalized location fields, numeric year and employee types, and a stable company identifier. Handle nulls, malformed years, duplicate domains, and locality parsing before data reaches OpenSearch. Transform raw rows into a normalized staged Parquet dataset so failures are auditable, reruns are deterministic, and indexing can be repeated without reparsing the source CSV. This depends on step 1.
5. Phase 2 - Index template and analyzers. Create a strict OpenSearch index template with dynamic set to strict. Use multi-fields for exact matching and full-text matching, keyword fields for filters and facets, numeric fields for year and employee counts, and a knn_vector field populated by the ingest pipeline. Define a synonym_graph token filter as the search_analyzer on industry and category fields. Add a default_pipeline setting so document ingestion triggers text_embedding automatically. This depends on step 4 and step 3.
6. Phase 2 - Seed flow. Build a one-time seed pipeline that reads a configurable CSV subset, normalizes records, writes a staged Parquet artifact, and then bulk indexes from that artifact into a write alias. Rely on the OpenSearch default ingest pipeline to generate embeddings. Include row-level validation reports, a dead-letter artifact for rejected rows, index creation, template application, and alias swap. This depends on step 5.
7. Phase 2 - Data sync flow. Build an incremental sync job that ingests changed rows or delta files, upserts by company identifier, soft-deletes missing records when configured, and relies on the ingest pipeline with skip_existing behavior. Prefer idempotent upserts and alias-based rollover over in-place destructive updates. This depends on step 6.
8. Phase 3 - Search API surface. Expose three POST endpoints: /search (deterministic, used by UI), /facets (deterministic aggregations, used by UI filter dropdowns), and /agent/search (LangChain agent path, used for demos and direct API callers). Add /health (includes Ollama reachability check) and /readiness. /search and /facets use query_planner.py directly and never touch Ollama, keeping the UI fast and reliable regardless of Ollama state. /agent/search uses the agent with query_planner.py as fallback. Response schema for /search and /agent/search is identical so the UI could swap between them trivially. This depends on step 5 and can start in parallel with step 6.
9. Phase 3 - LangChain agent setup. Create app/agent/search_agent.py. Use from langchain.agents import create_agent (LangChain v1.0) with from langchain_ollama import ChatOllama as the model. Configure ChatOllama pointing at http://ollama:11434 with model llama3.1:8b. Define a system prompt that instructs the agent to interpret natural language company search queries, extract filters (industry, location, size, founding year), and route to the correct tool. Add @wrap_tool_call middleware for error handling that returns a structured ToolMessage error rather than raising. Wire fallback: wrap agent.ainvoke in try/except catching httpx.ConnectError and httpx.TimeoutException and fall through to the deterministic planner. Add an Ollama health probe function that GETs http://ollama:11434/api/tags before routing — route directly to fallback if Ollama is down. This is only wired to /agent/search, not to /search or /facets. This depends on step 8.
10. Phase 3 - Agent tools. Create app/agent/tools.py with three @tool functions: search_companies(query, filters, page, page_size) for BM25 lexical search, hybrid_search(query, filters, page, page_size) for BM25 + neural combined, and get_facets(query, filters, facet_fields) for aggregation buckets. Each tool translates its parameters into an OpenSearch query via query_templates.py, executes against the read alias, and returns a typed dict the agent can interpret and forward as the final response. Tool docstrings are the agent's schema so keep them precise. This depends on step 9. Parallel with step 11.
11. Phase 3 - Query templates and deterministic fallback. Implement app/search/query_templates.py to build the OpenSearch query bodies for filtered match, exact-boost multi_match, neural kNN, and hybrid queries. Implement app/search/query_planner.py as a pure function fallback: regex-based entity extraction for location, founding year, size, and industry patterns, plus industry synonym expansion. The planner is used both as the fallback when Ollama is down and as a unit-testable reference for expected filter extraction. This depends on step 8. Parallel with step 10.
12. Phase 4 - OpenSearch-native vectorization. Define company_semantic_text combining name, industry, normalized locality, country, and domain tokens. Configure the text_embedding ingest processor to map that field into a knn_vector field. Test the pipeline with \_simulate before indexing real data. This depends on step 5.
13. Phase 4 - Hybrid retrieval. Create a hybrid search path combining BM25, boosted exact matches, explicit filters, and a neural kNN query over the vector field. Add an OpenSearch search pipeline for score normalization and blending. The hybrid_search agent tool uses this path. This depends on step 12 and step 11.
14. Phase 4 - Zero-result and external-data handling. When the agent receives zero results from any tool, it should return a structured response with an explanation and optionally suggest a refined query. Document the enrichment extension point (e.g., a future fetch_funding_news tool) without implementing it. The agent handles this gracefully through its ReAct loop without special API-layer logic. This depends on step 9.
15. Phase 5 - Tags design. Keep tags outside the core company index as user-generated metadata stored in a relational store or a separate OpenSearch index keyed by company id and user or team scope. Only generate tag-suggestion features during ingestion. This can run in parallel with step 12.
16. Phase 5 - Simple UI. Build a static HTML plus vanilla JavaScript interface with debounced search input, filter controls for industry, size, location, and founding year, pagination, sort selection, and result cards. Use fetch against /search. This depends on step 8.
17. Phase 5 - Observability. Add structured logs, request ids, latency metrics, search outcome counters, zero-result counters, OpenSearch query timings, Ollama reachability status, agent tool call counts, fallback activation counts, ML ingest pipeline failures, and vector generation failure counts. Enable LangSmith tracing via LANGSMITH_TRACING=true env var (optional, off by default). This depends on step 8 and step 3.
18. Phase 6 - Testing and docs. Add focused tests for CSV normalization, strict mapping assumptions, synonym analyzer behavior, query_planner fallback extraction, query_templates assembly, agent tool contracts, hybrid query assembly, and API response shapes. Document ML bootstrap, Ollama setup, seed and sync flows, agent architecture, fallback behavior, scaling strategy for 10x load, and latency budgets per search lane. This depends on steps 6 through 17.

**Relevant files**

- /Users/viknarasimhan/Documents/firmable/docker-compose.yml - Run OpenSearch, OpenSearch Dashboards, Ollama (ollama/ollama, port 11434), API, and a simple web server locally with ML-capable settings.
- /Users/viknarasimhan/Documents/firmable/Makefile - Standardize bootstrap, seed, sync, run, test, and index-management commands.
- /Users/viknarasimhan/Documents/firmable/infra/opensearch/bootstrap/00-cluster-settings.sh - Apply ML Commons cluster settings required for local development.
- /Users/viknarasimhan/Documents/firmable/infra/opensearch/bootstrap/01-register-model.sh - Register model groups and embedding models, handling reuse and task polling.
- /Users/viknarasimhan/Documents/firmable/infra/opensearch/bootstrap/02-deploy-model.sh - Deploy the embedding model and verify deployment completion.
- /Users/viknarasimhan/Documents/firmable/infra/opensearch/bootstrap/03-create-pipelines.sh - Create the text_embedding ingest pipeline and hybrid search pipeline.
- /Users/viknarasimhan/Documents/firmable/infra/ollama/pull-model.sh - Start ollama serve, wait for :11434 readiness, pull llama3.1:8b; model persists in Docker volume.
- /Users/viknarasimhan/Documents/firmable/app/settings.py - Central runtime configuration including OLLAMA_BASE_URL, OLLAMA_MODEL, OPENSEARCH_URL, LANGSMITH_TRACING.
- /Users/viknarasimhan/Documents/firmable/app/models/company.py - Canonical normalized company schema for ingestion and API responses.
- /Users/viknarasimhan/Documents/firmable/app/ingestion/normalize.py - CSV cleanup, null handling, locality parsing, and derived semantic text fields.
- /Users/viknarasimhan/Documents/firmable/app/ingestion/seed.py - One-time bulk index flow using the OpenSearch default ingest pipeline.
- /Users/viknarasimhan/Documents/firmable/app/ingestion/sync.py - Incremental upsert and optional delete flow for changed data.
- /Users/viknarasimhan/Documents/firmable/app/search/index_template.json - Strict mappings, analysis settings, synonym_graph search analyzers, default pipeline, and vector field definitions.
- /Users/viknarasimhan/Documents/firmable/app/search/synonyms.txt - Curated synonym rules for industry and category expansion, used by synonym_graph.
- /Users/viknarasimhan/Documents/firmable/app/search/search_pipeline.json - OpenSearch hybrid search pipeline for score normalization and blending.
- /Users/viknarasimhan/Documents/firmable/app/search/query_templates.py - Build OpenSearch query bodies for filtered match, exact-boost multi_match, neural kNN, and hybrid queries. Used directly by agent tools and as the fallback path.
- /Users/viknarasimhan/Documents/firmable/app/search/query_planner.py - Deterministic fallback: regex-based entity extraction and industry synonym expansion. Used by /search, /facets, and as fallback for /agent/search when Ollama is unreachable.
- /Users/viknarasimhan/Documents/firmable/app/agent/search_agent.py - LangChain create_agent setup: ChatOllama model, system prompt, @wrap_tool_call middleware, Ollama health probe, fallback wiring.
- /Users/viknarasimhan/Documents/firmable/app/agent/tools.py - Three @tool functions: search_companies (BM25 lexical), hybrid_search (BM25 + neural), get_facets (aggregations). Each delegates to query_templates.py.
- /Users/viknarasimhan/Documents/firmable/app/api/routes/search.py - POST /search and POST /facets (deterministic, UI-facing). POST /agent/search (agent path, demo/API-caller-facing). /health and /readiness.
- /Users/viknarasimhan/Documents/firmable/web/index.html - Simple UI shell with search box, filters, and result list.
- /Users/viknarasimhan/Documents/firmable/web/app.js - Debounced search requests, filter state, pagination, and rendering.
- /Users/viknarasimhan/Documents/firmable/tests/test_normalize.py - Validation of ingestion normalization and semantic text generation.
- /Users/viknarasimhan/Documents/firmable/tests/test_query_planner.py - Deterministic fallback extraction and synonym rules.
- /Users/viknarasimhan/Documents/firmable/tests/test_query_templates.py - BM25, exact-boost, hybrid query assembly.
- /Users/viknarasimhan/Documents/firmable/tests/test_agent_tools.py - Tool contract tests using mocked OpenSearch client.
- /Users/viknarasimhan/Documents/firmable/tests/test_hybrid_search.py - Hybrid query assembly and score blending behavior.
- /Users/viknarasimhan/Documents/firmable/README.md - Setup, local run commands, architecture, and delivery notes.
- /Users/viknarasimhan/Documents/firmable/docs/ingestion.md - Seed and sync operational details.
- /Users/viknarasimhan/Documents/firmable/docs/agent-search.md - LangChain agent architecture, tool definitions, fallback behavior, latency budgets, and LangSmith tracing notes.
- /Users/viknarasimhan/Documents/firmable/docs/opensearch-ml.md - ML Commons bootstrap flow, local caveats, and production topology notes.
- /Users/viknarasimhan/Documents/firmable/docs/scaling.md - 10x scale strategy, Ollama replacement with hosted LLM, ML-node separation, and fallback behavior.

**API Contracts**

- POST /search request JSON: {"query": "tech companies in california", "filters": {"industries": ["information technology and services"], "size_ranges": ["10001+"], "country": ["united states"], "city": ["new york"], "founded_year": {"from": 1900, "to": 2000}}, "page": 1, "page_size": 20, "sort": {"field": "relevance", "order": "desc"}, "include_facets": false}
- POST /search response JSON: {"items": [{"company_id": "5872184", "name": "ibm", "domain": "ibm.com", "industry": "information technology and services", "size_range": "10001+", "city": "new york", "region": "new york", "country": "united states", "year_founded": 1911, "current_employee_estimate": 274047, "total_employee_estimate": 716906, "linkedin_url": "linkedin.com/company/ibm", "score": 12.34, "match_reasons": ["name_match", "industry_synonym", "location_filter"]}], "total": 1247, "page": 1, "page_size": 20, "sort": {"field": "relevance", "order": "desc"}, "took_ms": 42}
- POST /agent/search request JSON: same schema as POST /search
- POST /agent/search response JSON: same schema as POST /search, with additional "agent_path": true and "fallback_used": false fields to make routing visible
- POST /facets request JSON: {"query": "tech companies", "filters": {"country": ["united states"], "size_ranges": ["10001+"]}, "facet_fields": ["industry", "size_range", "country", "city", "year_founded"]}
- POST /facets response JSON: {"facets": {"industry": [{"value": "information technology and services", "count": 820}, {"value": "computer software", "count": 311}], "size_range": [{"value": "10001+", "count": 120}], "country": [{"value": "united states", "count": 950}], "city": [{"value": "new york", "count": 110}], "year_founded": {"min": 1850, "max": 2024, "buckets": [{"from": 1900, "to": 1949, "count": 20}, {"from": 1950, "to": 1999, "count": 540}, {"from": 2000, "to": 2024, "count": 390}]}}, "took_ms": 18}
- Contract rule: /search and /facets are UI-facing and deterministic; they never call Ollama. /agent/search is agent-facing with identical response shape; it uses the LangChain agent with query_planner fallback. The agent_path and fallback_used fields in /agent/search responses make the routing decision observable.

**Verification**

1. Start the local stack with Docker Compose and confirm OpenSearch cluster health plus Dashboards availability.
2. Run the cluster bootstrap scripts and verify model group registration, model registration, deployment completion, ingest pipeline creation, and search pipeline creation.
3. Confirm Ollama model pull completed and the model is available via GET http://localhost:11434/api/tags.
4. Use the ingest pipeline \_simulate endpoint to verify that semantic source text is converted into the vector field as expected.
5. Run the seed flow on a small CSV subset and verify index creation, strict mapping enforcement, alias setup, document counts, and vector population.
6. Run the sync flow on a delta sample and verify idempotent upserts, selective reprocessing, and optional soft deletes.
7. Exercise /search queries including exact company names, tech companies in california, software companies, and structured year or location filters. Confirm these never touch Ollama.
8. Exercise /agent/search with the same queries and verify agent tool call counts in logs, agent_path and fallback_used fields in response.
9. Stop Ollama and verify /agent/search falls back cleanly with fallback_used: true; verify /search is unaffected.
10. Compare lexical-only versus hybrid results on synonym-heavy queries and verify the hybrid search pipeline combines scores predictably.
11. Confirm filter-only searches for industry, country, city, size range, and founding-year ranges behave correctly.
12. Open the static UI and verify debounced search, filter application, pagination, and sorting behavior against /search.
13. Run focused automated tests for normalization, query_planner fallback extraction, query_templates assembly, agent tool contracts, hybrid query assembly, API contracts, and synonym analyzer behavior using \_analyze requests for representative phrases such as software company, tech company, and information technology.

**Decisions**

- Use Python + FastAPI for the API and ingestion layer.
- Use LangChain v1.0 (from langchain.agents import create_agent) as the agent framework, backed by Ollama running llama3.1:8b locally.
- Use langchain-ollama (from langchain_ollama import ChatOllama) as the Ollama integration package; not the legacy langchain_community Ollama class.
- Use Ollama (ollama/ollama Docker image) as the local LLM runtime. Production replaces Ollama with a hosted provider (e.g. OpenAI, Anthropic) by swapping OLLAMA_BASE_URL and model env vars.
- Agent tools: three @tool functions (search_companies, hybrid_search, get_facets) that translate LLM-extracted parameters into OpenSearch queries.
- Deterministic query_planner.py is the primary path for /search and /facets (UI-facing), and also the fallback for /agent/search when Ollama is unreachable.
- /agent/search is a separate endpoint wired to the LangChain agent; /search and /facets never touch Ollama, keeping the UI reliable regardless of LLM state.
- Ollama health probe (GET /api/tags) runs only on /agent/search requests before routing to avoid per-request timeout cost when Ollama is down.
- LangSmith tracing enabled via LANGSMITH_TRACING=true env var, off by default in local Docker.
- Use pandas plus Pydantic for the first ingestion implementation.
- Use a staged Parquet artifact as the normalization boundary between raw CSV cleanup and OpenSearch bulk indexing.
- Use OpenSearch as the retrieval system with strict mappings, aliases, ML Commons, and ingest/search pipelines.
- Use OpenSearch-native text embedding via ML Commons and the text_embedding ingest processor.
- Use a single-node local Docker setup for the take-home; document dedicated ML nodes for production.
- Keep the UI intentionally minimal with static HTML and JavaScript.
- Keep tags as a separate concern from the base company ingestion pipeline.

**Further Considerations**

1. Ollama model size: llama3.1:8b needs ~5GB RAM. If memory-constrained, swap to qwen2.5:3b via OLLAMA_MODEL env var — it also has tool-calling support.
2. Streaming: ChatOllama does not support streaming tool calls (known Ollama limitation). Text streaming via agent.stream() is available if the UI later wants progressive rendering.
3. Future enrichment tool: a fetch_funding_news @tool slots into tools.py as a fourth tool; the agent gains access automatically with no API changes.
4. Match-query tuning: start with multi_match plus boosted exact fields and only add fuzziness in a constrained way after relevance testing.
5. Tag generation: store user tags separately and optionally compute suggested canonical tags offline from normalized industries, locations, and semantic clusters after the base search system works.
