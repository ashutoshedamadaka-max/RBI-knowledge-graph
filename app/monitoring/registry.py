from pathlib import Path

import yaml

from app.models.monitoring import RegulatorySource


class RegulatorySourceRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path

    def enabled_sources(self) -> list[RegulatorySource]:
        payload = yaml.safe_load(self.path.read_text()) or {}
        return [source for source in (RegulatorySource.model_validate(item) for item in payload.get("sources", [])) if source.enabled]
