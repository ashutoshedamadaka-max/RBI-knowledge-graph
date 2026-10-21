from datetime import date

from app.config.settings import Settings
from app.models.chunks import VectorSearchResult
from app.retrieval.vector_store import open_vector_store


class VectorRetrievalService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = open_vector_store(settings)

    def retrieve_vector(self, query: str, top_k: int | None = None, current_only: bool = True,
                        as_of: date | None = None) -> list[VectorSearchResult]:
        limit = top_k if top_k is not None else self.settings.vector_top_k
        return self.store.search(query, top_k=limit, current_only=current_only, as_of=as_of)
