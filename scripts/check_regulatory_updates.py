from app.config.settings import get_settings
from app.ingestion.service import IngestionService
from app.monitoring.fetcher import RbiHttpFetcher
from app.monitoring.processor import MonitoringDocumentProcessor
from app.monitoring.registry import RegulatorySourceRegistry
from app.monitoring.service import RegulatoryMonitor
from app.monitoring.store import MonitoringStore


def main() -> None:
    settings = get_settings()
    monitor = RegulatoryMonitor(
        MonitoringStore(settings.runtime_dir / "monitoring.json"),
        RbiHttpFetcher(),
        MonitoringDocumentProcessor(IngestionService(settings)),
    )
    for source in RegulatorySourceRegistry(settings.regulatory_sources_path).enabled_sources():
        check, updates = monitor.check_source(source)
        print(f"{source.source_id}: {check.status.value}; updates={len(updates)}")


if __name__ == "__main__":
    main()
