# Phase 3 — Search API — Code Generation Plan

## Unit Summary

| Attribute      | Value |
|----------------|-------|
| Unit name      | Phase 3 — Deterministic Search API |
| Phase          | Construction |
| Story coverage | P3-T03, P3-T04, P3-T05, P3-T06, P3-T07, P3-T08 |
| Status         | Part 2 — Code Generation (in-progress) |

## Stories Implemented

| Story ID | Title |
|----------|-------|
| P3-T03 | Deterministic Query Planner |
| P3-T04 | Reusable Search and Aggregation Templates |
| P3-T05/P3-T06 | Deterministic Search Endpoint (POST /search) |
| P3-T07 | Facet Aggregation Endpoint (POST /facets) |
| P3-T08 | Health and Readiness Endpoints |

## Architectural Constraints (from approved stories)

1. The API executes **named OpenSearch search templates** — it never assembles raw DSL bodies inline.
2. Named templates are **registered at bootstrap or API init**; if already present, the init step verifies them without re-registering.
3. The **deterministic lane** (Phase 3) has **no dependency on Ollama**; it falls back to BM25-only search cleanly.
4. `company_semantic_text` is the primary field for free-text relevance; exact boosts remain available for name and domain.
5. Structured filters are applied as **filter clauses** (not score-driving query clauses).
6. Tag facets return an **explicit empty-state contract** until Phase 6.

## Unit Dependencies

| Dependency | Status |
|------------|--------|
| Phase 2 normalization (identity.py, normalize.py, seed.py) | Complete |
| OpenSearch bootstrap (bootstrap scripts, index template) | Complete |
| app/api/main.py scaffold | Partial (needs /facets, template init) |
| app/api/schemas.py | Partial (needs FacetsRequest, FacetsResponse) |
| app/search/service.py | Scaffold only (all methods raise NotImplementedError) |

---

## Implementation Steps

### Step 1 — Extend API schemas for facets
- [x] Open `app/api/schemas.py`
- [x] Add `FacetsRequest` model: same filter fields as `SearchRequest`, no `query`, no pagination
- [x] Add `FacetBucket` model: `{ "key": str, "count": int }`
- [x] Add `FacetsResponse` model: `{ "industry": list[FacetBucket], "size_range": list[FacetBucket], "country": list[FacetBucket], "city": list[FacetBucket], "year_founded": list[FacetBucket], "tags": list[FacetBucket] }`
- [x] **Story reference**: P3-T07

