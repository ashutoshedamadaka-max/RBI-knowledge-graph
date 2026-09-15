from fastapi import APIRouter, Header, HTTPException, Request

from app.ingestion.exceptions import IngestionError
from app.models.documents import DocumentListResponse, IngestRequest, IngestResponse
from app.models.chunks import VectorSearchResult
from app.models.query import QueryRequest, QueryResponse
from app.retrieval.query_service import RegulatoryQueryService
from app.retrieval.service import VectorRetrievalService
from app.observability.costs import CostTracker
from app.observability.metrics import MetricsService
from app.monitoring.store import MonitoringStore
from app.models.monitoring import Materiality, RegulatoryUpdate
from app.llm.generation import AnswerGenerationError
from app.monitoring.runner import run_due_monitoring
from app.monitoring.registry import RegulatorySourceRegistry


def _require_secret(received: str | None, expected: str | None, label: str) -> None:
    if not expected:
        raise HTTPException(status_code=503, detail=f"{label} is not configured.")
    if received != expected:
        raise HTTPException(status_code=401, detail="Unauthorized.")

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/ingest", response_model=IngestResponse)
def ingest(
    request: Request,
    payload: IngestRequest,
    x_admin_key: str | None = Header(default=None),
) -> IngestResponse:
    settings = request.app.state.settings
    if settings.admin_api_key:
        _require_secret(x_admin_key, settings.admin_api_key, "ADMIN_API_KEY")
    try:
        return request.app.state.ingestion_service.ingest(payload)
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/monitor/run")
def run_monitor(
    request: Request,
    x_monitor_secret: str | None = Header(default=None),
) -> dict[str, object]:
    settings = request.app.state.settings
    _require_secret(x_monitor_secret, settings.monitor_secret, "MONITOR_SECRET")
    return run_due_monitoring(settings)


@router.get("/documents", response_model=DocumentListResponse)
def documents(request: Request) -> DocumentListResponse:
    results = request.app.state.ingestion_service.list_documents()
    return DocumentListResponse(documents=results, count=len(results))


@router.get("/search", response_model=list[VectorSearchResult])
def search(request: Request, query: str, top_k: int | None = None) -> list[VectorSearchResult]:
    return VectorRetrievalService(request.app.state.settings).retrieve_vector(query, top_k)


@router.post("/query", response_model=QueryResponse)
def query(request: Request, payload: QueryRequest) -> QueryResponse:
    request_id = request.headers.get("X-Request-ID")
    try:
        return RegulatoryQueryService(request.app.state.settings).query(payload.query, payload.top_k, request_id)
    except AnswerGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/metrics")
def metrics(request: Request) -> dict[str, float | int]:
    return MetricsService(CostTracker(request.app.state.settings.runtime_dir / "cost_events.json")).snapshot()


@router.get("/regulatory-updates", response_model=list[RegulatoryUpdate])
def regulatory_updates(
    request: Request, topic: str | None = None, materiality: Materiality | None = None,
) -> list[RegulatoryUpdate]:
    updates = MonitoringStore(request.app.state.settings.runtime_dir / "monitoring.json").updates()
    if materiality:
        updates = [item for item in updates if item.materiality is materiality]
    if topic:
        updates = [item for item in updates if topic.lower() in (item.title + " " + item.summary).lower()]
    return sorted(updates, key=lambda item: item.detected_at, reverse=True)


@router.get("/regulatory-updates/{update_id}", response_model=RegulatoryUpdate)
def regulatory_update(request: Request, update_id: str) -> RegulatoryUpdate:
    update = next((item for item in MonitoringStore(request.app.state.settings.runtime_dir / "monitoring.json").updates() if item.update_id == update_id), None)
    if not update:
        raise HTTPException(status_code=404, detail="Regulatory update not found.")
    return update


@router.get("/monitoring-status")
def monitoring_status(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    checks = MonitoringStore(settings.runtime_dir / "monitoring.json").checks()
    latest = {}
    for check in checks:
        latest[check.source_id] = check.model_dump(mode="json")
    last_checks = sorted(latest.values(), key=lambda check: check["checked_at"], reverse=True)
    sources = RegulatorySourceRegistry(settings.regulatory_sources_path).enabled_sources()
    documents = request.app.state.ingestion_service.list_documents()
    unavailable = sum(check["status"] in {"SOURCE_UNAVAILABLE", "PARSING_FAILURE", "PARTIAL_FAILURE"} for check in last_checks)
    return {
        "document_count": len(documents),
        "tracked_source_count": len(sources),
        "topics": sorted({topic for source in sources for topic in source.regulatory_topics}),
        "last_checks": last_checks,
        "health": "attention" if unavailable else "healthy",
    }
