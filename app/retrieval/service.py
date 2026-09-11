from app.config.settings import Settings
from app.models.chunks import VectorSearchResult
from app.retrieval.vector_store import LocalVectorStore


class VectorRetrievalService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = LocalVectorStore(settings.runtime_dir / "vectors.json")

    def retrieve_vector(self, query: str, top_k: int | None = None) -> list[VectorSearchResult]:
        limit = top_k if top_k is not None else self.settings.vector_top_k
        return self.store.search(query, top_k=limit)

