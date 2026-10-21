from dataclasses import asdict

import httpx

from app import clock

from app.config.settings import Settings
from app.ingestion.service import IngestionService
from app.monitoring.fetcher import RbiHttpFetcher
from app.monitoring.linking import LinkingService
from app.monitoring.processor import MonitoringDocumentProcessor
from app.monitoring.registry import RegulatorySourceRegistry
from app.monitoring.service import RegulatoryMonitor
from app.monitoring.store import MonitoringStore
from app.monitoring.withdrawn_register import REGISTER_URL, apply_register, parse_register


def run_due_monitoring(settings: Settings) -> dict[str, object]:
    """Run all enabled source checks, then link successors, and return an auditable compact result."""
    ingestion = IngestionService(settings)
    monitor = RegulatoryMonitor(
        MonitoringStore(settings.runtime_dir / "monitoring.json"),
        RbiHttpFetcher(),
        MonitoringDocumentProcessor(ingestion),
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
    register = check_withdrawn_register(ingestion)
    linking = LinkingService(ingestion, settings).reconcile()
    return {"runs": runs, "sources_checked": len(runs), "withdrawn_register": register, "linking": asdict(linking)}


def check_withdrawn_register(ingestion: IngestionService) -> dict[str, object]:
    """Withdraw corpus documents listed in RBI's register; a failed fetch is reported, not fatal."""
    try:
        response = httpx.get(REGISTER_URL, follow_redirects=True, timeout=90)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return {"status": "SOURCE_UNAVAILABLE", "error": str(exc)}
    entries = parse_register(response.text)
    withdrawn = apply_register(ingestion, entries, clock.now())
    return {"status": "CHECKED", "entries": len(entries), "documents_withdrawn": withdrawn}
