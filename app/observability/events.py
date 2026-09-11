import json
import logging
from datetime import UTC, datetime

from pydantic import BaseModel

logger = logging.getLogger("rbi_rag.query")


class QueryEvent(BaseModel):
    timestamp: datetime
    request_id: str
    query: str
    route: str
    retrieval_method: str
    retrieved_chunk_ids: list[str]
    graph_node_count: int
    graph_edge_count: int
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    latency_ms: float
    citation_valid: bool
    status: str


def log_query_event(event: QueryEvent) -> None:
    logger.info(json.dumps(event.model_dump(mode="json"), sort_keys=True))

