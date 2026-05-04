# Phase 2 Personas

## Persona 1: Search Platform Engineer

- **Goal**: Keep the indexed company document shape stable so search behavior and API contracts stay predictable.
- **Primary concerns**: Schema drift, alias safety, field parity with OpenSearch mappings, and replayable seed runs.
- **Relevant stories**: P2-T01, P2-T04, P2-T07, P2-T08.

## Persona 2: Data Engineer

- **Goal**: Convert noisy CSV input into a clean, validated, and reusable staged dataset.
- **Primary concerns**: Source-column mapping, normalization quality, deterministic artifact generation, and dead-letter visibility.
- **Relevant stories**: P2-T01, P2-T02, P2-T03, P2-T05, P2-T06.

## Persona 3: Ingestion Operator

- **Goal**: Run local and repeatable ingestion commands with clear outputs and failure visibility.
- **Primary concerns**: Small-subset runs, artifact locations, validation summaries, and safe alias changes.
- **Relevant stories**: P2-T02, P2-T05, P2-T06, P2-T07, P2-T08.

## Persona 4: API and Search Developer

- **Goal**: Build later search and API slices on top of normalized company data without adding ingestion-specific conditionals.
- **Primary concerns**: Stable identifiers, normalized geography fields, canonical domains, and semantic-text consistency.
- **Relevant stories**: P2-T01, P2-T03, P2-T04.
