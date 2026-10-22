"""Phase 4 gate, part 1: extraction precision and recall per edge type against Ashu's labels.

    python scripts/score_graph.py --corpus-dir data/runtime/corpus-v2

Reads data/evaluation/gold/graph-labels.json (scripts/label_graph.py) and the built graph. A provision
whose text changed since it was labelled is reported as stale, not scored.
Writes data/evaluation/graph-quality.json with a run manifest.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.evaluation.graph_metrics import score, sentence_of, sentences  # noqa: E402
from app.graph import ontology  # noqa: E402

GOLD = ROOT / "data" / "evaluation" / "gold" / "graph-labels.json"
SENTENCE_EDGES = {"requires": "REQUIRES", "defines": "DEFINES", "refers_to": "REFERS_TO"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "evaluation" / "graph-quality.json")
    args = parser.parse_args()
    graph_file = args.corpus_dir / "graph" / "graph.json"
    graph = ontology.load(graph_file)
    labels = json.loads(GOLD.read_text(encoding="utf-8"))["labels"]

    stale, gold, predicted = [], {key: {} for key in ["applies_to", *SENTENCE_EDGES]}, {key: {} for key in ["applies_to", *SENTENCE_EDGES]}
    for node, label in labels.items():
        text = graph.nodes[node]["text"] if node in graph else None
        if text is None or hashlib.sha256(text.encode("utf-8")).hexdigest() != label["text_sha256"]:
            stale.append(node)
            continue
        parts = sentences(text)
        edges = [data for _, _, data in graph.out_edges(node, data=True)]
        gold["applies_to"][node] = set(label["applies_to"])
        predicted["applies_to"][node] = {target.removeprefix("entity:") for _, target, data in graph.out_edges(node, data=True)
                                         if data["type"] == "APPLIES_TO"}
        for key, edge_type in SENTENCE_EDGES.items():
            gold[key][node] = set(label[key])
            predicted[key][node] = set().union(*[sentence_of(data["quote"], parts) for data in edges
                                                 if data["type"] == edge_type and data["quote"]])

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "labelled": len(labels), "scored": len(labels) - len(stale), "stale": stale,
        "unit": "APPLIES_TO: entity ids per provision; the others: sentences per provision (micro-averaged)",
        # Headline: Ashu's hand labels. Model-drafted labels Ashu reviewed are reported separately, never pooled.
        "results": {source: {"provisions": sum(1 for node in gold["applies_to"] if labels[node].get("source", "hand") == source),
                             **{SENTENCE_EDGES.get(key, "APPLIES_TO"): score(
                                 predicted[key], {node: value for node, value in gold[key].items()
                                                  if labels[node].get("source", "hand") == source})
                                for key in gold}}
                    for source in sorted({label.get("source", "hand") for label in labels.values()},
                                         key=lambda source: source != "hand")},
        "run_manifest": {
            "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
            "graph_sha256": hashlib.sha256(graph_file.read_bytes()).hexdigest(),
            "labels_sha256": hashlib.sha256(GOLD.read_bytes()).hexdigest(),
        },
    }
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["results"], indent=2))


if __name__ == "__main__":
    main()
