# Phase 1 Task 7 — Code Generation Plan

## Create embedding model registration and deployment scripts

### Steps

- [x] 1. Create `infra/opensearch/bootstrap/01-register-model.sh` — model group registration + model registration; writes MODEL_ID to a state file
- [x] 2. Create `infra/opensearch/bootstrap/02-deploy-model.sh` — reads MODEL_ID from state file; deploys model + creates ingest pipeline
- [x] 3. Create `infra/ollama/pull-model.sh` — pulls the configured Ollama model into the running container
- [x] 4. chmod +x all three scripts
- [x] 5. Update Makefile: add `OLLAMA_PULL_SCRIPT`, replace `SETUP_SCRIPT` with two-script chain, update `script-check`, `bootstrap-model`, `dev-setup`
- [x] 6. Validate all scripts with `bash -n` and `make script-check`
- [x] 7. Update task breakdown JSON (P1-T07 → completed)
- [x] 8. Update aidlc-state.md and append to audit.md
