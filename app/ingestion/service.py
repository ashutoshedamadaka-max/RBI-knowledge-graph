import hashlib
import json
import logging
import mimetypes
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app import clock
from app.config.settings import Settings
from app.ingestion.chunking import chunk_document
from app.ingestion.exceptions import IngestionError
from app.ingestion.manifest import DocumentManifest
from app.ingestion.parser import parse_document
from app.graph.service import GraphIngestionService
from app.models.documents import DocumentLifecycle, DocumentMetadata, IngestRequest, IngestResponse, IngestStatus
from app.retrieval.vector_store import open_vector_store

logger = logging.getLogger(__name__)

NON_OPERATIVE = {DocumentLifecycle.WITHDRAWN, DocumentLifecycle.REPEALED, DocumentLifecycle.SUPERSEDED}


class OfficialStatusError(Exception):
    """A reviewer tried to override an official withdrawal, repeal or supersession."""


class IngestionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.raw_dir.mkdir(parents=True, exist_ok=True)
        settings.processed_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = DocumentManifest(settings.runtime_dir / "documents.json")
        self.vector_store = open_vector_store(settings)
        self.graph_service = GraphIngestionService(settings)

    def ingest(self, request: IngestRequest) -> IngestResponse:
        source_path, source_url, file_name, mime_type = self._acquire(request)
        return self._ingest_acquired(
            source_path, source_url, file_name, mime_type, request.title,
            request.publication_date, request.issuing_authority,
        )

    def ingest_content(
        self, content: bytes, source_url: str, file_name: str, title: str,
        publication_date=None, document_version: int = 1,
    ) -> IngestResponse:
        suffix = Path(file_name).suffix or ".txt"
        temporary = self.settings.raw_dir / f"monitor_{hashlib.sha256(content).hexdigest()[:16]}{suffix}"
        temporary.write_bytes(content)
        mime_type = mimetypes.guess_type(file_name)[0] or "text/plain"
        return self._ingest_acquired(
            temporary, source_url, file_name, mime_type, title, publication_date,
            "Reserve Bank of India", document_version,
        )

    def _ingest_acquired(
        self, source_path: Path, source_url: str | None, file_name: str, mime_type: str,
        title: str | None, publication_date, issuing_authority: str, document_version: int = 1,
    ) -> IngestResponse:
        content = source_path.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()
        existing = self.manifest.get_by_hash(content_hash)
        if existing:
            return IngestResponse(status=IngestStatus.CACHED, document=existing, message="Unchanged document already ingested.")

        # RBI HTML pages can include changing presentation markup. A manual re-upload of
        # the same official page should therefore reuse the existing source record; actual
        # regulatory revisions are handled by the monitored versioning workflow.
        existing_source = self.manifest.get_by_source_url(source_url) if document_version == 1 else None
        if existing_source:
            return IngestResponse(status=IngestStatus.CACHED, document=existing_source, message="Official source page already ingested.")

        document_id = f"doc_{content_hash[:16]}"
        raw_path = self.settings.raw_dir / f"{document_id}{source_path.suffix.lower()}"
        if source_path.resolve() != raw_path.resolve():
            raw_path.write_bytes(content)
        parsed = parse_document(raw_path, mime_type)
        metadata = DocumentMetadata(
            document_id=document_id,
            title=title or self._title_from_name(file_name),
            issuing_authority=issuing_authority,
            publication_date=publication_date,
            source_url=source_url,
            content_hash=content_hash,
            file_name=file_name,
            mime_type=mime_type,
            ingested_at=clock.now(),
            page_count=parsed.page_count,
            document_version=document_version,
            valid_from=clock.now(),
        )
        self.manifest.save(metadata)
        chunks = chunk_document(metadata, parsed.pages, self.settings)
        self.vector_store.upsert(chunks)
        try:
            self.graph_service.index_chunks(chunks)
        except Exception:
            logger.exception("graph_extraction_failed document_id=%s", document_id)
        payload = {"document_id": document_id, "pages": [
            {"page_number": index + 1, "text": text} for index, text in enumerate(parsed.pages)
        ]}
        (self.settings.processed_dir / f"{document_id}.json").write_text(json.dumps(payload, indent=2))
        return IngestResponse(status=IngestStatus.INGESTED, document=metadata, message="Document parsed and cached for chunking.")

    def list_documents(self) -> list[DocumentMetadata]:
        # Present the latest captured version per RBI page; historical versions
        # remain stored for historical research rather than cluttering the catalogue.
        newest: dict[str, DocumentMetadata] = {}
        for document in self.manifest.all():
            key = self.manifest._canonical_url(document.source_url) if document.source_url else document.document_id
            candidate_key = (document.status_checked_at or document.ingested_at, document.document_version, document.ingested_at)
            existing = newest.get(key)
            existing_key = (existing.status_checked_at or existing.ingested_at, existing.document_version, existing.ingested_at) if existing else None
            if existing is None or candidate_key > existing_key:
                newest[key] = document
        return sorted(newest.values(), key=lambda item: item.ingested_at, reverse=True)

    def apply_lifecycle(self, source_url: str, lifecycle, evidence_excerpt: str, checked_at: datetime, resolution_method: str = "AUTOMATED") -> DocumentMetadata | None:
        document = self.manifest.get_by_source_url(source_url)
        if not document:
            return None
        updated = self.manifest.update_lifecycle(document.document_id, lifecycle, source_url, evidence_excerpt, checked_at, resolution_method)
        if updated:
            self.vector_store.apply_lifecycle(updated.document_id, updated.lifecycle.value)
            self.graph_service.apply_document_lifecycle(updated)
            updated = self._close_window(updated, checked_at)
        return updated

    def apply_monitoring_metadata(self, source_url: str, facts, checked_at: datetime) -> DocumentMetadata | None:
        document = self.manifest.get_by_source_url(source_url)
        if not document:
            return None
        updated = self.manifest.update_monitoring_metadata(document.document_id, facts, checked_at)
        if updated and not updated.in_force_from:
            # In force from the stated effective date, else the issue date (ADR-010).
            start = updated.effective_date or updated.publication_date
            if start:
                updated = self.set_in_force(updated.document_id, start, updated.in_force_to)
        return updated

    def get(self, document_id: str) -> DocumentMetadata | None:
        return next((item for item in self.manifest.all() if item.document_id == document_id), None)

    def set_lifecycle(self, document_id: str, lifecycle, evidence_url: str, excerpt: str, checked_at: datetime,
                      resolution_method: str) -> DocumentMetadata | None:
        """Set status by document ID (not by URL, which may hold several versions)."""
        updated = self.manifest.update_lifecycle(document_id, lifecycle, evidence_url, excerpt, checked_at, resolution_method)
        if updated:
            self.vector_store.apply_lifecycle(document_id, updated.lifecycle.value)
            self.graph_service.apply_document_lifecycle(updated)
            updated = self._close_window(updated, checked_at)
        return updated

    def _close_window(self, document: DocumentMetadata, checked_at: datetime) -> DocumentMetadata:
        """A withdrawn rule was in force no later than when the withdrawal was seen (ADR-012).

        A successor link or RBI's register can set an earlier, better-known end; this is the fallback.
        """
        if document.lifecycle in NON_OPERATIVE and document.in_force_to is None:
            return self.set_in_force(document.document_id, document.in_force_from, checked_at.date()) or document
        return document

    def mark_document_current(self, document_id: str) -> DocumentMetadata | None:
        updated = self.manifest.set_fields(document_id, is_current=True, valid_to=None)
        if updated:
            self.vector_store.mark_document_current(document_id)
        return updated

    def set_in_force(self, document_id: str, start, end) -> DocumentMetadata | None:
        updated = self.manifest.set_in_force(document_id, start, end)
        if updated:
            self.vector_store.set_in_force(document_id, start, end)
        return updated

    def mark_document_not_current(self, document_id: str, valid_to: str) -> DocumentMetadata | None:
        updated = self.manifest.mark_not_current(document_id, valid_to)
        if updated:
            self.vector_store.mark_document_not_current(document_id, valid_to)
        return updated

    def approve_lifecycle(self, document_id: str, lifecycle, evidence_url: str, excerpt: str, reviewed_at: datetime) -> DocumentMetadata | None:
        existing = next((item for item in self.manifest.all() if item.document_id == document_id), None)
        if existing and existing.lifecycle in NON_OPERATIVE:
            # Automation may remove trust; a person may not give it back.
            raise OfficialStatusError(
                f"RBI's own evidence marks this document {existing.lifecycle.value.lower()}; a reviewer cannot override it."
            )
        updated = self.manifest.approve_lifecycle(document_id, lifecycle, evidence_url, excerpt, reviewed_at)
        if updated:
            self.vector_store.apply_lifecycle(updated.document_id, updated.lifecycle.value)
            self.graph_service.apply_document_lifecycle(updated)
        return updated

    def cleanup_duplicate_sources(self) -> int:
        """Remove legacy duplicate copies of an RBI page; keep every retired version as history.

        A version the monitor replaced is marked not current and is history. Only an older
        copy that was never retired is a duplicate left by earlier ingestion behaviour.
        """
        by_source: dict[str, list[DocumentMetadata]] = {}
        for document in self.manifest.all():
            if document.source_url:
                key = self.manifest._canonical_url(document.source_url)
                by_source.setdefault(key, []).append(document)
        stale_ids: set[str] = set()
        for documents in by_source.values():
            if len(documents) > 1:
                keep = max(documents, key=lambda item: item.ingested_at)
                stale_ids.update(
                    item.document_id for item in documents if item.document_id != keep.document_id and item.is_current
                )
        if not stale_ids:
            return 0
        self.manifest.remove_document_ids(stale_ids)
        self.vector_store.remove_document_ids(stale_ids)
        self.graph_service.store.remove_document_ids(stale_ids)
        return len(stale_ids)

    def _acquire(self, request: IngestRequest) -> tuple[Path, str | None, str, str]:
        if request.local_path:
            path = Path(request.local_path)
            if not path.exists() or not path.is_file():
                raise IngestionError("Local source does not exist or is not a file.")
            return path, None, path.name, mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        assert request.source_url is not None
        url = str(request.source_url)
        try:
            response = httpx.get(url, follow_redirects=True, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise IngestionError(f"Unable to download source: {exc}") from exc
        file_name = Path(urlparse(url).path).name or "rbi_source.pdf"
        content_type = response.headers.get("content-type", "").split(";")[0].lower()
        mime_type = content_type if content_type and content_type != "application/octet-stream" else (mimetypes.guess_type(file_name)[0] or "application/pdf")
        temporary_path = self.settings.raw_dir / f"download_{hashlib.sha256(url.encode()).hexdigest()[:16]}{Path(file_name).suffix or '.pdf'}"
        temporary_path.write_bytes(response.content)
        return temporary_path, url, file_name, mime_type

    @staticmethod
    def _title_from_name(file_name: str) -> str:
        return re.sub(r"[_-]+", " ", Path(file_name).stem).strip().title()
