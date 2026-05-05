# Phase 3 and Phase 5 Stories — Deterministic Facets and Hybrid Neural Search

## Story P3-T03: Deterministic Query Planner

- **Backlog mapping**: `P3-T03`
- **Persona**: API and Search Developer, Search Platform Engineer
- **Story**: As an API and search developer, I want a deterministic query planner so free text and UI filters are normalized into one stable search plan before any OpenSearch query is built.

### Acceptance Criteria

- The planner accepts free text plus the supported filter inputs for location, industry, company size, founding-year range, and tags.
- Empty fields are omitted from the search plan instead of producing empty clauses.
- Industry filtering can expand through the configured synonym set without changing the original user-visible filter value.
- Tags are represented as a separate or optional filter source so the planner does not require tag data inside the base company index.
- The resulting plan is pure and deterministic so the same request payload always produces the same structured search plan.

## Story P3-T04: Reusable Search and Aggregation Templates

- **Backlog mapping**: `P3-T04`
- **Persona**: API and Search Developer, Business Analyst
- **Story**: As an API and search developer, I want reusable OpenSearch search templates so search hits and facet counts are built consistently from the same normalized request and managed outside ad hoc API-side DSL assembly.

### Acceptance Criteria

- Named search and aggregation templates are created either during OpenSearch startup/bootstrap or during deterministic API initialization before search requests are served.
- The faceted search template applies the active free-text query across all relevant fields, with the strongest weighting assigned to `company_semantic_text`.
- The search template also boosts exact or near-exact matches for fields such as company name and canonical domain.
- Structured filters for industry, size range, location, founding-year range, and optional tag scope are represented as template parameters and are applied as filter clauses rather than score-driving text clauses.
- The aggregation template applies the current text query and all currently selected filters before computing facet counts.
- Aggregations include industry, company size, geography, and founding-year coverage, while tag aggregation remains pluggable so it can be sourced externally in Phase 6.

## Story P3-T05 and P3-T06: Deterministic Search Endpoint

- **Backlog mapping**: `P3-T05`, `P3-T06`
- **Persona**: Sales Researcher, API and Search Developer
- **Story**: As a sales researcher, I want a deterministic `/search` endpoint so the UI can submit a query plus filters and receive ranked companies in a stable response envelope.

### Acceptance Criteria

- `POST /search` executes only the deterministic planner and deterministic query-template path for the Phase 3 slice.
- The endpoint executes named OpenSearch search templates with planner-produced parameters rather than constructing raw DSL request bodies inline.
- The endpoint returns result items shaped from the normalized company document contract.
- Pagination metadata remains stable and consistent with the request inputs.
- Search execution preserves active filters while ranking matching companies from the free-text query.
- The deterministic endpoint does not depend on Ollama or agent execution to succeed.

## Story P3-T07: Facet Aggregation Endpoint

- **Backlog mapping**: `P3-T07`
- **Persona**: Business Analyst, Sales Researcher
- **Story**: As a business analyst, I want a `/facets` endpoint that returns filter counts for the current query state so I can understand how the result set is distributed before changing filters.

### Acceptance Criteria

- `POST /facets` returns counts for location, industry, company size, and founding-year buckets for the current search state.
- The returned counts reflect both the active free-text query and all currently selected filters.
- The endpoint executes a named aggregation template with the current planner parameters instead of assembling the aggregation DSL inline in the API layer.
- The endpoint can return a tag facet section through a separate source or an explicit empty-state contract until Phase 6 tag storage is implemented.
- The aggregation request does not need to return search hits.
- The facet response shape is consistent enough for the UI to render filter counts without additional query parsing in the browser.

## Story P5-T08: Semantic Field Readiness

- **Backlog mapping**: `P5-T08`
- **Persona**: Search Platform Engineer, API and Search Developer
- **Story**: As a search platform engineer, I want the semantic embedding field to be built from normalized company attributes and validated before indexing so neural retrieval starts from stable, explainable text input.

### Acceptance Criteria

- `company_semantic_text` is composed only from normalized company attributes such as company name, industry, normalized locality, and founded-year language.
- The semantic text source is deterministic across reruns for the same normalized company record.
- Ingest-pipeline validation proves the semantic text can be transformed into the vector field required for neural retrieval.
- Raw or dirty source fragments are not injected directly into the semantic field.
- The semantic-field definition stays aligned with the normalized ingestion contract from Phase 2.

## Story P5-T09: Hybrid BM25 Plus Neural Retrieval

- **Backlog mapping**: `P5-T09`
- **Persona**: Sales Researcher, Search Platform Engineer
- **Story**: As a sales researcher, I want hybrid search that combines lexical matching and neural retrieval so natural-language queries can recover relevant companies while still honoring exact fields and structured filters.

### Acceptance Criteria

- The hybrid search path combines a lexical clause and a neural or vector clause against the same normalized request.
- The free-text portion of the query searches all relevant fields, but `company_semantic_text` remains the primary text field for semantic intent matching.
- Exact boosts for company name and canonical domain remain available so precise company searches are not degraded by the neural path.
- The same structured filters for industry, company size, location, founding year, and optional tag scope constrain both the lexical and neural retrieval portions.
- The hybrid retrieval contract remains compatible with stored OpenSearch templates so lexical and neural clauses can be versioned and rolled out through infra or API initialization rather than handwritten API DSL assembly.
- If neural retrieval is unavailable or unhealthy, the system can fall back to the deterministic lexical path without changing the request contract.
- Score blending remains understandable and tunable rather than opaque or hard-coded to the point of being unexplainable.

## Scope Notes

- These stories assume the Phase 2 normalization work remains the source of truth for company identity, geography, and semantic text composition.
- The deterministic API layer should treat OpenSearch search templates as deployable runtime artifacts managed by infra bootstrap or API initialization.
- Tag facets are part of the search contract, but tag storage remains outside the base company index and is implemented in Phase 6.
- The deterministic `/search` and `/facets` endpoints should ship before neural retrieval becomes required for the UI path.
- Agent-driven search may reuse these contracts later, but these stories keep the deterministic and hybrid search layers explicit and separable.
