"""Phase 3 gate: the retrieval ladder on the dev questions, one change per rung.

    python scripts/run_ladder.py --corpus-dir data/runtime/corpus-v2 --include-drafted

Each rung is its parent's settings with exactly one setting changed (the script refuses otherwise).
Retrieval takes the first 30 eligible chunks; re-ranking reorders those 30. Reports recall@5/10 and
MRR per gold sentence, nDCG@10 per question, withdrawn-trap leakage (a must-not-cite sentence in
the top 5), latency p50/p95 and cost per query, overall and by question type, with a run manifest.
Paid usage goes to data/evaluation/spend-ledger.jsonl. The held-out test split is never read.
"""
import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import clock  # noqa: E402
from app.config.settings import Settings  # noqa: E402
from app.evaluation import ladder  # noqa: E402
from app.evaluation.retrieval_metrics import contains, first_hit_rank, same_page, summarise  # noqa: E402
from app.ingestion.manifest import DocumentManifest  # noqa: E402
from app.models.chunks import ChunkMetadata  # noqa: E402
from app.retrieval.vector_store import LocalVectorStore, is_current_guidance  # noqa: E402

CANDIDATES = 30
COHERE_PRICE_PER_SEARCH = 0.002  # USD, Cohere list price for rerank-v3.5 ($2 per 1,000 searches)
BASE = {"retriever": "rung0", "filter": "off", "rerank": "none", "graph": "off"}
RUNGS = [  # (name, parent, the one setting it changes)
    ("rung0", None, {}),
    ("bm25", "rung0", {"retriever": "bm25"}),
    ("dense-openai", "bm25", {"retriever": "openai"}),
    ("dense-bge", "dense-openai", {"retriever": "bge"}),
    ("hybrid", "bm25", {"retriever": "hybrid"}),
    ("hybrid+as-of", "hybrid", {"filter": "as_of"}),
    ("rerank-cohere", "hybrid+as-of", {"rerank": "cohere"}),
    ("rerank-bge", "hybrid+as-of", {"rerank": "bge"}),
    ("graph", "hybrid+as-of", {"graph": "refers_to"}),  # Phase 4 fair test: graph on vs off
]


