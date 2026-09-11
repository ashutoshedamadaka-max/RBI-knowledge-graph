from datetime import UTC, datetime
from pathlib import Path

from app.config.settings import Settings
from app.ingestion.chunking import chunk_pages
from app.models.documents import DocumentMetadata
from app.retrieval.service import VectorRetrievalService


def document() -> DocumentMetadata:
    return DocumentMetadata(
        document_id="doc_example",
        title="Digital Lending Directions",
        content_hash="a" * 64,
        file_name="directions.txt",
        mime_type="text/plain",
        ingested_at=datetime.now(UTC),
    )


def test_chunks_are_page_bounded_and_stable() -> None:
    pages = ["one two three four five", "penal charges must be disclosed"]
    first = chunk_pages(document(), pages, chunk_size=3, overlap=1)
    second = chunk_pages(document(), pages, chunk_size=3, overlap=1)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert {chunk.page_number for chunk in first} == {1, 2}
    assert all(chunk.text for chunk in first)


def test_vector_retrieval_returns_relevant_chunk(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", vector_top_k=1)
    chunks = chunk_pages(document(), ["Penal charges must be disclosed clearly to borrowers.", "Co-lending arrangements involve regulated entities."], 50, 10)
    service = VectorRetrievalService(settings)
    service.store.upsert(chunks)

    results = service.retrieve_vector("What must lenders disclose about penal charges?")

    assert len(results) == 1
    assert results[0].chunk_id == chunks[0].chunk_id
    assert results[0].page_number == 1

