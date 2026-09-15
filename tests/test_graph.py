from datetime import UTC, datetime
from pathlib import Path

from app.config.settings import Settings
from app.graph.resolution import entity_id
from app.graph.service import GraphIngestionService
from app.models.chunks import ChunkMetadata
from app.models.graph import EntityType


def chunk() -> ChunkMetadata:
    return ChunkMetadata(
        chunk_id="chunk_123",
        document_id="doc_123",
        document_title="Digital Lending Directions",
        page_number=1,
        chunk_index=0,
        text="The Reserve Bank of India requires NBFCs to disclose penal charges clearly.",
    )


def test_aliases_resolve_to_one_rbi_node() -> None:
    assert entity_id("RBI", EntityType.AUTHORITY) == entity_id("Reserve Bank of India", EntityType.AUTHORITY)


def test_graph_edges_preserve_chunk_provenance(tmp_path: Path) -> None:
    service = GraphIngestionService(Settings(data_dir=tmp_path / "data"))
    service.index_chunks([chunk()])

    edges = list(service.store.graph.edges(data=True))
    assert edges
    assert all(edge[2]["source_chunk_id"] == "chunk_123" for edge in edges)
    assert all(edge[2]["source_document_id"] == "doc_123" for edge in edges)
    assert any(edge[2]["relationship_type"] == "REQUIRES" for edge in edges)


def test_graph_retains_lifecycle_evidence_without_inventing_a_successor(tmp_path: Path) -> None:
    service = GraphIngestionService(Settings(data_dir=tmp_path / "data"))
    service.store.apply_document_lifecycle("doc_old", "Withdrawn IRAC Circular", "WITHDRAWN", "https://rbi.org.in/example", "Withdrawn")

    node = service.store.graph.nodes[entity_id("Withdrawn IRAC Circular", EntityType.REGULATION)]
    assert node["lifecycle"] == "WITHDRAWN"
    assert node["status_evidence_excerpt"] == "Withdrawn"
