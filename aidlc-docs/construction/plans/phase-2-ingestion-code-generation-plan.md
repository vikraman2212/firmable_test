# Phase 2 Ingestion Code Generation Plan

## Unit Context

- **Unit Name**: phase-2-ingestion-foundation
- **Stories Implemented**: Canonical schema, normalization, staged artifacts, seed flow, incremental sync
- **Dependencies**: Phase 1 OpenSearch template, pipelines, aliases, and local infrastructure
- **Owned Scope**: `app/models/`, `app/ingestion/`, ingestion docs, and ingestion-focused tests

## Planning Assumptions

- The first implementation slice should prioritize a thin but runnable ingestion path over a fully optimized batch architecture.
- The canonical schema should stay aligned with `app/search/index_template.json` and avoid fields that are not required for the initial search slice.
- Phase 2 should produce deterministic local artifacts so Phase 3 can build against stable seeded data.

## Detailed Steps

### P2-T01 Define canonical company schema

- [x] Create `app/models/company.py` with a canonical company document model for indexing and API-safe reuse.
- [x] Align field names and optionality with the strict OpenSearch template.
- [x] Exclude tags and unsupported source-only fields from the base company schema.
- [x] Add validation rules for identifiers, normalized location fields, and numeric estimates.
- [x] Add unit tests for required and optional field behavior.

### P2-T02 Build configurable CSV reader

- [x] Create `app/ingestion/normalize.py` with a configurable CSV reader entry point.
- [x] Support row-limit based local runs and explicit source-file selection.
- [x] Map raw source columns into a canonical intermediate shape before validation.
- [x] Add unit tests covering subset reads, missing columns, and row-limit behavior.

### P2-T03 Normalize location and numeric fields

- [x] Implement normalization helpers for null handling, locality parsing, founded year cleanup, and employee estimate coercion.
- [x] Produce stable `city`, `region`, and `country` fields from raw locality inputs.
- [x] Keep malformed but recoverable source data visible in validation output instead of silently dropping it.
- [x] Add unit tests for malformed years, blank locality values, and numeric coercion edge cases.

### P2-T04 Generate stable company identifiers and semantic text

- [x] Define stable `company_id` generation rules with explicit precedence from source identifiers and normalized fallbacks.
- [x] Preserve canonical domain values for exact matching.
- [x] Generate `company_semantic_text` from the normalized company attributes needed by embeddings.
- [x] Add unit tests for identifier stability and semantic text composition.

### P2-T05 Write staged Parquet output

- [x] Write normalized valid records to a deterministic staged Parquet artifact.
- [x] Keep artifact naming stable enough for local replay and debugging.
- [x] Return artifact metadata needed by seed and sync commands.
- [x] Add tests that verify staged artifact creation and deterministic layout.

### P2-T06 Emit validation and dead-letter artifacts

- [x] Emit rejected rows to a dead-letter artifact with explicit failure reasons.
- [x] Emit a machine-readable validation summary for each normalization run.
- [x] Document artifact outputs and operator workflow in ingestion documentation.
- [x] Add tests covering rejected-row capture and summary generation.

### P2-T07 Implement seed flow with alias swap

- [x] Create `app/ingestion/seed.py` to normalize input, apply the template, create a write index, and bulk index staged records.
- [x] Route seed indexing through the default embedding pipeline.
- [x] Swap read and write aliases safely after a successful load.
- [x] Add a focused test surface for request construction and alias-swap sequencing.

### P2-T08 Implement incremental sync flow

- [ ] Create `app/ingestion/sync.py` for idempotent upserts by `company_id`.
- [ ] Support skip-existing behavior where embeddings do not need to be recomputed.
- [ ] Support optional soft-delete handling for records missing from the source snapshot.
- [ ] Add focused tests for upsert, unchanged-row skip logic, and soft-delete selection.

## Proposed Implementation Order

- [x] Slice 1 (started): P2-T01 complete. P2-T02–P2-T04 in progress.
- [x] Slice 2 (P2-T05 done): P2-T05 complete. P2-T06 in progress.
- [ ] Slice 3: P2-T07 seed flow against the existing local OpenSearch stack.
- [ ] Slice 4: P2-T08 incremental sync once the seed path is stable.

## Readiness Notes

- OpenSearch 3.1.0 and Dashboards 3.1.0 are already healthy locally.
- The next concrete implementation step should be P2-T01 because every later Phase 2 task depends on the canonical model.
- The biggest open design choices are identifier fallback precedence, artifact paths, and sync delete semantics.
