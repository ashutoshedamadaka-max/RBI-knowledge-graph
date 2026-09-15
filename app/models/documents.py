from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl, model_validator


class IngestStatus(str, Enum):
    INGESTED = "ingested"
    CACHED = "cached"


class DocumentLifecycle(str, Enum):
    ACTIVE = "ACTIVE"
    AMENDED = "AMENDED"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"
    REPEALED = "REPEALED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNKNOWN = "UNKNOWN"


class DocumentMetadata(BaseModel):
    document_id: str
    title: str
    issuing_authority: str = "Reserve Bank of India"
    publication_date: date | None = None
    source_url: str | None = None
    content_hash: str
    file_name: str
    mime_type: str
    ingested_at: datetime
    page_count: int | None = None
    lifecycle: DocumentLifecycle = DocumentLifecycle.UNKNOWN
    status_evidence_url: str | None = None
    status_evidence_excerpt: str | None = None
    status_checked_at: datetime | None = None
    document_identifier: str | None = None
    effective_date: date | None = None
    document_type: str | None = None
    applicable_entities: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    successor_document_id: str | None = None
    document_version: int = 1
    is_current: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class IngestRequest(BaseModel):
    source_url: HttpUrl | None = None
    local_path: str | None = None
    title: str | None = Field(default=None, max_length=500)
    publication_date: date | None = None
    issuing_authority: str = "Reserve Bank of India"

    @model_validator(mode="after")
    def exactly_one_source(self) -> "IngestRequest":
        if bool(self.source_url) == bool(self.local_path):
            raise ValueError("Provide exactly one of source_url or local_path.")
        return self


class IngestResponse(BaseModel):
    status: IngestStatus
    document: DocumentMetadata
    message: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentMetadata]
    count: int
