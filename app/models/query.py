from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.models.chunks import ChunkMetadata
from app.models.retrieval import RetrievalRoute
from app.models.research import StructuredResearch


class QueryRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    as_of: date | None = Field(default=None, description="Answer from the rules in force on this date; default today.")


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    page_number: int
    source_url: str | None = None


class ChangeNotice(BaseModel):
    """A statement about a rule change, with its own quoted evidence.

    Kept apart from the answer's citations: a notice may quote a rule that is not yet in
    force, which must never be cited as current guidance.
    """

    kind: Literal["replaced", "withdrawn", "upcoming"]
    text: str
    document_id: str
    related_document_id: str | None = None
    evidence_chunk_id: str | None = None
    evidence_excerpt: str | None = None


class QueryPipelineSummary(BaseModel):
    """Inspectable facts from a completed research turn, not model reasoning."""

    graph_node_count: int = 0
    graph_edge_count: int = 0
    candidate_evidence_count: int = 0
    excluded_after_validity_check: int = 0
    selected_evidence_count: int = 0
    historical_query: bool = False
    retrieval_method: str = "unknown"
    answer_mode: str = "unknown"


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
    as_of: date | None = None
    notices: list[ChangeNotice] = Field(default_factory=list)
    trace: dict = Field(default_factory=dict)  # per-step facts for the trace drawer (timings, candidates, filter, cost)
