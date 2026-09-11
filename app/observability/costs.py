import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel


class CostEvent(BaseModel):
    timestamp: datetime
    operation: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    correlation_id: str


class CostTracker:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: CostEvent) -> None:
        events = self.events()
        events.append(event)
        self.path.write_text(json.dumps([item.model_dump(mode="json") for item in events], indent=2))

    def events(self) -> list[CostEvent]:
        if not self.path.exists():
            return []
        return [CostEvent.model_validate(item) for item in json.loads(self.path.read_text())]

    def summary(self) -> dict[str, float | int]:
        events = self.events()
        return {
            "total_estimated_cost_usd": round(sum(event.estimated_cost_usd for event in events), 8),
            "total_input_tokens": sum(event.input_tokens for event in events),
            "total_output_tokens": sum(event.output_tokens for event in events),
            "model_operations": len(events),
        }


def estimate_openai_cost(input_tokens: int, output_tokens: int, input_rate: float, output_rate: float) -> float:
    return round((input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 8)

