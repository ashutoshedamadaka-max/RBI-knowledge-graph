from fastapi.testclient import TestClient

from app.main import create_app


def test_monitor_endpoint_requires_configuration_and_secret() -> None:
    client = TestClient(create_app())

    unavailable = client.post("/monitor/run")
    assert unavailable.status_code == 503

    client.app.state.settings.monitor_secret = "monitor-test-secret"
    unauthorized = client.post("/monitor/run")
    assert unauthorized.status_code == 401
