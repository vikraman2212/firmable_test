# Performance Test Instructions

## Purpose

Performance testing is deferred for the current take-home review slice.

## Current Decision

- No performance validation is required to accept the current Build and Test stage.
- The current priority remains correctness of the search, tagging, and browser interaction flows.
- If performance work is needed later, treat this file as a placeholder for a future load-test plan rather than an immediate execution checklist.

## Future Starting Point

If performance validation is added later, start with these targets:

- Search path toward `60` requests/second
- Facet path toward `60` parallel filter operations
- Optional AI-assisted path toward `30` requests/second with fallback documented

## Suggested Future Tooling

- `hey` or `k6` for HTTP load generation
- `make infra-logs` plus API logs for bottleneck inspection
- Seeded local company data before any future load run

## Current Status

- Performance tests are intentionally not part of the required verification path for this stage.
