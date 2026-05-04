# Story Generation Clarification Questions

I reviewed your answers in `story-generation-plan.md`. Questions 2, 4, and 5 are clear enough to proceed with. Questions 1 and 3 still need a precise decision because they directly affect schema and sync behavior.

## Clarification 1

For `company_id`, what exactly do you mean by "hash of first column and domain"?

A) Hash the raw value from the first CSV column together with normalized domain, and use that as `company_id` for all rows
B) Use the first CSV column as the primary identifier when present; otherwise hash normalized domain with a fallback field set
C) Use the People Data Labs identifier when present; otherwise hash normalized domain with a fallback field set
D) Other (please describe after [Answer]: tag below)

[Answer]: D

Hash the first CSV column value together with the normalized company name so the identifier is deterministic across reruns.

## Clarification 2

For sync deletion behavior, what should happen when a previously indexed company is missing from the latest source snapshot?

A) Mark it soft-deleted automatically during sync when it is missing from the latest snapshot
B) Soft-delete only rows explicitly marked deleted by the source, and ignore missing rows otherwise
C) Upsert changed rows only in Phase 2, and leave deletion handling for a later phase
D) Other (please describe after [Answer]: tag below)

[Answer]: C
