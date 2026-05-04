## Plan: Firmable Search System

Build the first end-to-end slice around Python + FastAPI + OpenSearch, with semantic vectorization handled inside OpenSearch using ML Commons, a deployed embedding model, and a text_embedding ingest pipeline. Keep the API thin: request validation, deterministic query parsing, and OpenSearch query construction. Narrow the search scope to match-based free-text search plus structured filters for name, industry, founding year, location, and size. Do not spend time on autocomplete or edge-ngram indexing in the first slice.

**Steps**

1. Phase 1 - Repository foundation. Create a minimal repo layout with app, web, infra, docs, and tests. Add Docker Compose and a Makefile to start OpenSearch, OpenSearch Dashboards, the API, and a static web server locally. This phase blocks all others.
2. Phase 1 - OpenSearch ML-capable local setup. Configure Docker Compose for a local OpenSearch node with ML Commons enabled and settings that allow local model deployment during development, including plugins.ml_commons.only_run_on_ml_node false for single-node local use, plugins.ml_commons.local_model.enabled true, and safe resource thresholds for local testing. Document that production should move ML workloads to dedicated ML nodes. This depends on step 1.
3. Phase 1 - Cluster bootstrap automation. Add initialization scripts that wait for cluster health, apply required cluster settings, register or reuse a model group, register the embedding model, wait for registration tasks, deploy the model, and create the ingest pipeline plus search pipeline. This depends on step 2.
4. Phase 2 - Data contract and normalization. Define a canonical company schema from the Kaggle CSV with strict validation, normalized location fields, numeric year and employee types, and a stable company identifier. Handle nulls, malformed years, duplicate domains, and locality parsing before data reaches OpenSearch. This depends on step 1.
5. Phase 2 - Index template and analyzers. Create a strict OpenSearch index template with dynamic set to strict. Use multi-fields for exact matching and full-text matching, keyword fields for filters and facets, numeric fields for year and employee counts, and a knn_vector field populated by the ingest pipeline. Add synonym filters for industry/category expansion and a default_pipeline setting so document ingestion triggers text_embedding automatically. This depends on step 4 and step 3.
6. Phase 2 - Seed flow. Build a one-time seed pipeline that reads a configurable CSV subset first, normalizes records, computes derived text fields for semantic indexing, and bulk indexes into a write alias. The ingest request should rely on the OpenSearch default ingest pipeline to generate embeddings rather than computing them in the application. Include index creation, template application, and alias swap so reseeding is safe and repeatable. This depends on step 5.
7. Phase 2 - Data sync flow. Build an incremental sync job that ingests changed rows or delta files, upserts by company identifier, soft-deletes missing records when configured, and relies on the ingest pipeline with skip_existing or targeted reindex behavior to avoid unnecessary vector regeneration. Prefer idempotent upserts and alias-based rollover over in-place destructive updates. This depends on step 6.
8. Phase 3 - Search API surface. Expose search, facets, health, and readiness endpoints. Keep request and response models explicit and thin. The API should construct deterministic OpenSearch queries but should not own embedding generation. This depends on step 5 and can start in parallel with step 6.
9. Phase 3 - Query understanding and planning. Implement deterministic query understanding in the API to extract structured filters from free text, expand high-value business concepts like tech into curated industry groups, normalize locations like california into region filters, and choose between lexical-only and hybrid retrieval. This depends on step 8.
10. Phase 3 - Search types. Support match and multi-match queries for core text search, boosted exact matching on company name and domain, curated synonyms for industries and category expansion, explicit filter clauses for country, locality, size range, and founding year, and constrained fuzziness only where typo tolerance materially helps company-name recall. This depends on step 9.
11. Phase 4 - OpenSearch-native vectorization. Define the searchable semantic source text, for example a company_semantic_text field combining name, industry, normalized locality, country, and optionally domain tokens. Configure the text_embedding processor to map that field into a knn_vector field. Test the ingest pipeline with \_simulate before indexing real data. This depends on step 5.
12. Phase 4 - Hybrid retrieval. Create a hybrid search path that combines BM25 text clauses, boosted exact matches, explicit filters, and a neural query over the vector field. Add an OpenSearch search pipeline for normalization and score combination so lexical and neural scores are blended consistently and explainably. This depends on step 11 and step 10.
13. Phase 4 - Empty-result and external-data strategy. Keep external-data search out of the first implementation. When the API detects a query that cannot be answered by indexed data or receives zero results, return a deterministic fallback response that explains the limitation and can later route to an external enrichment path. This depends on step 9.
14. Phase 5 - Tags design. Keep tags outside the core company index as user-generated metadata stored in a relational store or a separate OpenSearch index keyed by company id and user or team scope. During ingestion, only prepare features that help later tag suggestions, such as normalized industry buckets, geo buckets, size buckets, and semantic vectors already produced by OpenSearch. This can run in parallel with step 11.
15. Phase 5 - Simple UI. Build a static HTML plus vanilla JavaScript interface with debounced search input, filter controls for industry, size, location, and founding year, pagination, sort selection, and result cards. Use fetch against the API and keep rendering intentionally simple. This depends on step 8.
16. Phase 5 - Observability. Add structured logs, request ids, latency metrics, search outcome counters, indexing counters, zero-result counters, OpenSearch query timings, ML model deployment status checks, ingest pipeline failures, and vector generation failure counts. This depends on step 8 and step 3.
17. Phase 6 - Testing and docs. Add focused tests for CSV normalization, strict mapping assumptions, synonym and query parsing, match-query assembly, hybrid query assembly, and API contracts. Document ML bootstrap, seed and sync flows, hybrid search architecture, scaling strategy for 10x load, and fallback behavior when semantic or external-data features are unavailable. This depends on steps 6 through 16.

**Relevant files**

- /Users/viknarasimhan/Documents/firmable/docker-compose.yml - Run OpenSearch, OpenSearch Dashboards, API, and a simple web server locally with ML-capable settings.
- /Users/viknarasimhan/Documents/firmable/Makefile - Standardize bootstrap, seed, sync, run, test, and index-management commands.
- /Users/viknarasimhan/Documents/firmable/infra/opensearch/bootstrap/00-cluster-settings.sh - Apply ML Commons cluster settings required for local development.
- /Users/viknarasimhan/Documents/firmable/infra/opensearch/bootstrap/01-register-model.sh - Register model groups and embedding models, handling reuse and task polling.
- /Users/viknarasimhan/Documents/firmable/infra/opensearch/bootstrap/02-deploy-model.sh - Deploy the embedding model and verify deployment completion.
- /Users/viknarasimhan/Documents/firmable/infra/opensearch/bootstrap/03-create-pipelines.sh - Create the text_embedding ingest pipeline and hybrid search pipeline.
- /Users/viknarasimhan/Documents/firmable/app/settings.py - Central runtime configuration for API and OpenSearch endpoints.
- /Users/viknarasimhan/Documents/firmable/app/models/company.py - Canonical normalized company schema for ingestion and API responses.
- /Users/viknarasimhan/Documents/firmable/app/ingestion/normalize.py - CSV cleanup, null handling, locality parsing, and derived semantic text fields.
- /Users/viknarasimhan/Documents/firmable/app/ingestion/seed.py - One-time bulk index flow using the OpenSearch default ingest pipeline.
- /Users/viknarasimhan/Documents/firmable/app/ingestion/sync.py - Incremental upsert and optional delete flow for changed data.
- /Users/viknarasimhan/Documents/firmable/app/search/index_template.json - Strict mappings, analyzers, synonym filters, default pipeline, and vector field definitions.
- /Users/viknarasimhan/Documents/firmable/app/search/search_pipeline.json - OpenSearch hybrid search pipeline for normalization and score blending.
- /Users/viknarasimhan/Documents/firmable/app/search/query_planner.py - Interpret free text into structured filters and choose lexical versus hybrid retrieval.
- /Users/viknarasimhan/Documents/firmable/app/search/query_templates.py - Build OpenSearch query bodies for filtered match, exact-boost, neural, and hybrid search.
- /Users/viknarasimhan/Documents/firmable/app/api/routes/search.py - Search, facets, and health endpoints.
- /Users/viknarasimhan/Documents/firmable/web/index.html - Simple UI shell with search box, filters, and result list.
- /Users/viknarasimhan/Documents/firmable/web/app.js - Debounced search requests, filter state, pagination, and rendering.
- /Users/viknarasimhan/Documents/firmable/tests/test_normalize.py - Validation of ingestion normalization and semantic text generation.
- /Users/viknarasimhan/Documents/firmable/tests/test_query_planner.py - Query understanding and fallback rules.
- /Users/viknarasimhan/Documents/firmable/tests/test_hybrid_search.py - Hybrid query assembly and score blending behavior.
- /Users/viknarasimhan/Documents/firmable/README.md - Setup, local run commands, architecture, and delivery notes.
- /Users/viknarasimhan/Documents/firmable/docs/ingestion.md - Seed and sync operational details.
- /Users/viknarasimhan/Documents/firmable/docs/opensearch-ml.md - ML Commons bootstrap flow, local caveats, and production topology notes.
- /Users/viknarasimhan/Documents/firmable/docs/scaling.md - 10x scale strategy, ML-node separation, and fallback behavior.

