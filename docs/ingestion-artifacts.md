# Ingestion Artifacts

Each run of `stage_companies()` writes three artifacts to the configured
`output_dir` (default: `data/staged/`). All three files share the same
UTC timestamp suffix so they can be correlated unambiguously.

## Artifact Inventory

| File pattern                   | Format           | Purpose                                     |
| ------------------------------ | ---------------- | ------------------------------------------- |
| `companies_<ts>.parquet`       | Parquet (Snappy) | Valid normalized records ready for indexing |
| `dead_letter_<ts>.jsonl`       | JSONL            | Rejected rows with explicit failure reasons |
| `validation_summary_<ts>.json` | JSON             | Machine-readable run statistics             |
| `latest.parquet`               | Symlink          | Points to the most recent Parquet artifact  |

`<ts>` is a UTC timestamp in `YYYYMMDDTHHMMSSz` format
(e.g. `20260504T083012Z`).

---

## `companies_<ts>.parquet`

Snappy-compressed Parquet file. Schema aligns exactly with the OpenSearch
index template defined in `app/search/index_template.json`.

### Columns

| Column                      | Type   | Nullable | Notes                                                 |
| --------------------------- | ------ | -------- | ----------------------------------------------------- |
| `company_id`                | string | no       | SHA-256 hex derived from source_id + normalized name  |
| `name`                      | string | no       | Lower-cased, stripped                                 |
| `domain`                    | string | yes      | Lower-cased, stripped                                 |
| `industry`                  | string | yes      | Lower-cased, stripped                                 |
| `size_range`                | string | yes      | Preserved casing (e.g. `10001+`)                      |
| `city`                      | string | yes      | From locality split                                   |
| `region`                    | string | yes      | From locality split                                   |
| `country`                   | string | yes      | Locality-derived; falls back to source country column |
| `year_founded`              | int32  | yes      | Parsed from float string                              |
| `current_employee_estimate` | int32  | yes      |                                                       |
| `total_employee_estimate`   | int32  | yes      |                                                       |
| `linkedin_url`              | string | yes      | Stripped, original casing                             |
| `company_semantic_text`     | string | no       | Free-text for embedding pipeline                      |

### Usage

```python
import pyarrow.parquet as pq
table = pq.read_table("data/staged/latest.parquet")
df = table.to_pandas()
```

---

## `dead_letter_<ts>.jsonl`

One JSON object per line. Empty file when all rows are valid.

### Line schema

```json
{
  "source_id": "5872184",
  "raw_name": "",
  "reason": "blank name after normalization"
}
```

| Field       | Description                                                   |
| ----------- | ------------------------------------------------------------- |
| `source_id` | Unnamed first column from the source CSV (raw integer string) |
| `raw_name`  | Raw name value from the source row                            |
| `reason`    | Human-readable rejection reason                               |

### Operator workflow

1. After a staging run, check `skipped_rows` in `StagingResult` or in the
   validation summary.
2. If `skipped_rows > 0`, open `dead_letter_<ts>.jsonl` to inspect rejections.
3. Common fixes:
   - `"blank name after normalization"` — source row has no company name;
     investigate upstream data quality or exclude deliberately unnamed rows.
4. Re-run staging after fixing source data; compare `validation_summary`
   files across runs to track improvement.

---

## `validation_summary_<ts>.json`

Single JSON object summarising the entire run.

### Schema

```json
{
  "run_timestamp": "2026-05-04T08:30:12+00:00",
  "csv_path": "/path/to/companies_sorted.csv",
  "parquet_path": "/path/to/data/staged/companies_20260504T083012Z.parquet",
  "dead_letter_path": "/path/to/data/staged/dead_letter_20260504T083012Z.jsonl",
  "total_rows_read": 7173440,
  "valid_rows_written": 7173410,
  "skipped_rows": 30,
  "success_rate": 0.9999958,
  "skip_reason_counts": {
    "blank name after normalization": 30
  }
}
```

| Field                | Type            | Description                                            |
| -------------------- | --------------- | ------------------------------------------------------ |
| `run_timestamp`      | ISO 8601 string | UTC start time of the run                              |
| `csv_path`           | string          | Absolute path to the source CSV                        |
| `parquet_path`       | string          | Absolute path to the written Parquet file              |
| `dead_letter_path`   | string          | Absolute path to the dead-letter JSONL file            |
| `total_rows_read`    | int             | Rows read from the CSV (excluding header)              |
| `valid_rows_written` | int             | Rows written to Parquet                                |
| `skipped_rows`       | int             | Rows rejected (written to dead-letter)                 |
| `success_rate`       | float           | `valid_rows_written / total_rows_read`; 0.0 if no rows |
| `skip_reason_counts` | object          | Count of rejections keyed by reason string             |

---

## Local subset runs

Pass `row_limit` to `stage_companies` to process only the first N rows.
This is useful for fast iteration and debugging without reading the full
7 M-row dataset:

```python
from pathlib import Path
from app.ingestion.stage import stage_companies

result = stage_companies(
    csv_path=Path("data/companies_sorted.csv"),
    output_dir=Path("data/staged"),
    row_limit=10_000,
)
print(result.valid_rows_written, "rows written")
print(result.skipped_rows, "rows skipped")
```

---

## Scaling notes

- Parquet Snappy compression reduces artifact size by ~60-70 % vs CSV.
- The `data/staged/` directory accumulates one set of three files per run.
  Operators should prune old artifacts on a schedule (e.g. keep the last N
  runs) to avoid unbounded disk growth.
- For the full 7 M-row dataset, staging takes roughly 3-5 minutes on a
  laptop; peak memory is dominated by the in-memory `records` list. A
  future optimisation is to write Parquet in batches (row groups) rather
  than accumulating all records in memory.
