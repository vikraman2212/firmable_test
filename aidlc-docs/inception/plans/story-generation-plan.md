# Story Generation Plan

## Goal

Create a Phase 2 story pack that is implementation-ready for the staged ingestion milestone and traceable to `P2-T01` through `P2-T08`.

## Recommended Breakdown Approach

- **Primary approach**: Feature-based by ingestion capability.
- **Supporting view**: Persona mapping so each story reflects who benefits from the behavior.

## Why This Approach

- Phase 2 tasks already form a clean capability sequence from schema to sync.
- A feature-based breakdown matches the execution order and keeps traceability to the task backlog simple.
- Persona mapping adds useful acceptance criteria without forcing artificial user-journey stories onto a backend slice.

## Execution Checklist

- [x] Assess whether user stories add value for Phase 2.
- [x] Identify the personas affected by staged ingestion.
- [x] Draft one groomed story for each Phase 2 task.
- [x] Add acceptance criteria focused on data quality, repeatability, and operational safety.
- [x] Map each story back to the corresponding backlog item.
- [x] Resolve the open decisions captured below.
- [ ] Approve the story pack as the basis for code generation.

## Story Artifacts To Maintain

- [x] `aidlc-docs/inception/user-stories/stories.md`
- [x] `aidlc-docs/inception/user-stories/personas.md`
- [x] Acceptance criteria for each story
- [x] Persona-to-story mapping

## Open Decisions

## Question 1

What should be the primary source for `company_id` when the raw dataset provides multiple possible identifiers?

A) Use the People Data Labs company identifier whenever present, with a deterministic fallback only when absent
B) Derive a normalized identifier from domain first, then fall back to source identifiers
C) Derive a normalized identifier from name plus location fields for all rows, regardless of source IDs
D) Other (please describe after [Answer]: tag below)

[Answer]: D

Hash the first CSV column value together with the normalized company name, for example `5872184` + `ibm`, so the generated identifier stays deterministic across re-ingestion.

## Question 2

Where should staged Parquet and dead-letter artifacts live for the first local implementation?

A) Under a new top-level `data/staged/` path outside application code
B) Under a new top-level `artifacts/ingestion/` path for clearer operational separation
C) Under a configurable temp-style path with a documented default
D) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 3

How should the first sync implementation handle records that disappear from the latest source snapshot?

A) Soft-delete them only when an explicit flag is enabled
B) Always soft-delete missing records during sync
C) Never soft-delete in Phase 2; only upsert changed records
D) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 4

What level of Phase 2 implementation depth do you want first?

A) Thin vertical slice: make seed flow work end-to-end on a small subset, then harden it
B) Schema and normalization first with strong tests before any real indexing flow
C) Full Phase 2 implementation plan up front, then execute in the proposed slices
D) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 5

What should count as the first "done" milestone for Phase 2?

A) Valid normalized records and staged Parquet output
B) A successful seed run into OpenSearch with alias swap
C) Both staged artifacts and a successful seed run on a local subset
D) Other (please describe after [Answer]: tag below)

[Answer]: C

## Resolved Decision Summary

- `company_id`: deterministically hash the first CSV column value together with the normalized company name.
- Staged artifacts: store under `data/staged/`.
- Sync behavior in Phase 2: upsert changed records only; do not handle missing-row deletes.
- Initial implementation depth: schema and normalization first with strong tests before real indexing flow.
- First Phase 2 done milestone: both staged artifacts and a successful seed run on a local subset.
