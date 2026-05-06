# Phase 6 — Personal Tagging — Code Generation Plan

## Unit Summary

| Attribute      | Value                                                          |
| -------------- | -------------------------------------------------------------- |
| Unit name      | Phase 6 — Personal Tagging and Tag-Backed Retrieval            |
| Phase          | Construction                                                   |
| Story coverage | P6-T01, P6-T02, P6-T03, P6-T05 with P6-T04 explicitly deferred |
| Status         | Part 2 — Complete                                              |

## Stories Implemented By This Unit

| Story ID | Title                          |
| -------- | ------------------------------ |
| P6-T01   | Separate Tag Storage Strategy  |
| P6-T02   | Scoped Tag Schema              |
| P6-T03   | Tag Storage Access Layer       |
| P6-T05   | Tag APIs and Tag-Backed Search |

## Deferred Story

| Story ID | Title                    | Reason Deferred                                            |
| -------- | ------------------------ | ---------------------------------------------------------- |
| P6-T04   | Deferred Tag Suggestions | Explicitly out of scope for the first implementation slice |

## Unit Dependencies

| Dependency                                                             | Status                                |
| ---------------------------------------------------------------------- | ------------------------------------- |
| Existing company search index and search service                       | Complete                              |
| FastAPI application entry point in `app/api/main.py`                   | Complete, will be modified            |
| Existing API schemas in `app/api/schemas.py`                           | Complete, will be extended            |
| Existing static search UI in `web/index.html` and `web/app.js`         | Complete, will be extended in place   |
| Existing OpenSearch bootstrap pattern in `infra/opensearch/bootstrap/` | Complete, will be extended            |
| Search result shaping via `SearchService` and `CompanyResult`          | Complete, reusable for company lookup |

## Architectural Constraints (from approved requirements and stories)

1. Tags stay outside the canonical company schema and the companies index.
2. The tag index stores only skinny tag records and lookup metadata, never duplicated full company documents.
3. Full company details for `GET /tag/{tagName}` come from the existing companies index by `company_id`.
4. The first release uses a default local user and does not add authentication.
5. Tag behavior is explicit retrieval/filtering only; no hidden ranking boost or tag-response enrichment is introduced.
6. Tag suggestions remain out of scope for this implementation slice.
7. Brownfield rule: modify the existing API/search files in place rather than creating a parallel route structure.

## UI Interaction Flow For This Unit

1. The user runs a normal company search from the existing search form and sees result cards in the current results panel.
2. Each result card exposes a company-selection control so the user can select one or more visible companies from the current result page.
3. The results panel exposes a small tagging action bar with a tag-name input and an apply action that is disabled until at least one company is selected.
4. When the user submits a tag, the frontend sends one `POST /api/tag/` request per selected `company_id` using the same tag name, keeping the backend API simple and single-record oriented.
5. After a successful apply action, the UI clears the selection state, shows success or partial-failure feedback, and keeps the search results visible.
6. The UI also exposes a tag lookup control so the user can enter a tag name and load tagged companies through `GET /tag/{tagName}` without changing the normal `/search` ranking path.
7. This first slice stays intentionally simple: current-page selection only, no saved tag suggestions, no batch backend endpoint, and no hidden ranking side effects.

## Database Entities and Interfaces Owned By This Unit

- Tag record model in `app/models/tags.py`
- Tag repository interface and implementation in `app/tags/repository.py`
- Tag bootstrap/index creation artifact in `infra/opensearch/bootstrap/`
- API request/response models for tag operations in `app/api/schemas.py`
- Tag endpoints in `app/api/main.py`
- Company lookup helper reuse or extension in `app/search/service.py`
- Search-result selection and tagging flow in `web/index.html` and `web/app.js`

## Implementation Steps

### Step 1 — Add tag configuration and index naming

- [x] Edit `app/settings.py`
- [x] Add configuration for the tag index name, keeping the default local and simple (for example `company_tags`)
- [x] Add any small helper config needed for the default local user if it belongs in runtime settings
- [x] Keep new settings backward-compatible with the existing app startup path
- [x] **Story reference**: P6-T01, P6-T02

### Step 2 — Create the tag data model

- [x] Create `app/models/tags.py`
- [x] Define a normalized tag record model with at least `tag_name_normalized`, `tag_name_display`, `company_id`, `user_id`, and timestamps
- [x] Add deterministic normalization helpers for tag input
- [x] Leave room for future scope fields without implementing team behavior yet
- [x] Do not modify `app/models/company.py`
- [x] **Story reference**: P6-T02

### Step 3 — Create the tag repository package

- [x] Create `app/tags/__init__.py`
- [x] Create `app/tags/repository.py`
- [x] Implement repository methods for create, delete, list-by-company if needed, and resolve `company_id` values by normalized tag name
- [x] Keep the repository focused on tag-index concerns only
- [x] Ensure repository behavior is deterministic and independent from company-document shaping
- [x] **Story reference**: P6-T03

### Step 4 — Add tag index bootstrap artifact

- [x] Create a new bootstrap script under `infra/opensearch/bootstrap/` for the tag index or tag template
- [x] Define the minimal mapping needed for skinny tag records and normalized lookup
- [x] Wire the bootstrap script into `infra/opensearch/bootstrap/setup.sh`
- [x] Keep the tag index schema minimal and avoid storing company payload fields
- [x] **Story reference**: P6-T01, P6-T03

### Step 5 — Extend API schemas for tag operations

