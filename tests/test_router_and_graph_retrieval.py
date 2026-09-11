from pathlib import Path

from app.config.settings import Settings
from app.graph.query_service import GraphRetrievalService
from app.graph.service import GraphIngestionService
from app.models.chunks import ChunkMetadata
from app.models.retrieval import RetrievalRoute
from app.retrieval.router import QueryRouter


def chunk() -> ChunkMetadata:
    return ChunkMetadata(
        chunk_id="chunk_route",
        document_id="doc_route",
        document_title="Digital Lending Directions",
        page_number=1,
        chunk_index=0,
        text="The Reserve Bank of India requires NBFCs to disclose penal charges clearly.",
    )


def test_router_distinguishes_fact_and_applicability_questions() -> None:
    router = QueryRouter()
    assert router.route("What does RBI say about penal charges?").route is RetrievalRoute.VECTOR
    assert router.route("Which entities do Digital Lending Directions apply to?").route is RetrievalRoute.GRAPH


def test_graph_applicability_template_returns_two_hop_provenance(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    GraphIngestionService(settings).index_chunks([chunk()])

    result = GraphRetrievalService(settings).retrieve_graph(
        "Which entities do Digital Lending Directions apply to?"
    )

    assert result.template == "regulation_to_requirements_to_entities"
    assert {edge.relationship_type for edge in result.edges} >= {"REQUIRES", "APPLIES_TO"}
    assert result.chunk_ids == ["chunk_route"]

