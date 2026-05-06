# End-to-End Test Instructions

## Purpose

Exercise the full browser workflow for Phase 6 tagging from search results through tag retrieval.

## Test Scenario: Search → Select → Tag → Retrieve

### 1. Start the Local App

```bash
make infra-up
make dev
```

Open the UI at `http://127.0.0.1:8000/ui`.

### 2. Run a Search

1. Enter a query such as `information technology`
2. Submit the search
3. Confirm result cards render and each card shows a selection checkbox

### 3. Apply a Tag

1. Select one or more companies from the current result page
2. Enter a tag such as `competitors` in the tag action bar
3. Click `Apply Tag`
4. Confirm the UI shows success or partial-failure feedback without leaving the results page

### 4. Retrieve By Tag

1. Enter the same tag in `Load Companies By Tag`
2. Click `Load Tag`
3. Confirm the results list is replaced with companies returned by `GET /tag/{tagName}`

### 5. Regression Check

1. Run another normal `/search` request from the same UI
2. Confirm the standard results flow still works and tagging has not changed `/search` ranking behavior

## Expected Results

- The UI remains usable on desktop and mobile widths
- Tag controls render in the results panel
- The tag write path succeeds for selected results
- Tag retrieval renders company results rather than raw tag records
- Normal search remains unchanged when tag lookup is not being used

## Cleanup

```bash
make infra-down
```
