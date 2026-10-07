import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool

from app.api.routes import router
from app.config.settings import get_settings
from app.ingestion.service import IngestionService
from app.ingestion.repair import repair_legacy_notifications
from app.monitoring.registry import RegulatorySourceRegistry
from app.monitoring.store import MonitoringStore
from app.persistence.runtime_state import DurableRuntimeState


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(message)s")
    durable_state = DurableRuntimeState(settings)
    durable_state.restore()
    application = FastAPI(title=settings.app_name, version="0.1.0")
    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    application.state.settings = settings
    application.state.durable_state = durable_state
    application.state.ingestion_service = IngestionService(settings)
    try:
        repair_legacy_notifications(application.state.ingestion_service)
    except Exception:
        # The repair rolls indexes back. A failed repair must not take down the
        # service; leave the captured evidence intact for investigation.
        logging.getLogger(__name__).exception("legacy_extraction_repair_failed")
    application.state.ingestion_service.cleanup_duplicate_sources()
    curated_source_ids = {
        source.source_id for source in RegulatorySourceRegistry(settings.regulatory_sources_path).enabled_sources()
        if source.parser_strategy == "rbi_document"
    }
    monitoring_store = MonitoringStore(settings.runtime_dir / "monitoring.json")
    monitoring_store.remove_initial_catalogue_updates(curated_source_ids)
    monitoring_store.reset_legacy_catalogue_noise(curated_source_ids)
    monitoring_store.reset_catalogue_after_extraction_upgrade(curated_source_ids)
    durable_state.sync()
    application.include_router(router)
    static_dir = Path(__file__).parent / "static"
    application.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    @application.middleware("http")
    async def persist_runtime_state(request, call_next):
        try:
            return await call_next(request)
        finally:
            # Reads and health probes do not mutate the corpus. Streamed queries
            # persist after their generator finishes, not when headers are sent.
            if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path != "/query/stream":
                await run_in_threadpool(durable_state.sync)

    @application.get("/", include_in_schema=False)
    def frontend() -> FileResponse:
        return FileResponse(static_dir / "index.html")
    return application


app = create_app()
