"""Regressions for how superseded versions and official withdrawals are handled."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.ingestion.service import IngestionService, OfficialStatusError
from app.models.chunks import ChunkMetadata
from app.models.documents import DocumentLifecycle, IngestRequest
from app.retrieval.vector_store import LocalVectorStore


def _chunk(chunk_id: str, **overrides) -> ChunkMetadata:
    values = dict(chunk_id=chunk_id, document_id=chunk_id, document_title="Penal charges circular", page_number=1,
                  chunk_index=0, text="Penal charges must be disclosed.", lifecycle=DocumentLifecycle.ACTIVE,
                  authority_current=True)
    return ChunkMetadata(**{**values, **overrides})


def test_a_revised_version_replaces_the_old_one_in_current_answers(tmp_path: Path) -> None:
    store = LocalVectorStore(tmp_path / "vectors.json")
    store.upsert([_chunk("v1", document_id="doc_v1"), _chunk("v2", document_id="doc_v2", document_version=2)])

    store.mark_document_not_current("doc_v1", datetime.now(UTC).isoformat())

    assert [item.chunk_id for item in store.search("penal charges", top_k=5)] == ["v2"]
    assert {item.chunk_id for item in store.search("penal charges", top_k=5, current_only=False)} == {"v1", "v2"}


def _service_with_two_copies(tmp_path: Path, first_is_current: bool) -> tuple[IngestionService, str, str]:
    """Two stored versions of one RBI page; the older is retired unless it is a legacy duplicate."""
    service = IngestionService(Settings(_env_file=None, data_dir=tmp_path / "data"))
    url = "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=1"
    ids = [
        service.ingest_content(text.encode(), url, "page.txt", "Circular", document_version=version).document.document_id
        for version, text in enumerate(["First wording of the circular.", "Second wording of the circular."], start=1)
    ]
    if not first_is_current:
        service.mark_document_not_current(ids[0], datetime.now(UTC).isoformat())
    return service, ids[0], ids[1]


def test_startup_cleanup_keeps_superseded_versions_as_history(tmp_path: Path) -> None:
    service, old_id, new_id = _service_with_two_copies(tmp_path, first_is_current=False)

    service.cleanup_duplicate_sources()

    assert {item.document_id for item in service.manifest.all()} == {old_id, new_id}
    assert service.vector_store.get_by_document_id(old_id)


def test_startup_cleanup_still_removes_legacy_duplicates_of_the_same_page(tmp_path: Path) -> None:
    service, old_id, new_id = _service_with_two_copies(tmp_path, first_is_current=True)

    removed = service.cleanup_duplicate_sources()

    assert removed == 1
    assert {item.document_id for item in service.manifest.all()} == {new_id}


@pytest.mark.parametrize("status", [DocumentLifecycle.WITHDRAWN, DocumentLifecycle.REPEALED, DocumentLifecycle.SUPERSEDED])
def test_a_person_cannot_approve_a_document_rbi_has_withdrawn(tmp_path: Path, status) -> None:
    service = IngestionService(Settings(_env_file=None, data_dir=tmp_path / "data"))
    source = tmp_path / "rbi.txt"
    source.write_text("Reserve Bank of India lending direction.")
    document = service.ingest(IngestRequest(local_path=str(source), title="Direction")).document
    service.manifest.update_lifecycle(document.document_id, status, "https://www.rbi.org.in/x", "Withdrawn", datetime.now(UTC))

    with pytest.raises(OfficialStatusError):
        service.approve_lifecycle(document.document_id, DocumentLifecycle.ACTIVE, "https://www.rbi.org.in/x",
                                  "A reviewer says this is still operative.", datetime.now(UTC))

    assert service.manifest.get_by_hash(document.content_hash).lifecycle is status


def test_the_approval_endpoint_reports_a_conflict_for_a_withdrawn_document(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.config.settings import get_settings
    from app.main import create_app

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ADMIN_API_KEY", "key")
    get_settings.cache_clear()
    app = create_app()
    source = tmp_path / "rbi.txt"
    source.write_text("Reserve Bank of India lending direction.")
    document = app.state.ingestion_service.ingest(IngestRequest(local_path=str(source), title="Direction")).document
    app.state.ingestion_service.manifest.update_lifecycle(
        document.document_id, DocumentLifecycle.WITHDRAWN, "https://www.rbi.org.in/x", "Withdrawn", datetime.now(UTC))

    response = TestClient(app).post(
        f"/admin/documents/{document.document_id}/lifecycle-review", headers={"X-Admin-Key": "key"},
        json={"lifecycle": "ACTIVE", "evidence_url": "https://www.rbi.org.in/x",
              "evidence_excerpt": "A reviewer says this is still operative."})

    assert response.status_code == 409


def test_a_rule_is_answerable_only_inside_its_in_force_window(tmp_path: Path) -> None:
    from datetime import date

    from app import clock

    store = LocalVectorStore(tmp_path / "vectors.json")
    store.upsert([_chunk("old", document_id="old", in_force_to=date(2025, 11, 1)),
                  _chunk("new", document_id="new", in_force_from=date(2025, 11, 1))])

    def answers_on(day: date) -> list[str]:
        with clock.simulated(lambda: datetime(day.year, day.month, day.day, 9, tzinfo=UTC)):
            return [item.chunk_id for item in store.search("penal charges", top_k=5)]

    assert answers_on(date(2025, 10, 31)) == ["old"]  # issued May 2025, effective 1 November
    assert answers_on(date(2025, 11, 1)) == ["new"]


def test_in_force_dates_come_from_the_header_and_reach_the_chunks(tmp_path: Path) -> None:
    from datetime import date

    from app.monitoring.metadata import extract_rbi_document_facts

    service = IngestionService(Settings(_env_file=None, data_dir=tmp_path / "data"))
    text = (Path(__file__).parent / "fixtures" / "rbi_headers" / "digital_lending_directions_2025.txt").read_text(encoding="utf-8")
    document = service.ingest_content(text.encode(), "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12848&Mode=0",
                                      "page.txt", "Digital Lending Directions").document

    service.apply_monitoring_metadata(document.source_url, extract_rbi_document_facts(text), datetime.now(UTC))

    assert service.manifest.all()[0].in_force_from == date(2025, 11, 1)  # effective date wins over May 8 issue date
    assert {c.in_force_from for c in service.vector_store.get_by_document_id(document.document_id)} == {date(2025, 11, 1)}
