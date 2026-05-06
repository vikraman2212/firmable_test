# Requirements

## Intent Analysis Summary

- **User request**: Extend the system so user input in the form of company tags can be captured and incorporated back into search, while keeping the architecture simple and the implementation not overly complicated.
- **Request type**: Enhancement
- **Scope estimate**: Multiple components across API contracts, search orchestration, storage, documentation, and tests
- **Complexity estimate**: Moderate
- **Requirements depth**: Standard
- **Clarifying questions**: Answered in `aidlc-docs/inception/requirements/requirement-verification-questions.md`

## Interpreted Answer Summary

The answered question file used bracketed option tags such as `[B]:` instead of the usual `[Answer]: B` form. The selections are still clear enough to interpret as the following resolved answers:

- **Q1**: A — personal tags only, scoped to a single user
- **Q2**: B — use a single local default user for the first release
- **Q3**: B — free-form tags with automatic normalization only
- **Q4**: B — separate OpenSearch tag index, joined in the API by `company_id`
- **Q5**: C — use tags for retrieval and filtering only, not for response enrichment
- **Q6**: C — no tag suggestions in the first release
- **Q7**: C — documentation and user stories first, implementation deferred until after review
- **Q8**: B — security extension rules are not enabled for this slice
- **Q9**: C — property-based testing rules are not enabled for this slice

## Functional Requirements

- Support **personal tags only** in the first release.
- Allow users to create, list, and delete tags for a company.
- Expose a tag-creation API compatible with `POST /api/tag/` using a request body that includes `tagName` and `company_id`.
- Expose a tag-search API compatible with `GET /tag/{tagName}` that returns matching companies for the current user scope.
- Use a **single local default user** for the first release because authentication is not yet implemented.
- Normalize free-form tag input consistently, at minimum by trimming, lowercasing, and converting equivalent spellings into a stable stored form.
- Store tags **outside the core `companies` index**.
- Persist tags in a **separate OpenSearch tag index** keyed by company identity plus user scope.
- Keep the separate tag index limited to tag records and lookup keys such as normalized tag value, `company_id`, user scope, and metadata needed for tag lifecycle operations.
- Allow search to incorporate tags through **explicit retrieval and filtering** rather than hidden ranking behavior.
- Support keyword-style search by `tagName` as an explicit tag lookup flow.
- Keep the existing company search path as the ranking authority; tags must only narrow retrieval when a tag-aware filter is present.
- Do **not** attach tags to standard company search results in the first release.
- Do **not** generate tag suggestions in the first release.
- Produce planning artifacts and user stories for the tagging slice before implementation begins.

## Architecture Direction

### Chosen Direction

Use a **separate OpenSearch tag index** and keep the base company index, company schema, and company ingest flow unchanged.

### Rationale

- This preserves the current architectural rule that tags stay outside the core company document.
- It avoids adding a second storage technology such as SQLite or Postgres when OpenSearch is already a required platform dependency.
- It keeps the implementation simple by using the same deployment and operational surface already present in the repo.
- It avoids reindexing company documents whenever tags change.

### Planned Search Integration

- Add a dedicated tag repository layer that reads and writes the separate tag index.
- Add explicit tag-aware query inputs at the API layer.
- Implement `POST /api/tag/` as a write path into the tag index for the default local user.
- Implement `GET /tag/{tagName}` as a two-step read path:
  - query the tag index for matching normalized tag records
  - resolve the resulting `company_id` set against the existing companies index to return full company details
- When tag filters are present, resolve matching `company_id` values from the tag index first.
- Apply those `company_id` constraints to the normal company search path so OpenSearch still ranks only company documents.
- For tag-name search results, do **not** duplicate the entire company document into the tag index; always look up full company details from the companies index.
- Do not use tags for silent boost logic or response decoration in the first release.

### Planned Scope Boundaries

- No changes to `app/models/company.py` for tag fields.
- No changes to the main company index template to embed tag data.
- No background suggestion generation or ingestion-time tag materialization.
- No multi-user or team-sharing semantics in the first release beyond leaving room for future expansion.

## Non-Functional Requirements

- Keep the implementation simple and easy to explain in the take-home review.
- Reuse existing infrastructure wherever possible instead of introducing new operational dependencies.
- Keep tag behavior explicit and deterministic.
- Avoid duplicating full company documents into the tag index, so company truth stays in one place.
- Avoid hidden scoring changes that make search relevance harder to reason about.
- Ensure the first implementation can expand later to real user identity and optional team scope without invalidating the storage model.
- Preserve the existing search baseline when no tag filter is provided.

## Constraints

- Authentication does not yet exist, so the first release must rely on a local default user convention.
- The first release is limited to personal tags only.
- Tag suggestions are explicitly out of scope for the first release.
- Search-result enrichment with tag payloads is explicitly out of scope for the first release.
- The user requested a simple architecture, so the design should avoid adding unnecessary moving parts.
- Security baseline and property-based testing extensions are disabled for this planning slice.

## Acceptance Criteria

- The tagging architecture is documented as a **separate OpenSearch tag index** rather than a company-index extension.
- The first release supports create, list, and delete operations for personal tags under a default local user.
- `POST /api/tag/` is part of the documented first-release contract for creating a tag against a company.
- `GET /tag/{tagName}` is part of the documented first-release contract for retrieving companies by tag name.
- Tag values are stored in a normalized form.
- Tag-aware search works by explicit retrieval or filtering, not by hidden ranking boost.
- The tag index stores tag records and lookup metadata, not duplicated full company documents.
- Full company result payloads for tag-name retrieval are resolved from the existing companies index by `company_id`.
- Standard search results remain unchanged when no tag filter is provided.
- The first release does not add tag fields to the canonical company model or the company index mapping.
- The first release does not emit or store auto-generated tag suggestions.
- The follow-on user stories can be traced cleanly to Phase 6 backlog tasks without requiring a more complex storage architecture.
