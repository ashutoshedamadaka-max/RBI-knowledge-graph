"""The live retrieval path approved at the Phase 3 and 4 gates (ADR-026, ADR-027).

BM25 and OpenAI embeddings fused by reciprocal rank, then the paragraphs the top results cite (graph
REFERS_TO), then the past-date filter, then Cohere re-ranking of the first 30. Without an OpenAI key
it is BM25 alone, without a Cohere key there is no re-ranking and no abstention score, and without a
built graph there is no expansion; the result says which steps ran.
"""
import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import date

from app.config.settings import Settings
from app.observability.errors import log_failure
from app.observability.pipeline import PipelineRun, public_passage
from app.models.chunks import ChunkMetadata, VectorSearchResult
from app.retrieval.hybrid import BM25, CohereReranker, Dense, GraphExpansion, OpenAIEmbedder, corpus_embeddings, rrf
from app.retrieval.vector_store import UNSETTLED, is_current_guidance

logger = logging.getLogger(__name__)


@dataclass
class Retrieved:
    results: list[VectorSearchResult]
    top_score: float | None  # Cohere's top relevance score; None when re-ranking did not run
    steps: list[str] = field(default_factory=list)
    trace: dict = field(default_factory=dict)  # what each step did, for the answer's trace drawer
    unfiltered: list[VectorSearchResult] = field(default_factory=list)  # the same ranking before the in-force filter


# Indexes depend only on the chunk texts and the graph file, so every request shares them. The API creates a
# query service per request; keeping the index on the instance rebuilt it (~15 s) for every question.
_INDEXES: dict = {}
_BUILD_LOCK = threading.Lock()
_EXPANSION_LOCK = threading.Lock()


