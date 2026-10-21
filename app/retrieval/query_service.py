from datetime import UTC, datetime
from time import perf_counter
from collections.abc import Callable
from uuid import uuid4
import re

from app.config.settings import Settings
from app.graph.query_service import GraphRetrievalService
from app.llm.citations import validate_structured_citations
from app.llm.generation import DeterministicAnswerGenerator, get_answer_generator, research_to_markdown, align_research_headings
from app.models.chunks import ChunkMetadata
from app.models.documents import DocumentLifecycle
from app.models.query import ChangeNotice, Citation, QueryPipelineSummary, QueryResponse
from app.models.research import ResearchClaim, ResearchGraphContext, ResearchStatus, StructuredResearch
from app.models.retrieval import RetrievalRoute
from app.observability.costs import CostEvent, CostTracker
from app.observability.events import QueryEvent, log_query_event
from app.retrieval.router import QueryRouter
from app.retrieval.scope import is_rbi_lending_question
from app.retrieval.service import VectorRetrievalService
from app.retrieval.vector_store import is_current_guidance
from app.ingestion.manifest import DocumentManifest
from app.models.documents import DocumentMetadata
from app import clock
from datetime import date


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
        as_of: date | None = None,
    ) -> QueryResponse:
        started = perf_counter()
        day = as_of or clock.now().date()
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
        historical = self._is_historical_query(user_query)
        vector_used = decision.route in {RetrievalRoute.VECTOR, RetrievalRoute.HYBRID}
        graph_evidence = []
        if decision.route in {RetrievalRoute.VECTOR, RetrievalRoute.HYBRID}:
            if progress:
                progress("retrieving_official_evidence")
            historical = self._is_historical_query(user_query)
            evidence.extend(self.vector.retrieve_vector(user_query, top_k, current_only=not historical, as_of=day))
        if decision.route in {RetrievalRoute.GRAPH, RetrievalRoute.HYBRID}:
            graph_evidence = self.vector.store.get_by_ids(graph_result.chunk_ids)
            evidence.extend(graph_evidence)
            if decision.route is RetrievalRoute.GRAPH and not graph_evidence:
                vector_used = True
                if progress:
                    progress("retrieving_official_evidence")
                evidence.extend(self.vector.retrieve_vector(user_query, top_k, current_only=not historical, as_of=day))

        # Graph retrieval is semantic discovery, not a validity exception. Apply
        # regulatory authority resolution after every candidate source is merged.
        historical = self._is_historical_query(user_query)
        candidate_evidence_count = len(evidence)
        if progress:
            progress("checking_regulatory_validity")
        notices: list[ChangeNotice] = []
        if not historical:
            # The same rule as search, so graph evidence cannot bypass it: operative, latest
            # version, and in force on the as-of day.
            evidence = [chunk for chunk in evidence if is_current_guidance(chunk.model_dump(mode="json"), day)]
            notices, successor_evidence = self._change_notices(user_query, evidence, day, top_k or self.settings.vector_top_k)
            evidence = successor_evidence + evidence
        excluded_after_validity_check = candidate_evidence_count - len(evidence)
        merged = list({chunk.chunk_id: chunk for chunk in evidence}.values())[: top_k or self.settings.vector_top_k]
        if progress:
            progress("selecting_authoritative_evidence")
        if progress:
            progress("building_grounded_answer")
        sections = self.vector.store.sections(merged)  # empty unless chunks belong to sections (structure chunker)
        generation = self.generator.generate(user_query, merged, **({"sections": sections} if sections else {}))
        research = generation.research
        fallback_used = False
        if (
            research is None
            or not validate_structured_citations(research, merged)
        ):
            research = DeterministicAnswerGenerator().generate(user_query, merged).research
            fallback_used = True
        assert research is not None
        research = align_research_headings(research, merged)
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
            # Do not present edges backed only by excluded or unselected passages.
            selected_ids = {chunk.chunk_id for chunk in merged}
            eligible_edges = [edge for edge in graph_result.edges if edge.source_chunk_id in selected_ids]
            node_ids = {node_id for edge in eligible_edges for node_id in (edge.source_id, edge.target_id)}
            research = research.model_copy(update={
                "graph_context": ResearchGraphContext(
                    nodes=[node for node in graph_result.nodes if node.node_id in node_ids], edges=eligible_edges,
                ) if eligible_edges else None
            })

        answer = research_to_markdown(research)
        if notices:
            answer = "### What changed\n" + "\n".join(f"- {item.text}" for item in notices) + "\n\n" + answer
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
            citation_valid=citation_valid, research=research, as_of=day, notices=notices,
            pipeline=QueryPipelineSummary(
                graph_node_count=len(graph_result.nodes), graph_edge_count=len(graph_result.edges),
                candidate_evidence_count=candidate_evidence_count,
                excluded_after_validity_check=excluded_after_validity_check,
                selected_evidence_count=len(merged), historical_query=historical,
                answer_mode="excerpt" if fallback_used or generation.model == "deterministic" else "summary",
                retrieval_method=("hybrid" if vector_used else "graph") if any(
                    chunk.chunk_id in {item.chunk_id for item in graph_evidence} for chunk in merged
                ) else "vector" if vector_used else "none",
            ),
        )

    def _change_notices(self, query: str, eligible: list[ChunkMetadata], day: date, limit: int
                        ) -> tuple[list[ChangeNotice], list[ChunkMetadata]]:
        """Say what replaced a retired rule the question matches, and quote rules not yet in force.

        A retired passage counts when the status filter removed it from the top results the
        answer would otherwise have used. Its successor's best passages are added to the
        evidence. Rank-based; no tuned threshold.
        """
        documents = {item.document_id: item for item in DocumentManifest(self.settings.runtime_dir / "documents.json").all()}
        best = max((getattr(chunk, "similarity_score", 0.0) for chunk in eligible), default=0.0)
        notices: list[ChangeNotice] = []
        extra: list[ChunkMetadata] = []
        seen: set[str] = set()
        for result in self.vector.store.search(query, top_k=limit, current_only=False, as_of=day):
            if result.document_id in seen or is_current_guidance(result.model_dump(mode="json"), day):
                continue
            seen.add(result.document_id)
            old = documents.get(result.document_id)
            if old is None:
                continue
            successor = documents.get(old.successor_document_id) if old.successor_document_id else None
            retired = old.lifecycle in NON_CURRENT or (old.in_force_to is not None and old.in_force_to <= day)
            if successor and retired and _in_force(successor, day):
                notices.append(ChangeNotice(
                    kind="replaced", document_id=old.document_id, related_document_id=successor.document_id,
                    text=(f"{old.title} was repealed by {successor.title}, issued {_day(successor.publication_date)}, "
                          f"in force from {_day(successor.in_force_from)}; this is the current rule."),
                    evidence_excerpt=_link_quote(self.settings, old.document_id, successor.document_id),
                ))
                extra.extend(self.vector.store.search(query, top_k=2, as_of=day, document_ids={successor.document_id}))
            elif old.lifecycle in NON_CURRENT and successor is None and not any(n.kind == "withdrawn" for n in notices):
                # One withdrawal notice per answer, for the best-ranked removed rule: more is noise.
                notices.append(ChangeNotice(
                    kind="withdrawn", document_id=old.document_id,
                    text=(f"{old.title} is {old.lifecycle.value.lower()} (detected {_day(old.status_checked_at)}); "
                          "no replacement was found in the indexed RBI corpus."),
                    evidence_excerpt=old.status_evidence_excerpt,
                ))
        notices.extend(self._upcoming_notices(query, eligible, documents, day, best))
        return notices, extra

    def _upcoming_notices(self, query: str, eligible: list[ChunkMetadata], documents: dict[str, DocumentMetadata],
                          day: date, best: float) -> list[ChangeNotice]:
        """Rules issued but not yet in force: those replacing an answer's source, or ranking at the top."""
        replacing = {documents[c.document_id].successor_document_id for c in eligible
                     if c.document_id in documents and documents[c.document_id].successor_document_id}
        notices: list[ChangeNotice] = []
        seen: set[str] = set()
        for result in self.vector.store.search(query, top_k=5, as_of=day, upcoming_only=True):
            new = documents.get(result.document_id)
            if new is None or new.document_id in seen or (new.document_id not in replacing and result.similarity_score < best):
                continue
            seen.add(new.document_id)
            predecessor = next((item for item in documents.values() if item.successor_document_id == new.document_id), None)
            until = f"Until then, the rule in force is {predecessor.title}." if predecessor else "It does not apply yet."
            notices.append(ChangeNotice(
                kind="upcoming", document_id=new.document_id,
                related_document_id=predecessor.document_id if predecessor else None,
                text=f"{new.title}, issued {_day(new.publication_date)}, takes effect from {_day(new.in_force_from)}. {until}",
                evidence_chunk_id=result.chunk_id, evidence_excerpt=result.text[:400],
            ))
        return notices

    @staticmethod
    def _is_historical_query(query: str) -> bool:
        normalized = query.lower()
        # A year in a document title or an amendment question is not a request
        # to bypass current authority. Require an explicit history/change intent.
        return bool(re.search(
            r"\b(?:historical|previous(?:ly)?|what changed|as of|used to|no longer)\b"
            r"|\b(?:before|prior to)\s+(?:the\s+)?(?:20\d{2}|amendment|change|withdrawal)\b"
            r"|\b(?:what were|which rules applied|rules in force in)\b", normalized,
        ))

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


NON_CURRENT = {DocumentLifecycle.WITHDRAWN, DocumentLifecycle.REPEALED, DocumentLifecycle.SUPERSEDED}


def _in_force(document: DocumentMetadata, day: date) -> bool:
    return document.lifecycle in {DocumentLifecycle.ACTIVE, DocumentLifecycle.AMENDED} and (
        document.in_force_from is None or document.in_force_from <= day
    ) and (document.in_force_to is None or day < document.in_force_to)


def _day(value) -> str:
    if value is None:
        return "on an unrecorded date"
    return f"{value.day} {value:%B %Y}"


def _link_quote(settings: Settings, old_id: str, new_id: str) -> str | None:
    from app.monitoring.link_store import LinkStore

    link = next((item for item in LinkStore(settings.runtime_dir / "document_links.json").for_old(old_id)
                 if item.new_document_id == new_id), None)
    return link.evidence_quote if link else None