### Step 2 — Implement deterministic query planner
- [x] Create `app/search/query_planner.py`
- [x] Define `SearchPlan` dataclass/TypedDict: `{ query_text, filters, from_, size }`
- [x] Implement `build_search_plan(request: SearchRequest) -> SearchPlan`:
  - Trim and normalise query text; omit if blank
  - Collect non-empty filter values into a filters dict
  - Industry synonym expansion is handled **at query time by the OpenSearch `synonym_analyzer`** (the index template's named analyzer that chains `standard` → `lowercase` → `industry_synonyms` filter) — the planner passes the raw industry list and the template's `match` clause specifies `analyzer: "synonym_analyzer"`; no Python-side expansion needed
  - Compute `from_` = `(page - 1) * page_size`
- [x] Implement `build_facets_plan(request: FacetsRequest) -> SearchPlan`:
  - Same filter extraction, no pagination, `size=0` (aggregation-only)
- [x] Keep all functions **pure** — no side effects, no I/O
- [x] **Story reference**: P3-T03

### Step 3 — Register named OpenSearch search and aggregation templates (infra)
- [x] Create `infra/opensearch/bootstrap/04-create-search-templates.sh`
> **Phase boundary**: `firmable-search-v1` is **BM25-only** (Phase 3). The `hybrid-search-pipeline` (already created in `03-create-pipelines.sh` — min_max normalization + arithmetic_mean weights [0.3 BM25 : 0.7 kNN]) attaches in Phase 5 when the `hybrid` query type and `neural` sub-query are introduced. Phase 3 template does NOT reference `search_pipeline`.

- [x] Register named **search template** `firmable-search-v1` via `PUT /_scripts/firmable-search-v1`:
  - Top-level `bool.should` with the following scored clauses (all are `should`; filters live in `bool.filter`):
    1. **Broad match**: `multi_match` across `company_semantic_text^5`, `name^3`, `industry^2`, `city`, `region`, `country` using `best_fields` type
    2. **Synonym-expanded industry clause**: `match` on `industry` with `analyzer: "synonym_analyzer"` (defined in the index template `analysis.analyzer` settings — `synonym_analyzer` chains `standard` tokenizer → `lowercase` → `industry_synonyms` filter from `synonyms.txt`); boost `^3`
    3. **Fuzzy name match**: `match` on `name` (mapped as `text`) with `fuzziness: "AUTO"` and `prefix_length: 2`; boost `^4`
    4. **Fuzzy domain match**: `fuzzy` query on `domain` — **not** `match` with fuzziness; `domain` is mapped as `keyword` and `match` + `fuzziness` is ignored on keyword fields; use `fuzzy: { domain: { value: "{{query_text}}", fuzziness: 1, prefix_length: 3 } }`; boost `^3`
    5. **Exact-match boosts**: `term` on `name.keyword` (`^6`) and `term` on `domain` (`^5`) so precise matches rank highest
  - Template parameters: `query_text`, `industry`, `size_range`, `country`, `city`, `year_founded_gte`, `year_founded_lte`
  - All filter params guarded by mustache conditionals `{{#params.field}}...{{/params.field}}` so missing params produce no clause
  - Filters applied as `filter` clauses inside a `bool` query (never affect score)
  - Pagination via `from` and `size` template params
  - Sort support: `_score` desc by default; `minimum_should_match: 1` on the outer `should`
- [x] Register named **aggregation template** `firmable-facets-v1` via `PUT /_scripts/firmable-facets-v1`:
  - Zero hits (`size: 0`)
  - Same filter clause construction as search template
  - `terms` aggregations for `industry`, `size_range`, `country`, `city`
  - `date_histogram` or `range` aggregation for `year_founded`
  - Placeholder empty `tags` aggregation section (returns empty buckets until Phase 6)
- [x] Wire the new script into `infra/opensearch/bootstrap/setup.sh` call sequence
- [x] **Story reference**: P3-T04

### Step 4 — Implement template registration/verification at API startup
- [x] Create `app/search/templates.py`
- [x] Implement `ensure_search_templates(client: OpenSearch) -> None`:
  - Try `GET /_scripts/firmable-search-v1` and `GET /_scripts/firmable-facets-v1`
  - If either is missing, create them using the same DSL as Step 3 (multi_match + fuzzy `match` on `name` + `fuzzy` query on `domain` keyword field + exact-term boosts + `synonym_analyzer` industry clause)
  - Log a warning if templates were absent and had to be created
  - Raise a startup error only if creation also fails (OpenSearch unreachable)
- [x] **Story reference**: P3-T04

### Step 5 — Wire template init into API lifespan
- [x] Edit `app/api/main.py` lifespan function
- [x] After creating the OpenSearch client, call `ensure_search_templates(client)`
- [x] This ensures Phase 3 API can serve requests even without running the bootstrap script
- [x] **Story reference**: P3-T04, P3-T06

### Step 6 — Implement SearchService.search()
- [x] Edit `app/search/service.py`
- [x] Remove `_build_query()` stub (superseded by named templates)
- [x] Implement `search(request: SearchRequest) -> SearchResponse`:
  - Call `build_search_plan(request)` from `query_planner.py`
  - Call `client.search_template(body={"id": "firmable-search-v1", "params": plan.to_params()}, index=self._index)`
  - Map each hit via `_map_hit(hit) -> CompanyResult`
  - Assemble `SearchResponse` with `items`, `total`, `page`, `page_size`, `took_ms`
- [x] Implement `_map_hit(hit: dict) -> CompanyResult`:
  - Extract `_id` → `company_id`
  - Extract `_source` fields into `CompanyResult` fields
  - Gracefully handle optional/missing fields
- [x] **Story reference**: P3-T05, P3-T06

### Step 7 — Implement SearchService.facets()
- [x] Edit `app/search/service.py`
- [x] Implement `facets(request: FacetsRequest) -> FacetsResponse`:
  - Call `build_facets_plan(request)` from `query_planner.py`
  - Call `client.search_template(body={"id": "firmable-facets-v1", "params": plan.to_params()}, index=self._index)`
  - Extract `aggregations` from response
  - Map each aggregation bucket list to `list[FacetBucket]`
  - Return `FacetsResponse` with all facet fields; `tags` returns `[]`
- [x] **Story reference**: P3-T07

### Step 8 — Expose POST /facets endpoint
- [x] Edit `app/api/main.py`
- [x] Import `FacetsRequest`, `FacetsResponse` from `app.api.schemas`
- [x] Add `POST /facets` route calling `svc.facets(request)`
- [x] Return `FacetsResponse`
- [x] **Story reference**: P3-T07

### Step 9 — Strengthen /health and /readiness
- [x] Edit `app/api/main.py`
- [x] Extend `/health` response to include `{"status": "ok", "version": ...}`
- [x] Extend `/readiness`:
  - Check index alias exists via `client.indices.exists_alias(name=settings.index_name)`
  - Report `{"status": "ok", "opensearch": version, "index_ready": bool}`
  - Return 503 when OpenSearch is unreachable or alias missing
- [x] **Story reference**: P3-T08

### Step 10 — Unit tests: query planner
- [x] Create `tests/test_query_planner.py`
- [x] Test: empty request produces plan with no filters, `from_=0`, `size=20`
- [x] Test: query text is trimmed and preserved in plan
- [x] Test: all filter fields are extracted correctly
- [x] Test: industry filter value is passed through as-is (synonym expansion delegated to OpenSearch `synonym_analyzer` at query time)
- [x] Test: blank filter values are omitted from the plan
- [x] Test: `build_facets_plan` returns `size=0`
- [x] **Story reference**: P3-T03

### Step 11 — Unit tests: search service
- [x] Create `tests/test_search_service.py`
- [x] Mock `OpenSearch` client with `unittest.mock.MagicMock`
- [x] Test: `search()` calls `search_template` with correct template id and params
- [x] Test: `search()` maps hits to `CompanyResult` items correctly
- [x] Test: `search()` assembles correct pagination in `SearchResponse`
- [x] Test: `facets()` calls `search_template` with `firmable-facets-v1`
- [x] Test: `facets()` maps aggregation buckets to `FacetsResponse` fields
- [x] Test: `facets()` returns `tags: []` when no tag aggregation data is present
- [x] **Story reference**: P3-T05, P3-T06, P3-T07

### Step 12 — Update task-breakdown status
- [x] Open `planning/firmable-task-breakdown.json`
- [x] Mark P3-T01 through P3-T08 as `"status": "in-progress"` at start of generation
- [x] Update `summary.in_progress_tasks` and `summary.todo_tasks` counts

### Step 13 — Update aidlc-state.md
- [x] Set Working Unit to "Phase 3 — Deterministic Search API"
- [x] Mark Code Generation steps as in-progress
- [x] Record completed tasks as each step finishes

---

## File Targets

| Step | File(s) |
|------|---------|
| 1 | `app/api/schemas.py` (extend) |
| 2 | `app/search/query_planner.py` (create) |
| 3 | `infra/opensearch/bootstrap/04-create-search-templates.sh` (create), `infra/opensearch/bootstrap/setup.sh` (extend) |
| 4 | `app/search/templates.py` (create) |
| 5 | `app/api/main.py` (extend lifespan) |
| 6 | `app/search/service.py` (extend — implement search + _map_hit) |
| 7 | `app/search/service.py` (extend — add facets) |
| 8 | `app/api/main.py` (add /facets route) |
| 9 | `app/api/main.py` (extend /health and /readiness) |
| 10 | `tests/test_query_planner.py` (create) |
| 11 | `tests/test_search_service.py` (create) |
| 12 | `planning/firmable-task-breakdown.json` (update status) |
| 13 | `aidlc-docs/aidlc-state.md` (update status) |

---

## Completion Criteria

- `POST /search` returns ranked `CompanyResult` items using the `firmable-search-v1` named template
- `POST /facets` returns bucketed counts using the `firmable-facets-v1` named template
- `/health` returns 200 unconditionally; `/readiness` checks OpenSearch and index alias
- Named templates are absent from the API code as inline DSL — they are registered externally
- Query planner is a pure function with no side effects
- Unit tests for planner and search service pass with mocked dependencies
- No Ollama dependency in any Phase 3 code path

---

## Phase 5 Hybrid Pipeline — Forward Reference

The `hybrid-search-pipeline` already exists (created in `03-create-pipelines.sh`):

```
normalization-processor:
  normalization: min_max          ← each sub-query's scores normalized to [0,1] independently
  combination: arithmetic_mean
  weights: [0.3, 0.7]            ← 30% BM25 : 70% kNN
```

When Phase 5 adds neural retrieval, the template evolution is:

1. Register `firmable-search-hybrid-v1` using the **`hybrid` query type** (not `bool`):
   - Sub-query 1: `bool` (the same BM25/fuzzy/boost clauses from `firmable-search-v1`)
   - Sub-query 2: `neural` — `{ "company_vector": { "query_text": "{{params.query_text}}", "model_id": "{{params.model_id}}", "k": 50 } }` — the `neural` query type handles embedding at query time via ML Commons; it is the only kNN variant that works inside stored templates because it accepts text, not a pre-computed vector
2. Pass `search_pipeline: "hybrid-search-pipeline"` as a query parameter (or set `index.search.default_pipeline`) — the pipeline applies min_max normalization and combines the two sub-query score sets
3. Phase 3 `firmable-search-v1` is left unchanged and continues to serve as the fallback when Ollama/neural is unavailable
