from app.ingestion.service import IngestionService
from app.models.monitoring import DiscoveredDocument


class MonitoringDocumentProcessor:
    """Adapts discovered source text to the existing provenance-first ingestion path."""

    def __init__(self, ingestion: IngestionService) -> None:
        self.ingestion = ingestion

    def __call__(self, document: DiscoveredDocument, text: str, version: int) -> tuple[str | None, list[str]]:
        response = self.ingestion.ingest_content(
            content=text.encode("utf-8"),
            source_url=document.canonical_url,
            file_name="rbi_monitor_source.txt",
            title=document.title,
            publication_date=document.publication_date,
            document_version=version,
        )
        chunks = self.ingestion.vector_store.get_by_document_id(response.document.document_id)
        return response.document.document_id, [chunk.chunk_id for chunk in chunks]

    def mark_previous(self, document_id: str, valid_to: str) -> None:
        self.ingestion.vector_store.mark_document_not_current(document_id, valid_to)
