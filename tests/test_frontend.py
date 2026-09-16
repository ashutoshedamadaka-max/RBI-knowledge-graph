from fastapi.testclient import TestClient
from pathlib import Path

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


def test_vercel_frontend_uses_truthful_evidence_language_and_real_progress_stream() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "frontend" / "assets" / "app.js").read_text(encoding="utf-8")
    page = (root / "frontend" / "index.html").read_text(encoding="utf-8")

    assert "/query/stream" in script
    assert "Answer linked to source evidence" in script
    assert "Citations verified" not in script
    assert "retrieving_official_evidence" in page


def test_primary_navigation_uses_real_updates_and_no_knowledge_base_tab() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "frontend" / "assets" / "app.js").read_text(encoding="utf-8")
    page = (root / "frontend" / "index.html").read_text(encoding="utf-8")

    assert all(label in page for label in ("Research", "Regulatory updates", "How I built this", "Evals"))
    assert 'id="update-badge"' in page
    assert 'source-catalog-toggle' not in page
    assert "rbi-updates-last-seen-at" in script
    assert "function navigateTo" in script
    assert "window.addEventListener('popstate'" in script
    assert "window.addEventListener('hashchange'" in script
    assert "primary-view updates-page" in page


def test_portfolio_endpoints_and_pages_only_expose_available_data() -> None:
    client = TestClient(create_app())
    root = Path(__file__).resolve().parents[1]
    page = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (root / "frontend" / "assets" / "app.js").read_text(encoding="utf-8")

    graph = client.get("/graph-snapshot", params={"query": "Which entities are covered by digital lending guidance?"})
    evaluation = client.get("/evaluation-report")

    assert graph.status_code == 200
    assert {"nodes", "edges"}.issubset(graph.json())
    assert evaluation.status_code == 200
    assert "available" in evaluation.json()
    if evaluation.json()["available"]:
        report = evaluation.json()["report"]
        assert {"generated_at", "total_cases", "results"}.issubset(report)
    assert "Not yet evaluated" in script
    assert "Load a real relationship snapshot" in page


def test_research_workspace_has_conversation_follow_up_and_artifact_summary() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "frontend" / "assets" / "app.js").read_text(encoding="utf-8")
    page = (root / "frontend" / "index.html").read_text(encoding="utf-8")

    assert 'id="user-turn-question"' in page
    assert 'id="follow-up-form"' in page
    assert "Behind this answer" in page
    assert "This summary uses artifacts returned by this research turn." in script
