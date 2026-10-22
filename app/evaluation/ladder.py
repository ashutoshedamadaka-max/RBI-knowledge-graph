"""Phase 3 retrieval ladder: BM25, dense (OpenAI, bge), hybrid by reciprocal rank fusion, re-ranking.

Evaluation only: dense and re-ranking rungs need numpy and, for the open models, sentence-transformers
(requirements-eval.txt). Each retriever returns chunk indices, best first.
"""
import hashlib
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx
import numpy as np

from app.evaluation.questions import normalise

_TOKEN = re.compile(r"[a-z0-9]+")
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge-*-en-v1.5 model card
RRF_K = 60  # Cormack et al. (2009)


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(normalise(text))


class BM25:
    """Okapi BM25 (k1 = 1.2, b = 0.75) over an inverted index."""

    def __init__(self, texts: list[str], k1: float = 1.2, b: float = 0.75) -> None:
        counts = [Counter(tokens(text)) for text in texts]
        lengths = [sum(count.values()) for count in counts]
        average = sum(lengths) / len(lengths)
        self.postings: dict[str, list[tuple[int, float]]] = defaultdict(list)
        for index, count in enumerate(counts):
            norm = k1 * (1 - b + b * lengths[index] / average)
            for term, tf in count.items():
                self.postings[term].append((index, tf * (k1 + 1) / (tf + norm)))
        self.idf = {term: math.log(1 + (len(texts) - len(rows) + 0.5) / (len(rows) + 0.5))
                    for term, rows in self.postings.items()}

    def rank(self, query: str) -> list[int]:
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokens(query)):
            for index, weight in self.postings.get(term, []):
                scores[index] += self.idf[term] * weight
        return sorted(scores, key=lambda index: -scores[index])


class OpenAIEmbedder:
    price_per_million = 0.02  # USD, text-embedding-3-small list price
    name = "openai/text-embedding-3-small"

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self.api_key, self.model, self.tokens = api_key, model, 0

    def embed(self, texts: list[str], query: bool = False) -> np.ndarray:
        rows = []
        for start in range(0, len(texts), 100):
            response = httpx.post("https://api.openai.com/v1/embeddings", timeout=120,
                                  headers={"Authorization": f"Bearer {self.api_key}"},
                                  json={"model": self.model, "input": texts[start:start + 100]})
            response.raise_for_status()
            body = response.json()
            self.tokens += body["usage"]["total_tokens"]
            rows += [item["embedding"] for item in sorted(body["data"], key=lambda item: item["index"])]
        matrix = np.array(rows, dtype=np.float32)
        return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


class BgeEmbedder:
    price_per_million = 0.0  # runs locally
    name = "BAAI/bge-base-en-v1.5"

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer
        self.model, self.tokens = SentenceTransformer(self.name, device="cpu"), 0

    def embed(self, texts: list[str], query: bool = False) -> np.ndarray:
        texts = [BGE_QUERY_PREFIX + text for text in texts] if query else texts
        return self.model.encode(texts, batch_size=32, normalize_embeddings=True, convert_to_numpy=True)


def corpus_embeddings(embedder, texts: list[str], cache_dir: Path) -> np.ndarray:
    """Chunk embeddings, cached by model and text hash so a rerun costs nothing."""
    path = cache_dir / (re.sub(r"[^a-z0-9]+", "-", embedder.name.lower()) + ".npz")
    keys = [hashlib.sha256(text.encode("utf-8")).hexdigest() for text in texts]
    cached = {}
    if path.exists():
        stored = np.load(path)
        cached = dict(zip(stored["keys"].tolist(), stored["vectors"]))
    missing = [index for index, key in enumerate(keys) if key not in cached]
    if missing:
        for index, vector in zip(missing, embedder.embed([texts[index] for index in missing])):
            cached[keys[index]] = vector
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.savez(path, keys=np.array(list(cached)), vectors=np.array(list(cached.values()), dtype=np.float32))
    return np.array([cached[key] for key in keys], dtype=np.float32)


class Dense:
    def __init__(self, embedder, matrix: np.ndarray) -> None:
        self.embedder, self.matrix = embedder, matrix

    def rank(self, query: str) -> list[int]:
        scores = self.matrix @ self.embedder.embed([query], query=True)[0]
        return np.argsort(-scores).tolist()


def rrf(*rankings: list[int], depth: int = 100) -> list[int]:
    """Reciprocal rank fusion of the top ``depth`` of each ranking."""
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, index in enumerate(ranking[:depth], start=1):
            scores[index] += 1 / (RRF_K + rank)
    return sorted(scores, key=lambda index: -scores[index])


class CohereReranker:
    name = "cohere/rerank-v3.5"

    def __init__(self, api_key: str) -> None:
        self.api_key, self.search_units = api_key, 0

    def rerank(self, query: str, texts: list[str]) -> list[int]:
        for wait in (0, 10, 20, 40, 60, 60):  # trial keys are rate-limited per minute: wait and retry
            time.sleep(wait)
            response = httpx.post("https://api.cohere.com/v2/rerank", timeout=60,
                                  headers={"Authorization": f"Bearer {self.api_key}"},
                                  json={"model": "rerank-v3.5", "query": query, "documents": texts, "top_n": len(texts)})
            if response.status_code != 429:
                break
        response.raise_for_status()
        body = response.json()
        self.search_units += body.get("meta", {}).get("billed_units", {}).get("search_units", 0)
        self.top_score = max((item["relevance_score"] for item in body["results"]), default=0.0)
        return [item["index"] for item in body["results"]]


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


class GraphExpansion:
    """After the top results, add the paragraphs they cite (REFERS_TO), before the rest of the ranking."""

    def __init__(self, graph, chunks: list, head: int = 5) -> None:
        self.graph, self.head = graph, head
        by_document = defaultdict(list)
        for index, chunk in enumerate(chunks):
            by_document[chunk.document_id].append(index)
        self.chunk_of, self.provisions_in = {}, defaultdict(list)
        for node, data in graph.nodes(data=True):
            if data["type"] != "Provision":
                continue
            start = normalise(data["text"])[:60]
            index = next((i for i in by_document[data["document_id"]] if start in normalise(chunks[i].text)), None)
            if index is not None:
                self.chunk_of[node] = index
                self.provisions_in[index].append(node)

    def __call__(self, order: list[int]) -> list[int]:
        top = order[:self.head]
        added = []
        for index in top:
            for provision in self.provisions_in[index]:
                for _, target, data in self.graph.out_edges(provision, data=True):
                    cited = self.chunk_of.get(target) if data["type"] == "REFERS_TO" else None
                    if cited is not None and cited not in top and cited not in added:
                        added.append(cited)
        return top + added + [index for index in order[self.head:] if index not in added]
