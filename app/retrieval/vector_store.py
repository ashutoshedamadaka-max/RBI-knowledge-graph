import json
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

    def search(self, query: str, top_k: int = 5) -> list[VectorSearchResult]:
        if not query.strip():
            return []
        query_embedding = self.embedder.embed(query)
        matches = [
            VectorSearchResult(
                **row["chunk"],
                similarity_score=round(self.embedder.similarity(query_embedding, row["embedding"]), 6),
            )
            for row in self._read()
        ]
        return sorted(matches, key=lambda result: result.similarity_score, reverse=True)[:top_k]

    def get_by_ids(self, chunk_ids: list[str]) -> list[ChunkMetadata]:
        wanted = set(chunk_ids)
        return [ChunkMetadata.model_validate(row["chunk"]) for row in self._read() if row["chunk"]["chunk_id"] in wanted]
