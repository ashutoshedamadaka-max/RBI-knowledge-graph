from dataclasses import asdict
import asyncio
import json
import os
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app import clock
from app.ingestion.exceptions import IngestionError
from app.ingestion.manifest import DocumentManifest
from app.ingestion.service import OfficialStatusError
from app.models.documents import DocumentLifecycle, DocumentListResponse, IngestRequest, IngestResponse, LifecycleReviewRequest
from app.models.chunks import VectorSearchResult
from app.models.query import QueryRequest, QueryResponse
from app.models.retrieval import GraphRetrievalResult
from app.graph.query_service import GraphRetrievalService
from app.retrieval.query_service import RegulatoryQueryService
from app.retrieval.service import VectorRetrievalService
from app.observability.costs import CostTracker
from app.observability.metrics import MetricsService
from app.monitoring.store import MonitoringStore
from app.models.monitoring import Materiality, RegulatoryUpdate, RegulatoryUpdateView
from app.llm.generation import AnswerGenerationError
from app.monitoring.runner import run_due_monitoring
from app.monitoring.link_store import LinkStore
from app.monitoring.linking import LinkingService
from app.monitoring.paragraph_map import map_paragraphs
from app.models.links import DocumentLink, LinkReviewRequest
from app.monitoring.registry import RegulatorySourceRegistry


def _require_secret(received: str | None, expected: str | None, label: str) -> None:
    if not expected:
        raise HTTPException(status_code=503, detail=f"{label} is not configured.")
    if received != expected:
        raise HTTPException(status_code=401, detail="Unauthorized.")


_source_key = DocumentManifest.source_key

router = APIRouter()


@router.get("/health")
def health(response: Response) -> dict[str, str]:
    response.headers["X-App-Revision"] = os.environ.get("RENDER_GIT_COMMIT", "local")
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


@router.get("/admin/review-queue", response_model=DocumentListResponse)
def review_queue(request: Request, x_admin_key: str | None = Header(default=None)) -> DocumentListResponse:
    settings = request.app.state.settings
    _require_secret(x_admin_key, settings.admin_api_key, "ADMIN_API_KEY")
    results = [
        item for item in request.app.state.ingestion_service.list_documents()
        if item.lifecycle in {DocumentLifecycle.UNKNOWN, DocumentLifecycle.REVIEW_REQUIRED}
    ]
    return DocumentListResponse(documents=results, count=len(results))


@router.post("/admin/documents/{document_id}/lifecycle-review", response_model=IngestResponse)
def approve_lifecycle(
    request: Request,
    document_id: str,
    payload: LifecycleReviewRequest,
    x_admin_key: str | None = Header(default=None),
) -> IngestResponse:
    settings = request.app.state.settings
    _require_secret(x_admin_key, settings.admin_api_key, "ADMIN_API_KEY")
    try:
        document = request.app.state.ingestion_service.approve_lifecycle(
            document_id, payload.lifecycle, str(payload.evidence_url), payload.evidence_excerpt, clock.now(),
        )
    except OfficialStatusError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not document:
        raise HTTPException(status_code=404, detail="Indexed document not found.")
    return IngestResponse(status="ingested", document=document, message="Lifecycle approval recorded with official RBI evidence.")


@router.get("/document-links", response_model=list[DocumentLink])
def document_links(request: Request) -> list[DocumentLink]:
    """Every successor link with its quoted RBI evidence and trust decision."""
    return LinkStore(request.app.state.settings.runtime_dir / "document_links.json").all()


