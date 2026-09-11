from fastapi import APIRouter, HTTPException, Request

from app.ingestion.exceptions import IngestionError
from app.models.documents import DocumentListResponse, IngestRequest, IngestResponse
from app.models.chunks import VectorSearchResult
from app.models.query import QueryRequest, QueryResponse
from app.retrieval.query_service import RegulatoryQueryService
from app.retrieval.service import VectorRetrievalService
from app.observability.costs import CostTracker
from app.observability.metrics import MetricsService

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
    return RegulatoryQueryService(request.app.state.settings).query(payload.query, payload.top_k, request_id)


@router.get("/metrics")
def metrics(request: Request) -> dict[str, float | int]:
    return MetricsService(CostTracker(request.app.state.settings.runtime_dir / "cost_events.json")).snapshot()
