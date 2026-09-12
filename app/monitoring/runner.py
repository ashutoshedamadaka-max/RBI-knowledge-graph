from app.config.settings import Settings
from app.ingestion.service import IngestionService
from app.monitoring.fetcher import RbiHttpFetcher
from app.monitoring.processor import MonitoringDocumentProcessor
from app.monitoring.registry import RegulatorySourceRegistry
from app.monitoring.service import RegulatoryMonitor
from app.monitoring.store import MonitoringStore


def run_due_monitoring(settings: Settings) -> dict[str, object]:
    """Run all enabled source checks and return an auditable compact result."""
    monitor = RegulatoryMonitor(
        MonitoringStore(settings.runtime_dir / "monitoring.json"),
        RbiHttpFetcher(),
        MonitoringDocumentProcessor(IngestionService(settings)),
    )
    runs = []
    for source in RegulatorySourceRegistry(settings.regulatory_sources_path).enabled_sources():
        check, updates = monitor.check_source(source)
        runs.append({
            "source_id": source.source_id,
            "status": check.status.value,
            "discovered_count": check.discovered_count,
            "changes_detected": check.changes_detected,
            "updates": [update.update_id for update in updates],
            "error": check.error,
        })
    return {"runs": runs, "sources_checked": len(runs)}
