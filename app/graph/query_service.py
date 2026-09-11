from app.config.settings import Settings
from app.graph.retrieval import GraphRetriever
from app.graph.store import ProvenanceGraph
from app.models.retrieval import GraphRetrievalResult


class GraphRetrievalService:
    def __init__(self, settings: Settings) -> None:
        self.retriever = GraphRetriever(ProvenanceGraph(settings.runtime_dir / "knowledge_graph.json"))

    def retrieve_graph(self, query: str) -> GraphRetrievalResult:
        return self.retriever.retrieve_graph(query)

