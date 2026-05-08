"""Unit tests for app/ingestion/identity.py."""
from __future__ import annotations

import hashlib

import pytest

from app.ingestion.identity import build_company_id, build_semantic_text


def _sha256_hex(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TestBuildCompanyId:
    def test_returns_64_char_lowercase_hex(self):
        result = build_company_id("5872184", "ibm")
        assert len(result) == 64
        assert result == result.lower()
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic_same_inputs(self):
        a = build_company_id("5872184", "ibm")
        b = build_company_id("5872184", "ibm")
        assert a == b

    def test_different_source_ids_produce_different_ids(self):
        a = build_company_id("5872184", "ibm")
        b = build_company_id("9999999", "ibm")
        assert a != b

    def test_different_names_produce_different_ids(self):
        a = build_company_id("5872184", "ibm")
        b = build_company_id("5872184", "accenture")
        assert a != b

    def test_uppercase_and_lowercase_name_produce_same_id(self):
        lower = build_company_id("5872184", "ibm")
        upper = build_company_id("5872184", "IBM")
        assert lower == upper

    def test_leading_trailing_spaces_stripped(self):
        clean = build_company_id("5872184", "ibm")
        padded = build_company_id("5872184", "  ibm  ")
        assert clean == padded

    def test_matches_expected_sha256(self):
        expected = _sha256_hex("5872184:ibm")
        assert build_company_id("5872184", "ibm") == expected

    def test_uppercase_name_normalized_before_hashing(self):
        # sha256("5872184:ibm") == sha256("5872184:IBM") after normalization
        assert build_company_id("5872184", "IBM") == _sha256_hex("5872184:ibm")


class TestBuildSemanticText:
    def test_all_fields_present(self):
        result = build_semantic_text(
            "ibm",
            industry="information technology and services",
            city="new york",
            region="new york",
            country="united states",
            year_founded=1911,
            employee_estimate=350000,
            size_range="10001+",
        )
        assert result == (
            "ibm information technology and services "
            "new york new york united states founded 1911 "
            "employees 350000 10001+"
        )

    def test_name_only(self):
        assert build_semantic_text("foo") == "foo"

    def test_name_and_country_only(self):
        assert build_semantic_text("acme", country="germany") == "acme germany"

    def test_name_and_industry(self):
        assert build_semantic_text("acme", industry="software") == "acme software"

    def test_name_city_region_country(self):
        result = build_semantic_text(
            "acme", city="berlin", region="berlin", country="germany"
        )
        assert result == "acme berlin berlin germany"

    def test_year_founded_only_no_location_or_industry(self):
        assert build_semantic_text("ibm", year_founded=1911) == "ibm founded 1911"

    def test_none_industry_skipped(self):
        result = build_semantic_text("acme", industry=None, country="germany")
        assert result == "acme germany"

    def test_none_city_skipped_region_country_included(self):
        result = build_semantic_text(
            "acme", city=None, region="bavaria", country="germany"
        )
        assert result == "acme bavaria germany"

    def test_none_region_skipped_city_country_included(self):
        result = build_semantic_text(
            "acme", city="munich", region=None, country="germany"
        )
        assert result == "acme munich germany"

    def test_blank_name_raises_value_error(self):
        with pytest.raises(ValueError):
            build_semantic_text("")

    def test_whitespace_only_name_raises_value_error(self):
        with pytest.raises(ValueError):
            build_semantic_text("   ")

    def test_parts_joined_with_single_space(self):
        result = build_semantic_text(
            "foo", industry="bar", country="baz", year_founded=2000
        )
        # No double spaces
        assert "  " not in result
        assert result == "foo bar baz founded 2000"

    def test_employee_estimate_included(self):
        result = build_semantic_text("acme", employee_estimate=1500)
        assert result == "acme employees 1500"

    def test_size_range_included(self):
        result = build_semantic_text("acme", size_range="1001 - 5000")
        assert result == "acme 1001 - 5000"

    def test_employee_and_size_range_order(self):
        result = build_semantic_text(
            "acme",
            country="australia",
            year_founded=2005,
            employee_estimate=3000,
            size_range="1001 - 5000",
        )
        assert result == "acme australia founded 2005 employees 3000 1001 - 5000"

    def test_none_employee_estimate_skipped(self):
        result = build_semantic_text("acme", employee_estimate=None)
        assert result == "acme"

    def test_none_size_range_skipped(self):
        result = build_semantic_text("acme", size_range=None)
        assert result == "acme"
