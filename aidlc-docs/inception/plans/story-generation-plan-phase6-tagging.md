# Tagging Story Generation Plan

## Goal

Create an implementation-ready story pack for the Phase 6 tagging system, with explicit coverage for personal tag creation, tag retrieval by name, explicit tag-based search, a separate tag index, and the lookup of full company details from the existing companies index.

## Recommended Breakdown Approach

- **Primary approach**: Capability-based by tagging responsibility.
- **Supporting view**: Persona mapping so user workflows and backend boundaries stay equally visible.

## Why This Approach

- The Phase 6 backlog already separates storage strategy, schema, repository work, suggestions, and APIs into distinct responsibilities.
- The first slice is intentionally narrow, so capability-based stories keep the implementation simple and traceable.
- Personas are still important because the feature is directly user-facing even though the architecture is mostly backend-heavy.

## Execution Checklist

- [x] Assess whether user stories add value for Phase 6 tagging.
- [x] Confirm the Phase 6 requirements and architecture direction.
- [x] Confirm there are no remaining clarification questions blocking story generation.
- [x] Draft personas for user-owned tagging, tag-backed search, and operations/development support.
- [x] Draft one groomed story for each relevant Phase 6 backlog item.
- [x] Capture the API contracts `POST /api/tag/` and `GET /tag/{tagName}` in the story acceptance criteria.
- [x] Lock the decision that the tag index stores only tag records and lookup metadata, not duplicated company documents.
- [x] Mark tag suggestions as a deferred follow-on story rather than part of the first implementation slice.
- [ ] Approve the Phase 6 story pack as the basis for implementation.

## Story Artifacts To Maintain

- [x] `aidlc-docs/inception/user-stories/stories-phase6-tagging.md`
- [x] `aidlc-docs/inception/user-stories/personas-phase6-tagging.md`
- [x] Acceptance criteria for each story
- [x] Persona-to-story mapping

## Clarification Status

- No additional clarification questions are required.
- The requirements are concrete enough to generate the story pack without another question round.

## Decision Summary

- Phase 6 uses a separate OpenSearch tag index.
- The tag index stores normalized tag records and lookup metadata only.
- Full company details are resolved from the companies index by `company_id`.
- `POST /api/tag/` creates tags for the default local user in the first release.
- `GET /tag/{tagName}` returns companies associated with that tag for the current user scope.
- Tag-aware search is explicit retrieval/filtering only, with no hidden ranking boost.
- Tag suggestions remain out of the first implementation slice.
