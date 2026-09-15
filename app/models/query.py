from pydantic import BaseModel, Field

from app.models.chunks import ChunkMetadata
from app.models.retrieval import RetrievalRoute
from app.models.research import StructuredResearch


class QueryRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    page_number: int
    source_url: str | None = None


class QueryPipelineSummary(BaseModel):
    """Inspectable facts from a completed research turn, not model reasoning."""

    graph_node_count: int = 0
    graph_edge_count: int = 0
    candidate_evidence_count: int = 0
    excluded_after_validity_check: int = 0
    selected_evidence_count: int = 0
    historical_query: bool = False


class QueryResponse(BaseModel):
    request_id: str
    answer: str
    citations: list[Citation]
    route: RetrievalRoute
    in_scope: bool = True
    retrieved_evidence: list[ChunkMetadata]
    latency_ms: float
    estimated_cost_usd: float
    citation_valid: bool
    research: StructuredResearch | None = None
    pipeline: QueryPipelineSummary = Field(default_factory=QueryPipelineSummary)
