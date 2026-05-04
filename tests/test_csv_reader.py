"""Unit tests for the CSV reader layer in app/ingestion/normalize.py (P2-T02).

Covers:
- read_csv_rows yields correct RawCompanyRow values
- row_limit restricts the number of rows yielded
- validate_csv_columns raises on missing columns
- FileNotFoundError for missing CSV path
- Whitespace stripping at read time
- Empty optional fields come through as empty strings (not None) — normalization
  converts them; the reader does not
"""

import csv
import io
from pathlib import Path

import pytest

from app.ingestion.normalize import (
    REQUIRED_SOURCE_COLUMNS,
    RawCompanyRow,
    read_csv_rows,
    validate_csv_columns,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_CSV = FIXTURES / "companies_sample.csv"


# ---------------------------------------------------------------------------
# validate_csv_columns
# ---------------------------------------------------------------------------

class TestValidateCsvColumns:
    def _all_columns(self) -> list[str]:
        """Return the full set of expected column names."""
        return ["", "name", "domain", "year founded", "industry",
                "size range", "locality", "country", "linkedin url",
                "current employee estimate", "total employee estimate"]

    def test_passes_with_all_columns(self):
        validate_csv_columns(self._all_columns())  # should not raise

    def test_raises_on_single_missing_column(self):
        cols = [c for c in self._all_columns() if c != "name"]
        with pytest.raises(ValueError) as exc_info:
            validate_csv_columns(cols)
        assert "'name'" in str(exc_info.value)

    def test_raises_on_multiple_missing_columns(self):
        cols = [c for c in self._all_columns() if c not in ("name", "domain")]
        with pytest.raises(ValueError) as exc_info:
            validate_csv_columns(cols)
        error_text = str(exc_info.value)
        assert "'name'" in error_text
        assert "'domain'" in error_text

    def test_extra_columns_are_ignored(self):
        cols = self._all_columns() + ["extra_column", "another_extra"]
        validate_csv_columns(cols)  # should not raise

    def test_empty_fieldnames_raises(self):
        with pytest.raises(ValueError):
            validate_csv_columns([])

    def test_required_source_columns_covers_unnamed_first_col(self):
        assert "" in REQUIRED_SOURCE_COLUMNS


# ---------------------------------------------------------------------------
# read_csv_rows — basic reading
# ---------------------------------------------------------------------------

class TestReadCsvRowsBasic:
    def test_yields_correct_number_of_rows(self):
        rows = list(read_csv_rows(SAMPLE_CSV))
        assert len(rows) == 3

    def test_first_row_source_id(self):
        rows = list(read_csv_rows(SAMPLE_CSV))
        assert rows[0].source_id == "5872184"

    def test_first_row_name(self):
        rows = list(read_csv_rows(SAMPLE_CSV))
        assert rows[0].name == "ibm"

    def test_first_row_domain(self):
        rows = list(read_csv_rows(SAMPLE_CSV))
        assert rows[0].domain == "ibm.com"

    def test_first_row_year_founded_raw(self):
        rows = list(read_csv_rows(SAMPLE_CSV))
        assert rows[0].year_founded_raw == "1911.0"

    def test_first_row_industry(self):
        rows = list(read_csv_rows(SAMPLE_CSV))
        assert rows[0].industry == "information technology and services"

    def test_first_row_size_range(self):
        rows = list(read_csv_rows(SAMPLE_CSV))
        assert rows[0].size_range == "10001+"

    def test_first_row_locality_raw(self):
        rows = list(read_csv_rows(SAMPLE_CSV))
        assert rows[0].locality_raw == "new york, new york, united states"

    def test_first_row_country_raw(self):
        rows = list(read_csv_rows(SAMPLE_CSV))
        assert rows[0].country_raw == "united states"

    def test_first_row_linkedin_url(self):
        rows = list(read_csv_rows(SAMPLE_CSV))
        assert rows[0].linkedin_url == "linkedin.com/company/ibm"

    def test_first_row_current_employee_estimate_raw(self):
        rows = list(read_csv_rows(SAMPLE_CSV))
        assert rows[0].current_employee_estimate_raw == "274047"

    def test_first_row_total_employee_estimate_raw(self):
        rows = list(read_csv_rows(SAMPLE_CSV))
        assert rows[0].total_employee_estimate_raw == "716906"

    def test_all_rows_are_raw_company_row_instances(self):
        for row in read_csv_rows(SAMPLE_CSV):
            assert isinstance(row, RawCompanyRow)

    def test_third_row_name(self):
        rows = list(read_csv_rows(SAMPLE_CSV))
        assert rows[2].name == "accenture"


# ---------------------------------------------------------------------------
# read_csv_rows — row_limit
# ---------------------------------------------------------------------------

class TestReadCsvRowsRowLimit:
    def test_row_limit_zero_yields_nothing(self):
        rows = list(read_csv_rows(SAMPLE_CSV, row_limit=0))
        assert rows == []

    def test_row_limit_one_yields_one_row(self):
        rows = list(read_csv_rows(SAMPLE_CSV, row_limit=1))
        assert len(rows) == 1
        assert rows[0].name == "ibm"

    def test_row_limit_two_yields_two_rows(self):
        rows = list(read_csv_rows(SAMPLE_CSV, row_limit=2))
        assert len(rows) == 2

    def test_row_limit_larger_than_file_yields_all_rows(self):
        rows = list(read_csv_rows(SAMPLE_CSV, row_limit=1000))
        assert len(rows) == 3

    def test_row_limit_none_yields_all_rows(self):
        rows = list(read_csv_rows(SAMPLE_CSV, row_limit=None))
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# read_csv_rows — error cases
# ---------------------------------------------------------------------------

class TestReadCsvRowsErrors:
    def test_missing_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            list(read_csv_rows(tmp_path / "does_not_exist.csv"))

    def test_missing_column_raises_value_error(self, tmp_path):
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("name,domain\nfoo,bar.com\n", encoding="utf-8")
        with pytest.raises(ValueError) as exc_info:
            list(read_csv_rows(bad_csv))
        assert "missing required columns" in str(exc_info.value)

    def test_empty_file_with_header_yields_nothing(self, tmp_path):
        header = ",name,domain,year founded,industry,size range,locality,country,linkedin url,current employee estimate,total employee estimate\n"
        empty_csv = tmp_path / "empty.csv"
        empty_csv.write_text(header, encoding="utf-8")
        rows = list(read_csv_rows(empty_csv))
        assert rows == []


# ---------------------------------------------------------------------------
# read_csv_rows — whitespace stripping
# ---------------------------------------------------------------------------

class TestReadCsvRowsWhitespaceStripping:
    def _make_csv_with_spaces(self, tmp_path: Path) -> Path:
        content = (
            ",name,domain,year founded,industry,size range,locality,"
            "country,linkedin url,current employee estimate,total employee estimate\n"
            "  99  ,  Acme Corp  ,  acme.com  , 2000.0 , software , 1-10 ,"
            " austin , united states , linkedin.com/company/acme , 10 , 20 \n"
        )
        p = tmp_path / "spaces.csv"
        p.write_text(content, encoding="utf-8")
        return p

    def test_source_id_stripped(self, tmp_path):
        rows = list(read_csv_rows(self._make_csv_with_spaces(tmp_path)))
        assert rows[0].source_id == "99"

    def test_name_stripped(self, tmp_path):
        rows = list(read_csv_rows(self._make_csv_with_spaces(tmp_path)))
        assert rows[0].name == "Acme Corp"

    def test_domain_stripped(self, tmp_path):
        rows = list(read_csv_rows(self._make_csv_with_spaces(tmp_path)))
        assert rows[0].domain == "acme.com"