- [x] Edit `app/api/schemas.py`
- [x] Add request and response models for `POST /api/tag/`
- [x] Add response models for tag-name retrieval, preferably reusing `CompanyResult` for returned companies when practical
- [x] Keep contracts aligned with the approved endpoint shapes and first-release scope
- [x] **Story reference**: P6-T02, P6-T05

### Step 6 — Add company lookup helper for tag results

- [x] Edit `app/search/service.py`
- [x] Add a helper to fetch company documents by a list of `company_id` values from the existing companies index
- [x] Reuse existing `CompanyResult` mapping logic where possible
- [x] Keep this helper separate from the main ranked `/search` path so tag retrieval remains explicit and simple
- [x] **Story reference**: P6-T01, P6-T05

### Step 7 — Add tag endpoints to the FastAPI app

- [x] Edit `app/api/main.py`
- [x] Instantiate and wire the tag repository through dependency helpers using the shared OpenSearch client
- [x] Add `POST /api/tag/` to create a normalized tag record for the default local user
- [x] Add `GET /tag/{tagName}` to resolve matching `company_id` values from the tag index and then fetch full company details from the companies index
- [x] Keep implementation in the existing `main.py` file rather than creating a new route tree for this slice
- [x] **Story reference**: P6-T03, P6-T05

### Step 8 — Add UI flow for company selection and tag submission

- [x] Edit `web/index.html`
- [x] Edit `web/app.js`
- [x] Add a per-card company-selection control in the existing search results list
- [x] Add a lightweight tagging action bar in the results area with selected-count feedback, a tag-name input, and an apply action
- [x] Implement the submit flow so the UI iterates over selected companies and calls `POST /api/tag/` once per selected `company_id`
- [x] Add a simple tag lookup control that loads `GET /tag/{tagName}` results into the existing results list
- [x] Keep the flow intentionally simple and static-site friendly: no frontend framework, no batch endpoint, no autocomplete
- [x] **Story reference**: P6-T05

### Step 9 — Add focused unit tests for tag normalization and repository behavior

- [x] Create `tests/test_tags_model.py`
- [x] Create `tests/test_tags_repository.py`
- [x] Test normalization behavior, duplicate-safe creation behavior if applicable, and tag-name lookup by normalized value
- [x] Keep tests independent of the existing company search tests where possible
- [x] **Story reference**: P6-T02, P6-T03

### Step 10 — Add focused API tests for tag endpoints

- [x] Create `tests/test_tag_api.py`
- [x] Test `POST /api/tag/` request validation and success behavior
- [x] Test `GET /tag/{tagName}` resolution flow and company result shaping
- [x] Test not-found or empty-result behavior for unknown tag names
- [x] **Story reference**: P6-T05

### Step 11 — Document and manually validate the UI tagging flow

- [x] Edit `docs/architecture.md`
- [x] Document the chosen UI interaction model: select result cards, enter tag name once, submit per-company API calls, and retrieve tagged companies by tag name
- [x] Add a short manual smoke path for the browser flow rather than introducing a frontend test harness in this slice
- [x] **Story reference**: P6-T05

### Step 12 — Update architecture documentation

- [x] Edit `docs/architecture.md`
- [x] Replace the outdated Phase 6 tagging note with the approved skinny-tag-index plus company-lookup design
- [x] Document the first-release API surface, UI flow, and deferred scope boundaries
- [x] **Story reference**: P6-T01, P6-T05

### Step 13 — Update planning and workflow state artifacts during generation

- [x] Update `planning/firmable-task-breakdown.json` as implementation steps are completed
- [x] Update `aidlc-docs/aidlc-state.md` progress and current status during generation
- [x] Keep the code-generation plan as the source of truth for step completion
- [x] **Story reference**: P6-T01 through P6-T05

## File Targets

| Step | File(s)                                                                                    |
| ---- | ------------------------------------------------------------------------------------------ |
| 1    | `app/settings.py`                                                                          |
| 2    | `app/models/tags.py`                                                                       |
| 3    | `app/tags/__init__.py`, `app/tags/repository.py`                                           |
| 4    | `infra/opensearch/bootstrap/07-create-tag-index.sh`, `infra/opensearch/bootstrap/setup.sh` |
| 5    | `app/api/schemas.py`                                                                       |
| 6    | `app/search/service.py`                                                                    |
| 7    | `app/api/main.py`                                                                          |
| 8    | `web/index.html`, `web/app.js`                                                             |
| 9    | `tests/test_tags_model.py`, `tests/test_tags_repository.py`                                |
| 10   | `tests/test_tag_api.py`                                                                    |
| 11   | `docs/architecture.md`                                                                     |
| 12   | `docs/architecture.md`                                                                     |
| 13   | `planning/firmable-task-breakdown.json`, `aidlc-docs/aidlc-state.md`                       |

## Completion Criteria

- Tag records are modeled and normalized outside the company schema.
- A skinny OpenSearch tag index exists and is bootstrap-managed.
- `POST /api/tag/` creates tag records for the default local user.
- `GET /tag/{tagName}` returns full company details by resolving `company_id` values through the existing companies index.
- The static UI allows the user to select one or more companies from visible search results and apply a tag from the results panel.
- The static UI allows the user to retrieve companies by tag name without altering the existing `/search` contract.
- No full company documents are stored in the tag index.
- Focused unit and API tests cover the first implementation slice.
- Tag suggestions remain unimplemented and explicitly deferred.
