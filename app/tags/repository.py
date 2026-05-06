"""OpenSearch-backed storage for personal company tags."""

from __future__ import annotations

from opensearchpy import OpenSearch

from app.models.tags import TagLookupResult, TagRecord, normalize_tag_name


class TagRepository:
    def __init__(self, client: OpenSearch, index_name: str, default_user_id: str) -> None:
        self._client = client
        self._index = index_name
        self._default_user_id = default_user_id

    def create_tag(self, *, tag_name: str, company_id: str, user_id: str | None = None) -> TagRecord:
        record = TagRecord.create(
            tag_name=tag_name,
            company_id=company_id,
            user_id=user_id or self._default_user_id,
        )
        self._client.index(
            index=self._index,
            id=record.document_id(),
            body=record.to_document(),
            refresh=True,
        )
        return record

    def find_tagged_company_ids(self, tag_name: str, user_id: str | None = None) -> TagLookupResult:
        normalized = normalize_tag_name(tag_name)
        resolved_user_id = user_id or self._default_user_id
        response = self._client.search(
            index=self._index,
            body={
                "size": 1000,
                "sort": [
                    {"created_at": {"order": "desc"}},
                    {"company_id": {"order": "asc"}},
                ],
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"user_id": resolved_user_id}},
                            {"term": {"tag_name_normalized": normalized}},
                        ]
                    }
                },
            },
        )
        records = [
            TagRecord.model_validate(hit.get("_source", {}))
            for hit in response.get("hits", {}).get("hits", [])
        ]
        company_ids = list(dict.fromkeys(record.company_id for record in records))
        return TagLookupResult(
            tag_name_display=records[0].tag_name_display if records else tag_name.strip(),
            tag_name_normalized=normalized,
            company_ids=company_ids,
        )