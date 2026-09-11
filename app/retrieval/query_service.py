from time import perf_counter

from app.config.settings import Settings
from app.graph.query_service import GraphRetrievalService
from app.llm.citations import validate_citations
from app.llm.generation import get_answer_generator
from app.models.chunks import ChunkMetadata
from app.models.query import Citation, QueryResponse
from app.models.retrieval import RetrievalRoute
from app.retrieval.router import QueryRouter
from app.retrieval.service import VectorRetrievalService


class RegulatoryQueryService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.router = QueryRouter()
        self.vector = VectorRetrievalService(settings)
        self.graph = GraphRetrievalService(settings)
        self.generator = get_answer_generator(settings)

    def query(self, user_query: str, top_k: int | None = None) -> QueryResponse:
        started = perf_counter()
        decision = self.router.route(user_query)
        evidence: list[ChunkMetadata] = []

        if decision.route in {RetrievalRoute.VECTOR, RetrievalRoute.HYBRID}:
            evidence.extend(self.vector.retrieve_vector(user_query, top_k))
        if decision.route in {RetrievalRoute.GRAPH, RetrievalRoute.HYBRID}:
            graph_result = self.graph.retrieve_graph(user_query)
            evidence.extend(self.vector.store.get_by_ids(graph_result.chunk_ids))

        unique = {chunk.chunk_id: chunk for chunk in evidence}
        merged = list(unique.values())[: top_k or self.settings.vector_top_k]
        answer = self.generator.generate(user_query, merged)
        citation_valid = validate_citations(answer, merged) if merged else not bool(answer and "[" in answer)
        if merged and not citation_valid:
            answer = (
                "### Answer\n"
                "I cannot provide a verified answer because the generated citations did not resolve to the retrieved evidence.\n\n"
                "### Regulatory basis\nPlease retry after reviewing the source material."
            )

        citations = [
            Citation(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                page_number=chunk.page_number,
                source_url=chunk.source_url,
            )
            for chunk in merged
            if f"[{chunk.chunk_id}]" in answer
        ]
        return QueryResponse(
            answer=answer,
            citations=citations,
            route=decision.route,
            retrieved_evidence=merged,
            latency_ms=round((perf_counter() - started) * 1000, 2),
            estimated_cost_usd=0.0,
            citation_valid=citation_valid,
        )

