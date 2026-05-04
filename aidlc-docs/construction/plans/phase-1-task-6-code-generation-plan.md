# Phase 1 Task 6 — Code Generation Plan

## Create cluster settings bootstrap script

### Steps

- [x] 1. Create `infra/opensearch/bootstrap/00-cluster-settings.sh` — wait for cluster health then PUT /\_cluster/settings with ML Commons transient settings
- [x] 2. Make the script executable (chmod +x)
- [x] 3. Add `CLUSTER_SETTINGS_SCRIPT` variable to Makefile
- [x] 4. Add `cluster-settings` Makefile target invoking the new script
- [x] 5. Extend `script-check` to also validate `00-cluster-settings.sh`
- [x] 6. Update `bootstrap` target to run `cluster-settings` before `bootstrap-model`
- [x] 7. Update `dev-setup` target to include `cluster-settings`
- [x] 8. Validate script syntax with `bash -n`
- [x] 9. Update task breakdown JSON (P1-T06 → completed)
- [x] 10. Update aidlc-state.md and append to audit.md
