from app.ingestion.service import IngestionService
from app.models.monitoring import DiscoveredDocument
from app.monitoring.lifecycle import resolve_lifecycle


class MonitoringDocumentProcessor:
    """Adapts discovered source text to the existing provenance-first ingestion path."""

    def __init__(self, ingestion: IngestionService) -> None:
        self.ingestion = ingestion

    def __call__(self, document: DiscoveredDocument, text: str, version: int) -> tuple[str | None, list[str]]:
        # A curated source may have been deliberately loaded before monitoring was enabled.
        # Adopt that evidence for its initial monitored version instead of creating a duplicate.
        existing = self.ingestion.manifest.get_by_source_url(document.canonical_url)
        if existing and version == 1:
            chunks = self.ingestion.vector_store.get_by_document_id(existing.document_id)
            return existing.document_id, [chunk.chunk_id for chunk in chunks]
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

    def assess_lifecycle(self, document: DiscoveredDocument, text: str) -> None:
        resolution = resolve_lifecycle(text)
        self.ingestion.apply_lifecycle(
            document.canonical_url, resolution.lifecycle, resolution.excerpt, resolution.checked_at,
        )
