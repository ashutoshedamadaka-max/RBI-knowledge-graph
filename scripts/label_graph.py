"""Phase 4 answer key: label 50 random provisions, without seeing what the system extracted.

    python scripts/label_graph.py --corpus-dir data/runtime/corpus-v2

For each provision (document title, heading and numbered sentences are shown) you answer four
questions by typing numbers separated by commas, or Enter for none:
  1. Which lenders or products does this provision govern?   (numbers from the entity list)
  2. Which sentences impose an obligation on someone?
  3. Which sentences define a term?
  4. Which sentences refer to another paragraph or another RBI circular/direction?
Saved after every provision (q to stop, run again to resume) to data/evaluation/gold/graph-labels.json.
The sample is drawn once (seed 5), leaving out the 20 provisions used to write the extraction prompt.
"""
import argparse
import hashlib
import json
import random
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.evaluation.graph_metrics import sample, sentences  # noqa: E402
from app.graph import ontology  # noqa: E402
from app.graph.llm_extraction import load_entities  # noqa: E402

GOLD = ROOT / "data" / "evaluation" / "gold" / "graph-labels.json"
SIZE, SEED, PILOT_SEED, PILOT_SIZE = 50, 5, 11, 20
QUESTIONS = {
    "applies_to": "Which lenders or products does it govern? (entity numbers)",
    "requires": "Which sentences impose an obligation?",
    "defines": "Which sentences define a term?",
    "refers_to": "Which sentences refer to another paragraph or RBI document?",
}


def numbers(answer: str, highest: int) -> list[int] | None:
    try:
        values = sorted({int(part) for part in answer.replace(" ", ",").split(",") if part})
    except ValueError:
        return None
    return values if all(1 <= value <= highest for value in values) else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    args = parser.parse_args()
    graph = ontology.load(args.corpus_dir / "graph" / "graph.json")
    provisions = sorted(node for node, data in graph.nodes(data=True) if data["type"] == "Provision")
    entities = load_entities()
    entity_ids = list(entities)

    data = json.loads(GOLD.read_text(encoding="utf-8")) if GOLD.exists() else {}
    if "sample" not in data:
        pilot = set(random.Random(PILOT_SEED).sample(provisions, PILOT_SIZE))  # as scripts/extract_graph_edges.py --limit 20
        data = {"seed": SEED, "excluded_prompt_development": sorted(pilot),
                "sample": sample(provisions, SIZE, SEED, pilot), "labels": {}}
        GOLD.parent.mkdir(parents=True, exist_ok=True)
        GOLD.write_text(json.dumps(data, indent=2), encoding="utf-8")

    listing = [f"{number:>2}. {entities[key]['name']}" for number, key in enumerate(entity_ids, start=1)]
    todo = [node for node in data["sample"] if node not in data["labels"]]
    print(f"{SIZE - len(todo)} of {SIZE} provisions labelled.")
    for count, node in enumerate(todo, start=SIZE - len(todo) + 1):
        provision = graph.nodes[node]
        parts = sentences(provision["text"])
        print("\n" + "=" * 100)
        print(f"[{count}/{SIZE}] {graph.nodes[provision['document_id']]['title']}")
        if provision["heading"]:
            print(f"Under: {provision['heading']}")
        for number, part in enumerate(parts, start=1):
            print(textwrap.fill(f"({number}) {part}", width=100, subsequent_indent="     "))
        answers = {}
        for key, question in QUESTIONS.items():
            if key == "applies_to":
                for left in range(0, len(listing), 2):
                    print(f"  {listing[left]:<52}{listing[left + 1] if left + 1 < len(listing) else ''}")
            highest = len(entity_ids) if key == "applies_to" else len(parts)
            while True:
                answer = input(f"  {question} [numbers, Enter = none, q = quit] ").strip().lower()
                if answer == "q":
                    return
                picked = numbers(answer, highest)
                if picked is not None:
                    break
                print(f"  Please type numbers between 1 and {highest}, separated by commas.")
            answers[key] = [entity_ids[value - 1] for value in picked] if key == "applies_to" else picked
        current = json.loads(GOLD.read_text(encoding="utf-8"))  # re-read so nothing saved elsewhere is lost
        current["labels"][node] = {**answers, "sentences": len(parts),
                                   "text_sha256": hashlib.sha256(provision["text"].encode("utf-8")).hexdigest(),
                                   "labelled_at": datetime.now(UTC).isoformat()}
        GOLD.write_text(json.dumps(current, indent=2), encoding="utf-8")
    print("\nAll 50 provisions labelled.")


if __name__ == "__main__":
    main()
