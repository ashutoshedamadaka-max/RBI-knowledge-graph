import json
from datetime import UTC, datetime

from app.config.settings import Settings
from app.ingestion.repair import repair_legacy_notifications
from app.ingestion.service import IngestionService
from app.models.documents import DocumentLifecycle, IngestRequest


def legacy_service(tmp_path, body):
    service = IngestionService(Settings(_env_file=None, data_dir=tmp_path / "data"))
    source = tmp_path / "old.html"
    source.write_text(body)
    document = service.ingest(IngestRequest(local_path=str(source))).document
    document = service.approve_lifecycle(document.document_id, DocumentLifecycle.ACTIVE,
                                         "https://www.rbi.org.in/", "Verified official source evidence", datetime.now(UTC))
    return service, document


def test_repairs_legacy_index_without_changing_approval_and_keeps_backup(tmp_path):
    service, document = legacy_service(tmp_path,
        "Skip to main content Not Pressed RBI/2026-27/15 Priority sector lending limits shall increase to ten lakh rupees.")
    before = service.manifest.path.read_bytes()
    old_vectors = json.loads(service.vector_store.path.read_text())
    assert repair_legacy_notifications(service) == 1
    chunks = service.vector_store.get_by_document_id(document.document_id)
    assert len(chunks) == 1
    assert "Skip to main content" not in chunks[0].text
    assert "increase to ten lakh rupees" in chunks[0].text
    assert chunks[0].authority_current
    assert service.manifest.path.read_bytes() == before
    backup = json.loads((service.settings.runtime_dir / "extraction_repair_backup.json").read_text())
    assert backup["vectors.json"] == old_vectors
    assert repair_legacy_notifications(service) == 0


def test_repair_without_cached_files_reconstructs_verified_overlap(tmp_path):
    service, document = legacy_service(tmp_path,
        "Skip to main content Not Pressed RBI/2026-27/15 " + "eligible borrowers shall qualify for lending. " * 200)
    for path in service.settings.processed_dir.iterdir():
        path.unlink()
    assert repair_legacy_notifications(service) == 1
    assert all("Not Pressed" not in c.text for c in service.vector_store.get_by_document_id(document.document_id))


def test_repair_skips_when_body_boundary_cannot_be_verified(tmp_path):
    service, document = legacy_service(tmp_path, "Skip to main content Not Pressed No verified notification boundary")
    before = service.vector_store.path.read_bytes()
    assert repair_legacy_notifications(service) == 0
    assert service.vector_store.path.read_bytes() == before


def test_repair_rolls_back_indexes_on_failure(tmp_path, monkeypatch):
    service, document = legacy_service(tmp_path,
        "Skip to main content Not Pressed RBI/2026-27/15 Borrowers shall receive the lending disclosures.")
    before = service.vector_store.path.read_bytes()
    def fail(*args, **kwargs):
        raise RuntimeError("simulated graph write failure")
    monkeypatch.setattr(service.graph_service, "apply_document_lifecycle", fail)
    import pytest
    with pytest.raises(RuntimeError):
        repair_legacy_notifications(service)
    assert json.loads(service.vector_store.path.read_text()) == json.loads(before)


def test_repair_supports_monitored_plain_text_and_department_circular_id(tmp_path):
    service = IngestionService(Settings(_env_file=None, data_dir=tmp_path / "data"))
    document = service.ingest_content(
        b"Skip to main content Not Pressed RBI/FIDD/2025-26/196 Priority sector lending shall include eligible borrowers.",
        "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=13280&Mode=0",
        "rbi_monitor_source.txt", "Priority Sector Lending").document
    assert document.mime_type == "text/plain"
    assert repair_legacy_notifications(service) == 1
    assert service.vector_store.get_by_document_id(document.document_id)[0].text.startswith("RBI/FIDD/")
