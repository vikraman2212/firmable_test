"""Canonical company document model for indexing and API-safe reuse.

Field names align 1:1 with the OpenSearch index template mappings defined in
app/search/index_template.json.  company_vector is intentionally omitted — it
is injected by the ingest pipeline after the document is written to the index.
"""

import hashlib
from datetime import date
from typing import Optional

from pydantic import BaseModel, field_validator

_MAX_FOUNDED_YEAR = date.today().year
_MIN_FOUNDED_YEAR = 1700


def make_company_id(source_id: str, normalized_name: str) -> str:
    """Return a deterministic, hex-encoded SHA-256 company identifier.

    Combines the raw source row identifier (the unnamed first CSV column) with
    the normalized company name so that IDs remain stable across partial
    renames while still being derivable from the source data.

    Args:
        source_id: Raw integer string from the first CSV column (e.g. "5872184").
        normalized_name: Lower-cased, stripped company name (e.g. "ibm").

    Returns:
        64-character lowercase hex digest.
    """
    payload = f"{source_id}:{normalized_name}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class Company(BaseModel):
    """Canonical document shape written to the OpenSearch companies index.

    All field names match the strict index mapping exactly so the model can be
    serialised directly to an index request body.  Fields that are absent from
    a source row are kept as None and excluded from the serialised output by
    ``to_index_doc``, which prevents spurious null writes against the strict
    dynamic mapping.
    """

    company_id: str
    name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    size_range: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    year_founded: Optional[int] = None
    current_employee_estimate: Optional[int] = None
    total_employee_estimate: Optional[int] = None
    linkedin_url: Optional[str] = None
    company_semantic_text: str

    # ------------------------------------------------------------------
    # Field-level validators
    # ------------------------------------------------------------------

    @field_validator("company_id")
    @classmethod
    def company_id_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("company_id must not be blank")
        return v

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v

    @field_validator("year_founded")
    @classmethod
    def year_founded_must_be_plausible(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (_MIN_FOUNDED_YEAR <= v <= _MAX_FOUNDED_YEAR):
            raise ValueError(
                f"year_founded {v} is outside plausible range "
                f"{_MIN_FOUNDED_YEAR}–{_MAX_FOUNDED_YEAR}"
            )
        return v

    @field_validator("current_employee_estimate", "total_employee_estimate")
    @classmethod
    def employee_estimates_must_be_non_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("employee estimates must be non-negative")
        return v

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_index_doc(self) -> dict:
        """Return a dict suitable for a bulk index request body.

        None-valued fields are excluded so OpenSearch does not attempt to
        write null into fields constrained by the strict dynamic mapping.
        """
        return {k: v for k, v in self.model_dump().items() if v is not None}
