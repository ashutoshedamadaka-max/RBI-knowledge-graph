import json

from fastapi.testclient import TestClient

from app.main import create_app


def test_query_stream_emits_actual_lifecycle_events_and_result() -> None:
    client = TestClient(create_app())

    response = client.post("/query/stream", json={"query": "What is the weather in Mumbai?"})

    assert response.status_code == 200
    assert "event: progress" in response.text
    assert '"stage": "understanding_question"' in response.text
    assert '"stage": "searching_regulatory_relationships"' not in response.text
    result_payload = response.text.split("event: result\ndata: ", 1)[1].split("\n\n", 1)[0]
    assert json.loads(result_payload)["research"]["status"] == "out_of_scope"
