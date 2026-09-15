from pydantic import BaseModel
from datetime import datetime

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


class VectorSearchResult(ChunkMetadata):
    similarity_score: float
