"""Phase 6 API: the quality numbers come only from saved runs, and the map serves the built graph."""

import json

from fastapi.testclient import TestClient

from app.api import quality
from app.main import create_app


def test_quality_reports_only_saved_runs_and_says_what_is_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(quality, "EVALUATION", tmp_path)
    (tmp_path / "ladder-dev.json").write_text(json.dumps({"results": {"bm25": {"recall@5": {"value": 0.59}}}}))
    (tmp_path / "answers-dev-gpt-4o-mini.json").write_text(json.dumps({"results": {}, "records": [
        {"id": "q1", "type": "single_fact", "answered": False},
        {"id": "q2", "type": "single_fact", "answered": True, "gold_cited": [True],
         "claims": [{"text": "A rule.", "verdict": "supported"}]},
        {"id": "q3", "type": "withdrawn_trap", "answered": True, "cited_withdrawn": True}]}))
    (tmp_path / "spend-ledger.jsonl").write_text(json.dumps({"phase": 3, "estimated_cost_usd": 0.02}) + "\n")

    report = TestClient(create_app()).get("/quality").json()

    assert report["ladder"]["data"]["results"]["bm25"]["recall@5"]["value"] == 0.59
    assert report["answers_test"] == {"status": "not yet measured", "file": "answers-test-gpt-4o-mini.json"}
    answers = report["answers_dev"]["data"]
    assert "records" not in answers  # trimmed to the failure gallery
    assert [(item["id"], item["reasons"]) for item in answers["failures"]] == [
        ("q1", ["answerable, but refused"]), ("q3", ["cited a withdrawn rule"])]
    assert report["spend"]["total_usd"] == 0.02


def test_the_map_explains_when_no_graph_has_been_built() -> None:
    response = TestClient(create_app()).get("/graph/map")

    assert response.status_code == 404 and "not been built" in response.json()["detail"]