**Verification**

1. Start the local stack with Docker Compose and confirm OpenSearch cluster health plus Dashboards availability.
2. Run the cluster bootstrap scripts and verify model group registration, model registration, deployment completion, ingest pipeline creation, and search pipeline creation.
3. Use the ingest pipeline \_simulate endpoint to verify that semantic source text is converted into the vector field as expected.
4. Run the seed flow on a small CSV subset and verify index creation, strict mapping enforcement, alias setup, document counts, and vector population.
5. Run the sync flow on a delta sample and verify idempotent upserts, selective reprocessing, and optional soft deletes.
6. Exercise search queries including exact company names, typo variants, tech companies in california, software companies, and structured year or location filters.
7. Compare lexical-only versus hybrid results on synonym-heavy queries and verify the hybrid search pipeline combines scores predictably.
8. Confirm filter-only searches for industry, country, city, size range, and founding-year ranges behave correctly.
9. Confirm zero-result and external-data-required requests return deterministic fallback behavior in the first slice.
10. Open the static UI and verify debounced search, filter application, pagination, and sorting behavior against the API.
11. Run focused automated tests for normalization, query planning, filtered match queries, hybrid query assembly, and API contracts.

**Decisions**

- Use Python + FastAPI for the API and ingestion layer.
- Use OpenSearch as the retrieval system and source of truth for company search, with strict mappings, aliases, ML Commons, and ingest/search pipelines.
- Use OpenSearch-native text embedding via ML Commons and the text_embedding ingest processor rather than application-side embedding generation.
- Use a single-node local Docker setup for the take-home, but document dedicated ML nodes and stricter cluster settings for production.
- Keep the primary search surface focused on match-based free-text search and structured filters, not autocomplete.
- Keep external-data search out of the critical path in version one; provide a deterministic fallback policy instead of live web search as a requirement.
- Keep the UI intentionally minimal with static HTML and JavaScript.
- Keep tags as a separate concern from the base company ingestion pipeline. Only generate tag-suggestion features during ingestion, not final user tags.

**Further Considerations**

1. Match-query tuning: Recommendation is to start with multi_match plus boosted exact fields and only add fuzziness in a constrained way after relevance testing.
2. Tag generation: Recommendation is to store user tags separately and optionally compute suggested canonical tags offline from normalized industries, locations, and semantic clusters after the base search system works.
3. Empty-search fallback: Recommendation is deterministic query classification and explicit unsupported responses in version one, with a future enrichment adapter added only after the indexed search path is stable.
