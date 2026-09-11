import hashlib
import json
import logging
import mimetypes
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config.settings import Settings
from app.ingestion.chunking import chunk_pages
from app.ingestion.exceptions import IngestionError
from app.ingestion.manifest import DocumentManifest
from app.ingestion.parser import parse_document
from app.graph.service import GraphIngestionService
from app.models.documents import DocumentMetadata, IngestRequest, IngestResponse, IngestStatus
from app.retrieval.vector_store import LocalVectorStore

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.raw_dir.mkdir(parents=True, exist_ok=True)
        settings.processed_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = DocumentManifest(settings.runtime_dir / "documents.json")
        self.vector_store = LocalVectorStore(settings.runtime_dir / "vectors.json")
        self.graph_service = GraphIngestionService(settings)

    def ingest(self, request: IngestRequest) -> IngestResponse:
        source_path, source_url, file_name, mime_type = self._acquire(request)
        content = source_path.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()
        existing = self.manifest.get_by_hash(content_hash)
        if existing:
            return IngestResponse(status=IngestStatus.CACHED, document=existing, message="Unchanged document already ingested.")

        document_id = f"doc_{content_hash[:16]}"
        raw_path = self.settings.raw_dir / f"{document_id}{source_path.suffix.lower()}"
        if source_path.resolve() != raw_path.resolve():
            raw_path.write_bytes(content)
        parsed = parse_document(raw_path, mime_type)
        metadata = DocumentMetadata(
            document_id=document_id,
            title=request.title or self._title_from_name(file_name),
            issuing_authority=request.issuing_authority,
            publication_date=request.publication_date,
            source_url=source_url,
            content_hash=content_hash,
            file_name=file_name,
            mime_type=mime_type,
            ingested_at=datetime.now(UTC),
            page_count=parsed.page_count,
        )
        self.manifest.save(metadata)
        chunks = chunk_pages(
            metadata,
            parsed.pages,
            chunk_size=self.settings.chunk_size,
            overlap=self.settings.chunk_overlap,
        )
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
        return sorted(self.manifest.all(), key=lambda item: item.ingested_at, reverse=True)

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
