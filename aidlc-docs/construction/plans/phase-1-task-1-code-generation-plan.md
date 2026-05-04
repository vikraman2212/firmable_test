# Phase 1 Task 1 Code Generation Plan

## Unit Context

- **Unit Name**: phase-1-task-1-repository-foundation
- **Stories Implemented**: Repository bootstrap for local search infrastructure
- **Dependencies**: None
- **Owned Scope**: Workspace directories and local OpenSearch compose slice

## Detailed Steps

- [x] Step 1: Create repository skeleton directories for `app/`, `web/`, `infra/`, `docs/`, and `tests/`.
- [x] Step 2: Create `infra/docker-compose.yml` for the initial OpenSearch and OpenSearch Dashboards local stack.
- [x] Step 3: Create `infra/opensearch/Dockerfile` referenced by the compose configuration.
- [x] Step 4: Create `infra/opensearch/index.json` as the mounted OpenSearch config artifact.
- [x] Step 5: Create minimal AIDLC state, audit, requirements, and execution-plan artifacts for this slice.
- [x] Step 6: Validate the compose file configuration.
- [x] Step 7: Create `infra/opensearch/bootstrap/setup.sh` to register the embedding model group, register and deploy the model, and create the ingest pipeline.
- [x] Step 8: Validate the setup script with a shell syntax check.
- [x] Step 9: Create a root `Makefile` that orchestrates compose lifecycle, bootstrap flow, and CI-friendly validation targets.
- [x] Step 10: Validate the `Makefile` with a help or validation target.

## Notes

- The compose slice intentionally stops short of ML Commons, Ollama, and bootstrap scripts, which belong to later Phase 1 tasks.
- The new `setup.sh` is a bootstrap utility for later ML-capable local setup and does not yet wire itself into compose startup.
- The `Makefile` is intentionally non-interactive so GitHub Actions can call stable targets such as `ci-validate` and `bootstrap`.
- Paths are organized under `infra/` instead of placing infrastructure files in the repository root.
