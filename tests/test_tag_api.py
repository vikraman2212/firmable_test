"""Unit tests for Phase 6 tag API handlers."""

import pytest
from pydantic import ValidationError

from app.api.main import create_tag, get_tagged_companies
from app.api.schemas import TagCreateRequest
from app.api.schemas import CompanyResult
from app.models.tags import TagLookupResult, TagRecord


class StubTagRepository:
    def create_tag(self, *, tag_name: str, company_id: str):
        return TagRecord.create(tag_name=tag_name, company_id=company_id, user_id="local-user")

    def find_tagged_company_ids(self, tag_name: str):
        if tag_name == "unknown":
            return TagLookupResult(
                tag_name_display="unknown",
                tag_name_normalized="unknown",
                company_ids=[],
            )
        return TagLookupResult(
            tag_name_display="Competitors",
            tag_name_normalized="competitors",
            company_ids=["company-2", "company-1"],
        )


class StubSearchService:
    def get_companies_by_ids(self, company_ids):
        return [
            CompanyResult(company_id=company_id, name=f"Company {company_id}")
            for company_id in company_ids
        ]


def test_tag_create_request_accepts_tag_name_alias():
    request = TagCreateRequest.model_validate({"tagName": "Competitors", "company_id": "company-1"})

    assert request.tag_name == "Competitors"
    assert request.company_id == "company-1"


def test_tag_create_request_rejects_blank_values():
    with pytest.raises(ValidationError):
        TagCreateRequest.model_validate({"tagName": "   ", "company_id": "company-1"})


def test_create_tag_returns_created_record_shape():
    response = create_tag(
        TagCreateRequest.model_validate({"tagName": "Competitors", "company_id": "company-1"}),
        repo=StubTagRepository(),
    )

    assert response.tag_name == "Competitors"
    assert response.tag_name_normalized == "competitors"
    assert response.company_id == "company-1"
    assert response.user_id == "local-user"


def test_get_tagged_companies_resolves_company_details():
    response = get_tagged_companies(
        "Competitors",
        repo=StubTagRepository(),
        svc=StubSearchService(),
    )

    assert response.tag_name == "Competitors"
    assert response.tag_name_normalized == "competitors"
    assert response.total == 2
    assert [item.company_id for item in response.items] == ["company-2", "company-1"]


def test_get_tagged_companies_returns_empty_items_when_tag_missing():
    response = get_tagged_companies(
        "unknown",
        repo=StubTagRepository(),
        svc=StubSearchService(),
    )

    assert response.total == 0
    assert response.items == []