class ApprovedRetriever:
    def __init__(self, settings: Settings, store) -> None:
        self.settings, self.store = settings, store
        self.rerank_waits: tuple[int, ...] = (0,)  # live queries try Cohere once

    def _build(self, rows: list[dict]):
        """Indexes depend only on chunk texts; statuses are read fresh from the store on every query."""
        texts = [row["text"] for row in rows]
        graph_file = self.settings.data_dir / "graph" / "graph.json"
        key = (hashlib.sha256("\n".join(row["chunk_id"] for row in rows).encode()).hexdigest(),
               bool(self.settings.openai_api_key), graph_file.stat().st_mtime_ns if graph_file.exists() else None)
        if key in _INDEXES:
            return _INDEXES[key]
        with _BUILD_LOCK:  # a question during the start-up warm-up waits for it rather than building twice
            if key not in _INDEXES:
                self._build_into(key, rows, texts, graph_file)
        return _INDEXES[key]

    def _build_into(self, key, rows: list[dict], texts: list[str], graph_file) -> None:
        bm25 = BM25(texts)
        dense = None
        if self.settings.openai_api_key:
            embedder = OpenAIEmbedder(self.settings.openai_api_key)
            try:
                dense = Dense(embedder, corpus_embeddings(embedder, texts, self.settings.runtime_dir / "embedding-cache"))
            except Exception as exc:  # the answer still comes from BM25; the result records it
                log_failure(logger, "dense_index_unavailable", exc)
        expansion = None
        if graph_file.exists():
            from app.graph import ontology
            expansion = GraphExpansion(ontology.load(graph_file), [ChunkMetadata.model_validate(row) for row in rows])
        _INDEXES.clear()  # one corpus is served at a time; keep memory flat
        _INDEXES[key] = (bm25, dense, expansion)

    def warm(self) -> None:
        """Build the indexes before the first question (called at start-up, in the background)."""
        rows = self.store._chunks()
        if rows:
            self._build(rows)

    def search(self, query: str, day: date, limit: int, filtered: bool = True, run: PipelineRun | None = None) -> Retrieved:
        run = run or PipelineRun()
        run.start("prepare", "Opening the indexed corpus and preparing search.")
        rows = self.store._chunks()
        if not rows or not query.strip():
            run.finish("prepare", "No searchable passages are available.")
            for stage in ("bm25", "openai_embeddings", "graph_cross_references", "in_force_filter", "cohere_rerank"):
                run.skip(stage, "No searchable passages.")
            return Retrieved([], None)
        bm25, dense, expansion = self._build(rows)
        run.finish("prepare", f"{len(rows)} indexed passages available.", count=len(rows))
        trace: dict = {"timings_ms": {}, "candidates": {}}
        clock_start = time.perf_counter()

        def lap(stage: str) -> None:
            nonlocal clock_start
            trace["timings_ms"][stage] = round((time.perf_counter() - clock_start) * 1000, 1)
            clock_start = time.perf_counter()

        def ids(indices) -> list[str]:
            return [rows[index]["chunk_id"] for index in indices[:TRACE_TOP]]

        def passages(indices):
            return [public_passage(rows[index]) for index in indices[:TRACE_TOP]]

        steps = ["bm25"]
        run.start("bm25", "Matching the words in your question.", model="BM25 keyword search")
        order = bm25.rank(query)
        trace["candidates"]["bm25"] = ids(order)
        lap("bm25")
        run.finish("bm25", f"{len(order)} passages matched; showing the leading {min(len(order), TRACE_TOP)}.",
                   count=len(order), evidence=passages(order))
        if dense is not None:
            run.start("openai_embeddings", "Searching by meaning and combining the rankings.", model="text-embedding-3-small")
            try:
                if hasattr(dense, "rank_with_usage"):
                    dense_order, query_tokens = dense.rank_with_usage(query)
                else:
                    dense_order, query_tokens = dense.rank(query), None
                trace["candidates"]["openai_embeddings"] = ids(dense_order)
                order = rrf(order, dense_order)
                trace["candidates"]["fused"] = ids(order)
                steps.append("openai_embeddings")
                run.finish("openai_embeddings", f"Combined keyword and meaning search into {len(order)} candidates.",
                           evidence=passages(order), count=len(order), input_tokens=query_tokens,
                           cost_usd=query_tokens * OpenAIEmbedder.price_per_million / 1_000_000 if query_tokens is not None else None,
                           cost_basis="Input tokens × configured $0.02 per million; query embedding only.")
            except Exception as exc:
                log_failure(logger, "dense_query_failed", exc)
                run.finish("openai_embeddings", "Meaning search failed; continuing with keyword results.", status="failed", cost_usd=None)
            lap("openai_embeddings")
        else:
            run.skip("openai_embeddings", "Meaning search is unavailable; using keyword search.")
        if expansion is not None:
            run.start("graph_cross_references", "Following references in the leading passages.")
            with _EXPANSION_LOCK:
                order = expansion(order)
                added = list(expansion.last_added)
            trace["graph_added"] = [{"from": rows[a]["chunk_id"], "to": rows[b]["chunk_id"]} for a, b in added]
            steps.append("graph_cross_references")
            lap("graph_cross_references")
            # Include both endpoints of every displayed edge; no invented relationships.
            visible_added = added[:TRACE_TOP]
            run.finish("graph_cross_references", f"{len(added)} referenced passages added to the ranking.", count=len(added),
                       evidence=[public_passage(rows[i]) for i in dict.fromkeys(i for pair in visible_added for i in pair)] + passages(order),
                       edges=trace["graph_added"][:TRACE_TOP])
        else:
            run.skip("graph_cross_references", "No reference graph is available for this corpus.")
        unfiltered = order[:limit]
        if filtered:
            run.start("in_force_filter", f"Checking source validity on {day}.")
            inspected_count = min(len(order), self.settings.rerank_candidates)
            removed = [index for index in order[:self.settings.rerank_candidates] if not is_current_guidance(rows[index], day)]
            trace["filtered_out"] = [{"chunk_id": rows[index]["chunk_id"], "document_title": rows[index]["document_title"],
                                      "reason": why_excluded(rows[index], day)} for index in removed[:TRACE_TOP]]
            trace["filtered_out_count"] = len(removed)
            order = [index for index in order if is_current_guidance(rows[index], day)]
            steps.append("in_force_filter")
            lap("in_force_filter")
            run.finish("in_force_filter", f"{len(removed)} of the leading candidates excluded for this date.",
                       count=len(removed), removed=trace["filtered_out"], evidence=passages(order),
                       inspected_count=inspected_count)
        else:
            run.skip("in_force_filter", "Historical unfiltered retrieval requested.")
        order = order[:self.settings.rerank_candidates]
        top_score = None
        if filtered and self.settings.cohere_api_key and order:
            run.start("cohere_rerank", f"Re-ranking {len(order)} passages against the question.", model="rerank-v3.5")
            reranker = CohereReranker(self.settings.cohere_api_key, waits=self.rerank_waits)
            try:
                before = list(order)
                order = [before[i] for i in reranker.rerank(query, [rows[i]["text"] for i in before])]
                top_score = reranker.top_score
                trace["rerank"] = [{"chunk_id": rows[index]["chunk_id"], "before": before.index(index) + 1, "after": rank,
                                    "score": round(reranker.scores.get(before.index(index), 0.0), 4)}
                                   for rank, index in enumerate(order[:TRACE_TOP], start=1)]
                steps.append("cohere_rerank")
                units = reranker.search_units if getattr(reranker, "usage_reported", False) else None
                run.finish("cohere_rerank", f"Re-ranked {len(order)} passages; selected the leading {min(limit, len(order))}.",
                           evidence=passages(order[:limit]), ranking=trace["rerank"], search_units=units,
                           cost_usd=units * self.settings.cohere_cost_per_thousand_searches / 1000 if units is not None else None,
                           cost_basis=f"Reported search units × configured ${self.settings.cohere_cost_per_thousand_searches:g} per thousand.")
            except Exception as exc:  # keep the fused order; no abstention score this time
                log_failure(logger, "rerank_failed", exc)
                run.finish("cohere_rerank", "Re-ranking failed; keeping the combined search order.", status="failed", cost_usd=None)
            lap("cohere_rerank")
        else:
            run.skip("cohere_rerank", "Re-ranking is unavailable or there are no eligible passages.")
        results = [VectorSearchResult(**rows[index], similarity_score=round(1 / (rank + 1), 6))
                   for rank, index in enumerate(order[:limit])]
        return Retrieved(results, top_score, steps, trace,
                         [VectorSearchResult(**rows[index], similarity_score=round(1 / (rank + 1), 6))
                          for rank, index in enumerate(unfiltered)])


TRACE_TOP = 10  # how many candidates per step the trace keeps


def why_excluded(chunk: dict, day: date) -> str:
    """The plain reason the in-force filter removed a passage on ``day``."""
    lifecycle = (chunk.get("lifecycle") or "UNKNOWN").upper()
    if lifecycle in UNSETTLED:
        return "status not yet confirmed by review"
    if chunk.get("in_force_from") and date.fromisoformat(chunk["in_force_from"]) > day:
        return f"not yet in force on {day} (from {chunk['in_force_from']})"
    if chunk.get("in_force_to") and date.fromisoformat(chunk["in_force_to"]) <= day:
        return f"no longer in force on {day} (ended {chunk['in_force_to']}, {lifecycle.lower()})"
    if chunk.get("is_current") is False:
        return "an older version of the RBI page"
    return f"{lifecycle.lower()}"
