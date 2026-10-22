"""The live retrieval path approved at the Phase 3 and 4 gates (ADR-026, ADR-027).

BM25 and OpenAI embeddings fused by reciprocal rank, then the paragraphs the top results cite (graph
REFERS_TO), then the past-date filter, then Cohere re-ranking of the first 30. Without an OpenAI key
it is BM25 alone, without a Cohere key there is no re-ranking and no abstention score, and without a
built graph there is no expansion; the result says which steps ran.
"""
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date

from app.config.settings import Settings
from app.models.chunks import ChunkMetadata, VectorSearchResult
from app.retrieval.hybrid import BM25, CohereReranker, Dense, GraphExpansion, OpenAIEmbedder, corpus_embeddings, rrf
from app.retrieval.vector_store import is_current_guidance

logger = logging.getLogger(__name__)


@dataclass
class Retrieved:
    results: list[VectorSearchResult]
    top_score: float | None  # Cohere's top relevance score; None when re-ranking did not run
    steps: list[str] = field(default_factory=list)


class ApprovedRetriever:
    def __init__(self, settings: Settings, store) -> None:
        self.settings, self.store = settings, store
        self._key, self._index = None, None
        self.rerank_waits: tuple[int, ...] = (0,)  # live queries try Cohere once

    def _build(self, rows: list[dict]):
        """Indexes depend only on chunk texts; statuses are read fresh from the store on every query."""
        texts = [row["text"] for row in rows]
        key = hashlib.sha256("\n".join(row["chunk_id"] for row in rows).encode()).hexdigest()
        if key == self._key:
            return self._index
        bm25 = BM25(texts)
        dense = None
        if self.settings.openai_api_key:
            embedder = OpenAIEmbedder(self.settings.openai_api_key)
            try:
                dense = Dense(embedder, corpus_embeddings(embedder, texts, self.settings.runtime_dir / "embedding-cache"))
            except Exception as exc:  # the answer still comes from BM25; the result records it
                logger.warning("dense_index_unavailable error=%s", exc)
        expansion = None
        graph_file = self.settings.data_dir / "graph" / "graph.json"
        if graph_file.exists():
            from app.graph import ontology
            expansion = GraphExpansion(ontology.load(graph_file), [ChunkMetadata.model_validate(row) for row in rows])
        self._key, self._index = key, (bm25, dense, expansion)
        return self._index

    def search(self, query: str, day: date, limit: int, filtered: bool = True) -> Retrieved:
        rows = [row["chunk"] for row in self.store._read()]
        if not rows or not query.strip():
            return Retrieved([], None)
        bm25, dense, expansion = self._build(rows)
        steps = ["bm25"]
        order = bm25.rank(query)
        if dense is not None:
            try:
                order = rrf(order, dense.rank(query))
                steps.append("openai_embeddings")
            except Exception as exc:
                logger.warning("dense_query_failed error=%s", exc)
        if expansion is not None:
            order = expansion(order)
            steps.append("graph_cross_references")
        if filtered:
            order = [index for index in order if is_current_guidance(rows[index], day)]
            steps.append("in_force_filter")
        order = order[:self.settings.rerank_candidates]
        top_score = None
        if filtered and self.settings.cohere_api_key and order:
            reranker = CohereReranker(self.settings.cohere_api_key, waits=self.rerank_waits)
            try:
                order = [order[i] for i in reranker.rerank(query, [rows[i]["text"] for i in order])]
                top_score = reranker.top_score
                steps.append("cohere_rerank")
            except Exception as exc:  # keep the fused order; no abstention score this time
                logger.warning("rerank_failed error=%s", exc)
        results = [VectorSearchResult(**rows[index], similarity_score=round(1 / (rank + 1), 6))
                   for rank, index in enumerate(order[:limit])]
        return Retrieved(results, top_score, steps)