@router.get("/document-links/{link_id}/paragraph-map")
def paragraph_map(request: Request, link_id: str) -> dict[str, object]:
    """Each paragraph of the replaced document beside the closest paragraph of its successor."""
    settings = request.app.state.settings
    link = LinkStore(settings.runtime_dir / "document_links.json").get(link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Document link not found.")

    def pages(document_id: str) -> list[str]:
        processed = settings.processed_dir / f"{document_id}.json"
        if not processed.exists():
            raise HTTPException(status_code=404, detail="Stored text for a linked document is missing.")
        return [page["text"] for page in json.loads(processed.read_text(encoding="utf-8"))["pages"]]

    matches = map_paragraphs(pages(link.old_document_id), pages(link.new_document_id))
    return {"link_id": link_id, "method": "lexical similarity (rung 0); accuracy not yet measured",
            "matches": [asdict(match) for match in matches]}


@router.get("/admin/links/review-queue", response_model=list[DocumentLink])
def link_review_queue(request: Request, x_admin_key: str | None = Header(default=None)) -> list[DocumentLink]:
    settings = request.app.state.settings
    _require_secret(x_admin_key, settings.admin_api_key, "ADMIN_API_KEY")
    return LinkStore(settings.runtime_dir / "document_links.json").pending_review()


@router.post("/admin/links/{link_id}/approve", response_model=DocumentLink)
def approve_link(request: Request, link_id: str, payload: LinkReviewRequest,
                 x_admin_key: str | None = Header(default=None)) -> DocumentLink:
    settings = request.app.state.settings
    _require_secret(x_admin_key, settings.admin_api_key, "ADMIN_API_KEY")
    try:
        return LinkingService(request.app.state.ingestion_service, settings).approve(
            link_id, str(payload.evidence_url), payload.evidence_excerpt,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Document link not found.") from exc
    except OfficialStatusError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/admin/links/{link_id}/reject", response_model=DocumentLink)
def reject_link(request: Request, link_id: str, x_admin_key: str | None = Header(default=None)) -> DocumentLink:
    settings = request.app.state.settings
    _require_secret(x_admin_key, settings.admin_api_key, "ADMIN_API_KEY")
    try:
        return LinkingService(request.app.state.ingestion_service, settings).reject(link_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Document link not found.") from exc


@router.get("/search", response_model=list[VectorSearchResult])
def search(request: Request, query: str, top_k: int | None = None) -> list[VectorSearchResult]:
    return VectorRetrievalService(request.app.state.settings).retrieve_vector(query, top_k)


@router.post("/query", response_model=QueryResponse)
def query(request: Request, payload: QueryRequest) -> QueryResponse:
    request_id = request.headers.get("X-Request-ID")
    try:
        return RegulatoryQueryService(request.app.state.settings).query(
            payload.query, payload.top_k, request_id, as_of=payload.as_of,
        )
    except AnswerGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/query/stream")
async def query_stream(request: Request, payload: QueryRequest) -> StreamingResponse:
    """Emit only lifecycle states the query service actually enters, followed by its result."""
    loop = asyncio.get_running_loop()
    events: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
    service = RegulatoryQueryService(request.app.state.settings)
    request_id = request.headers.get("X-Request-ID")

    def progress(stage: str) -> None:
        loop.call_soon_threadsafe(events.put_nowait, ("progress", {"stage": stage}))

    async def stream():
        task = asyncio.create_task(
            run_in_threadpool(service.query, payload.query, payload.top_k, request_id, progress, payload.as_of)
        )
        while not task.done() or not events.empty():
            try:
                kind, body = await asyncio.wait_for(events.get(), timeout=0.1)
                yield f"event: {kind}\ndata: {json.dumps(body)}\n\n"
            except TimeoutError:
                continue
        try:
            result = await task
            yield f"event: result\ndata: {result.model_dump_json()}\n\n"
        except AnswerGenerationError as exc:
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
        except Exception:
            yield "event: error\ndata: {\"detail\": \"The RBI research service is temporarily unavailable.\"}\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"},
        background=BackgroundTask(request.app.state.durable_state.sync),
    )


@router.get("/documents/{document_id}/chunks")
def document_chunks(document_id: str, request: Request) -> list[dict]:
    """How a document was cut: each chunk's paragraph, heading path, size and text (the Sources chunk viewer)."""
    chunks = request.app.state.ingestion_service.vector_store.get_by_document_id(document_id)
    if not chunks:
        raise HTTPException(status_code=404, detail="No chunks for that document.")
    return [{"chunk_id": chunk.chunk_id, "chunk_index": chunk.chunk_index, "page_number": chunk.page_number,
             "paragraph_ref": chunk.paragraph_ref, "heading_path": chunk.heading_path, "token_count": chunk.token_count,
             "chunker": chunk.chunker, "text": chunk.text} for chunk in sorted(chunks, key=lambda item: item.chunk_index)]


@router.get("/quality")
def quality() -> dict:
    """The quality dashboard's numbers, read only from saved evaluation runs."""
    from app.api.quality import quality_report

    return quality_report()


@router.get("/graph/map")
def graph_map(request: Request) -> dict:
    from app.api.graph_map import graph_for, overview

    graph = graph_for(request.app.state.settings.data_dir)
    if graph is None:
        raise HTTPException(status_code=404, detail="The knowledge graph has not been built for this corpus yet.")
    return overview(graph)


@router.get("/graph/node/{node_id:path}")
def graph_node(node_id: str, request: Request) -> dict:
    from app.api.graph_map import graph_for, node_detail

    graph = graph_for(request.app.state.settings.data_dir)
    detail = node_detail(graph, node_id) if graph is not None else None
    if detail is None:
        raise HTTPException(status_code=404, detail="No such node in the knowledge graph.")
    return detail


@router.get("/metrics")
def metrics(request: Request) -> dict[str, float | int]:
    return MetricsService(CostTracker(request.app.state.settings.runtime_dir / "cost_events.json")).snapshot()


@router.get("/evaluation-report")
def evaluation_report() -> dict[str, object]:
    """Return only a versioned, freshly generated benchmark report.

    The UI must not convert an untracked developer artifact into a portfolio
    metric. Until a report is intentionally generated and committed, callers
    receive an honest unavailable state.
    """
    report_dir = Path(__file__).resolve().parents[2] / "data" / "evaluation"
    report_path = report_dir / "current-report.json"
    if not report_path.exists():
        report_path = report_dir / "portfolio-report.json"
    if not report_path.exists():
        return {
            "available": False,
            "reason": "No published benchmark report is available yet.",
        }
    try:
        return {"available": True, "report": json.loads(report_path.read_text(encoding="utf-8"))}
    except (json.JSONDecodeError, OSError):
        return {
            "available": False,
            "reason": "The published benchmark report could not be read.",
        }


@router.get("/graph-snapshot", response_model=GraphRetrievalResult)
def graph_snapshot(request: Request, query: str) -> GraphRetrievalResult:
    """Expose query-relevant graph evidence without generating an answer.

    The portfolio UI uses this only for an explicit, live example; it never
    substitutes decorative or inferred relationships for graph evidence.
    """
    if len(query.strip()) < 3:
        raise HTTPException(status_code=422, detail="A graph question must contain at least three characters.")
    return GraphRetrievalService(request.app.state.settings).retrieve_graph(query)


@router.get("/regulatory-updates", response_model=list[RegulatoryUpdateView])
def regulatory_updates(
    request: Request, topic: str | None = None, materiality: Materiality | None = None,
) -> list[RegulatoryUpdateView]:
    updates = MonitoringStore(request.app.state.settings.runtime_dir / "monitoring.json").updates()
    if materiality:
        updates = [item for item in updates if item.materiality is materiality]
    if topic:
        updates = [item for item in updates if topic.lower() in (item.title + " " + item.summary).lower()]
    documents_by_url = {
        _source_key(item.source_url): item
        for item in request.app.state.ingestion_service.list_documents()
        if item.source_url
    }
    response = []
    for update in updates:
        document = documents_by_url.get(_source_key(str(update.source_url)))
        lifecycle = document.lifecycle if document else DocumentLifecycle.REVIEW_REQUIRED
        response.append(RegulatoryUpdateView(
            **update.model_dump(),
            current_lifecycle=lifecycle,
            current_document_id=document.document_id if document else None,
            status_evidence_url=document.status_evidence_url if document else None,
            status_evidence_excerpt=document.status_evidence_excerpt if document else None,
            status_checked_at=document.status_checked_at if document else None,
            action_required=lifecycle in {DocumentLifecycle.REVIEW_REQUIRED, DocumentLifecycle.UNKNOWN},
        ))
    return sorted(response, key=lambda item: item.detected_at, reverse=True)


@router.get("/regulatory-updates/{update_id}", response_model=RegulatoryUpdateView)
def regulatory_update(request: Request, update_id: str) -> RegulatoryUpdateView:
    update = next((item for item in regulatory_updates(request) if item.update_id == update_id), None)
    if update is None:
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
    lifecycle_counts = {status: sum(item.lifecycle.value == status for item in documents) for status in (
        "ACTIVE", "AMENDED", "SUPERSEDED", "WITHDRAWN", "REPEALED", "REVIEW_REQUIRED", "UNKNOWN"
    )}
    return {
        "document_count": len(documents),
        "tracked_source_count": len(sources),
        "topics": sorted({topic for source in sources for topic in source.regulatory_topics}),
        "last_checks": last_checks,
        "health": "attention" if unavailable else "healthy",
        "lifecycle_counts": lifecycle_counts,
    }
