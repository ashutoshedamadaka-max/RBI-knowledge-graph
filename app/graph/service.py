from app.config.settings import Settings
from app.graph.extraction import get_extractor
from app.graph.store import ProvenanceGraph
from app.models.chunks import ChunkMetadata


class GraphIngestionService:
    def __init__(self, settings: Settings) -> None:
        self.extractor = get_extractor(settings)
        self.store = ProvenanceGraph(settings.runtime_dir / "knowledge_graph.json")

    def index_chunks(self, chunks: list[ChunkMetadata]) -> None:
        for chunk in chunks:
            self.store.add_extraction(chunk, self.extractor.extract(chunk))

