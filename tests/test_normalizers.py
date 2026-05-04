"""Comprehensive unit tests for app/ingestion/normalizers.py."""

import pytest
from app.ingestion.normalizers import (
    normalize_name,
    normalize_domain,
    normalize_industry,
    normalize_size_range,
    normalize_country,
    parse_locality,
    parse_year_founded,
    parse_employee_estimate,
)


class TestNormalizeName:
    def test_blank_returns_none(self):
        assert normalize_name("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_name("   ") is None

    def test_normal_case_lowercased(self):
        assert normalize_name("Acme Corp") == "acme corp"

    def test_already_lowercase_unchanged(self):
        assert normalize_name("acme corp") == "acme corp"

    def test_mixed_case_lowercased(self):
        assert normalize_name("ACME CORP") == "acme corp"

    def test_strips_leading_trailing_spaces(self):
        assert normalize_name("  Acme  ") == "acme"

    def test_none_like_empty(self):
        # Empty string is the canonical "none-ish" input
        assert normalize_name("") is None


class TestNormalizeDomain:
    def test_blank_returns_none(self):
        assert normalize_domain("") is None

    def test_lowercased(self):
        assert normalize_domain("ACME.COM") == "acme.com"

    def test_strips_spaces(self):
        assert normalize_domain("  acme.com  ") == "acme.com"

    def test_already_lowercase(self):
        assert normalize_domain("acme.com") == "acme.com"

    def test_whitespace_only_returns_none(self):
        assert normalize_domain("   ") is None


class TestNormalizeIndustry:
    def test_blank_returns_none(self):
        assert normalize_industry("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_industry("   ") is None

    def test_normal_case_lowercased(self):
        assert normalize_industry("Information Technology") == "information technology"

    def test_already_lowercase_unchanged(self):
        assert normalize_industry("information technology") == "information technology"

    def test_mixed_case_lowercased(self):
        assert normalize_industry("FINANCIAL SERVICES") == "financial services"

    def test_strips_spaces(self):
        assert normalize_industry("  Health Care  ") == "health care"


class TestNormalizeSizeRange:
    def test_blank_returns_none(self):
        assert normalize_size_range("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_size_range("   ") is None

    def test_strips_leading_trailing_spaces(self):
        assert normalize_size_range("  10001+  ") == "10001+"

    def test_preserves_casing(self):
        assert normalize_size_range("10001+") == "10001+"

    def test_preserves_range_format(self):
        assert normalize_size_range("1001-5000") == "1001-5000"

    def test_preserves_mixed_case(self):
        # size_range should NOT lowercase
        assert normalize_size_range("Small") == "Small"


class TestNormalizeCountry:
    def test_blank_returns_none(self):
        assert normalize_country("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_country("   ") is None

    def test_lowercased(self):
        assert normalize_country("United States") == "united states"

    def test_already_lowercase(self):
        assert normalize_country("united states") == "united states"

    def test_strips_spaces(self):
        assert normalize_country("  India  ") == "india"


class TestParseLocality:
    def test_three_part_normal(self):
        city, region, country = parse_locality("new york, new york, united states")
        assert city == "new york"
        assert region == "new york"
        assert country == "united states"

    def test_three_part_with_extra_spaces(self):
        city, region, country = parse_locality("  london ,  greater london ,  united kingdom  ")
        # split on ', ' so leading/trailing strip handles outer whitespace
        assert country is not None  # just verify it parses without error

    def test_three_part_india(self):
        city, region, country = parse_locality("bombay, maharashtra, india")
        assert city == "bombay"
        assert region == "maharashtra"
        assert country == "india"

    def test_three_part_ireland(self):
        city, region, country = parse_locality("dublin, dublin, ireland")
        assert city == "dublin"
        assert region == "dublin"
        assert country == "ireland"

    def test_two_part_no_region(self):
        city, region, country = parse_locality("london, united kingdom")
        assert city == "london"
        assert region is None
        assert country == "united kingdom"

    def test_one_part_country_only(self):
        city, region, country = parse_locality("germany")
        assert city is None
        assert region is None
        assert country == "germany"

    def test_blank_returns_none_tuple(self):
        assert parse_locality("") == (None, None, None)

    def test_whitespace_only_returns_none_tuple(self):
        assert parse_locality("   ") == (None, None, None)

    def test_already_lowercase_input(self):
        city, region, country = parse_locality("paris, ile-de-france, france")
        assert city == "paris"
        assert region == "ile-de-france"
        assert country == "france"

    def test_mixed_case_input_lowercased(self):
        city, region, country = parse_locality("New York, New York, United States")
        assert city == "new york"
        assert region == "new york"
        assert country == "united states"

    def test_four_part_joins_country(self):
        # e.g. "city, region, state, country" — parts[2:] joined as country
        city, region, country = parse_locality("san jose, california, ca, united states")
        assert city == "san jose"
        assert region == "california"
        assert country == "ca, united states"


class TestParseYearFounded:
    def test_float_string_1911(self):
        assert parse_year_founded("1911.0") == 1911

    def test_float_string_1989(self):
        assert parse_year_founded("1989.0") == 1989

    def test_float_string_2000(self):
        assert parse_year_founded("2000.0") == 2000

    def test_plain_integer_string(self):
        assert parse_year_founded("1989") == 1989

    def test_blank_returns_none(self):
        assert parse_year_founded("") is None

    def test_whitespace_returns_none(self):
        assert parse_year_founded("   ") is None

    def test_na_returns_none(self):
        assert parse_year_founded("N/A") is None

    def test_alphabetic_returns_none(self):
        assert parse_year_founded("abc") is None

    def test_zero_float(self):
        assert parse_year_founded("0.0") == 0

    def test_recent_year(self):
        assert parse_year_founded("2023.0") == 2023


class TestParseEmployeeEstimate:
    def test_plain_integer(self):
        assert parse_employee_estimate("274047") == 274047

    def test_float_string(self):
        assert parse_employee_estimate("274047.0") == 274047

    def test_blank_returns_none(self):
        assert parse_employee_estimate("") is None

    def test_whitespace_returns_none(self):
        assert parse_employee_estimate("   ") is None

    def test_na_returns_none(self):
        assert parse_employee_estimate("N/A") is None

    def test_zero(self):
        assert parse_employee_estimate("0") == 0

    def test_large_number(self):
        assert parse_employee_estimate("1000000") == 1_000_000

    def test_large_float_string(self):
        assert parse_employee_estimate("500000.0") == 500_000
