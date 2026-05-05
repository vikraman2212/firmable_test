# Search Story Refinement Plan

## Goal

Create an implementation-ready story pack for the Phase 3 Search API and the Phase 5 intelligent-search slice, with explicit coverage for deterministic facets, aggregation queries, normalized semantic input, and hybrid BM25 plus neural retrieval.

## Recommended Breakdown Approach

- **Primary approach**: Capability-based by search responsibility.
- **Supporting view**: Persona mapping so the deterministic UI path and the neural retrieval path stay grounded in user and operator outcomes.

## Why This Approach

- The backlog already separates deterministic search infrastructure from hybrid neural retrieval, so the story pack should preserve that boundary.
- The normalized company schema and `company_semantic_text` are already defined in Phase 2, so the search stories can depend on those artifacts instead of reopening ingestion design.
- Facets and aggregations must remain predictable for the UI even after neural search is added, which makes a capability-based split clearer than a user-journey-only breakdown.

## Execution Checklist

- [x] Review the backlog tasks for Phase 3 and Phase 5 search-related work.
- [x] Confirm that normalized company attributes and `company_semantic_text` are already planned as the embedding source.
- [x] Lock the decision that neural search is in scope for the intelligent-search slice.
- [x] Draft personas for deterministic search, faceted analysis, and search operations.
- [x] Draft stories for deterministic query planning, faceted query construction, aggregation counts, semantic field readiness, and hybrid retrieval.
- [x] Capture the constraint that tag filtering remains external to the core company index until the Phase 6 tagging system exists.
- [ ] Approve the search story pack as the basis for Phase 3 and Phase 5 implementation.

## Story Artifacts To Maintain

- [x] `aidlc-docs/inception/user-stories/stories-phase3-phase5.md`
- [x] `aidlc-docs/inception/user-stories/personas-phase3-phase5.md`
- [x] Acceptance criteria for each story
- [x] Persona-to-story mapping

## Refinement Inputs Confirmed

- Neural search is in scope.
- The normalized search document shape and semantic-text generation are already planned and partially implemented in Phase 2.
- The search text must be evaluated across all relevant fields, with strongest weighting toward the semantic field.
- Facet and aggregation behavior must cover location, industry, company size, founding year, and tags.
- Search and facet execution should prefer named OpenSearch search templates created during infra bootstrap or deterministic API initialization, not handwritten inline DSL assembly in request handlers.
- Tags remain outside the core company index and must be treated as an external or deferred facet source until Phase 6.

## Decision Summary

- Phase 3 remains the deterministic API layer for request contracts, query planning, search execution, and facet aggregation.
- Phase 5 adds hybrid BM25 plus neural retrieval on top of the same normalized request and filter model.
- `company_semantic_text` is the primary text field for semantic matching and should be derived only from normalized company attributes.
- Facet counts must be filter-aware and query-aware, so aggregation requests must reuse the active text query and all currently selected filters.
- Phase 3 should treat search templates as deployable artifacts that are registered at startup and invoked with planner-generated parameters from the API.
- Tag facets must not force tag data into the base company index; the contract should allow a separate tag source to participate later.
