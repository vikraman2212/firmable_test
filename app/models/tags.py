"""Tag models and normalization helpers for the Phase 6 tagging slice."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re

from pydantic import BaseModel, Field, field_validator


_WHITESPACE_RE = re.compile(r"[\s_]+")
_DASH_RE = re.compile(r"-+")


def normalize_tag_name(tag_name: str) -> str:
    """Normalize free-form tag input into a stable lookup key."""
    normalized = _WHITESPACE_RE.sub("-", tag_name.strip().lower())
    normalized = _DASH_RE.sub("-", normalized).strip("-")
    if not normalized:
        raise ValueError("Tag name must not be blank")
    return normalized


class TagRecord(BaseModel):
    tag_name_display: str
    tag_name_normalized: str
    company_id: str
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("tag_name_display", "company_id", "user_id")
    @classmethod
    def _validate_non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @classmethod
    def create(
        cls,
        *,
        tag_name: str,
        company_id: str,
        user_id: str,
        created_at: datetime | None = None,
    ) -> "TagRecord":
        display = tag_name.strip()
        return cls(
            tag_name_display=display,
            tag_name_normalized=normalize_tag_name(display),
            company_id=company_id,
            user_id=user_id,
            created_at=created_at or datetime.now(timezone.utc),
        )

    def document_id(self) -> str:
        payload = f"{self.user_id}|{self.tag_name_normalized}|{self.company_id}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_document(self) -> dict:
        return self.model_dump(mode="json")


class TagLookupResult(BaseModel):
    tag_name_display: str
    tag_name_normalized: str
    company_ids: list[str]