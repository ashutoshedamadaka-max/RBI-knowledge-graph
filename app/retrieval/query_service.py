from time import perf_counter
from datetime import UTC, datetime
from uuid import uuid4

from app.config.settings import Settings
from app.graph.query_service import GraphRetrievalService
from app.llm.citations import validate_citations
from app.llm.generation import get_answer_generator
from app.models.chunks import ChunkMetadata
from app.models.query import Citation, QueryResponse
from app.models.retrieval import RetrievalRoute
from app.retrieval.router import QueryRouter
from app.retrieval.service import VectorRetrievalService
from app.observability.costs import CostEvent, CostTracker
from app.observability.events import QueryEvent, log_query_event


class RegulatoryQueryService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.router = QueryRouter()
        self.vector = VectorRetrievalService(settings)
        self.graph = GraphRetrievalService(settings)
        self.generator = get_answer_generator(settings)
        self.cost_tracker = CostTracker(settings.runtime_dir / "cost_events.json")

    def query(self, user_query: str, top_k: int | None = None, request_id: str | None = None) -> QueryResponse:
        started = perf_counter()
        request_id = request_id or f"req_{uuid4().hex}"
        decision = self.router.route(user_query)
        evidence: list[ChunkMetadata] = []
        graph_node_count = 0
        graph_edge_count = 0

        if decision.route in {RetrievalRoute.VECTOR, RetrievalRoute.HYBRID}:
            historical = any(term in user_query.lower() for term in ("before", "previous", "historical", "what changed"))
            evidence.extend(self.vector.retrieve_vector(user_query, top_k, current_only=not historical))
        if decision.route in {RetrievalRoute.GRAPH, RetrievalRoute.HYBRID}:
            graph_result = self.graph.retrieve_graph(user_query)
            graph_node_count = len(graph_result.nodes)
            graph_edge_count = len(graph_result.edges)
            evidence.extend(self.vector.store.get_by_ids(graph_result.chunk_ids))

        unique = {chunk.chunk_id: chunk for chunk in evidence}
        merged = list(unique.values())[: top_k or self.settings.vector_top_k]
        generation = self.generator.generate(user_query, merged)
        answer = generation.answer
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
        latency_ms = round((perf_counter() - started) * 1000, 2)
        if generation.model != "deterministic":
            self.cost_tracker.record(CostEvent(
                timestamp=datetime.now(UTC),
                operation="answer_generation",
                model=generation.model,
                input_tokens=generation.input_tokens,
                output_tokens=generation.output_tokens,
                estimated_cost_usd=generation.estimated_cost_usd,
                correlation_id=request_id,
            ))
        log_query_event(QueryEvent(
            timestamp=datetime.now(UTC),
            request_id=request_id,
            query=user_query,
            route=decision.route.value,
            retrieval_method=decision.route.value.lower(),
            retrieved_chunk_ids=[chunk.chunk_id for chunk in merged],
            graph_node_count=graph_node_count,
            graph_edge_count=graph_edge_count,
            model=generation.model,
            input_tokens=generation.input_tokens,
            output_tokens=generation.output_tokens,
            estimated_cost_usd=generation.estimated_cost_usd,
            latency_ms=latency_ms,
            citation_valid=citation_valid,
            status="ok" if citation_valid else "citation_validation_failed",
        ))
        return QueryResponse(
            request_id=request_id,
            answer=answer,
            citations=citations,
            route=decision.route,
            retrieved_evidence=merged,
            latency_ms=latency_ms,
            estimated_cost_usd=generation.estimated_cost_usd,
            citation_valid=citation_valid,
        )
