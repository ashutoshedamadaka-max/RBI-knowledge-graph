import re
from collections.abc import Iterable

from app.graph.store import ProvenanceGraph
from app.models.retrieval import GraphEdgeEvidence, GraphNodeEvidence, GraphRetrievalResult


class GraphRetriever:
    """Runs only named retrieval templates against the evidence graph."""

    def __init__(self, store: ProvenanceGraph) -> None:
        self.graph = store.graph

    def retrieve_graph(self, query: str) -> GraphRetrievalResult:
        normalized = query.lower()
        if any(signal in normalized for signal in ("supersed", "replaced", "replaces")):
            return self.regulation_change(query)
        if "amend" in normalized:
            return self.regulation_amendments(query)
        if any(signal in normalized for signal in ("apply", "subject to", "which entities")):
            return self.regulation_applicability(query)
        if any(signal in normalized for signal in ("product", "digital lending", "co-lending")):
            return self.requirement_products(query)
        return self.entity_regulations(query)

    def regulation_applicability(self, query: str) -> GraphRetrievalResult:
        regulations = self._match_nodes(query, entity_type="Regulation")
        requirements = self._neighbors(regulations, {"REQUIRES"})
        entities = self._neighbors(requirements, {"APPLIES_TO"})
        return self._result("regulation_to_requirements_to_entities", regulations + requirements + entities)

    def regulation_change(self, query: str) -> GraphRetrievalResult:
        regulations = self._match_nodes(query, entity_type="Regulation")
        related = self._neighbors(regulations, {"SUPERSEDES", "REPLACES"})
        return self._result("regulation_to_superseded_regulation", regulations + related)

    def regulation_amendments(self, query: str) -> GraphRetrievalResult:
        regulations = self._match_nodes(query, entity_type="Regulation")
        related = self._neighbors(regulations, {"AMENDS"})
        return self._result("regulation_to_amendments", regulations + related)

    def requirement_products(self, query: str) -> GraphRetrievalResult:
        requirements = self._match_nodes(query, entity_type="Requirement")
        products = self._neighbors(requirements, {"APPLIES_TO_PRODUCT"})
        return self._result("requirement_to_lending_product", requirements + products)

    def entity_regulations(self, query: str) -> GraphRetrievalResult:
        entities = self._match_nodes(query, entity_type="RegulatedEntity")
        regulations = self._neighbors(entities, {"APPLIES_TO"}, reverse=True)
        return self._result("entity_to_applicable_regulations", entities + regulations)

    def _match_nodes(self, query: str, entity_type: str) -> list[str]:
        terms = {term for term in re.findall(r"[a-z0-9]{3,}", query.lower()) if term not in {"which", "does", "this", "that", "what"}}
        scored = []
        for node_id, attrs in self.graph.nodes(data=True):
            if attrs.get("entity_type") != entity_type:
                continue
            name_terms = set(re.findall(r"[a-z0-9]{3,}", attrs.get("name", "").lower()))
            score = len(terms & name_terms)
            if score:
                scored.append((score, node_id))
        return [node_id for _, node_id in sorted(scored, reverse=True)[:3]]

    def _neighbors(self, nodes: Iterable[str], relationship_types: set[str], reverse: bool = False) -> list[str]:
        found: set[str] = set()
        for node_id in nodes:
            edges = self.graph.in_edges(node_id, data=True) if reverse else self.graph.out_edges(node_id, data=True)
            for source_id, target_id, data in edges:
                if data.get("relationship_type") in relationship_types:
                    found.add(source_id if reverse else target_id)
        return sorted(found)

    def _result(self, template: str, node_ids: list[str]) -> GraphRetrievalResult:
        selected = set(node_ids)
        edges = []
        for source_id, target_id, data in self.graph.edges(data=True):
            if source_id in selected and target_id in selected:
                edges.append(GraphEdgeEvidence(
                    source_id=source_id,
                    target_id=target_id,
                    relationship_type=data["relationship_type"],
                    source_chunk_id=data["source_chunk_id"],
                    source_document_id=data["source_document_id"],
                    confidence=data["confidence"],
                ))
        nodes = [
            GraphNodeEvidence(node_id=node_id, name=self.graph.nodes[node_id]["name"], entity_type=self.graph.nodes[node_id]["entity_type"])
            for node_id in sorted(selected)
        ]
        return GraphRetrievalResult(template=template, nodes=nodes, edges=edges)

