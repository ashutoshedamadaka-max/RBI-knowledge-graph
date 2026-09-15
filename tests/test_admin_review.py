from fastapi.testclient import TestClient

from app.config.settings import get_settings
from app.ingestion.service import IngestionService
from app.main import create_app
from app.models.documents import DocumentLifecycle, IngestRequest


def test_admin_can_approve_review_required_document_with_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    get_settings.cache_clear()
    app = create_app()
    source = tmp_path / "rbi.txt"
    source.write_text("Reserve Bank of India lending direction.")
    document = IngestionService(app.state.settings).ingest(IngestRequest(local_path=str(source), title="RBI direction")).document
    client = TestClient(app)

    unauthorised = client.post(
        f"/admin/documents/{document.document_id}/lifecycle-review",
        json={"lifecycle": "ACTIVE", "evidence_url": "https://www.rbi.org.in/example", "evidence_excerpt": "Official RBI source confirms this direction remains operative."},
    )
    approved = client.post(
        f"/admin/documents/{document.document_id}/lifecycle-review",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"lifecycle": "ACTIVE", "evidence_url": "https://www.rbi.org.in/example", "evidence_excerpt": "Official RBI source confirms this direction remains operative."},
    )

    assert unauthorised.status_code == 401
    assert approved.status_code == 200
    assert approved.json()["document"]["lifecycle"] == DocumentLifecycle.ACTIVE.value
    assert approved.json()["document"]["status_resolution_method"] == "ADMIN_REVIEW"
    get_settings.cache_clear()


def test_admin_cannot_manually_approve_a_withdrawn_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    get_settings.cache_clear()
    app = create_app()
    source = tmp_path / "rbi.txt"
    source.write_text("Reserve Bank of India lending direction.")
    document = IngestionService(app.state.settings).ingest(IngestRequest(local_path=str(source), title="RBI direction")).document
    client = TestClient(app)

    response = client.post(
        f"/admin/documents/{document.document_id}/lifecycle-review",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"lifecycle": "WITHDRAWN", "evidence_url": "https://www.rbi.org.in/example", "evidence_excerpt": "Official RBI source confirms this direction is withdrawn."},
    )

    assert response.status_code == 422
    get_settings.cache_clear()
