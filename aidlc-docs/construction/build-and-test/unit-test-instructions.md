# Unit Test Execution

## Run Unit Tests

### 1. Execute All Unit Tests

```bash
uv run pytest tests/ -v -m "not integration"
```

### 2. Execute the Focused Phase 6 Slice

```bash
uv run pytest tests/test_tags_model.py tests/test_tags_repository.py tests/test_tag_api.py tests/test_search_service.py -q
```

### 3. Review Test Results

- **Expected**: all non-integration tests pass with `0` failures
- **Phase 6 reference check**: the focused tagging slice should pass, matching the latest local verification run
- **Test Coverage**: no enforced coverage threshold is configured in the repo
- **Test Report Location**: console output only unless you pass `--junitxml` or another pytest reporter option explicitly

### 4. Fix Failing Tests

If tests fail:

1. Review the failing traceback in the terminal output
2. Re-run only the failing module or test case
3. Fix the underlying code or fixture issue
4. Re-run the full non-integration command before merging
