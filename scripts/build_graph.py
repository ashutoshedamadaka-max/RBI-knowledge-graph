"""Build the Phase 4 knowledge graph from a corpus (no model calls).

    python scripts/build_graph.py --corpus-dir data/runtime/corpus-v2

Re-parses each stored original, adds structure, document-link, register, cross-reference and
definition edges, then LLM edges if --llm-edges points at a saved extraction. Precomputes the map
layout and communities. Writes <corpus>/graph/graph.json and data/evaluation/graph-build.json.
RBI's register page is fetched once and kept as <corpus>/register.html.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.graph import ontology  # noqa: E402
from app.ingestion.manifest import DocumentManifest  # noqa: E402
from app.ingestion.parser import parse_document  # noqa: E402
from app.monitoring.link_store import LinkStore  # noqa: E402
from app.monitoring.withdrawn_register import REGISTER_URL, match_register, parse_register  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--llm-edges", type=Path, help="Saved LLM extraction (scripts/extract_graph_edges.py).")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "evaluation" / "graph-build.json")
    args = parser.parse_args()

    documents = DocumentManifest(args.corpus_dir / "runtime" / "documents.json").all()
    pages = {document.document_id: parse_document(next((args.corpus_dir / "raw").glob(f"{document.document_id}.*")),
                                                  document.mime_type).pages for document in documents}
    links = LinkStore(args.corpus_dir / "runtime" / "document_links.json").all()
    register_file = args.corpus_dir / "register.html"
    if not register_file.exists():
        register_file.write_text(httpx.get(REGISTER_URL, follow_redirects=True, timeout=90).text, encoding="utf-8")
    register = match_register(documents, parse_register(register_file.read_text(encoding="utf-8")))

    graph, report = ontology.build_graph(documents, pages, links, register, REGISTER_URL)
    if args.llm_edges:
        report["llm"] = ontology.add_llm_edges(graph, json.loads(args.llm_edges.read_text(encoding="utf-8")))
        report["edges"] = ontology.edge_counts(graph)
        report["nodes"] = dict(Counter(data["type"] for _, data in graph.nodes(data=True)))
    ontology.add_layout(graph)
    ontology.save(graph, args.corpus_dir / "graph" / "graph.json")

    report["run_manifest"] = {
        "built_at": datetime.now(UTC).isoformat(),
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
        "working_tree_dirty": bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", "app",
                                                   "scripts", "config"], cwd=ROOT, capture_output=True, text=True).stdout.strip()),
        "corpus_fingerprint": hashlib.sha256("".join(sorted(f"{d.document_id}:{d.content_hash}" for d in documents))
                                             .encode()).hexdigest(),
        "register_sha256": hashlib.sha256(register_file.read_bytes()).hexdigest(),
        "llm_edges_sha256": hashlib.sha256(args.llm_edges.read_bytes()).hexdigest() if args.llm_edges else None,
    }
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
