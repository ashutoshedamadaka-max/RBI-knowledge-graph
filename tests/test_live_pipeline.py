"""The live 'behind this answer' events: real stage boundaries, honest skips, and costs only when reported."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from app.retrieval.query_service import RegulatoryQueryService
from tests.test_query_and_citations import _Reranker, ingest_verified_active

STAGES = ["prepare", "bm25", "openai_embeddings", "graph_cross_references", "in_force_filter", "cohere_rerank",
          "source_selection", "answer", "claim_check"]


def _service(tmp_path: Path, **settings) -> RegulatoryQueryService:
    source = tmp_path / "rbi.txt"
    source.write_text("Reserve Bank of India states that lenders must disclose penal charges clearly.")
    config = Settings(data_dir=tmp_path / "data", **settings)
    ingest_verified_active(config, source)
    return RegulatoryQueryService(config)


def test_every_stage_reports_once_it_finishes_or_is_skipped(tmp_path) -> None:
    events = []
    response = _service(tmp_path).query("What must lenders disclose about penal charges?", on_pipeline=events.append)

    final = {stage["id"]: stage for stage in response.trace["stages"]}
    assert list(final) == STAGES
    # No keys and no graph in tests: those steps say so instead of pretending to run.
    assert {final[s]["status"] for s in ("openai_embeddings", "graph_cross_references", "cohere_rerank")} == {"skipped"}
    assert final["bm25"]["status"] == "complete" and final["bm25"]["evidence"]
    assert final["in_force_filter"]["inspected_count"] >= 1 and final["in_force_filter"]["count"] == 0
    assert final["claim_check"]["status"] == "skipped"  # the deterministic answer gets no model check
    # Each running stage is announced before it completes, in pipeline order.
    running = [event["id"] for event in events if event["status"] == "running"]
    assert running == [s for s in STAGES if final[s]["status"] == "complete"]
    assert all(event.get("cost_usd") is None for event in events if event["status"] == "skipped")


def test_a_refusal_skips_the_answer_and_check(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.retrieval.pipeline.CohereReranker", _Reranker)
    _Reranker.score = 0.1
    service = _service(tmp_path, cohere_api_key="test")

    response = service.query("What must lenders disclose about penal charges?")

    final = {stage["id"]: stage for stage in response.trace["stages"]}
    assert final["cohere_rerank"]["status"] == "complete"
    assert [final[s]["status"] for s in ("source_selection", "answer", "claim_check")] == ["skipped"] * 3
    assert "below the answer threshold" in final["answer"]["summary"]


def test_the_stream_sends_pipeline_events_before_the_result(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(data_dir=tmp_path / "data"))
    source = tmp_path / "rbi.txt"
    source.write_text("Reserve Bank of India states that lenders must disclose penal charges clearly.")
    ingest_verified_active(Settings(data_dir=tmp_path / "data"), source)

    text = TestClient(create_app()).post("/query/stream", json={"query": "What must lenders disclose about penal charges?"}).text

    blocks = [block for block in text.split("\n\n") if block.startswith("event: ")]
    kinds = [block.split("\n", 1)[0].removeprefix("event: ") for block in blocks]
    assert "pipeline" in kinds and kinds.index("pipeline") < kinds.index("result")
    first = json.loads(next(block for block in blocks if block.startswith("event: pipeline")).split("data: ", 1)[1])
    assert first["id"] == "prepare" and first["status"] == "running"
