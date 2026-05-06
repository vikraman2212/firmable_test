# Build and Test Summary

## Build Status

- **Build Tool**: `uv`, Docker Compose, project Makefile targets
- **Build Status**: Instruction pack generated; latest focused verification checks passed during Phase 6 code generation
- **Build Artifacts**:
  - `.venv/`
  - Docker `firmable-api` image
  - OpenSearch runtime artifacts including search templates and `company_tags` index
- **Build Time**: depends on local Docker bootstrap and whether the embedding model is already cached

## Test Strategy

- **Unit Tests**: `uv run pytest tests/ -v -m "not integration"`
- **Focused Phase 6 Slice**: `uv run pytest tests/test_tags_model.py tests/test_tags_repository.py tests/test_tag_api.py tests/test_search_service.py -q`
- **Integration Tests**: `uv run pytest tests/integration -m integration -v`
- **Performance Tests**: deferred for the current take-home review slice
- **End-to-End Tests**: manual browser workflow at `/ui`

## Latest Validation Snapshot

- Non-integration pytest suite passed locally: `361 passed, 15 deselected`
- Integration pytest suite passed locally: `15 passed`
- Focused Phase 6 backend tests passed locally: `27 passed`
- `node --check web/app.js` passed
- `make script-check` passed
- `make infra-up` rebuilt the API image, deployed the OpenSearch ML model, recreated the runtime templates, and created the `company_tags` index
- `make seed` restored the `companies` index required by `/search` and `/facets`
- Live API verification passed for `GET /health`, `GET /readiness`, `POST /search`, `POST /facets`, and `POST /agent/search`
- Live browser verification at `/ui/` passed for deterministic search, facet loading, company selection, tag application, and tag lookup rendering

## Runtime Issues Resolved During Validation

- Reseeding against an existing OpenSearch index initially failed because the live cluster returned `resource_already_exists_exception` instead of `index_already_exists_exception`; the seed flow now treats both as reusable existing-index cases.
- The containerized API initially failed hybrid search with `Invalid neural query: model_id field can not be empty`; the local deployment now mounts `/tmp/firmable-ml` into the API container so the runtime can resolve the deployed model id from the shared state file.
- The UI initially returned `503` on `/facets` because the `companies` index had not been seeded yet; seeding the dataset restored the deterministic search and facets path.

## Files Generated In This Stage

- `aidlc-docs/construction/build-and-test/build-instructions.md`
- `aidlc-docs/construction/build-and-test/unit-test-instructions.md`
- `aidlc-docs/construction/build-and-test/integration-test-instructions.md`
- `aidlc-docs/construction/build-and-test/performance-test-instructions.md`
- `aidlc-docs/construction/build-and-test/e2e-test-instructions.md`
- `aidlc-docs/construction/build-and-test/build-and-test-summary.md`

## Recommended Review Order

1. Build instructions
2. Unit and integration test instructions
3. E2E instructions
4. Summary file
