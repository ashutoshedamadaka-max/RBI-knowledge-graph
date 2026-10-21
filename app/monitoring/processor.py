from app.ingestion.service import IngestionService
from app.models.monitoring import DiscoveredDocument
from app.models.documents import DocumentLifecycle
from app.monitoring.lifecycle import LifecycleResolution, resolve_lifecycle
from app.monitoring.metadata import extract_rbi_document_facts


# Statuses set from evidence a check cannot re-read: a reviewer's approval or a trusted successor link.
PERSISTENT_METHODS = {"ADMIN_REVIEW", "AUTO_SUCCESSOR", "RBI_WITHDRAWN_REGISTER"}
OFFICIAL_NEGATIVE = {DocumentLifecycle.WITHDRAWN, DocumentLifecycle.REPEALED, DocumentLifecycle.SUPERSEDED}


class MonitoringDocumentProcessor:
    """Adapts discovered source text to the existing provenance-first ingestion path."""

    def __init__(self, ingestion: IngestionService) -> None:
        self.ingestion = ingestion

    def __call__(
        self, document: DiscoveredDocument, text: str, version: int, raw_html: str | None = None,
    ) -> tuple[str | None, list[str]]:
        # A curated source may have been deliberately loaded before monitoring was enabled.
        # Adopt that evidence for its initial monitored version instead of creating a duplicate.
        existing = self.ingestion.manifest.get_by_source_url(document.canonical_url)
        if existing and version == 1:
            chunks = self.ingestion.vector_store.get_by_document_id(existing.document_id)
            return existing.document_id, [chunk.chunk_id for chunk in chunks]
        # Prefer the fetched page: the same extractor runs on it at ingestion, and the
        # stored HTML keeps headings, tables and status markup for later parsing.
        response = self.ingestion.ingest_content(
            content=(raw_html or text).encode("utf-8"),
            source_url=document.canonical_url,
            file_name="rbi_page.html" if raw_html else "rbi_monitor_source.txt",
            title=document.title,
            publication_date=document.publication_date,
            document_version=version,
        )
        chunks = self.ingestion.vector_store.get_by_document_id(response.document.document_id)
        return response.document.document_id, [chunk.chunk_id for chunk in chunks]

    def mark_previous(self, document_id: str, valid_to: str) -> None:
        self.ingestion.mark_document_not_current(document_id, valid_to)

    def assess_lifecycle(self, document: DiscoveredDocument, text: str, resolution=None):
        resolution = resolution or resolve_lifecycle(text)
        existing = self.ingestion.manifest.get_by_source_url(document.canonical_url)
        if (
            existing
            and resolution.lifecycle not in OFFICIAL_NEGATIVE
            and existing.lifecycle in {DocumentLifecycle.ACTIVE, DocumentLifecycle.AMENDED, DocumentLifecycle.SUPERSEDED,
                                       DocumentLifecycle.WITHDRAWN}
            and existing.status_resolution_method in PERSISTENT_METHODS
        ):
            # A status from a reviewer or a trusted successor link rests on evidence this check
            # cannot re-read. Finding no signal, or the curated approval, does not change it;
            # only a negative finding on the RBI page (watermark or withdrawal wording) does.
            resolution = LifecycleResolution(
                existing.lifecycle, existing.status_evidence_excerpt or "", resolution.checked_at,
                existing.status_resolution_method,
            )
        facts = extract_rbi_document_facts(text)
        self.ingestion.apply_lifecycle(
            document.canonical_url, resolution.lifecycle, resolution.excerpt, resolution.checked_at, resolution.resolution_method,
        )
        self.ingestion.apply_monitoring_metadata(document.canonical_url, facts, resolution.checked_at)
        return resolution