def configs() -> dict[str, dict]:
    out = {}
    for name, parent, change in RUNGS:
        if len(change) > 1:
            sys.exit(f"{name} changes {len(change)} settings; a rung may change one.")
        out[name] = {**(out[parent] if parent else BASE), **change}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--questions", type=Path, default=ROOT / "data" / "evaluation" / "v2")
    parser.add_argument("--include-drafted", action="store_true", help="Also use unreviewed drafts (provisional).")
    parser.add_argument("--rungs", nargs="*", help="Run only these rungs (default: all).")
    parser.add_argument("--cohere-trial", action="store_true", help="The Cohere key is a free trial key (no charge).")
    parser.add_argument("--hybrid-dense", choices=["openai", "bge"], default="openai")
    parser.add_argument("--graph-file", type=Path, help="Default: <corpus>/graph/graph.json")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "evaluation" / "ladder-dev.json")
    args = parser.parse_args()
    settings = Settings()
    plan = configs()
    names = args.rungs or list(plan)

    usable = {"accepted", "edited"} | ({"drafted"} if args.include_drafted else set())
    dev_file = args.questions / "dev.jsonl"
    questions = [row for row in map(json.loads, dev_file.read_text(encoding="utf-8").splitlines())
                 if row["status"] in usable]
    store = LocalVectorStore(args.corpus_dir / "runtime" / "vectors.json")
    rows = [row["chunk"] for row in store._read()]
    chunks = [ChunkMetadata.model_validate(row) for row in rows]
    by_id = {chunk.chunk_id: index for index, chunk in enumerate(chunks)}
    texts = [chunk.text for chunk in chunks]
    today = clock.now().date()

    # Retrievers are built only when a selected rung needs them (open models download on first use).
    needed = {plan[name]["retriever"] for name in names}
    rerank_needed = {plan[name]["rerank"] for name in names}
    cache = ROOT / "data" / "runtime" / "embedding-cache"
    retrievers, embedders, rerankers = {}, {}, {}
    if needed & {"bm25", "hybrid"}:
        retrievers["bm25"] = ladder.BM25(texts)
    for kind in ("openai", "bge"):
        if kind in needed or ("hybrid" in needed and args.hybrid_dense == kind):
            embedders[kind] = ladder.OpenAIEmbedder(settings.openai_api_key) if kind == "openai" else ladder.BgeEmbedder()
            retrievers[kind] = ladder.Dense(embedders[kind], ladder.corpus_embeddings(embedders[kind], texts, cache))
            print(f"{kind}: {len(texts)} chunks embedded ({embedders[kind].tokens} new tokens)", flush=True)
    corpus_tokens = {kind: embedder.tokens for kind, embedder in embedders.items()}
    if "cohere" in rerank_needed:
        rerankers["cohere"] = ladder.CohereReranker(settings.cohere_api_key)
    if "bge" in rerank_needed:
        rerankers["bge"] = ladder.BgeReranker()

    expand = None
    if any(plan[name]["graph"] != "off" for name in names):
        from app.graph import ontology
        expand = ladder.GraphExpansion(ontology.load(args.graph_file or args.corpus_dir / "graph" / "graph.json"), chunks)

    def ranking(config: dict, query: str) -> list[int]:
        if config["retriever"] == "rung0":
            return [by_id[item.chunk_id] for item in store.search(query, top_k=len(chunks), current_only=False)]
        if config["retriever"] == "hybrid":
            return ladder.rrf(retrievers["bm25"].rank(query), retrievers[args.hybrid_dense].rank(query))
        return retrievers[config["retriever"]].rank(query)

    results = {}
    for name in names:
        config = plan[name]
        before_tokens = {kind: embedder.tokens for kind, embedder in embedders.items()}
        before_units = {kind: reranker.search_units for kind, reranker in rerankers.items()}
        ranks, ndcg, leaks, latencies = [], [], [], []
        by_type = defaultdict(lambda: {"ranks": [], "ndcg": []})
        for question in questions:
            day = date_of(question) or today
            started = time.perf_counter()
            order = ranking(config, question["question"])
            if config["graph"] == "refers_to":
                order = expand(order)
            if config["filter"] == "as_of":
                order = [index for index in order if is_current_guidance(rows[index], day)]
            order = order[:CANDIDATES]
            if config["rerank"] != "none":
                order = [order[i] for i in rerankers[config["rerank"]].rerank(question["question"], [texts[i] for i in order])]
            latencies.append((time.perf_counter() - started) * 1000)
            found = [chunks[index] for index in order]
            for gold in question["gold"]:
                rank = first_hit_rank(found, gold)
                ranks.append(rank)
                by_type[question["type"]]["ranks"].append(rank)
            if question["gold"]:
                score = ladder.ndcg_at([(chunk.source_url, chunk.text) for chunk in found], question["gold"])
                ndcg.append(score)
                by_type[question["type"]]["ndcg"].append(score)
            if question["must_not_cite"]:
                leaks.append(any(same_page(chunk.source_url, bad["url"]) and contains(chunk.text, bad["span"])
                                 for chunk in found[:5] for bad in question["must_not_cite"]))
        tokens = sum(embedder.tokens - before_tokens[kind] for kind, embedder in embedders.items())
        units = sum(reranker.search_units - before_units[kind] for kind, reranker in rerankers.items())
        cost = tokens * ladder.OpenAIEmbedder.price_per_million / 1e6 * ("openai" in embedders) \
            + units * COHERE_PRICE_PER_SEARCH
        cuts = statistics.quantiles(latencies, n=20)
        results[name] = {
            "config": config, **summarise(ranks),
            "ndcg@10": round(statistics.mean(ndcg), 4) if ndcg else None,
            "withdrawn_trap_leak@5": {"numerator": sum(leaks), "denominator": len(leaks)},
            "latency_ms": {"p50": round(statistics.median(latencies), 1), "p95": round(cuts[18], 1)},
            "paid_usage": {"openai_query_tokens": tokens, "cohere_search_units": units},
            "cost_per_query_usd": round(cost / len(questions), 9),
            "by_type": {kind: {**summarise(value["ranks"]),
                               "ndcg@10": round(statistics.mean(value["ndcg"]), 4) if value["ndcg"] else None}
                        for kind, value in sorted(by_type.items())},
        }
        print(name, json.dumps({key: value for key, value in results[name].items() if key != "by_type"}), flush=True)

    paid_tokens = sum(embedder.tokens for kind, embedder in embedders.items() if kind == "openai")
    paid_units = sum(reranker.search_units for kind, reranker in rerankers.items() if kind == "cohere")
    with (ROOT / "data" / "evaluation" / "spend-ledger.jsonl").open("a", encoding="utf-8") as ledger:
        if paid_tokens:
            ledger.write(json.dumps({"at": datetime.now(UTC).isoformat(), "phase": 3, "task": "ladder embeddings",
                                     "model": "text-embedding-3-small", "prompt_tokens": paid_tokens,
                                     "estimated_cost_usd": paid_tokens * ladder.OpenAIEmbedder.price_per_million / 1e6}) + "\n")
        if paid_units:
            ledger.write(json.dumps({"at": datetime.now(UTC).isoformat(), "phase": 3, "task": "ladder re-ranking",
                                     "model": "rerank-v3.5", "search_units": paid_units,
                                     "estimated_cost_usd": 0 if args.cohere_trial else paid_units * COHERE_PRICE_PER_SEARCH,
                                     **({"note": "Cohere trial key: no charge. Cost per query in the report uses the "
                                                 "list price, as production would pay."} if args.cohere_trial else {})}) + "\n")

    documents = DocumentManifest(args.corpus_dir / "runtime" / "documents.json").all()
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "questions": len(questions), "gold_sentences": sum(len(row["gold"]) for row in questions),
        "includes_unreviewed_drafts": args.include_drafted,
        "chunks": len(chunks), "chunkers": sorted({chunk.chunker for chunk in chunks if chunk.chunker}),
        "candidates": CANDIDATES, "hybrid_dense": args.hybrid_dense,
        "models": {"openai": ladder.OpenAIEmbedder.name, "bge": ladder.BgeEmbedder.name,
                   "cohere": ladder.CohereReranker.name, "bge_rerank": ladder.BgeReranker.name},
        "cohere_trial_key": args.cohere_trial,
        "prices_usd": {"openai_per_million_tokens": ladder.OpenAIEmbedder.price_per_million,
                       "cohere_per_search": COHERE_PRICE_PER_SEARCH},
        "corpus_embedding_tokens_this_run": corpus_tokens,
        "rungs": [{"name": name, "parent": parent, "change": change} for name, parent, change in RUNGS if name in names],
        "results": results,
        "run_manifest": {
            "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
            "working_tree_dirty": bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", "app",
                                                       "scripts", "config"], cwd=ROOT, capture_output=True, text=True).stdout.strip()),
            "corpus_fingerprint": hashlib.sha256("".join(sorted(f"{d.document_id}:{d.content_hash}" for d in documents)).encode()).hexdigest(),
            "dev_questions_sha256": hashlib.sha256(dev_file.read_bytes()).hexdigest(),
            "as_of_today": str(today),
        },
    }
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")


def date_of(question: dict):
    from datetime import date
    return date.fromisoformat(question["as_of"]) if question.get("as_of") else None


if __name__ == "__main__":
    main()
