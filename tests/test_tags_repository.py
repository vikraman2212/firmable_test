"""Unit tests for the OpenSearch-backed tag repository."""

from unittest.mock import MagicMock

from app.tags.repository import TagRepository


def _make_repository():
    client = MagicMock()
    return TagRepository(client=client, index_name="company_tags", default_user_id="local-user"), client


def test_create_tag_indexes_a_deterministic_document():
    repo, client = _make_repository()

    record = repo.create_tag(tag_name="Competitors", company_id="company-1")

    assert record.tag_name_normalized == "competitors"
    assert client.index.call_args.kwargs["index"] == "company_tags"
    assert client.index.call_args.kwargs["id"] == record.document_id()
    assert client.index.call_args.kwargs["refresh"] is True
    assert client.index.call_args.kwargs["body"]["company_id"] == "company-1"


def test_find_tagged_company_ids_searches_by_user_and_normalized_tag():
    repo, client = _make_repository()
    client.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "tag_name_display": "Competitors",
                        "tag_name_normalized": "competitors",
                        "company_id": "company-2",
                        "user_id": "local-user",
                        "created_at": "2026-05-06T01:00:00Z",
                    }
                },
                {
                    "_source": {
                        "tag_name_display": "Competitors",
                        "tag_name_normalized": "competitors",
                        "company_id": "company-1",
                        "user_id": "local-user",
                        "created_at": "2026-05-06T00:59:00Z",
                    }
                },
            ]
        }
    }

    lookup = repo.find_tagged_company_ids("Competitors")

    body = client.search.call_args.kwargs["body"]
    assert body["query"]["bool"]["filter"] == [
        {"term": {"user_id": "local-user"}},
        {"term": {"tag_name_normalized": "competitors"}},
    ]
    assert lookup.tag_name_display == "Competitors"
    assert lookup.company_ids == ["company-2", "company-1"]


def test_find_tagged_company_ids_deduplicates_company_ids():
    repo, client = _make_repository()
    client.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "tag_name_display": "Competitors",
                        "tag_name_normalized": "competitors",
                        "company_id": "company-1",
                        "user_id": "local-user",
                        "created_at": "2026-05-06T01:00:00Z",
                    }
                },
                {
                    "_source": {
                        "tag_name_display": "Competitors",
                        "tag_name_normalized": "competitors",
                        "company_id": "company-1",
                        "user_id": "local-user",
                        "created_at": "2026-05-06T00:59:00Z",
                    }
                },
            ]
        }
    }

    lookup = repo.find_tagged_company_ids("Competitors")

    assert lookup.company_ids == ["company-1"]