# Phase 4 Personas

## Persona 1: Sales Researcher

- **Goal**: Quickly find target companies that match a named market segment, geography, and size profile so they can build a prospect list without writing any queries.
- **Primary concerns**: Filter combinations must be intuitive, result cards must surface the decision-relevant fields (industry, location, size, employees, founded), and the page must respond fast enough that they can iterate filters without waiting.
- **Relevant stories**: P4-T01, P4-T03, P4-T04.

## Persona 2: Business Analyst

- **Goal**: Explore the dataset to understand industry distribution, geographic spread, and company density before deeper analysis.
- **Primary concerns**: Being able to narrow down results with multiple simultaneous filters (industry + size + country), see result counts per filter state, and scan cards for outliers.
- **Relevant stories**: P4-T01, P4-T02, P4-T04.

## Persona 3: Front-End Developer

- **Goal**: Ship a maintainable, vanilla JS UI that calls only the deterministic API endpoints, loads fast with no build step, and degrades gracefully when the API is unavailable.
- **Primary concerns**: Clear state model, predictable DOM update cycle, debounce hygiene, and error-state coverage.
- **Relevant stories**: P4-T01, P4-T02, P4-T03, P4-T04.
