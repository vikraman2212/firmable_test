# Phase 6 Tagging System Requirements Questions

Please answer each question by filling in the letter choice after the `[Answer]:` tag.

Recommended baseline for this repo: keep tags outside the `companies` index, store them in a separate lightweight persistence layer, and enrich search responses by `company_id` after OpenSearch returns the ranked company hits.

## Question 1

What is the first release scope for user-owned tagging?

A) Personal tags only, scoped to a single user
B) Personal tags plus optional team-shared tags
C) Shared tags only for all users
X) Other (please describe after [Answer]: tag below)

[A]:

## Question 2

How should we represent user identity in the first implementation, given the repo does not yet have authentication?

A) Require explicit `user_id` and optional `team_id` fields in tag API requests, with no auth enforcement yet
B) Use a single local default user for all tagging flows in the first release
C) Delay personal scope and treat all tags as global until auth exists
X) Other (please describe after [Answer]: tag below)

[B]:

## Question 3

What level of tag consistency do you want in the first release?

A) Free-form tags, but return suggested canonical tags so users can choose consistent wording
B) Free-form tags with automatic normalization only (for example lowercasing and slugging)
C) Controlled vocabulary only; users must choose from approved tags
X) Other (please describe after [Answer]: tag below)

[B]:

## Question 4

Which storage strategy should we use for the first implementation, while keeping the architecture simple and tags outside the company index?

A) Separate SQLite-backed tag store in the API service, keyed by `company_id`, `user_id`, and tag value
B) Separate OpenSearch tag index, joined in the API by `company_id`
C) Separate Postgres-backed tag store
X) Other (please describe after [Answer]: tag below)

[B]:

## Question 5

How should tags be incorporated back into search in the first release?

A) Return tags on company results and allow explicit tag filters, but do not silently boost ranking
B) Return tags on company results and use matching tags as a ranking boost
C) Use tags only for retrieval and filtering, not for response enrichment
X) Other (please describe after [Answer]: tag below)

[C]:

## Question 6

How should tag suggestions be generated initially?

A) Materialize simple candidate tags during ingestion from normalized industry and geography fields, then let users accept or ignore them
B) Generate suggestions on demand at API time from each company document, without storing suggestion artifacts
C) Do not generate suggestions yet; only store user-entered tags in the first release
X) Other (please describe after [Answer]: tag below)

[C]:

## Question 7

Which implementation depth do you want for the first Phase 6 slice?

A) Thin vertical slice: create/list/delete tags plus search-result enrichment for one user scope
B) Full Phase 6 architecture and contracts up front, then implement in smaller steps
C) Documentation and user stories first, with implementation deferred until after review
X) Other (please describe after [Answer]: tag below)

[C]:

## Question 8

Should security extension rules be enforced for this project?

A) Yes — enforce all SECURITY rules as blocking constraints (recommended for production-grade applications)
B) No — skip all SECURITY rules (suitable for PoCs, prototypes, and experimental projects)
X) Other (please describe after [Answer]: tag below)

[B]:

## Question 9

Should property-based testing (PBT) rules be enforced for this project?

A) Yes — enforce all PBT rules as blocking constraints (recommended for projects with business logic, data transformations, serialization, or stateful components)
B) Partial — enforce PBT rules only for pure functions and serialization round-trips (suitable for projects with limited algorithmic complexity)
C) No — skip all PBT rules (suitable for simple CRUD applications, UI-only projects, or thin integration layers with no significant business logic)
X) Other (please describe after [Answer]: tag below)

[C]:
