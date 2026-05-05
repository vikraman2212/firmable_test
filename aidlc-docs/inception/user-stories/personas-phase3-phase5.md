# Phase 3 and Phase 5 Personas

## Persona 1: Sales Researcher

- **Goal**: Find target companies quickly using natural phrases plus structured filters, without needing to know the exact indexed wording.
- **Primary concerns**: Search should recover relevant companies from semantic phrasing, filters should narrow the result set predictably, and counts should update in a way that makes the query understandable.
- **Relevant stories**: P3-T03, P3-T04, P3-T06, P3-T07, P5-T09.

## Persona 2: Business Analyst

- **Goal**: Explore segments of the company dataset and understand how many companies match each filter combination before exporting or sharing findings.
- **Primary concerns**: Aggregation counts must reflect the active search text and selected filters, location and industry buckets must remain stable, and year-founded ranges must be explorable without manual query writing.
- **Relevant stories**: P3-T04, P3-T07.

## Persona 3: Search Platform Engineer

- **Goal**: Keep the deterministic search path reliable while adding neural retrieval in a way that can degrade gracefully if the model or vector path is unavailable.
- **Primary concerns**: Filter parity between lexical and neural search, explainable ranking, semantic-field stability, and preserving the separation between the company index and external tag storage.
- **Relevant stories**: P3-T03, P3-T04, P3-T05, P5-T08, P5-T09.

## Persona 4: API and Search Developer

- **Goal**: Implement search and facet endpoints against a stable contract that can serve the UI now and support the future agent path later.
- **Primary concerns**: Pure planning logic, reusable query builders, response consistency, and keeping search templates aligned with normalized ingestion outputs.
- **Relevant stories**: P3-T02, P3-T03, P3-T04, P3-T05, P3-T06, P3-T07, P3-T08.
