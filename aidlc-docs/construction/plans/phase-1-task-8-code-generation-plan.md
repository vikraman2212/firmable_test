# Phase 1 Task 8 — Code Generation Plan

## Create ingest pipeline, search pipeline, strict template, and synonyms

### Steps

- [x] 1. Create `app/search/synonyms.txt` — industry/category synonym groups (Solr format, one group per line)
- [x] 2. Create `app/search/index_template.json` — strict mappings, knn_vector (384d), synonym_analyzer, default_pipeline
- [x] 3. Create `app/search/search_pipeline.json` — hybrid normalization+combination pipeline (min_max + arithmetic_mean, weights 0.3 BM25 / 0.7 kNN)
- [x] 4. Create `infra/opensearch/bootstrap/03-create-pipelines.sh` — reads MODEL_ID from state file; creates ingest pipeline, applies index template, creates search pipeline
- [x] 5. Strip ingest pipeline creation from `02-deploy-model.sh` (moves to 03-create-pipelines.sh)
- [x] 6. Add `CREATE_PIPELINES_SCRIPT` Makefile variable; extend `script-check` and `bootstrap-model`
- [x] 7. Validate all scripts with `bash -n` and `make script-check`
- [x] 8. Update task breakdown JSON (P1-T08 → completed)
- [x] 9. Update aidlc-state.md and append to audit.md
