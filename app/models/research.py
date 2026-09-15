from enum import Enum

from pydantic import BaseModel, Field

from app.models.retrieval import GraphEdgeEvidence, GraphNodeEvidence


class ResearchStatus(str, Enum):
    GROUNDED = "grounded"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    OUT_OF_SCOPE = "out_of_scope"


class ResearchClaim(BaseModel):
    text: str = Field(min_length=1, max_length=1800)
    citation_ids: list[str] = Field(default_factory=list)


class ResearchSection(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=1, max_length=100)
    claims: list[ResearchClaim] = Field(default_factory=list, max_length=8)


class ResearchGraphContext(BaseModel):
    nodes: list[GraphNodeEvidence] = Field(default_factory=list)
    edges: list[GraphEdgeEvidence] = Field(default_factory=list)


class StructuredResearch(BaseModel):
    status: ResearchStatus
    direct_answer: ResearchClaim | None = None
    sections: list[ResearchSection] = Field(default_factory=list, max_length=6)
    related_questions: list[str] = Field(default_factory=list, max_length=3)
    graph_context: ResearchGraphContext | None = None
