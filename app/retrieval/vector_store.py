import json
import re
from pathlib import Path

from app.embeddings.hashing import HashingEmbedder
from app.models.chunks import ChunkMetadata, VectorSearchResult


class LocalVectorStore:
    """Filesystem-backed vector index used by the local-first development mode."""

    def __init__(self, path: Path, embedder: HashingEmbedder | None = None) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or HashingEmbedder()

    def _read(self) -> list[dict]:
        return json.loads(self.path.read_text()) if self.path.exists() else []

    def upsert(self, chunks: list[ChunkMetadata]) -> None:
        indexed = {row["chunk"]["chunk_id"]: row for row in self._read()}
        for chunk in chunks:
            indexed[chunk.chunk_id] = {
                "chunk": chunk.model_dump(mode="json"),
                "embedding": self.embedder.embed(chunk.text),
            }
        self.path.write_text(json.dumps(list(indexed.values()), indent=2))

    @staticmethod
    def _keywords(value: str) -> set[str]:
        """Return meaningful terms for a small, explainable lexical relevance signal."""
        stop_words = {
            "about", "after", "against", "among", "and", "are", "can", "does", "for",
            "from", "how", "into", "must", "of", "on", "or", "rbi", "the", "to",
            "under", "what", "when", "which", "with", "would",
        }
        return {
            word
            for word in re.findall(r"[a-z0-9]{3,}", value.lower())
            if word not in stop_words
        }

    @classmethod
    def _lexical_score(cls, query_terms: set[str], text: str, title: str) -> float:
        """Reward direct term matches, especially when the official document title matches."""
        if not query_terms:
            return 0.0
        text_overlap = len(query_terms & cls._keywords(text)) / len(query_terms)
        title_overlap = len(query_terms & cls._keywords(title)) / len(query_terms)
        return (0.55 * text_overlap) + (0.45 * title_overlap)

    def search(self, query: str, top_k: int = 5, current_only: bool = True) -> list[VectorSearchResult]:
        if not query.strip():
            return []
        query_embedding = self.embedder.embed(query)
        query_terms = self._keywords(query)
        matches = []
        for row in self._read():
            chunk = row["chunk"]
            # File-version recency is not regulatory authority. Current-guidance
            # retrieval is limited to evidence-backed, operative sources.
            if current_only and not chunk.get("authority_current", False):
                continue
            vector_score = max(0.0, self.embedder.similarity(query_embedding, row["embedding"]))
            lexical_score = self._lexical_score(query_terms, chunk["text"], chunk["document_title"])
            # Semantic similarity remains the primary signal, while exact lending-topic and
            # official-document-title matches prevent unrelated boilerplate from winning.
            relevance_score = (0.55 * vector_score) + (0.45 * lexical_score)
            matches.append(VectorSearchResult(**chunk, similarity_score=round(relevance_score, 6)))
        return sorted(matches, key=lambda result: result.similarity_score, reverse=True)[:top_k]

    def get_by_ids(self, chunk_ids: list[str]) -> list[ChunkMetadata]:
        wanted = set(chunk_ids)
        return [ChunkMetadata.model_validate(row["chunk"]) for row in self._read() if row["chunk"]["chunk_id"] in wanted]

    def get_by_document_id(self, document_id: str) -> list[ChunkMetadata]:
        return [ChunkMetadata.model_validate(row["chunk"]) for row in self._read() if row["chunk"]["document_id"] == document_id]

    def mark_document_not_current(self, document_id: str, valid_to: str) -> None:
        rows = self._read()
        for row in rows:
            if row["chunk"]["document_id"] == document_id:
                row["chunk"]["is_current"] = False
                row["chunk"]["valid_to"] = valid_to
        self.path.write_text(json.dumps(rows, indent=2))

    def apply_lifecycle(self, document_id: str, lifecycle: str) -> None:
        rows = self._read()
        authority_current = lifecycle in {"ACTIVE", "AMENDED"}
        for row in rows:
            if row["chunk"]["document_id"] == document_id:
                row["chunk"]["lifecycle"] = lifecycle
                row["chunk"]["authority_current"] = authority_current
        self.path.write_text(json.dumps(rows, indent=2))

    def remove_document_ids(self, document_ids: set[str]) -> None:
        if not document_ids:
            return
        rows = [row for row in self._read() if row["chunk"]["document_id"] not in document_ids]
        self.path.write_text(json.dumps(rows, indent=2))
