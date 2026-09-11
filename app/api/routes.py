from fastapi import APIRouter, HTTPException, Request

from app.ingestion.exceptions import IngestionError
from app.models.documents import DocumentListResponse, IngestRequest, IngestResponse

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

