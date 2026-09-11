from pathlib import Path

import pytest

from app.config.settings import Settings
from app.ingestion.exceptions import IngestionError
from app.ingestion.service import IngestionService
from app.models.documents import IngestRequest, IngestStatus


@pytest.fixture
def service(tmp_path: Path) -> IngestionService:
    return IngestionService(Settings(data_dir=tmp_path / "data"))


def test_ingest_text_creates_metadata_and_processed_pages(service: IngestionService, tmp_path: Path) -> None:
    source = tmp_path / "digital_lending.txt"
    source.write_text("Reserve Bank of India\nDigital Lending directions")

    result = service.ingest(IngestRequest(local_path=str(source), title="Digital Lending Directions"))

    assert result.status is IngestStatus.INGESTED
    assert result.document.document_id.startswith("doc_")
    assert result.document.page_count == 1
    assert (service.settings.processed_dir / f"{result.document.document_id}.json").exists()


def test_unchanged_document_is_cached(service: IngestionService, tmp_path: Path) -> None:
    source = tmp_path / "notice.txt"
    source.write_text("An RBI lending notice")

    first = service.ingest(IngestRequest(local_path=str(source)))
    second = service.ingest(IngestRequest(local_path=str(source)))

    assert first.status is IngestStatus.INGESTED
    assert second.status is IngestStatus.CACHED
    assert first.document.document_id == second.document.document_id


def test_rejects_unsupported_file(service: IngestionService, tmp_path: Path) -> None:
    source = tmp_path / "notice.docx"
    source.write_bytes(b"not a word document")

    with pytest.raises(IngestionError, match="Only PDF"):
        service.ingest(IngestRequest(local_path=str(source)))

