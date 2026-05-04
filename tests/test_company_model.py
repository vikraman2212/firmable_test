"""Unit tests for the canonical Company model (P2-T01).

Covers:
- Valid instantiation with all fields
- Valid instantiation with only required fields
- Validation errors for blank company_id and name
- year_founded plausibility bounds
- employee estimate non-negative constraints
- make_company_id determinism and uniqueness
- to_index_doc excludes None fields and includes all required fields
"""

import hashlib

import pytest
from pydantic import ValidationError

from app.models.company import Company, make_company_id


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _minimal_company(**overrides) -> dict:
    """Return keyword args that satisfy required fields only."""
    base = {
        "company_id": "abc123",
        "name": "Acme Corp",
        "company_semantic_text": "Acme Corp technology united states",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# make_company_id
# ---------------------------------------------------------------------------

class TestMakeCompanyId:
    def test_returns_64_char_hex(self):
        result = make_company_id("5872184", "ibm")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic_for_same_inputs(self):
        assert make_company_id("5872184", "ibm") == make_company_id("5872184", "ibm")

    def test_differs_for_different_source_ids(self):
        assert make_company_id("5872184", "ibm") != make_company_id("9999999", "ibm")

    def test_differs_for_different_names(self):
        assert make_company_id("5872184", "ibm") != make_company_id("5872184", "apple")

    def test_matches_expected_sha256(self):
        source_id, norm_name = "5872184", "ibm"
        expected = hashlib.sha256(f"{source_id}:{norm_name}".encode("utf-8")).hexdigest()
        assert make_company_id(source_id, norm_name) == expected

    def test_empty_source_id_is_valid_input(self):
        # Function itself does not validate — callers are responsible
        result = make_company_id("", "ibm")
        assert isinstance(result, str) and len(result) == 64


# ---------------------------------------------------------------------------
# Company construction — happy path
# ---------------------------------------------------------------------------

class TestCompanyValidInstantiation:
    def test_minimal_required_fields(self):
        company = Company(**_minimal_company())
        assert company.company_id == "abc123"
        assert company.name == "Acme Corp"
        assert company.company_semantic_text == "Acme Corp technology united states"
        # All optional fields default to None
        assert company.domain is None
        assert company.industry is None
        assert company.size_range is None
        assert company.city is None
        assert company.region is None
        assert company.country is None
        assert company.year_founded is None
        assert company.current_employee_estimate is None
        assert company.total_employee_estimate is None
        assert company.linkedin_url is None

    def test_all_fields_populated(self):
        company = Company(
            company_id=make_company_id("5872184", "ibm"),
            name="ibm",
            domain="ibm.com",
            industry="information technology and services",
            size_range="10001+",
            city="new york",
            region="new york",
            country="united states",
            year_founded=1911,
            current_employee_estimate=274047,
            total_employee_estimate=716906,
            linkedin_url="linkedin.com/company/ibm",
            company_semantic_text="ibm information technology and services new york united states founded 1911",
        )
        assert company.year_founded == 1911
        assert company.current_employee_estimate == 274047
        assert company.total_employee_estimate == 716906

    def test_year_founded_at_lower_bound(self):
        company = Company(**_minimal_company(year_founded=1700))
        assert company.year_founded == 1700

    def test_year_founded_at_current_year(self):
        from datetime import date
        current_year = date.today().year
        company = Company(**_minimal_company(year_founded=current_year))
        assert company.year_founded == current_year

    def test_employee_estimate_zero_is_valid(self):
        company = Company(**_minimal_company(current_employee_estimate=0))
        assert company.current_employee_estimate == 0

    def test_employee_estimate_large_value(self):
        company = Company(**_minimal_company(total_employee_estimate=1_000_000))
        assert company.total_employee_estimate == 1_000_000


# ---------------------------------------------------------------------------
# Company construction — validation errors
# ---------------------------------------------------------------------------

class TestCompanyValidationErrors:
    def test_blank_company_id_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            Company(**_minimal_company(company_id="   "))
        assert "company_id must not be blank" in str(exc_info.value)

    def test_empty_company_id_raises(self):
        with pytest.raises(ValidationError):
            Company(**_minimal_company(company_id=""))

    def test_blank_name_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            Company(**_minimal_company(name="  "))
        assert "name must not be blank" in str(exc_info.value)

    def test_year_founded_below_1700_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            Company(**_minimal_company(year_founded=1699))
        assert "year_founded" in str(exc_info.value)

    def test_year_founded_future_raises(self):
        from datetime import date
        future_year = date.today().year + 1
        with pytest.raises(ValidationError) as exc_info:
            Company(**_minimal_company(year_founded=future_year))
        assert "year_founded" in str(exc_info.value)

    def test_negative_current_employee_estimate_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            Company(**_minimal_company(current_employee_estimate=-1))
        assert "non-negative" in str(exc_info.value)

    def test_negative_total_employee_estimate_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            Company(**_minimal_company(total_employee_estimate=-100))
        assert "non-negative" in str(exc_info.value)

    def test_missing_company_semantic_text_raises(self):
        kwargs = _minimal_company()
        del kwargs["company_semantic_text"]
        with pytest.raises(ValidationError):
            Company(**kwargs)

    def test_missing_name_raises(self):
        kwargs = _minimal_company()
        del kwargs["name"]
        with pytest.raises(ValidationError):
            Company(**kwargs)


# ---------------------------------------------------------------------------
# to_index_doc
# ---------------------------------------------------------------------------

class TestToIndexDoc:
    def test_excludes_none_fields(self):
        company = Company(**_minimal_company())
        doc = company.to_index_doc()
        # Optional fields not supplied must be absent
        assert "domain" not in doc
        assert "industry" not in doc
        assert "size_range" not in doc
        assert "city" not in doc
        assert "region" not in doc
        assert "country" not in doc
        assert "year_founded" not in doc
        assert "current_employee_estimate" not in doc
        assert "total_employee_estimate" not in doc
        assert "linkedin_url" not in doc

    def test_includes_required_fields(self):
        company = Company(**_minimal_company())
        doc = company.to_index_doc()
        assert "company_id" in doc
        assert "name" in doc
        assert "company_semantic_text" in doc

    def test_includes_populated_optional_fields(self):
        company = Company(
            **_minimal_company(
                domain="acme.com",
                industry="manufacturing",
                year_founded=1950,
                current_employee_estimate=500,
            )
        )
        doc = company.to_index_doc()
        assert doc["domain"] == "acme.com"
        assert doc["industry"] == "manufacturing"
        assert doc["year_founded"] == 1950
        assert doc["current_employee_estimate"] == 500

    def test_does_not_include_company_vector(self):
        """company_vector is added by the ingest pipeline, never by the model."""
        company = Company(**_minimal_company())
        doc = company.to_index_doc()
        assert "company_vector" not in doc

    def test_returns_dict(self):
        company = Company(**_minimal_company())
        assert isinstance(company.to_index_doc(), dict)
