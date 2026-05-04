# Phase 1 Task 4 Code Generation Plan

## Unit Context

- **Unit Name**: phase-1-task-4-healthchecks-startup-ordering
- **Stories Implemented**: Add service health checks and startup ordering to the local stack
- **Dependencies**: `P1-T02` and `P1-T03` completed; full 5-service `infra/docker-compose.yml` present with ML Commons env vars
- **Owned Scope**: `infra/docker-compose.yml` only — healthcheck blocks and `depends_on` condition forms for all five services; no other files
- **Expected Interfaces and Contracts**:
  - `opensearch-dashboards` waits for `opensearch` to be `service_healthy` before starting
  - `api` waits for `opensearch` and `ollama` to be `service_healthy` before starting
  - `web` waits for `api` to be `service_started`
  - `opensearch`, `opensearch-dashboards`, `ollama`, and `api` each declare a `healthcheck`

## Healthcheck Design

| Service                 | Test command                                    | interval | timeout | retries | start_period |
| ----------------------- | ----------------------------------------------- | -------- | ------- | ------- | ------------ |
| `opensearch`            | `curl -f http://localhost:9200/_cluster/health` | 30s      | 30s     | 5       | 60s          |
| `opensearch-dashboards` | `curl -fsS http://localhost:5601/api/status`    | 30s      | 15s     | 5       | 60s          |
| `ollama`                | `curl -fsS http://localhost:11434/`             | 30s      | 10s     | 5       | 30s          |
| `api`                   | `curl -fsS http://localhost:8000/`              | 30s      | 10s     | 3       | 10s          |

## Startup Ordering

| Service                 | depends_on             | condition         |
| ----------------------- | ---------------------- | ----------------- |
| `opensearch-dashboards` | `opensearch`           | `service_healthy` |
| `api`                   | `opensearch`, `ollama` | `service_healthy` |
| `web`                   | `api`                  | `service_started` |

## Story Traceability

- **Primary Task**: `P1-T04` - Add service health checks and startup ordering
- **Downstream Tasks Enabled**: `P1-T05`, `P1-T06` (bootstrap scripts benefit from a reliable startup sequence)

## Detailed Steps

- [x] Step 1: Review the current `infra/docker-compose.yml` and confirm which services are missing healthchecks and which `depends_on` blocks are in bare list form.
- [x] Step 2: Strengthen the `opensearch` healthcheck — add `start_period: 60s` and increase `retries` to `5`.
- [x] Step 3: Add a healthcheck to `opensearch-dashboards` (`/api/status`) and convert its `depends_on` to condition form with `service_healthy`.
- [x] Step 4: Add a healthcheck to `ollama` (`GET /`).
- [x] Step 5: Add a healthcheck to `api` (`GET /`) and convert its `depends_on` to condition form with `service_healthy` for both `opensearch` and `ollama`.
- [x] Step 6: Add `depends_on: api: condition: service_started` to `web`.
- [x] Step 7: Validate with `docker compose -f infra/docker-compose.yml config` and confirm healthcheck and depends_on blocks appear for all relevant services.
- [x] Step 8: Record completion in `planning/firmable-task-breakdown.json`, `aidlc-docs/aidlc-state.md`, and `aidlc-docs/audit.md`.

## Notes

- `start_period` tells Docker to not count failing healthchecks as retries during the grace period — critical for OpenSearch which takes 30-60 s to reach green.
- `web` uses `service_started` (not `service_healthy`) because the placeholder `api` healthcheck is not meaningful for the frontend's actual readiness dependency; this will be tightened when the real FastAPI app lands in P3-T01.
- No Makefile changes are part of this task.
