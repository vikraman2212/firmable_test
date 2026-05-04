"""Pydantic contracts for the search API.

SearchRequest  — POST /search request body
SearchResponse — POST /search response body
CompanyResult  — single result item inside SearchResponse
"""

from typing import Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: Optional[str] = None

    # Filters
    industry: Optional[list[str]] = None
    size_range: Optional[list[str]] = None
    country: Optional[str] = None
    city: Optional[str] = None
    year_founded_gte: Optional[int] = None
    year_founded_lte: Optional[int] = None

    # Pagination
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class CompanyResult(BaseModel):
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


class SearchResponse(BaseModel):
    items: list[CompanyResult]
    total: int
    page: int
    page_size: int
    took_ms: int
