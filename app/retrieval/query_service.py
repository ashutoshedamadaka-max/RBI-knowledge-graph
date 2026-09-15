from datetime import UTC, datetime
from time import perf_counter
from collections.abc import Callable
from uuid import uuid4

from app.config.settings import Settings
from app.graph.query_service import GraphRetrievalService
from app.llm.citations import validate_structured_citations
from app.llm.generation import DeterministicAnswerGenerator, get_answer_generator, research_to_markdown
from app.models.chunks import ChunkMetadata
from app.models.query import Citation, QueryResponse
from app.models.research import ResearchClaim, ResearchGraphContext, ResearchStatus, StructuredResearch
from app.models.retrieval import RetrievalRoute
from app.observability.costs import CostEvent, CostTracker
from app.observability.events import QueryEvent, log_query_event
from app.retrieval.router import QueryRouter
from app.retrieval.scope import is_rbi_lending_question
from app.retrieval.service import VectorRetrievalService


class RegulatoryQueryService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.router = QueryRouter()
        self.vector = VectorRetrievalService(settings)
        self.graph = GraphRetrievalService(settings)
        self.generator = get_answer_generator(settings)
        self.cost_tracker = CostTracker(settings.runtime_dir / "cost_events.json")

    def query(
        self,
        user_query: str,
        top_k: int | None = None,
        request_id: str | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> QueryResponse:
        started = perf_counter()
        request_id = request_id or f"req_{uuid4().hex}"
        if progress:
            progress("understanding_question")
        decision = self.router.route(user_query)
        in_scope = is_rbi_lending_question(user_query)
        if not in_scope:
            return self._out_of_scope_response(user_query, decision.route, request_id, started)

        evidence: list[ChunkMetadata] = []
        if progress:
            progress("searching_regulatory_relationships")
        graph_result = self.graph.retrieve_graph(user_query)
        if decision.route in {RetrievalRoute.VECTOR, RetrievalRoute.HYBRID}:
            if progress:
                progress("retrieving_official_evidence")
            historical = any(term in user_query.lower() for term in ("before", "previous", "historical", "what changed"))
            evidence.extend(self.vector.retrieve_vector(user_query, top_k, current_only=not historical))
        if decision.route in {RetrievalRoute.GRAPH, RetrievalRoute.HYBRID}:
            graph_evidence = self.vector.store.get_by_ids(graph_result.chunk_ids)
            evidence.extend(graph_evidence)
            if decision.route is RetrievalRoute.GRAPH and not graph_evidence:
                evidence.extend(self.vector.retrieve_vector(user_query, top_k))

        merged = list({chunk.chunk_id: chunk for chunk in evidence}.values())[: top_k or self.settings.vector_top_k]
        if progress:
            progress("building_grounded_answer")
        generation = self.generator.generate(user_query, merged)
        research = generation.research
        fallback_used = False
        if research is None or not validate_structured_citations(research, merged):
            research = DeterministicAnswerGenerator().generate(user_query, merged).research
            fallback_used = True
        assert research is not None
        if research.status is ResearchStatus.INSUFFICIENT_EVIDENCE:
            research = research.model_copy(update={
                "direct_answer": ResearchClaim(
                    text="I could not find an RBI provision in the indexed lending corpus that directly establishes an answer to this question.",
                    citation_ids=[],
                ),
                "sections": [],
                "graph_context": None,
            })
        elif graph_result.edges:
            research = research.model_copy(update={
                "graph_context": ResearchGraphContext(nodes=graph_result.nodes, edges=graph_result.edges)
            })

        answer = research_to_markdown(research)
        citation_valid = validate_structured_citations(research, merged)
        cited_ids = self._cited_ids(research)
        citations = [
            Citation(chunk_id=chunk.chunk_id, document_id=chunk.document_id, document_title=chunk.document_title,
                     page_number=chunk.page_number, source_url=chunk.source_url)
            for chunk in merged if chunk.chunk_id in cited_ids
        ]
        latency_ms = round((perf_counter() - started) * 1000, 2)
        if generation.model != "deterministic":
            self.cost_tracker.record(CostEvent(
                timestamp=datetime.now(UTC), operation="answer_generation", model=generation.model,
                input_tokens=generation.input_tokens, output_tokens=generation.output_tokens,
                estimated_cost_usd=generation.estimated_cost_usd, correlation_id=request_id,
            ))
        log_query_event(QueryEvent(
            timestamp=datetime.now(UTC), request_id=request_id, query=user_query, route=decision.route.value,
            retrieval_method=decision.route.value.lower(), retrieved_chunk_ids=[chunk.chunk_id for chunk in merged],
            graph_node_count=len(graph_result.nodes), graph_edge_count=len(graph_result.edges), model=generation.model,
            input_tokens=generation.input_tokens, output_tokens=generation.output_tokens,
            estimated_cost_usd=generation.estimated_cost_usd, latency_ms=latency_ms, citation_valid=citation_valid,
            status="citation_fallback" if fallback_used else "ok",
        ))
        return QueryResponse(
            request_id=request_id, answer=answer, citations=citations, route=decision.route, in_scope=True,
            retrieved_evidence=merged, latency_ms=latency_ms, estimated_cost_usd=generation.estimated_cost_usd,
            citation_valid=citation_valid, research=research,
        )

    @staticmethod
    def _cited_ids(research: StructuredResearch) -> set[str]:
        claims = ([research.direct_answer] if research.direct_answer else []) + [
            claim for section in research.sections for claim in section.claims
        ]
        return {citation_id for claim in claims if claim for citation_id in claim.citation_ids}

    def _out_of_scope_response(self, query: str, route: RetrievalRoute, request_id: str, started: float) -> QueryResponse:
        research = StructuredResearch(
            status=ResearchStatus.OUT_OF_SCOPE,
            direct_answer=ResearchClaim(text="This question is outside the RBI lending guidelines indexed in this knowledge base.", citation_ids=[]),
            related_questions=[
                "What are RBI's rules on penal charges in loan accounts?",
                "Which entities do the RBI Digital Lending Directions, 2025 apply to?",
            ],
        )
        latency_ms = round((perf_counter() - started) * 1000, 2)
        log_query_event(QueryEvent(
            timestamp=datetime.now(UTC), request_id=request_id, query=query, route=route.value,
            retrieval_method="out_of_scope", retrieved_chunk_ids=[], graph_node_count=0, graph_edge_count=0,
            model="scope_guard", input_tokens=0, output_tokens=0, estimated_cost_usd=0.0,
            latency_ms=latency_ms, citation_valid=True, status="out_of_scope",
        ))
        return QueryResponse(
            request_id=request_id, answer=research_to_markdown(research), citations=[], route=route, in_scope=False,
            retrieved_evidence=[], latency_ms=latency_ms, estimated_cost_usd=0.0, citation_valid=True, research=research,
        )
