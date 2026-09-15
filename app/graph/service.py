from app.config.settings import Settings
from app.graph.extraction import get_extractor
from app.graph.store import ProvenanceGraph
from app.models.chunks import ChunkMetadata
from app.models.documents import DocumentMetadata


class GraphIngestionService:
    def __init__(self, settings: Settings) -> None:
        self.extractor = get_extractor(settings)
        self.store = ProvenanceGraph(settings.runtime_dir / "knowledge_graph.json")

    def index_chunks(self, chunks: list[ChunkMetadata]) -> None:
        for chunk in chunks:
            self.store.add_extraction(chunk, self.extractor.extract(chunk), persist=False)
        self.store.persist()

    def apply_document_lifecycle(self, document: DocumentMetadata) -> None:
        self.store.apply_document_lifecycle(
            document.document_id, document.title, document.lifecycle.value,
            document.status_evidence_url or document.source_url or "",
            document.status_evidence_excerpt or "",
        )
