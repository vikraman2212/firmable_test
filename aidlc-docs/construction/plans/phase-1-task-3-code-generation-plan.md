# Phase 1 Task 3 Code Generation Plan

## Unit Context

- **Unit Name**: phase-1-task-3-opensearch-ml-commons
- **Stories Implemented**: Enable OpenSearch ML Commons for local text embeddings
- **Dependencies**: `P1-T02` completed; full 5-service `infra/docker-compose.yml` present
- **Owned Scope**: `infra/docker-compose.yml` — `opensearch` service `environment` block only; no other files
- **Expected Interfaces and Contracts**:
  - OpenSearch starts with ML Commons permitted on the single ingest/ml node
  - `setup.sh` model registration succeeds without manual cluster-settings API calls at startup
  - No change to ports, volumes, healthcheck, or other services

## ML Commons Environment Variables for This Unit

The following variables must be added to the `opensearch` service environment block:

| Variable                                             | Value     | Reason                                                                                                         |
| ---------------------------------------------------- | --------- | -------------------------------------------------------------------------------------------------------------- |
| `plugins.ml_commons.only_run_on_ml_node`             | `"false"` | Allows ML tasks on the combined data/ingest/ml node (single-node dev stack)                                    |
| `plugins.ml_commons.max_ml_task_per_node`            | `"10"`    | Permits up to 10 concurrent ML tasks; default is 10 but explicit declaration avoids runtime surprises          |
| `plugins.ml_commons.allow_registering_model_via_url` | `"true"`  | Required for registering the HuggingFace sentence-transformer model via URL                                    |
| `plugins.ml_commons.native_memory_threshold`         | `"99"`    | Relaxes the default 90% native-memory guard so local dev doesn't block model load on a memory-constrained host |

## Story Traceability

- **Primary Task**: `P1-T03` - Enable OpenSearch ML Commons for local embeddings
- **Downstream Tasks Enabled**: `P1-T06`, `P1-T07`, `P1-T08` (bootstrap scripts depend on ML Commons being active at node start)

## Detailed Steps

- [x] Step 1: Review the current `opensearch` service environment block and confirm which ML Commons variables are missing.
- [x] Step 2: Add `plugins.ml_commons.only_run_on_ml_node: "false"` to the `opensearch` environment block.
- [x] Step 3: Add `plugins.ml_commons.max_ml_task_per_node: "10"` to the `opensearch` environment block.
- [x] Step 4: Add `plugins.ml_commons.allow_registering_model_via_url: "true"` to the `opensearch` environment block.
- [x] Step 5: Add `plugins.ml_commons.native_memory_threshold: "99"` to the `opensearch` environment block.
- [x] Step 6: Validate the compose file with `docker compose -f infra/docker-compose.yml config` and confirm all four ML Commons variables appear in the rendered `opensearch` environment.
- [x] Step 7: Mark `P1-T03` complete only if all four ML Commons variables are present and `docker compose config` exits without error.
- [x] Step 8: Record the completed ML Commons slice in `planning/firmable-task-breakdown.json`, `aidlc-docs/aidlc-state.md`, and `aidlc-docs/audit.md`.

## Notes

- These are node-start environment variables — they are read by OpenSearch at JVM startup via `opensearch.yml` env interpolation. They cannot be applied via the cluster settings API alone without a restart, so compose is the right place.
- `plugins.ml_commons.only_run_on_ml_node: "false"` is the single most critical setting; without it the ML task dispatcher will refuse to schedule on the combined node and `setup.sh` will fail.
- Cluster-settings bootstrap (transient/persistent settings applied post-start) belongs to `P1-T06`; this task is only the static compose env block.
- Do not modify any other service, volume, network, or the Makefile.
