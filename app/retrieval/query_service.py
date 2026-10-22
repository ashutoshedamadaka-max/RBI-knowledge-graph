from datetime import UTC, datetime
from time import perf_counter
from collections.abc import Callable
from uuid import uuid4

import logging

from app.config.settings import Settings
from app.llm import claim_checker
from app.llm.citations import validate_structured_citations
from app.llm.generation import DeterministicAnswerGenerator, get_answer_generator, research_to_markdown, align_research_headings
from app.models.chunks import ChunkMetadata
from app.models.documents import DocumentLifecycle
from app.models.query import ChangeNotice, Citation, QueryPipelineSummary, QueryResponse
from app.models.research import ResearchClaim, ResearchStatus, StructuredResearch
from app.models.retrieval import RetrievalRoute
from app.observability.costs import CostEvent, CostTracker, estimate_openai_cost
from app.observability.events import QueryEvent, log_query_event
from app.observability.errors import log_failure
from app.retrieval.pipeline import ApprovedRetriever
from app.retrieval.service import VectorRetrievalService
from app.retrieval.vector_store import is_current_guidance
from app.ingestion.manifest import DocumentManifest
from app.models.documents import DocumentMetadata
from app import clock
from datetime import date

logger = logging.getLogger(__name__)


class RegulatoryQueryService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.vector = VectorRetrievalService(settings)
        self.retriever = ApprovedRetriever(settings, self.vector.store)
        self.generator = get_answer_generator(settings)
        self.cost_tracker = CostTracker(settings.runtime_dir / "cost_events.json")

    def query(
        self,
        user_query: str,
        top_k: int | None = None,
        request_id: str | None = None,
        progress: Callable[[str], None] | None = None,
        as_of: date | None = None,
        on_answer: Callable[[dict], None] | None = None,
        on_partial: Callable[[str], None] | None = None,
    ) -> QueryResponse:
        started = perf_counter()
        day = as_of or clock.now().date()
        request_id = request_id or f"req_{uuid4().hex}"
        if progress:
            progress("understanding_question")
        limit = top_k or self.settings.vector_top_k
        if progress:
            progress("retrieving_official_evidence")
        # ADR-026/027: hybrid search, cited paragraphs, the in-force filter on ``day``, Cohere re-ranking.
        retrieved = self.retriever.search(user_query, day, limit)
        if retrieved.top_score is not None and retrieved.top_score < self.settings.abstain_below:
            return self._abstain_response(user_query, request_id, started, day, retrieved)

        if progress:
            progress("checking_regulatory_validity")
        evidence: list[ChunkMetadata] = list(retrieved.results)
        notices, successor_evidence = self._change_notices(user_query, evidence, day, limit, retrieved.unfiltered)
        candidate_evidence_count = len(evidence) + len(successor_evidence)
        merged = list({chunk.chunk_id: chunk for chunk in successor_evidence + evidence}.values())[:limit]
        excluded_after_validity_check = candidate_evidence_count - len(merged)
        if progress:
            progress("selecting_authoritative_evidence")
        if progress:
            progress("building_grounded_answer")
        sections = self.vector.store.sections(merged)  # empty unless chunks belong to sections (structure chunker)
        generation_started = perf_counter()
        generation = self.generator.generate(user_query, merged, **({"sections": sections} if sections else {}),
                                             as_of=day, notices=[item.text for item in notices],
                                             **({"on_text": on_partial} if on_partial else {}))
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

        answer_ms = round((perf_counter() - generation_started) * 1000, 1)
        checker_cost, checker_usage = 0.0, {}
        check_started = perf_counter()
        if on_answer:  # show the answer now; the claim check (several seconds) adds its verdicts afterwards
            on_answer({"research": research.model_dump(mode="json"), "as_of": str(day),
                       "retrieved_evidence": [chunk.model_dump(mode="json") for chunk in merged],
                       "notices": [notice.model_dump(mode="json") for notice in notices]})
        if research.status is ResearchStatus.GROUNDED and not fallback_used and generation.model != "deterministic":
            if progress:
                progress("checking_claims")
            # ADR-030: every claim is checked against its own citations and flagged, never rewritten.
            try:
                verdicts, checker_usage = claim_checker.check(self.settings.openai_api_key, self.settings.openai_extraction_model,
                                                      research, merged)
                research = claim_checker.with_verdicts(research, verdicts)
                checker_cost = estimate_openai_cost(checker_usage.get("prompt_tokens", 0), checker_usage.get("completion_tokens", 0),
                                                    self.settings.openai_input_cost_per_million,
                                                    self.settings.openai_output_cost_per_million)
            except Exception as exc:  # the answer stands; its claims simply carry no verdict
                log_failure(logger, "claim_check_failed", exc)
        trace = {**retrieved.trace, "timings_ms": {**retrieved.trace.get("timings_ms", {}), "answer": answer_ms,
                 **({"claim_check": round((perf_counter() - check_started) * 1000, 1)} if checker_usage else {})},
                 "tokens": {"answer_input": generation.input_tokens, "answer_output": generation.output_tokens,
                            "check_input": checker_usage.get("prompt_tokens", 0),
                            "check_output": checker_usage.get("completion_tokens", 0)},
                 "cost_usd": {"answer": generation.estimated_cost_usd, "claim_check": checker_cost}}
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
        if checker_usage:
            self.cost_tracker.record(CostEvent(
                timestamp=datetime.now(UTC), operation="claim_check", model=self.settings.openai_extraction_model,
                input_tokens=checker_usage.get("prompt_tokens", 0), output_tokens=checker_usage.get("completion_tokens", 0),
                estimated_cost_usd=checker_cost, correlation_id=request_id,
            ))
        method = "+".join(retrieved.steps)
        log_query_event(QueryEvent(
            timestamp=datetime.now(UTC), request_id=request_id, query=user_query, route=RetrievalRoute.HYBRID.value,
            retrieval_method=method, retrieved_chunk_ids=[chunk.chunk_id for chunk in merged],
            graph_node_count=0, graph_edge_count=0, model=generation.model,
            input_tokens=generation.input_tokens, output_tokens=generation.output_tokens,
            estimated_cost_usd=generation.estimated_cost_usd, latency_ms=latency_ms, citation_valid=citation_valid,
            status="citation_fallback" if fallback_used else "ok",
        ))
        return QueryResponse(
            request_id=request_id, answer=answer, citations=citations, route=RetrievalRoute.HYBRID, in_scope=True,
            retrieved_evidence=merged, latency_ms=latency_ms, estimated_cost_usd=generation.estimated_cost_usd + checker_cost,
            citation_valid=citation_valid, research=research, as_of=day, notices=notices, trace=trace,
            pipeline=QueryPipelineSummary(
                candidate_evidence_count=candidate_evidence_count,
                excluded_after_validity_check=excluded_after_validity_check,
                selected_evidence_count=len(merged), historical_query=day < clock.now().date(),
                answer_mode="excerpt" if fallback_used or generation.model == "deterministic" else "summary",
                retrieval_method=method,
            ),
        )

    def _change_notices(self, query: str, eligible: list[ChunkMetadata], day: date, limit: int,
                        unfiltered: list | None = None) -> tuple[list[ChangeNotice], list[ChunkMetadata]]:
        """Say what replaced a retired rule the question matches, and quote rules not yet in force.

        A retired passage counts when the status filter removed it from the top results the
        answer would otherwise have used. Its successor's best passages are added to the
        evidence. Rank-based; no tuned threshold.
        """
        documents = {item.document_id: item for item in DocumentManifest(self.settings.runtime_dir / "documents.json").all()}
        # Upcoming rules are compared on the store's own relevance scale (the approved path ranks, it does not score).
        best = max((item.similarity_score for item in self.vector.store.search(query, top_k=1, as_of=day)), default=0.0)
        notices: list[ChangeNotice] = []
        extra: list[ChunkMetadata] = []
        seen: set[str] = set()
        ranked = unfiltered if unfiltered is not None else self.retriever.search(query, day, limit, filtered=False).results
        for result in ranked:  # the main search's own ranking before the in-force filter: no second search
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
    def _cited_ids(research: StructuredResearch) -> set[str]:
        claims = ([research.direct_answer] if research.direct_answer else []) + [
            claim for section in research.sections for claim in section.claims
        ]
        return {citation_id for claim in claims if claim for citation_id in claim.citation_ids}

    def _abstain_response(self, query: str, request_id: str, started: float, day: date, retrieved) -> QueryResponse:
        """No indexed passage is relevant enough to answer from (re-ranker score below ADR-026's threshold)."""
        route = RetrievalRoute.HYBRID
        research = StructuredResearch(
            status=ResearchStatus.OUT_OF_SCOPE,
            direct_answer=ResearchClaim(text=(
                "The indexed RBI lending rules do not contain a passage that answers this question, so I have not "
                "answered it. The corpus covers RBI's NBFC lending directions and the circulars they replaced."),
                citation_ids=[]),
            related_questions=[
                "What are RBI's rules on penal charges in loan accounts?",
                "Which entities do the RBI Digital Lending Directions, 2025 apply to?",
            ],
        )
        latency_ms = round((perf_counter() - started) * 1000, 2)
        log_query_event(QueryEvent(
            timestamp=datetime.now(UTC), request_id=request_id, query=query, route=route.value,
            retrieval_method="+".join(retrieved.steps), retrieved_chunk_ids=[], graph_node_count=0, graph_edge_count=0,
            model="abstained", input_tokens=0, output_tokens=0, estimated_cost_usd=0.0,
            latency_ms=latency_ms, citation_valid=True, status=f"abstained top_score={retrieved.top_score:.3f}",
        ))
        return QueryResponse(
            request_id=request_id, answer=research_to_markdown(research), citations=[], route=route, in_scope=False,
            retrieved_evidence=[], latency_ms=latency_ms, estimated_cost_usd=0.0, citation_valid=True, research=research,
            as_of=day, pipeline=QueryPipelineSummary(retrieval_method="+".join(retrieved.steps), answer_mode="abstained"),
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
