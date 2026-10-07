import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.config.settings import Settings
from app.persistence.runtime_state import DurableRuntimeState


def test_query_stream_emits_actual_lifecycle_events_and_result() -> None:
    client = TestClient(create_app())

    response = client.post("/query/stream", json={"query": "What is the weather in Mumbai?"})

    assert response.status_code == 200
    assert "event: progress" in response.text
    assert '"stage": "understanding_question"' in response.text
    assert '"stage": "searching_regulatory_relationships"' not in response.text
    result_payload = response.text.split("event: result\ndata: ", 1)[1].split("\n\n", 1)[0]
    assert json.loads(result_payload)["research"]["status"] == "out_of_scope"


def test_reads_do_not_sync_and_stream_syncs_after_generation(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(_env_file=None, data_dir=tmp_path))
    client = TestClient(create_app())
    sequence = []
    monkeypatch.setattr(DurableRuntimeState, "sync", lambda self: sequence.append("sync"))
    assert client.get("/health").status_code == 200
    assert client.get("/documents").status_code == 200
    assert sequence == []
    from app.retrieval.query_service import RegulatoryQueryService
    original = RegulatoryQueryService.query
    def query(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        sequence.append("generated")
        return result
    monkeypatch.setattr(RegulatoryQueryService, "query", query)
    response = client.post("/query/stream", json={"query": "What is the weather in Mumbai?"})
    assert "event: result" in response.text
    assert sequence == ["generated", "sync"]
