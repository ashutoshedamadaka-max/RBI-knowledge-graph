# RBI Lending Intelligence Graph RAG

## Problem

Regulatory lending information is fragmented across documents, and conventional vector RAG can struggle with questions requiring relationships between regulations, entities, requirements, and amendments.

## What I built

A graph-enhanced regulatory intelligence system combining vector retrieval, knowledge graphs, routing, grounded generation, and citation validation. The repository is being delivered in testable phases; Phase 1 is a runnable, provenance-first ingestion foundation.

## Results

- X% retrieval recall (measured after the evaluation corpus is ingested)
- X% citation validity (measured after grounded generation is implemented)
- X% improvement on multi-hop questions (measured against the vector baseline)
- X ms median latency (measured after the query service is implemented)
- $X estimated cost per query (measured after model-backed operations are enabled)

No benchmark values are fabricated. Placeholders will be replaced only by evaluation output.

## Phase 1: ingestion foundation

This phase accepts a local PDF/TXT/Markdown file or an HTTPS document URL through `POST /ingest`. It records RBI-oriented provenance metadata, extracts page-preserving text, assigns a content-addressed stable document ID, and caches unchanged source bytes. Parsed pages are written to `data/processed/`; no LLM calls occur in this phase.

### Run locally

1. Copy `.env.example` to `.env`.
2. Install dependencies: `pip install -r requirements.txt`.
3. Start the API: `uvicorn app.main:app --reload`.
4. Open `http://localhost:8000/docs` and call `POST /ingest`.

For the future pgvector deployment, run `docker compose up --build`.

Example local source payload:

```json
{
  "local_path": "C:/authoritative-rbi-document.pdf",
  "title": "RBI Digital Lending Directions",
  "publication_date": "2025-05-08"
}
```

Only obtain documents from authoritative RBI pages. The system preserves the supplied source URL and never presents unsupported regulations as facts.

## Architecture roadmap

`RBI sources → ingestion → parsed pages → chunking + metadata → vector index and provenance graph → router → evidence merger → grounded answer → citation validator`

The initial ontology and the NetworkX-to-Neo4j migration boundary are documented in [docs/decisions.md](docs/decisions.md). The detailed Phase 1 acceptance criteria are in [docs/phase-1-plan.md](docs/phase-1-plan.md).

## API surface today

- `POST /ingest` — acquire, hash, parse, cache a source
- `GET /documents` — list ingested metadata
- `GET /health` — service status

`/query` and `/metrics` are intentionally deferred until the vector, graph, evaluation, and observability layers are implemented; they will not return misleading partial answers.

