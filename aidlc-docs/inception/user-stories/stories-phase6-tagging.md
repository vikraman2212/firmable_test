# Phase 6 Stories — Personal Tagging and Tag-Backed Retrieval

## Story P6-T01: Separate Tag Storage Strategy

- **Backlog mapping**: `P6-T01`
- **Persona**: API and Search Developer, Search Platform Engineer, Competitor and Relationship Analyst
- **Story**: As an API and search developer, I want tag data stored in a separate index so personal user tags can be added without changing the canonical company document or reindexing company data.

### Acceptance Criteria

- The tagging architecture uses a dedicated OpenSearch tag index rather than embedding tags into the companies index.
- The tag index stores only normalized tag records and lookup metadata needed for lifecycle and retrieval operations.
- The tag index does not duplicate the full company document.
- The architecture explicitly states that full company details are resolved from the companies index by `company_id`.
- The storage decision is documented clearly enough to justify why this is simpler than denormalizing company data into the tag index.

## Story P6-T02: Scoped Tag Schema

- **Backlog mapping**: `P6-T02`
- **Persona**: Market Researcher, API and Search Developer
- **Story**: As a market researcher, I want a stable personal-tag schema so I can create tags against companies and retrieve them consistently later.

### Acceptance Criteria

- The schema includes at least a normalized tag value, display tag value, `company_id`, and local user scope.
- The schema supports the first-release default local user without requiring a real authentication system.
- Tag normalization rules are deterministic and applied consistently to writes and reads.
- The schema leaves room for future scope expansion such as team sharing without forcing that behavior into the first release.
- The schema does not require changes to `app/models/company.py`.

## Story P6-T03: Tag Storage Access Layer

- **Backlog mapping**: `P6-T03`
- **Persona**: API and Search Developer, Search Platform Engineer
- **Story**: As an API and search developer, I want a tag repository over the dedicated tag index so tag records can be created, listed, deleted, and queried by normalized tag name without affecting company indexing.

### Acceptance Criteria

- The repository can create and delete tag records for a company under the default local user scope.
- The repository can resolve all `company_id` values associated with a normalized tag name.
- The repository interface keeps tag-index concerns separate from company-search concerns.
- The repository behavior is deterministic and testable without mutating the companies index.
- The repository does not need a full company payload in the tag index to serve its contract.

## Story P6-T04: Deferred Tag Suggestions

- **Backlog mapping**: `P6-T04`
- **Persona**: Search Platform Engineer
- **Story**: As a search platform engineer, I want tag suggestions treated as a follow-on capability so the first implementation can stay focused on user-entered tags and explicit retrieval behavior.

### Acceptance Criteria

- The first implementation slice does not generate or store tag suggestions.
- The story pack records tag suggestions as a deferred follow-on item rather than silently dropping the backlog task.
- The first implementation remains compatible with a future suggestion source that still keeps tags outside the core company schema.
- Deferring suggestions does not force a redesign of the chosen skinny tag-index architecture.

## Story P6-T05: Tag APIs and Tag-Backed Search

- **Backlog mapping**: `P6-T05`
- **Persona**: Market Researcher, Competitor and Relationship Analyst, API and Search Developer
- **Story**: As a market researcher, I want to create a tag for a company and later retrieve companies by tag name so I can use my own categorization as an explicit search input.

### Acceptance Criteria

- `POST /api/tag/` accepts a body containing `tagName` and `company_id` and creates a normalized tag record for the default local user.
- `GET /tag/{tagName}` queries the tag index by normalized tag name and returns matching companies.
- `GET /tag/{tagName}` resolves full company details from the companies index by `company_id` rather than returning duplicated company payloads stored in the tag index.
- Tag-name search is explicit keyword retrieval on the tag value and does not silently alter the ranking behavior of the standard `/search` endpoint.
- The tag-backed retrieval path keeps the companies index as the source of truth for company details.
- The API surface is simple enough for a minimal first implementation and clear enough to extend later with delete/list variants.

## Scope Notes

- The first Phase 6 implementation is intentionally narrower than the full milestone: it covers personal tags, a default local user, and explicit tag retrieval.
- Team scope, suggestions, and response enrichment remain follow-on capabilities.
- The story pack preserves the architectural boundary that tag data stays outside the canonical company schema and company index template.
- Tag-backed retrieval should compose with the existing search system through `company_id` lookup rather than schema duplication.
