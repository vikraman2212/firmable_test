# Integration Test Instructions

## Purpose

Validate the real interaction points between ingestion code, OpenSearch, the API service, and the Phase 6 tag retrieval path.

## Test Scenarios

### Scenario 1: Ingestion seed and sync ↔ OpenSearch

- **Description**: verify the Parquet seed and sync flows work against a live OpenSearch node
- **Setup**: start the local OpenSearch stack
- **Test Steps**:
  1. Run `make infra-up`
  2. Run `uv run pytest tests/integration -m integration -v`
- **Expected Results**:
  - seed creates indices and indexes the expected document count
  - sync upserts changed documents and soft-deletes missing documents when requested
  - tests skip automatically if OpenSearch is unreachable
- **Cleanup**: `make infra-down`

### Scenario 2: API tag creation ↔ companies index lookup

- **Description**: verify that `POST /api/tag/` writes skinny tag records and `GET /tag/{tagName}` enriches through the companies index
- **Setup**:
  1. Start the local stack with `make infra-up`
  2. Start the API locally with `make dev` or use the running container on port `8000`
  3. Seed company data if the `companies` index is empty
- **Test Steps**:
  1. Create a tag:

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/tag/ \
  -H 'Content-Type: application/json' \
  -d '{"tagName":"competitors","company_id":"<known-company-id>"}' | jq .
```

2. Retrieve tagged companies:

```bash
curl -fsS http://127.0.0.1:8000/tag/competitors | jq .
```

- **Expected Results**:
  - the POST response returns the normalized tag metadata
  - the GET response returns full company objects via `company_id` lookup, not skinny tag records
- **Cleanup**:

```bash
make infra-down
```

## Setup Integration Test Environment

### 1. Start Required Services

```bash
make infra-up
```

### 2. Configure Service Endpoints

```bash
export API_URL=http://127.0.0.1:8000
export OPENSEARCH_URL=http://127.0.0.1:9200
```

## Run Integration Tests

### 1. Execute Automated Integration Test Suite

```bash
uv run pytest tests/integration -m integration -v
```

### 2. Verify Service Interactions

- **Test Scenarios**:
  - ingestion seed and sync against live OpenSearch
  - tag create plus tag lookup against the API
- **Expected Results**:
  - all integration tests pass or skip cleanly when OpenSearch is unavailable
  - API responses return valid JSON and the tag lookup path returns enriched company results
- **Logs Location**:
  - `make infra-logs`
  - API stdout when running `make dev`

### 3. Cleanup

```bash
make infra-down
```
