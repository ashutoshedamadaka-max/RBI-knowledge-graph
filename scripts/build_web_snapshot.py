"""Public browsing fallback from the committed evaluated corpus, never from production credentials."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data/releases/corpus-v2.zip"
OUT = ROOT / "web/public/evidence"
OUT.mkdir(parents=True, exist_ok=True)


def save(name, data):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


with ZipFile(RELEASE) as archive:
    graph = json.loads(archive.read("graph/graph.json"))
    docs = json.loads(archive.read("runtime/documents.json"))
    vectors = json.loads(archive.read("runtime/vectors.json"))

# Explicit allowlists prevent operational metadata or vector arrays from reaching the browser.
doc_fields = "document_id title lifecycle document_type publication_date in_force_from in_force_to source_url status_evidence_excerpt status_resolution_method".split()
save("documents.json", {"documents": [{k: d.get(k) for k in doc_fields} for d in docs]})
chunk_fields = "chunk_id paragraph_ref heading_path token_count text page_number".split()
chunks = defaultdict(list)
for row in vectors:
    chunk = row["chunk"]
    chunks[chunk["document_id"]].append({k: chunk.get(k) for k in chunk_fields})
for doc_id, rows in chunks.items():
    save(f"chunks/{doc_id}.json", rows)

node_fields = "id type title label text heading lifecycle url issued in_force_from in_force_to provision_count document_id x y community".split()
edge_fields = "source target type quote method evidence_url trust confidence".split()
nodes = [{k: n[k] for k in node_fields if k in n} for n in graph["nodes"]]
edges = [{k: e[k] for k in edge_fields if k in e} for e in graph["edges"]]
save("graph.json", {"nodes": nodes, "edges": edges})
degree = Counter()
for edge in edges:
    degree.update([edge["source"], edge["target"]])
by_id = {n["id"]: n for n in nodes}
overview = []
for n in nodes:
    if n["type"] == "Obligation":
        continue
    item = {k: v for k, v in n.items() if k not in ("text",)}
    item["degree"] = degree[n["id"]]
    if n["type"] == "Provision":
        item["title"] = f'{by_id.get(n.get("document_id"), {}).get("title", "")[:80]} – para {n.get("label", "")}'
    overview.append(item)
kept = {n["id"] for n in overview}
save("graph-map.json", {"nodes": overview, "edges": [{k: e[k] for k in ("source", "target", "type", "trust") if k in e} for e in edges if e["source"] in kept and e["target"] in kept], "applies_to_precision": {"numerator": 6, "denominator": 18}})
save("manifest.json", {"source": "data/releases/corpus-v2.zip", "sha256": hashlib.sha256(RELEASE.read_bytes()).hexdigest(), "documents": len(docs), "chunks": len(vectors), "nodes": len(nodes), "edges": len(edges)})
print(f"Public snapshot: {len(docs)} documents; {len(vectors)} passages; {len(nodes)} graph nodes.")
