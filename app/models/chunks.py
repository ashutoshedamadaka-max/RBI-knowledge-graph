from pydantic import BaseModel


class ChunkMetadata(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    page_number: int
    chunk_index: int
    text: str
    source_url: str | None = None


class VectorSearchResult(ChunkMetadata):
    similarity_score: float

