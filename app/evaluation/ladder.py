"""Phase 3 retrieval ladder: the evaluation-only rungs (bge embeddings and re-ranker) and nDCG.

The approved pieces live in app/retrieval/hybrid.py; sentence-transformers is in requirements-eval.txt.
"""
import math

import numpy as np

from app.retrieval.hybrid import (  # noqa: F401  (re-exported for the ladder runner and tests)
    BM25, CohereReranker, Dense, GraphExpansion, OpenAIEmbedder, corpus_embeddings, rrf, tokens)

__all__ = ["BM25", "CohereReranker", "Dense", "GraphExpansion", "OpenAIEmbedder", "corpus_embeddings", "rrf",
           "tokens", "BgeEmbedder", "BgeReranker", "ndcg_at"]

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge-*-en-v1.5 model card


class BgeEmbedder:
    price_per_million = 0.0  # runs locally
    name = "BAAI/bge-base-en-v1.5"

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer
        self.model, self.tokens = SentenceTransformer(self.name, device="cpu"), 0

    def embed(self, texts: list[str], query: bool = False) -> np.ndarray:
        texts = [BGE_QUERY_PREFIX + text for text in texts] if query else texts
        return self.model.encode(texts, batch_size=32, normalize_embeddings=True, convert_to_numpy=True)



class BgeReranker:
    name = "BAAI/bge-reranker-base"

    def __init__(self) -> None:
        from sentence_transformers import CrossEncoder
        self.model, self.search_units = CrossEncoder(self.name, device="cpu"), 0

    def rerank(self, query: str, texts: list[str]) -> list[int]:
        scores = self.model.predict([(query, text) for text in texts], batch_size=32)
        self.top_score = float(np.max(scores)) if len(scores) else 0.0
        return np.argsort(-np.asarray(scores)).tolist()


def ndcg_at(found_texts_urls: list[tuple[str, str]], gold: list[dict], k: int = 10) -> float:
    """Binary-relevance nDCG@k: a result scores once for each gold sentence it newly contains."""
    from app.evaluation.retrieval_metrics import contains, same_page

    left, dcg = list(gold), 0.0
    for rank, (url, text) in enumerate(found_texts_urls[:k], start=1):
        hit = next((item for item in left if same_page(url, item["url"]) and contains(text, item["span"])), None)
        if hit:
            left.remove(hit)
            dcg += 1 / math.log2(rank + 1)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(gold), k) + 1))
    return dcg / ideal if ideal else 0.0


