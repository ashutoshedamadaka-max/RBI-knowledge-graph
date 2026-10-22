"""The regulation map (Phase 6): the Phase 4 graph with its precomputed layout, and one node's evidence.

The overview leaves out Obligation nodes (5,578 of them, one per extracted requirement); they appear in a
provision's detail. APPLIES_TO edges carry their measured precision (ADR-027), because the map labels them.
"""
import json
from functools import lru_cache
from pathlib import Path

from app.graph import ontology

MAP_TYPES = {"Document", "Provision", "DefinedTerm", "Authority", "RegulatedEntity", "Product"}
NODE_FIELDS = ("type", "title", "label", "lifecycle", "issued", "in_force_from", "in_force_to", "document_id",
               "x", "y", "community", "url", "heading")
QUALITY_FILE = Path(__file__).resolve().parents[2] / "data" / "evaluation" / "graph-quality.json"


@lru_cache(maxsize=2)
def _load(path: str, modified: float):
    return ontology.load(Path(path))


def graph_for(data_dir: Path):
    path = data_dir / "graph" / "graph.json"
    if not path.exists():
        return None
    return _load(str(path), path.stat().st_mtime)


def applies_to_precision() -> dict | None:
    """APPLIES_TO precision on the fresh paragraphs, for the map's caveat (None until measured)."""
    if not QUALITY_FILE.exists():
        return None
    results = json.loads(QUALITY_FILE.read_text(encoding="utf-8"))["results"]
    fresh = next((value for key, value in results.items() if key.startswith("fresh")), None)
    return fresh["APPLIES_TO"]["precision"] if fresh else None


def overview(graph) -> dict:
    nodes = []
    degree = dict(graph.degree())
    for node, data in graph.nodes(data=True):
        if data["type"] not in MAP_TYPES:
            continue
        item = {"id": node, "degree": degree.get(node, 0), **{key: data[key] for key in NODE_FIELDS if data.get(key) not in (None, "")}}
        if data["type"] == "Provision":
            item["title"] = f"{graph.nodes[data['document_id']].get('title', '')[:80]} – para {data.get('label')}"
        nodes.append(item)
    kept = {node["id"] for node in nodes}
    edges = [{"source": source, "target": target, "type": data["type"], **({"trust": data["trust"]} if data.get("trust") else {})}
             for source, target, data in graph.edges(data=True) if source in kept and target in kept]
    return {"nodes": nodes, "edges": edges, "applies_to_precision": applies_to_precision()}


def node_detail(graph, node: str) -> dict | None:
    if node not in graph:
        return None
    data = dict(graph.nodes[node])

    def describe(other: str) -> dict:
        other_data = graph.nodes[other]
        return {"id": other, "type": other_data["type"], "title": other_data.get("title") or other_data.get("label")}

    edges = [{"direction": "out", "type": edge["type"], "other": describe(target), "quote": edge.get("quote"),
              "method": edge.get("method"), "evidence_url": edge.get("evidence_url"), "trust": edge.get("trust"),
              "confidence": edge.get("confidence")}
             for _, target, edge in graph.out_edges(node, data=True)]
    edges += [{"direction": "in", "type": edge["type"], "other": describe(source), "quote": edge.get("quote"),
               "method": edge.get("method"), "evidence_url": edge.get("evidence_url"), "trust": edge.get("trust"),
               "confidence": edge.get("confidence")}
              for source, _, edge in graph.in_edges(node, data=True) if graph.nodes[source]["type"] != "Provision"
              or edge["type"] != "PART_OF"]
    if data["type"] == "Document":
        data["provision_count"] = sum(1 for source, _, edge in graph.in_edges(node, data=True) if edge["type"] == "PART_OF")
    return {"id": node, **{key: value for key, value in data.items() if key not in ("x", "y")}, "edges": edges}
