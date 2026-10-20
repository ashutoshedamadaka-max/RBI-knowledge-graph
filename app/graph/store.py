import json
from pathlib import Path
import time

import networkx as nx
from networkx.readwrite import json_graph

from app.graph.resolution import entity_id
from app.models.chunks import ChunkMetadata
from app.models.graph import EntityType, ExtractionResult


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

    def _persist(self) -> None:
        """Replace the graph snapshot atomically to avoid partial or locked writes on Windows."""
        temporary_path = self.path.with_name(f"{self.path.name}.tmp")
        temporary_path.write_text(json.dumps(json_graph.node_link_data(self.graph, edges="edges"), indent=2))
        for attempt in range(5):
            try:
                temporary_path.replace(self.path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)

    def persist(self) -> None:
        self._persist()

    def add_extraction(self, chunk: ChunkMetadata, extraction: ExtractionResult, persist: bool = True) -> None:
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
        if persist:
            self._persist()

    def apply_document_lifecycle(self, document_id: str, title: str, lifecycle: str, evidence_url: str, excerpt: str) -> None:
        """Attach lifecycle provenance to the regulation node without inferring links."""
        node_id = entity_id(title, EntityType.REGULATION)
        self.graph.add_node(node_id, name=title, entity_type="Regulation", aliases=[])
        node = self.graph.nodes[node_id]
        node.update({
            "lifecycle": lifecycle,
            "status_evidence_url": evidence_url,
            "status_evidence_excerpt": excerpt,
            "source_document_id": document_id,
        })
        self._persist()

    def set_document_link(self, link_id: str, old_document_id: str, old_title: str, new_document_id: str, new_title: str,
                          relation: str, evidence_quote: str, trust: str, present: bool = True) -> None:
        """A document-to-document edge carrying its quoted evidence; removed when ``present`` is false."""
        old_node, new_node = f"document:{old_document_id}", f"document:{new_document_id}"
        if not present:
            if self.graph.has_edge(new_node, old_node, key=link_id):
                self.graph.remove_edge(new_node, old_node, key=link_id)
                self._persist()
            return
        for node, title, document_id in ((old_node, old_title, old_document_id), (new_node, new_title, new_document_id)):
            self.graph.add_node(node, name=title, entity_type="Document", aliases=[], source_document_id=document_id)
        self.graph.add_edge(
            new_node, old_node, key=link_id, relationship_type=relation, evidence_quote=evidence_quote, trust=trust,
            source_chunk_id="", source_document_id=new_document_id, confidence=1.0, extraction_method="successor_link",
        )
        self._persist()

    def remove_document_ids(self, document_ids: set[str]) -> None:
        if not document_ids:
            return
        stale_edges = [
            (source, target, key)
            for source, target, key, data in self.graph.edges(keys=True, data=True)
            if data.get("source_document_id") in document_ids
        ]
        self.graph.remove_edges_from(stale_edges)
        self.graph.remove_nodes_from(list(nx.isolates(self.graph)))
        self._persist()
