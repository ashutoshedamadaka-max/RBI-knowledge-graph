from pydantic import BaseModel, Field

from app.models.chunks import ChunkMetadata
from app.models.retrieval import RetrievalRoute


class QueryRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    page_number: int
    source_url: str | None = None


class QueryResponse(BaseModel):
    request_id: str
    answer: str
    citations: list[Citation]
    route: RetrievalRoute
    retrieved_evidence: list[ChunkMetadata]
    latency_ms: float
    estimated_cost_usd: float
    citation_valid: bool
