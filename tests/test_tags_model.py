"""Unit tests for tag normalization and tag record behavior."""

from datetime import datetime, timezone

import pytest

from app.models.tags import TagRecord, normalize_tag_name


def test_normalize_tag_name_lowercases_and_hyphenates():
    assert normalize_tag_name("  Potential Partners  ") == "potential-partners"


def test_normalize_tag_name_rejects_blank_input():
    with pytest.raises(ValueError, match="must not be blank"):
        normalize_tag_name("   ")


def test_tag_record_create_sets_normalized_name_and_strips_fields():
    created_at = datetime(2026, 5, 6, tzinfo=timezone.utc)

    record = TagRecord.create(
        tag_name="  Enterprise Clients ",
        company_id=" company-1 ",
        user_id=" local-user ",
        created_at=created_at,
    )

    assert record.tag_name_display == "Enterprise Clients"
    assert record.tag_name_normalized == "enterprise-clients"
    assert record.company_id == "company-1"
    assert record.user_id == "local-user"
    assert record.created_at == created_at


def test_tag_record_document_id_is_deterministic():
    first = TagRecord.create(tag_name="Competitors", company_id="company-1", user_id="local-user")
    second = TagRecord.create(tag_name="competitors", company_id="company-1", user_id="local-user")

    assert first.document_id() == second.document_id()


def test_tag_record_to_document_serializes_created_at():
    record = TagRecord.create(
        tag_name="Competitors",
        company_id="company-1",
        user_id="local-user",
        created_at=datetime(2026, 5, 6, 1, 0, tzinfo=timezone.utc),
    )

    document = record.to_document()

    assert document["tag_name_normalized"] == "competitors"
    assert document["created_at"].startswith("2026-05-06T01:00:00")