# Phase 1 Task 5 Code Generation Plan

## Unit Context

- **Unit Name**: phase-1-task-5-makefile-workflow-commands
- **Stories Implemented**: Add standard developer workflow commands to the Makefile
- **Dependencies**: `P1-T02`, `P1-T04` completed; full 5-service compose with health checks present
- **Owned Scope**: `Makefile` only — new variables and targets; no changes to scripts, compose, or app code
- **Expected Interfaces and Contracts**:
  - `make ollama-pull` pulls `llama3.1:8b` inside the running `firmable-ollama` container
  - `make seed` runs `app/ingestion/seed.py` with a configurable `CSV` path (default `data/sample.csv`)
  - `make sync` runs `app/ingestion/sync.py` against the live index
  - `make test` runs `pytest` against the `tests/` directory
  - `make dev-setup` is a one-shot local onboarding command combining infra-up + ollama-pull + bootstrap-model
  - All existing targets remain unmodified

## New Variables

| Variable           | Default           | Purpose                                                |
| ------------------ | ----------------- | ------------------------------------------------------ |
| `OLLAMA_MODEL`     | `llama3.1:8b`     | Model name passed to `ollama pull`                     |
| `OLLAMA_CONTAINER` | `firmable-ollama` | Container name for `docker exec`                       |
| `CSV`              | `data/sample.csv` | Input CSV path for `make seed`                         |
| `PYTHON`           | `python`          | Python interpreter (override with `python3` if needed) |

## New Targets

| Target        | Depends On                             | Description                                                    |
| ------------- | -------------------------------------- | -------------------------------------------------------------- |
| `ollama-pull` | —                                      | Pull the LLM model into the running Ollama container           |
| `seed`        | —                                      | Index companies from a CSV file via `app/ingestion/seed.py`    |
| `sync`        | —                                      | Re-sync / incremental index update via `app/ingestion/sync.py` |
| `test`        | —                                      | Run the test suite with pytest                                 |
| `dev-setup`   | `infra-up ollama-pull bootstrap-model` | Full local onboarding in one command                           |

## Story Traceability

- **Primary Task**: `P1-T05` - Add Makefile workflow commands
- **Downstream Tasks Enabled**: `P1-T06`, `P1-T07`, `P1-T08` (developers can now bootstrap and test with single commands)

## Detailed Steps

- [x] Step 1: Review the current `Makefile` and confirm which variables and targets already exist.
- [x] Step 2: Add `OLLAMA_MODEL`, `OLLAMA_CONTAINER`, `CSV`, and `PYTHON` variables after the existing variable block.
- [x] Step 3: Add `ollama-pull`, `seed`, `sync`, `test`, and `dev-setup` to the `.PHONY` declaration.
- [x] Step 4: Implement the `ollama-pull` target using `docker exec $(OLLAMA_CONTAINER) ollama pull $(OLLAMA_MODEL)`.
- [x] Step 5: Implement the `seed` target using `$(PYTHON) app/ingestion/seed.py --csv $(CSV)`.
- [x] Step 6: Implement the `sync` target using `$(PYTHON) app/ingestion/sync.py`.
- [x] Step 7: Implement the `test` target using `$(PYTHON) -m pytest tests/ -v`.
- [x] Step 8: Implement the `dev-setup` target as a phony chain: `infra-up ollama-pull bootstrap-model`.
- [x] Step 9: Validate with `make help` and confirm all new targets appear with descriptions.
- [x] Step 10: Record completion in `planning/firmable-task-breakdown.json`, `aidlc-docs/aidlc-state.md`, and `aidlc-docs/audit.md`.

## Notes

- `seed` and `sync` targets invoke `app/ingestion/seed.py` and `app/ingestion/sync.py` respectively. These scripts do not exist yet (created in later tasks); the Makefile wiring is defined now so callers have a stable interface.
- `dev-setup` does not re-run `infra-up` if the stack is already running; `docker compose up -d` is idempotent.
- Do not modify existing targets (`bootstrap`, `validate`, `ci-validate`, etc.).
