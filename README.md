# RBI Lending Intelligence

[Open the app](https://rbiknowledgegraph.vercel.app/) · Independent AI product portfolio prototype · Not affiliated with RBI

## Problem

Lending and compliance researchers need to find a relevant rule and check whether its source can still be relied on. An official citation may resolve correctly while pointing to a withdrawn document. This prototype explores that problem with a selected RBI lending corpus; user adoption and time savings have not been validated.

## What I built

A research workspace that retrieves selected official RBI material, filters current-guidance evidence by recorded lifecycle, generates cited summaries, and exposes source monitoring events. Relationship-aware retrieval uses a provenance graph when supported; text retrieval is a hashing/lexical baseline, not a semantic embedding model. Historical/change research can include prior material but does not reconstruct exact legal authority on a specified date.

## Results

The [current deterministic benchmark](data/evaluation/current-report.json) records measured source retrieval, citation mapping, abstention and routing on 30 unchanged labelled questions. Its manifest includes the base commit, dirty-worktree flag, code/dataset/corpus fingerprints, source checks and lifecycle counts. The [older report](data/evaluation/portfolio-report.json) is retained for comparison.

Source-retrieval performance remains weak; several benchmark labels refer to documents excluded from current guidance. The benchmark is not live-model answer accuracy. Citation mapping does not establish semantic correctness, and deterministic latency/cost must not be presented as OpenAI production latency/cost. No graph superiority or business-impact improvement is claimed.

## Regulatory monitoring coverage

The registry monitors official RBI Notifications, Master Directions, and lending FAQs on RBI-owned domains. It is configured for daily or weekly polling by source and records every successful, failed, and partial check. Monitoring is deliberately scoped to lending-related title/topic signals; it is not a guarantee of complete regulatory compliance. Regulatory interpretation and operational decisions should be reviewed by qualified compliance and legal professionals.

## Architecture

The system keeps vector chunks, graph edges, citations, evaluation cases, and debugging identifiers anchored to the same stable chunk ID. See the full [architecture diagram](docs/architecture.md).

## System design

- **Ingestion:** provenance-first PDF/text extraction, document hashing, page metadata, and cache reuse.
- **Retrieval:** lexical vector baseline for direct facts; reviewed graph templates for entity scope, amendments, replacements, and multi-hop connections.
- **Generation:** answer only from retrieved evidence; decline when evidence is absent.
- **Verification:** every answer citation must resolve to a retrieved chunk or the response fails closed.

## Ontology and trade-offs

The graph deliberately restricts entity types (such as Regulation, Requirement, RegulatedEntity, LendingProduct, and Authority) and relationships (such as APPLIES_TO, REQUIRES, AMENDS, and SUPERSEDES). This makes graph retrieval auditable but means new relationship types need an explicit, tested template. The decision record is in [docs/decisions.md](docs/decisions.md).

## Evaluation methodology

The 30-question portfolio benchmark covers single-hop, two-hop, multi-hop, comparison, temporal/change, and out-of-scope queries. Vector-only and routed retrieval use the same historical-intent eligibility rule. Questions and source labels are not rewritten to improve the score. Lifecycle regression tests and the retrieval benchmark are separate evidence.

Reproduce in an isolated directory (never use the production data directory):

```powershell
python scripts/publish_evaluation.py --data-dir data/runtime/isolated-evaluation --output data/evaluation/current-report.json
python -m pytest -q
node --test tests/frontend-behavior.test.cjs
```

The publisher checks all individually curated sources through the existing monitor and configured approval path. It does not manually approve unresolved documents. `--offline` records that no source refresh was attempted.

## Failure handling

The service handles unparseable documents, duplicate content, empty retrieval, malformed extraction, invalid citations, and unavailable model configuration. It does not return a confident answer when supporting evidence cannot be verified.

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

## Phase 2: chunking and vector baseline

Ingested pages are split into page-bounded chunks using configurable size and overlap. Each chunk receives a stable ID shared by vector retrieval, future graph provenance, citations, evaluation, and debugging. `GET /search?query=...&top_k=5` exposes the local vector baseline and returns chunk text, document, page, source URL, and score.

The local baseline uses deterministic feature hashing to stay free and reproducible. It is intentionally documented as lexical—not semantic—and does not claim benchmark quality. [Phase 2 details](docs/phase-2-plan.md) explain the adapter boundary for a sentence-transformer and pgvector production store.

## Phase 3: provenance graph

The graph is deliberately constrained: it admits only documented entity and relationship types, performs deterministic alias resolution, and retains source chunk/document provenance on every edge. The default extractor is conservative and free; an OpenAI strict-JSON adapter can be enabled only through configuration. [Phase 3 details](docs/phase-3-plan.md) document its limitations and safety controls.

## Phase 4: relationship-aware routing

The query router selects vector retrieval for direct factual questions, graph retrieval for relationship and change questions, and hybrid retrieval for questions that need both. Graph retrieval is limited to reviewed templates rather than arbitrary model-generated queries. [Phase 4 details](docs/phase-4-plan.md) describe the supported patterns.

## Phase 5: grounded answers

`POST /query` merges routed evidence and returns an answer only from retrieved chunks. Every material statement is tagged with a chunk ID, and citation validation rejects answer citations that are absent from the retrieved evidence. The default response composer is free and deterministic; OpenAI generation is an opt-in, evidence-only adapter. [Phase 5 details](docs/phase-5-plan.md) describe the failure behavior.

## Phase 6: evaluation

The evaluation harness compares vector-only retrieval against routed retrieval across labelled questions, stratified by hop count and question type. The current portfolio run and its limitations are linked above; older phase documents describe the original implementation plan.

## Phase 7: observability and cost

Each `POST /query` response now has a request ID and produces a structured event containing its route, evidence IDs, graph footprint, model usage, latency, cost, and citation status. `GET /metrics` reports aggregate recorded token and cost usage. [Phase 7 details](docs/phase-7-plan.md) document the cost model.

## Phase 8: product surface

The root page is a focused regulatory research workspace: submit a question, inspect its retrieval mode, read the grounded answer, open the cited RBI source, and inspect the underlying evidence if needed. [Phase 8 details](docs/phase-8-plan.md) explain the product choices.

## Phase 9: monitoring and change intelligence

The monitoring pipeline uses source URL, listing metadata, and normalized content hashes to detect new and modified RBI material without using an LLM. It preserves document versions, marks earlier chunks as non-current, creates deduplicated update records, and exposes them through the Regulatory Updates panel. Phase 9 integration and the local-schema migration are documented in [docs/phase-9-plan.md](docs/phase-9-plan.md).

## Architecture roadmap

`RBI sources → ingestion → parsed pages → chunking + metadata → vector index and provenance graph → router → evidence merger → grounded answer → citation validator`

The initial ontology and the NetworkX-to-Neo4j migration boundary are documented in [docs/decisions.md](docs/decisions.md). The detailed Phase 1 acceptance criteria are in [docs/phase-1-plan.md](docs/phase-1-plan.md).

## API surface today

- `POST /ingest` — acquire, hash, parse, cache a source
- `GET /documents` — list ingested metadata
- `GET /search` — retrieve the top matching chunks from the vector baseline
- `POST /query` — answer from routed evidence with validated citations
- `GET /metrics` — aggregate model usage and estimated cost
- `GET /health` — service status

The default mode is deterministic and has no API cost. Configure an OpenAI provider only after reviewing the documented cost controls and source corpus.

## Deployment

The Python API runs on Render and the static browser interface on Vercel. Configured durable runtime snapshots use PostgreSQL; otherwise local files require durable hosting storage. Both the API root and Vercel build now serve the canonical `frontend/` implementation, avoiding two diverging UIs. See [the deployment guide](docs/deployment.md); verify actual environment settings before deploying.
