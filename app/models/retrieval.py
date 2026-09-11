from enum import Enum

from pydantic import BaseModel, Field


class RetrievalRoute(str, Enum):
    VECTOR = "VECTOR"
    GRAPH = "GRAPH"
    HYBRID = "HYBRID"


class RouteDecision(BaseModel):
    route: RetrievalRoute
    reasons: list[str] = Field(default_factory=list)


class GraphNodeEvidence(BaseModel):
    node_id: str
    name: str
    entity_type: str


class GraphEdgeEvidence(BaseModel):
    source_id: str
    target_id: str
    relationship_type: str
    source_chunk_id: str
    source_document_id: str
    confidence: float


class GraphRetrievalResult(BaseModel):
    template: str | None
    nodes: list[GraphNodeEvidence] = Field(default_factory=list)
    edges: list[GraphEdgeEvidence] = Field(default_factory=list)

    @property
    def chunk_ids(self) -> list[str]:
        return sorted({edge.source_chunk_id for edge in self.edges})

