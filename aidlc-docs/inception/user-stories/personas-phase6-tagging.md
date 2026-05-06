# Phase 6 Tagging Personas

## Persona 1: Market Researcher

- **Goal**: Organize companies into personally meaningful buckets such as competitors, targets, or partners so findings can be revisited quickly.
- **Primary concerns**: Tag creation must be fast, tag names must be easy to search, and saved tags must not require re-running broad free-text searches.
- **Relevant stories**: P6-T02, P6-T03, P6-T05.

## Persona 2: Competitor and Relationship Analyst

- **Goal**: Retrieve all companies attached to a tag such as `competitors` or `potential-partners` without depending on exact company-name recall.
- **Primary concerns**: Tag-name retrieval should be explicit and deterministic, and returned company details must stay current with the main company dataset.
- **Relevant stories**: P6-T01, P6-T03, P6-T05.

## Persona 3: API and Search Developer

- **Goal**: Implement tagging and tag-backed search without polluting the base company schema or duplicating company truth across indexes.
- **Primary concerns**: Clean API contracts, a skinny tag index, stable normalization rules, and simple lookup paths that preserve the existing search architecture.
- **Relevant stories**: P6-T01, P6-T02, P6-T03, P6-T05.

## Persona 4: Search Platform Engineer

- **Goal**: Add tag support in a way that remains easy to operate and extend later to real identity and optional team scope.
- **Primary concerns**: Avoiding reindex pressure on the companies index, keeping data ownership clear, and preserving a straightforward path to future enhancements such as suggestions.
- **Relevant stories**: P6-T01, P6-T03, P6-T04, P6-T05.
