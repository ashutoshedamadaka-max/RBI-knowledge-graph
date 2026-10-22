"""Quoted LLM extraction of APPLIES_TO and REQUIRES for every provision in a built graph (Phase 4).

    python scripts/build_graph.py --corpus-dir data/runtime/corpus-v2           (provisions first)
    python scripts/extract_graph_edges.py --corpus-dir data/runtime/corpus-v2 --limit 20   (pilot)
    python scripts/extract_graph_edges.py --corpus-dir data/runtime/corpus-v2
    python scripts/build_graph.py --corpus-dir data/runtime/corpus-v2 --llm-edges data/runtime/corpus-v2/graph/llm-edges.json

Saves after every batch and skips provisions already done, so a stopped run resumes for free.
Token usage and cost go to data/evaluation/spend-ledger.jsonl.
"""
import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config.settings import Settings  # noqa: E402
from app.graph import llm_extraction, ontology  # noqa: E402

WORKERS = 8


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, help="Only this many more provisions (a random pilot, seed 11).")
    args = parser.parse_args()
    settings = Settings()
    model = settings.openai_extraction_model
    if not settings.openai_api_key:
        sys.exit("OPENAI_API_KEY is not set.")
    graph = ontology.load(args.corpus_dir / "graph" / "graph.json")
    out = args.corpus_dir / "graph" / "llm-edges.json"
    saved = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"model": model, "provisions": {}}
    if saved["model"] != model:
        sys.exit(f"{out} was made with {saved['model']}; move it aside to extract with {model}.")
    entities = llm_extraction.load_entities()
    todo = sorted(node for node, data in graph.nodes(data=True)
                  if data["type"] == "Provision" and node not in saved["provisions"])
    if args.limit:
        todo = sorted(random.Random(11).sample(todo, min(args.limit, len(todo))))
    print(f"{len(todo)} provisions to extract with {model}", flush=True)

    def run(node: str):
        data = graph.nodes[node]
        try:
            raw, usage = llm_extraction.extract(settings.openai_api_key, model, graph.nodes[data["document_id"]]["title"], data["heading"], data["text"], entities)
        except Exception as exc:  # counted per provision and surfaced in the build report
            return node, {"error": f"{type(exc).__name__}: {exc}"[:200]}, {}
        edges, dropped = llm_extraction.validate(raw, data["text"], entities)
        return node, {"edges": edges, "dropped": dropped}, usage

    tokens = {"prompt_tokens": 0, "completion_tokens": 0}
    with ThreadPoolExecutor(WORKERS) as pool:
        for start in range(0, len(todo), 50):
            for node, result, usage in pool.map(run, todo[start:start + 50]):
                saved["provisions"][node] = result
                for key in tokens:
                    tokens[key] += usage.get(key, 0)
            out.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{min(start + 50, len(todo))}/{len(todo)}", flush=True)

    input_price, output_price = llm_extraction.PRICES[model]
    cost = (tokens["prompt_tokens"] * input_price + tokens["completion_tokens"] * output_price) / 1e6
    with (ROOT / "data" / "evaluation" / "spend-ledger.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps({"at": datetime.now(UTC).isoformat(), "phase": 4, "task": "graph edge extraction",
                                 "model": model, **tokens, "provisions": len(todo), "estimated_cost_usd": cost}) + "\n")
    errors = sum(1 for node in todo if saved["provisions"][node].get("error"))
    print(json.dumps({"extracted": len(todo), "call_errors": errors, **tokens, "estimated_cost_usd": round(cost, 4)}))


if __name__ == "__main__":
    main()
