"""The approved retrieval path (ADR-026): BM25 and OpenAI embeddings fused by reciprocal rank, the paragraphs
the top results cite (ADR-027), and Cohere re-ranking. Each retriever returns chunk indices, best first.
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

    def __init__(self, api_key: str, waits: tuple[int, ...] = (0,)) -> None:
        # Live queries try once; the evaluation ladder waits out a trial key's per-minute limit.
        self.api_key, self.waits, self.search_units, self.top_score = api_key, waits, 0, 0.0

    def rerank(self, query: str, texts: list[str]) -> list[int]:
        for wait in self.waits:
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
        self.scores = {item["index"]: item["relevance_score"] for item in body["results"]}
        return [item["index"] for item in body["results"]]



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
        added, self.last_added = [], []
        for index in top:
            for provision in self.provisions_in[index]:
                for _, target, data in self.graph.out_edges(provision, data=True):
                    cited = self.chunk_of.get(target) if data["type"] == "REFERS_TO" else None
                    if cited is not None and cited not in top and cited not in added:
                        added.append(cited)
                        self.last_added.append((index, cited))
        return top + added + [index for index in order[self.head:] if index not in added]
