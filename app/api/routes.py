from fastapi import APIRouter, HTTPException, Request

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

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/ingest", response_model=IngestResponse)
def ingest(request: Request, payload: IngestRequest) -> IngestResponse:
    try:
        return request.app.state.ingestion_service.ingest(payload)
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
    checks = MonitoringStore(request.app.state.settings.runtime_dir / "monitoring.json").checks()
    latest = {}
    for check in checks:
        latest[check.source_id] = check.model_dump(mode="json")
    return {"last_checks": list(latest.values())}
