from app.observability.costs import CostTracker


class MetricsService:
    def __init__(self, tracker: CostTracker) -> None:
        self.tracker = tracker

    def snapshot(self) -> dict[str, float | int]:
        return self.tracker.summary()

