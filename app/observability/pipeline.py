"""Request-local, public pipeline facts. Never serialize provider requests or exceptions."""
from time import perf_counter


class PipelineRun:
    def __init__(self, emit=None):
        self.started = perf_counter()
        self.emit = emit
        self.steps: dict[str, dict] = {}
        self.clocks: dict[str, float] = {}

    def start(self, stage: str, summary: str, **facts):
        self.clocks[stage] = perf_counter()
        self._send(stage, status="running", started_ms=self.elapsed(), summary=summary, **facts)

    def finish(self, stage: str, summary: str, status="complete", **facts):
        duration = round((perf_counter() - self.clocks[stage]) * 1000, 2) if stage in self.clocks else None
        self._send(stage, status=status, duration_ms=duration, summary=summary, **facts)

    def skip(self, stage: str, summary: str):
        self._send(stage, status="skipped", started_ms=self.elapsed(), duration_ms=None, summary=summary)

    def elapsed(self):
        return round((perf_counter() - self.started) * 1000, 2)

    def _send(self, stage, **facts):
        event = {**self.steps.get(stage, {}), "id": stage, **facts}
        self.steps[stage] = event
        if self.emit:
            self.emit(event)

    def snapshot(self):
        return list(self.steps.values())


def public_passage(row):
    """Only the source fields needed to inspect a displayed graph node."""
    fields = ("chunk_id", "document_id", "document_title", "text", "source_url", "paragraph_ref",
              "heading_path", "lifecycle", "in_force_from", "in_force_to")
    return {key: row.get(key) for key in fields}
