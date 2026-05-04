# Phase 2 Groomed Stories

## Story P2-T01: Canonical Company Schema

- **Backlog mapping**: `P2-T01`
- **Persona**: Search Platform Engineer, Data Engineer, API and Search Developer
- **Story**: As a search platform engineer, I want one canonical company schema so ingestion, indexing, and API layers all depend on the same normalized field contract.

### Acceptance Criteria

- The schema defines the canonical company fields required by the current OpenSearch template.
- Optional versus required fields are explicit and testable.
- Unsupported source-only fields are not carried into the canonical model.
- The base company schema does not include tag fields.

## Story P2-T02: Configurable CSV Reader

- **Backlog mapping**: `P2-T02`
- **Persona**: Data Engineer, Ingestion Operator
- **Story**: As a data engineer, I want a configurable CSV reader so I can run small local subsets and full-file normalization through the same code path.

### Acceptance Criteria

- The normalization entry point accepts an explicit source file path.
- A row-limit or equivalent subset option is available for local iteration.
- Missing or renamed source columns fail with actionable validation errors.
- The reader emits a stable intermediate shape for downstream normalization.

## Story P2-T03: Location and Numeric Normalization

- **Backlog mapping**: `P2-T03`
- **Persona**: Data Engineer, API and Search Developer
- **Story**: As a data engineer, I want location and numeric fields normalized so downstream search filters can rely on consistent geography and estimate values.

### Acceptance Criteria

- Raw locality values are normalized into stable `city`, `region`, and `country` fields when recoverable.
- Malformed founded years are repaired when possible and rejected when not trustworthy.
- Employee estimate fields are coerced into consistent numeric values.
- Invalid or missing values remain visible through validation output rather than being silently hidden.

## Story P2-T04: Stable Identifiers and Semantic Text

- **Backlog mapping**: `P2-T04`
- **Persona**: Search Platform Engineer, API and Search Developer
- **Story**: As a search engineer, I want stable company identifiers and embedding source text so indexed companies can be updated reliably and searched semantically.

### Acceptance Criteria

- `company_id` generation follows a documented deterministic precedence order.
- The canonical domain value is preserved for exact matching and deduplication.
- `company_semantic_text` is generated from normalized company attributes, not raw source fragments.
- The same input row produces the same identifier and semantic text across reruns.

## Story P2-T05: Staged Parquet Output

- **Backlog mapping**: `P2-T05`
- **Persona**: Data Engineer, Ingestion Operator
- **Story**: As an ingestion operator, I want normalized records written to a staged Parquet artifact so I can replay indexing runs without reparsing the raw CSV.

### Acceptance Criteria

- Successful normalization writes a deterministic Parquet artifact for valid rows.
- Artifact metadata is available to downstream seed and sync commands.
- The staged artifact format is stable enough for local debugging and replay.
- Local runs can distinguish the current staged artifact from dead-letter output.

## Story P2-T06: Validation Summary and Dead-Letter Output

- **Backlog mapping**: `P2-T06`
- **Persona**: Data Engineer, Ingestion Operator
- **Story**: As an ingestion operator, I want rejected rows and validation summaries captured explicitly so bad source data does not fail silently.

### Acceptance Criteria

- Rejected rows are preserved with row-level failure reasons.
- Each normalization run emits a machine-readable validation summary.
- Artifact locations and operator behavior are documented.
- The validation output is usable for iterative cleanup during local development.

## Story P2-T07: Seed Flow with Alias Swap

- **Backlog mapping**: `P2-T07`
- **Persona**: Search Platform Engineer, Ingestion Operator
- **Story**: As a search platform engineer, I want a safe seed flow with alias swap so I can load a fresh index without exposing partial data to readers.

### Acceptance Criteria

- The seed command applies the template and creates a target write index.
- Bulk indexing routes through the configured default embedding pipeline.
- Read and write aliases are updated only after a successful load.
- Seed failures do not leave the read alias pointed at a partial index.

## Story P2-T08: Incremental Sync Flow

- **Backlog mapping**: `P2-T08`
- **Persona**: Search Platform Engineer, Ingestion Operator
- **Story**: As an ingestion operator, I want an incremental sync flow so I can upsert changes efficiently and manage removals without full re-seeding.

### Acceptance Criteria

- Sync operations upsert by stable `company_id`.
- Unchanged records can be skipped when recomputation is unnecessary.
- Missing-record behavior is explicit and configurable.
- Sync behavior is testable without requiring a full production-sized dataset.

## Grooming Notes

- The stories are already small enough to map 1:1 with the current Phase 2 backlog.
- P2-T01 through P2-T04 form the enabling slice and should be treated as the first implementation batch.
- P2-T07 and P2-T08 should not start until the canonical model and staging artifacts are stable.
