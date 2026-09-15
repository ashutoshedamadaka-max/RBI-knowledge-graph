from datetime import UTC, datetime
from pathlib import Path

from app.config.settings import Settings
from app.ingestion.chunking import chunk_pages
from app.ingestion.manifest import DocumentManifest
from app.models.documents import DocumentLifecycle, DocumentMetadata
from app.models.chunks import ChunkMetadata
from app.retrieval.service import VectorRetrievalService
from app.retrieval.vector_store import LocalVectorStore


def document() -> DocumentMetadata:
    return DocumentMetadata(
        document_id="doc_example",
        title="Digital Lending Directions",
        content_hash="a" * 64,
        file_name="directions.txt",
        mime_type="text/plain",
        ingested_at=datetime.now(UTC),
        lifecycle=DocumentLifecycle.ACTIVE,
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


def test_title_and_keyword_matches_outrank_unrelated_document_boilerplate(tmp_path: Path) -> None:
    store = LocalVectorStore(tmp_path / "vectors.json")
    chunks = [
        ChunkMetadata(
            chunk_id="digital-consent",
            document_id="digital-directions",
            document_title="RBI Digital Lending Directions, 2025",
            page_number=1,
            chunk_index=0,
            text="A Regulated Entity must obtain explicit consent before collecting borrower data.",
            lifecycle=DocumentLifecycle.ACTIVE,
            authority_current=True,
        ),
        ChunkMetadata(
            chunk_id="irac-consent",
            document_id="irac",
            document_title="Prudential Norms on Income Recognition, Asset Classification and Provisioning",
            page_number=1,
            chunk_index=0,
            text="The borrower consent and related documentation should be retained by the regulated entity.",
            lifecycle=DocumentLifecycle.WITHDRAWN,
            authority_current=False,
        ),
    ]
    store.upsert(chunks)

    results = store.search("What consent is required in digital lending?", top_k=2)

    assert results[0].chunk_id == "digital-consent"


def test_current_retrieval_excludes_withdrawn_and_unknown_sources(tmp_path: Path) -> None:
    store = LocalVectorStore(tmp_path / "vectors.json")
    chunks = [
        ChunkMetadata(chunk_id="old", document_id="old", document_title="Old circular", page_number=1, chunk_index=0,
                      text="Penal charges must be disclosed.", lifecycle=DocumentLifecycle.WITHDRAWN),
        ChunkMetadata(chunk_id="uncertain", document_id="uncertain", document_title="Unverified circular", page_number=1, chunk_index=0,
                      text="Penal charges must be disclosed.", lifecycle=DocumentLifecycle.REVIEW_REQUIRED),
        ChunkMetadata(chunk_id="current", document_id="current", document_title="Current circular", page_number=1, chunk_index=0,
                      text="Penal charges must be disclosed.", lifecycle=DocumentLifecycle.ACTIVE, authority_current=True),
    ]
    store.upsert(chunks)

    assert [item.chunk_id for item in store.search("penal charges", top_k=3)] == ["current"]
    assert {item.chunk_id for item in store.search("penal charges", top_k=3, current_only=False)} == {"old", "uncertain", "current"}


def test_manifest_selects_latest_version_for_one_rbi_source(tmp_path: Path) -> None:
    manifest = DocumentManifest(tmp_path / "documents.json")
    older = document().model_copy(update={"document_id": "doc_old", "source_url": "https://rbi.org.in/a", "document_version": 1})
    newer = document().model_copy(update={"document_id": "doc_new", "source_url": "https://rbi.org.in/a", "document_version": 2})
    manifest.save(older)
    manifest.save(newer)

    assert manifest.get_by_source_url("https://rbi.org.in/a").document_id == "doc_new"
