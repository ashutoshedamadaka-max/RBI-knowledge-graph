import json
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

from app.graph.resolution import entity_id
from app.models.chunks import ChunkMetadata
from app.models.graph import ExtractionResult


class ProvenanceGraph:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.graph = self._load()

    def _load(self) -> nx.MultiDiGraph:
        if not self.path.exists():
            return nx.MultiDiGraph()
        return json_graph.node_link_graph(
            json.loads(self.path.read_text()), directed=True, multigraph=True, edges="edges"
        )

    def add_extraction(self, chunk: ChunkMetadata, extraction: ExtractionResult) -> None:
        for entity in extraction.entities:
            node_id = entity_id(entity.name, entity.entity_type)
            self.graph.add_node(
                node_id,
                name=entity.name,
                entity_type=entity.entity_type.value,
                aliases=entity.aliases,
            )
        for relationship in extraction.relationships:
            source_id = entity_id(relationship.source_name, relationship.source_type)
            target_id = entity_id(relationship.target_name, relationship.target_type)
            self.graph.add_edge(
                source_id,
                target_id,
                key=f"{relationship.chunk_id}:{relationship.relationship_type.value}:{source_id}:{target_id}",
                relationship_type=relationship.relationship_type.value,
                source_chunk_id=relationship.chunk_id,
                source_document_id=relationship.source_document_id,
                confidence=relationship.confidence,
                extraction_method=relationship.extraction_method,
            )
        self.path.write_text(json.dumps(json_graph.node_link_data(self.graph, edges="edges"), indent=2))
