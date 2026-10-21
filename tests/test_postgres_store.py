"""The PostgreSQL chunk store must behave exactly like the file store (one change at a time)."""

from datetime import date
from pathlib import Path

import pytest

from app.models.chunks import ChunkMetadata
from app.models.documents import DocumentLifecycle
from app.retrieval.vector_store import LocalVectorStore, PostgresVectorStore

pgserver = pytest.importorskip("pgserver", reason="development dependency (requirements-dev.txt)")


@pytest.fixture(scope="session")
def database_url(tmp_path_factory):
    server = pgserver.get_server(str(tmp_path_factory.mktemp("postgres")), cleanup_mode="stop")
    yield server.get_uri()
    server.cleanup()


def chunks() -> list[ChunkMetadata]:
    def make(chunk_id, document_id, text, **fields):
        return ChunkMetadata(chunk_id=chunk_id, document_id=document_id, document_title=f"Title of {document_id}",
                             page_number=1, chunk_index=0, text=text, lifecycle=DocumentLifecycle.ACTIVE,
                             authority_current=True, **fields)
    return [
        make("a1", "old", "Penal charges must not be capitalised into interest.", in_force_to=date(2025, 11, 1)),
        make("a2", "old", "Lenders must disclose penal charges in the Key Facts Statement."),
        make("b1", "new", "Penal charges shall be reasonable and disclosed upfront.", in_force_from=date(2025, 11, 1)),
        make("c1", "kfs", "A Key Facts Statement must be given to every borrower before signing."),
        make("d1", "other", "Gold loans require purity certification of the jewellery pledged."),
    ]


def both(tmp_path: Path, database_url: str) -> list:
    pg = PostgresVectorStore(database_url)
    with pg._connect() as connection:
        connection.execute("TRUNCATE chunks")
    stores = [LocalVectorStore(tmp_path / "vectors.json"), pg]
    for store in stores:
        store.upsert(chunks())
        store.apply_lifecycle("kfs", "WITHDRAWN")
        store.mark_document_not_current("other", "2025-06-01T00:00:00+00:00")
        store.set_in_force("new", date(2025, 11, 1), None)
    return stores


@pytest.mark.parametrize("kwargs", [
    dict(),
    dict(current_only=False),
    dict(as_of=date(2025, 10, 31)),
    dict(as_of=date(2025, 11, 1)),
    dict(as_of=date(2025, 6, 1), upcoming_only=True),
    dict(current_only=False, document_ids={"old", "kfs"}),
])
def test_search_results_are_identical(tmp_path, database_url, kwargs) -> None:
    file_store, pg = both(tmp_path, database_url)

    for query in ("penal charges disclosure", "Key Facts Statement borrower", "gold loan purity"):
        expected = [(r.chunk_id, r.similarity_score) for r in file_store.search(query, top_k=5, **kwargs)]
        assert [(r.chunk_id, r.similarity_score) for r in pg.search(query, top_k=5, **kwargs)] == expected


def test_reads_and_removal_are_identical(tmp_path, database_url) -> None:
    file_store, pg = both(tmp_path, database_url)

    for store in (file_store, pg):
        store.mark_document_current("other")
        store.remove_document_ids({"kfs"})
    assert pg.get_by_document_id("other") == file_store.get_by_document_id("other")
    assert pg.get_by_ids(["a1", "b1", "c1"]) == file_store.get_by_ids(["a1", "b1", "c1"])
    assert pg.get_by_document_id("kfs") == []


def test_stored_embeddings_round_trip_exactly(tmp_path, database_url) -> None:
    file_store, pg = both(tmp_path, database_url)

    assert [row["embedding"] for row in pg._read()] == [
        row["embedding"] for row in sorted(file_store._read(), key=lambda row: row["chunk"]["chunk_id"])
    ]
