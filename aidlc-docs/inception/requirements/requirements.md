# Requirements

## Intent Analysis Summary

- **User request**: Implement Task 1 using AIDLC by creating the repository foundation, specifically including an infra folder and a Docker Compose file for local OpenSearch and OpenSearch Dashboards.
- **Request type**: New project bootstrap
- **Scope estimate**: Single component with repository skeleton impact
- **Complexity estimate**: Simple
- **Requirements depth**: Minimal
- **Clarifying questions**: Skipped because the request is concrete and implementation-scoped

## Functional Requirements

- Create the baseline repository directories needed by the plan: `app/`, `web/`, `infra/`, `docs/`, and `tests/`.
- Create `infra/docker-compose.yml` as the first local infrastructure entry point.
- Include an `opensearch` service configured for single-node local development.
- Include an `opensearch-dashboards` service connected to the local OpenSearch node.
- Preserve the user-requested local ports: `9200`, `9300`, and `5601`.
- Mount an index configuration JSON file into the OpenSearch container so the compose slice has a stable config artifact to evolve later.
- Provide the referenced Docker build file required by the compose configuration.
- Create a bootstrap setup script that waits for OpenSearch readiness, registers the embedding model group, registers and deploys the embedding model, and creates an ingest pipeline.
- Create a root `Makefile` that standardizes local infra commands and exposes non-interactive targets suitable for GitHub Actions.

## Non-Functional Requirements

- Keep the implementation minimal and easy to extend into the later ML-capable OpenSearch setup.
- Use stable file paths under the workspace root, not under `aidlc-docs/`.
- Keep the compose slice syntactically valid so it can be checked with a compose config command.
- Avoid adding unrelated application code in this step.

## Constraints

- This step implements the repository-foundation slice, not the full ML bootstrap or Ollama integration.
- The compose file should stay close to the user-provided structure while fitting the new `infra/` directory layout.

## Acceptance Criteria

- The repository contains the requested base directories.
- `infra/docker-compose.yml` exists and defines the two requested services.
- Supporting files referenced by the compose file exist.
- The compose file passes a configuration validation command.
- `infra/opensearch/bootstrap/setup.sh` exists and passes a shell syntax validation command.
- `Makefile` exists and exposes validation and bootstrap targets that can be invoked from local development or CI.
