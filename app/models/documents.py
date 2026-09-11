from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl, model_validator


class IngestStatus(str, Enum):
    INGESTED = "ingested"
    CACHED = "cached"


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

