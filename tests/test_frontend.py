from fastapi.testclient import TestClient

from app.main import create_app


def test_frontend_and_metrics_are_available() -> None:
    client = TestClient(create_app())

    homepage = client.get("/")
    metrics = client.get("/metrics")
    monitoring = client.get("/monitoring-status")
    script = client.get("/assets/app.js")

    assert homepage.status_code == 200
    assert "RBI Lending Intelligence" in homepage.text
    assert script.status_code == 200
    assert metrics.status_code == 200
    assert monitoring.status_code == 200
    assert {"document_count", "tracked_source_count", "health"}.issubset(monitoring.json())
