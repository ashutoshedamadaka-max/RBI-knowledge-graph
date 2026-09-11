from pathlib import Path

from app.observability.costs import CostEvent, CostTracker, estimate_openai_cost
from datetime import UTC, datetime


def test_cost_tracker_aggregates_recorded_events(tmp_path: Path) -> None:
    tracker = CostTracker(tmp_path / "costs.json")
    tracker.record(CostEvent(
        timestamp=datetime.now(UTC),
        operation="answer_generation",
        model="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=500,
        estimated_cost_usd=estimate_openai_cost(1000, 500, 0.15, 0.60),
        correlation_id="req_1",
    ))

    summary = tracker.summary()
    assert summary["total_input_tokens"] == 1000
    assert summary["total_output_tokens"] == 500
    assert summary["total_estimated_cost_usd"] == 0.00045

