from enum import Enum

from pydantic import BaseModel, Field

from app.models.retrieval import RetrievalRoute


class QuestionCategory(str, Enum):
    SINGLE_HOP = "single-hop"
    TWO_HOP = "two-hop"
    MULTI_HOP = "multi-hop"
    COMPARISON = "comparison"
    TEMPORAL_CHANGE = "temporal-change"
    OUT_OF_SCOPE = "out-of-scope"


class EvaluationCase(BaseModel):
    case_id: str
    question: str
    category: QuestionCategory
    hop_count: int = Field(ge=0, le=5)
    expected_route: RetrievalRoute
    expected_source_urls: list[str] = Field(default_factory=list)


class CaseResult(BaseModel):
    case_id: str
    category: QuestionCategory
    hop_count: int
    route_correct: bool
    vector_recall: float
    proposed_recall: float
    citation_valid: bool
    latency_ms: float
    estimated_cost_usd: float


class EvaluationReport(BaseModel):
    total_cases: int
    retrieval_recall_at_k: float
    citation_validity: float
    routing_accuracy: float
    median_latency_ms: float
    estimated_cost_usd: float
    by_hop_count: dict[str, dict[str, float]]
    results: list[CaseResult]

