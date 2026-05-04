# Phase 1 Task 2 Code Generation Plan

## Unit Context

- **Unit Name**: phase-1-task-2-docker-compose-stack
- **Stories Implemented**: Extend the local infrastructure stack beyond the initial OpenSearch slice
- **Dependencies**: `P1-T01` completed; existing `infra/docker-compose.yml`, `Makefile`, and repository skeleton are present
- **Owned Scope**: `infra/docker-compose.yml` only for this unit; no additional app or web source files are created as part of `P1-T02`
- **Expected Interfaces and Contracts**:
  - `opensearch` remains reachable on `9200`
  - `opensearch-dashboards` remains reachable on `5601`
  - `ollama` is exposed on `11434`
  - `api` is exposed on `8000`
  - `web` is exposed on `3000`

## Service Definitions for This Unit

- **ollama**: use the `ollama/ollama` image, expose port `11434`, and attach a persistent named volume for local model cache.
- **api**: add a minimal placeholder service on port `8000` that keeps the stack shape ready for later FastAPI wiring without requiring application implementation in this task.
- **web**: add a minimal placeholder service on port `3000` that keeps the stack shape ready for later static UI wiring without requiring UI implementation in this task.

## Story Traceability

- **Primary Task**: `P1-T02` - Add Docker Compose stack
- **Downstream Tasks Enabled**: `P1-T03`, `P1-T04`, `P1-T05`, `P4-T06`, `P5-T01`

## Detailed Steps

- [x] Step 1: Review the current `infra/docker-compose.yml` and confirm which services already exist versus which services are still missing for `P1-T02`.
- [x] Step 2: Define the missing services explicitly for this task: `ollama` on `11434` with a named model-cache volume, `api` on `8000` as a placeholder local service, and `web` on `3000` as a placeholder local service.
- [x] Step 3: Update `infra/docker-compose.yml` to add the `ollama` service with persistent model cache volume and published port `11434`.
- [x] Step 4: Update `infra/docker-compose.yml` to add a minimal `api` service definition suitable for local development and later FastAPI wiring.
- [x] Step 5: Update `infra/docker-compose.yml` to add a minimal `web` service definition suitable for serving the static UI locally.
- [x] Step 6: Ensure shared network, volume, and environment wiring remain coherent across `opensearch`, `opensearch-dashboards`, `ollama`, `api`, and `web`.
- [x] Step 7: Do not modify `Makefile` as part of `P1-T02` unless compose validation becomes impossible without a path correction; otherwise keep this unit compose-only.
- [x] Step 8: Validate the compose file with `docker compose -f infra/docker-compose.yml config` and confirm the rendered stack contains `opensearch`, `opensearch-dashboards`, `ollama`, `api`, and `web` plus the expected named volumes.
- [x] Step 9: Mark `P1-T02` complete only if `infra/docker-compose.yml` defines the full five-service local stack with ports, volumes, and basic container wiring in place.
- [x] Step 10: Record the completed compose-stack slice in `planning/firmable-task-breakdown.json`, `aidlc-docs/aidlc-state.md`, and `aidlc-docs/audit.md`.

## Notes

- This unit is limited to defining the local service stack. It does not implement the FastAPI app, static UI behavior, or Ollama model pull automation.
- Health checks and startup ordering for new services belong primarily to `P1-T04`; only minimal non-conflicting wiring should be introduced here.
- ML Commons tuning belongs to `P1-T03`; this plan only ensures the required service containers exist in the stack.
- `P1-T02` is not complete if the compose file still defines only the OpenSearch slice; the task requires the full local stack shape even if `api` and `web` are placeholders.
