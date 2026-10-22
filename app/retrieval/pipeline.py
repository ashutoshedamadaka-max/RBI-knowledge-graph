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
                logger.warning("dense_index_unavailable error=%s", exc)
        expansion = None
        if graph_file.exists():
            from app.graph import ontology
            expansion = GraphExpansion(ontology.load(graph_file), [ChunkMetadata.model_validate(row) for row in rows])
        _INDEXES.clear()  # one corpus is served at a time; keep memory flat
        _INDEXES[key] = (bm25, dense, expansion)

    def warm(self) -> None:
        """Build the indexes before the first question (called at start-up, in the background)."""
        rows = [row["chunk"] for row in self.store._rows()]
        if rows:
            self._build(rows)

    def search(self, query: str, day: date, limit: int, filtered: bool = True) -> Retrieved:
        rows = [row["chunk"] for row in self.store._rows()]
        if not rows or not query.strip():
            return Retrieved([], None)
        bm25, dense, expansion = self._build(rows)
        trace: dict = {"timings_ms": {}, "candidates": {}}
        clock_start = time.perf_counter()

        def lap(stage: str) -> None:
            nonlocal clock_start
            trace["timings_ms"][stage] = round((time.perf_counter() - clock_start) * 1000, 1)
            clock_start = time.perf_counter()

        def ids(indices) -> list[str]:
            return [rows[index]["chunk_id"] for index in indices[:TRACE_TOP]]

        steps = ["bm25"]
        order = bm25.rank(query)
        trace["candidates"]["bm25"] = ids(order)
        lap("bm25")
        if dense is not None:
            try:
                dense_order = dense.rank(query)
                trace["candidates"]["openai_embeddings"] = ids(dense_order)
                order = rrf(order, dense_order)
                trace["candidates"]["fused"] = ids(order)
                steps.append("openai_embeddings")
            except Exception as exc:
                logger.warning("dense_query_failed error=%s", exc)
            lap("openai_embeddings")
        if expansion is not None:
            order = expansion(order)
            trace["graph_added"] = [{"from": rows[a]["chunk_id"], "to": rows[b]["chunk_id"]} for a, b in expansion.last_added]
            steps.append("graph_cross_references")
            lap("graph_cross_references")
        unfiltered = order[:limit]
        if filtered:
            removed = [index for index in order[:self.settings.rerank_candidates] if not is_current_guidance(rows[index], day)]
            trace["filtered_out"] = [{"chunk_id": rows[index]["chunk_id"], "document_title": rows[index]["document_title"],
                                      "reason": why_excluded(rows[index], day)} for index in removed[:TRACE_TOP]]
            trace["filtered_out_count"] = len(removed)
            order = [index for index in order if is_current_guidance(rows[index], day)]
            steps.append("in_force_filter")
            lap("in_force_filter")
        order = order[:self.settings.rerank_candidates]
        top_score = None
        if filtered and self.settings.cohere_api_key and order:
            reranker = CohereReranker(self.settings.cohere_api_key, waits=self.rerank_waits)
            try:
                before = list(order)
                order = [before[i] for i in reranker.rerank(query, [rows[i]["text"] for i in before])]
                top_score = reranker.top_score
                trace["rerank"] = [{"chunk_id": rows[index]["chunk_id"], "before": before.index(index) + 1, "after": rank,
                                    "score": round(reranker.scores.get(before.index(index), 0.0), 4)}
                                   for rank, index in enumerate(order[:TRACE_TOP], start=1)]
                steps.append("cohere_rerank")
            except Exception as exc:  # keep the fused order; no abstention score this time
                logger.warning("rerank_failed error=%s", exc)
            lap("cohere_rerank")
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
