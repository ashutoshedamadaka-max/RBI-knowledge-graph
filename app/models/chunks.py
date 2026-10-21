from pydantic import BaseModel
from datetime import date, datetime

from app.models.documents import DocumentLifecycle


class ChunkMetadata(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    page_number: int
    chunk_index: int
    text: str
    source_url: str | None = None
    document_version: int = 1
    is_current: bool = True
    lifecycle: DocumentLifecycle = DocumentLifecycle.UNKNOWN
    authority_current: bool = False
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    in_force_from: date | None = None
    in_force_to: date | None = None
    # Set by the Phase 2 chunkers; empty for chunks made by the legacy word chunker.
    chunker: str = "legacy"
    heading_path: str | None = None
    paragraph_ref: str | None = None
    token_count: int | None = None
    parent_id: str | None = None  # chunks sharing it form one section, passed whole to the answer step


class VectorSearchResult(ChunkMetadata):
    similarity_score: float
