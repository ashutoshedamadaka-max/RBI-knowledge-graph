import json
from pathlib import Path

from app.models.monitoring import DocumentVersion, RegulatoryUpdate, SourceCheck


class MonitoringStore:
    """Append-only local history for monitoring runs, versions, and updates."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {
            "checks": [], "versions": [], "updates": [], "alerted_update_ids": []
        }

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2, default=str))

    def checks(self) -> list[SourceCheck]:
        return [SourceCheck.model_validate(item) for item in self._read()["checks"]]

    def versions(self, canonical_url: str | None = None) -> list[DocumentVersion]:
        values = [DocumentVersion.model_validate(item) for item in self._read()["versions"]]
        return [value for value in values if value.canonical_url == canonical_url] if canonical_url else values

    def current_version(self, canonical_url: str) -> DocumentVersion | None:
        return next((item for item in reversed(self.versions(canonical_url)) if item.is_current), None)

    def add_check(self, check: SourceCheck) -> None:
        data = self._read()
        data["checks"].append(check.model_dump(mode="json"))
        self._write(data)

    def add_version(self, version: DocumentVersion) -> None:
        data = self._read()
        for item in data["versions"]:
            if item["canonical_url"] == version.canonical_url and item.get("is_current"):
                item["is_current"] = False
                item["lifecycle"] = "AMENDED"
                item["valid_to"] = version.valid_from.isoformat()
        data["versions"].append(version.model_dump(mode="json"))
        self._write(data)

    def add_update_once(self, update: RegulatoryUpdate) -> bool:
        data = self._read()
        if any(item["update_id"] == update.update_id for item in data["updates"]):
            return False
        data["updates"].append(update.model_dump(mode="json"))
        self._write(data)
        return True

    def updates(self) -> list[RegulatoryUpdate]:
        return [RegulatoryUpdate.model_validate(item) for item in self._read()["updates"]]

    def mark_alerted(self, update_id: str) -> bool:
        data = self._read()
        if update_id in data["alerted_update_ids"]:
            return False
        data["alerted_update_ids"].append(update_id)
        self._write(data)
        return True

    def remove_initial_catalogue_updates(self, source_ids: set[str]) -> int:
        """Remove historical first-scan events from curated document baselines."""
        data = self._read()
        before = len(data["updates"])
        data["updates"] = [
            item for item in data["updates"]
            if not (item.get("source_id") in source_ids and item.get("change_type") == "NEW")
        ]
        removed = before - len(data["updates"])
        if removed:
            self._write(data)
        return removed

    def reset_legacy_catalogue_noise(self, source_ids: set[str]) -> int:
        """One-time migration: remove false historical changes from HTML page chrome."""
        data = self._read()
        maintenance = data.setdefault("maintenance", {})
        migration = "normalized_catalogue_baseline_v1"
        if maintenance.get(migration):
            return 0
        original_updates = len(data["updates"])
        data["updates"] = [item for item in data["updates"] if item.get("source_id") not in source_ids]
        grouped: dict[str, list[dict]] = {}
        retained: list[dict] = []
        for version in data["versions"]:
            if version.get("source_id") in source_ids:
                grouped.setdefault(version["canonical_url"], []).append(version)
            else:
                retained.append(version)
        for versions in grouped.values():
            newest = max(versions, key=lambda item: item["valid_from"])
            newest["version"] = 1
            newest["is_current"] = True
            newest["valid_to"] = None
            retained.append(newest)
        data["versions"] = retained
        maintenance[migration] = True
        self._write(data)
        return original_updates - len(data["updates"])
