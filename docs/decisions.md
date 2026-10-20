# Architecture decisions

## ADR-001: Local manifest before persistent document repository

**Decision:** Phase 1 stores document metadata and parsed text in a version-ignored local data directory. Docker Compose provisions PostgreSQL with pgvector, but document persistence is not coupled to it yet.

**Why:** Ingestion, source provenance, stable IDs, hashing, parsing, and cache behavior can be tested without database migrations or embedding infrastructure. This keeps the first runnable slice inexpensive and makes failures inspectable.

**Trade-off:** The filesystem manifest is not suitable for concurrent production workers. Phase 2 moves document/chunk metadata to PostgreSQL alongside pgvector.

## ADR-002: Content-addressed document identities

**Decision:** `document_id` is derived from a SHA-256 content hash (`doc_<first 16 hex>`). The full hash is preserved in metadata.

**Why:** Re-ingesting identical bytes is deterministic and does not repeat parsing or later LLM extraction.

**Trade-off:** A source URL can change while retaining the same content. Source URLs are preserved as provenance but are not identity.

## ADR-003: Start with NetworkX, keep graph behind a retrieval boundary

**Decision:** The initial graph implementation will use NetworkX and expose fixed retrieval functions rather than graph query strings.

**Why:** It demonstrates provenance-aware multi-hop retrieval without introducing a graph database before scale warrants it.

**Trade-off:** NetworkX is single-process and not a multi-user graph store. A Neo4j adapter can replace it later without changing route selection or answer generation contracts.

## ADR-004: Deterministic hashing vectors for the first retrieval baseline

**Decision:** Phase 2 uses a local feature-hashing embedder, persisted beside the document manifest, behind a vector-retrieval service boundary.

**Why:** It creates a free, reproducible, testable retrieval baseline without a model download, GPU requirement, database migration, or API spend. It also makes the later Graph RAG comparison honest: vector-only metrics start from a known baseline.

**Trade-off:** Feature hashing captures lexical overlap rather than semantic similarity, so it is not the production-quality embedding choice. Before publishing benchmark claims, the adapter will be switched to sentence-transformer embeddings and pgvector persistence; the API and evidence contracts will remain unchanged.

## ADR-005: Template-only graph retrieval

**Decision:** The graph retriever exposes named traversal templates and a deterministic query router instead of accepting generated graph-query language.

**Why:** Regulatory questions need predictable behavior and evidence provenance. Templates make the allowed traversal scope reviewable, testable, and measurable by question type.

**Trade-off:** Coverage grows incrementally as new templates are designed. Unsupported relationship questions return limited evidence rather than an unbounded graph search.

## ADR-006: Fail closed on invalid citations

**Decision:** Generated answers are validated against the exact retrieved chunk IDs. Invalid citations produce a verification-failure response rather than a best-effort answer.

**Why:** A regulatory assistant must not make its evidence trail look stronger than it is. This check is deterministic and independently testable.

**Trade-off:** A useful but incorrectly formatted model response is withheld. The model prompt and retry behavior can be improved later, but citation validity remains non-negotiable.

## ADR-007: Evaluate against authoritative source URLs

**Decision:** Evaluation cases define expected RBI source URLs and are scored only against the corpus actually ingested into the system.

**Why:** Stable chunk IDs are content-addressed and cannot be guessed before a source is ingested. URL-level expected evidence makes the dataset reviewable while preserving a hard link to authoritative material.

**Trade-off:** Scores are corpus-dependent. The harness must be rerun after changing documents, parsers, or chunking configuration.

## ADR-008: Persist aggregate model-cost events locally

**Decision:** Model token usage and estimated cost are written to a local, ignored event file and aggregated by the metrics endpoint.

**Why:** This gives a small local deployment auditable cost visibility without introducing paid observability infrastructure or exposing prompts in the UI.

**Trade-off:** The file is single-process development storage. A production deployment should emit the same event schema to a durable telemetry service.

## ADR-009: Deterministic monitoring before change interpretation

**Decision:** Phase 9 introduces a configurable RBI source registry and a monitoring history store. Source and document changes are detected with canonical URLs, metadata, and content hashes before any relevance or LLM interpretation step.

**Why:** Website availability, source changes, and regulatory meaning are separate concerns. Deterministic detection makes monitoring idempotent, auditable, and inexpensive; it also creates a concrete old/new evidence set for later interpretation.

**Trade-off:** The local JSON implementation is a development repository rather than a concurrent production database. Its versioned records intentionally mirror the later PostgreSQL schema: source checks, document versions, change reports, alerts, and evidence references.

## ADR-010: A rule is in force from its effective date, and future dates are quoted

**Decision:** A document is in force from its stated effective date, or from its issue date when it states none. Between a new rule's issue date and its effective date, current answers come from the rule in force today. The answer also quotes the new rule and states that it "takes effect from <date>". Trust in a successor is still decided by the brief's rule (official domain, later issue date, explicit link).

**Why:** RBI often issues rules months ahead of their effective date (Digital Lending Directions, 2025: issued 8 May 2025, effective 1 November 2025). Answering from the new rule early would describe an obligation that does not yet apply. Hiding the new rule would leave the analyst unprepared. Decided by Ashu on 21 October 2026.

**Trade-off:** Two dates per document must be extracted reliably. When the effective date cannot be parsed, the issue date is used and the answer says so.

## ADR-011: PostgreSQL with pgvector for documents, links and chunks

**Decision:** Documents, document links, chunks (with embeddings) and monitoring records move from whole-file JSON stores to PostgreSQL tables with the pgvector extension, in Phase 1. Production uses the existing Supabase database (`DATABASE_URL`). Local development and all evaluation runs use the existing Docker `pgvector/pgvector:pg16` service. BM25 keyword scores are computed in-process from chunk text, because PostgreSQL's full-text ranking is not BM25. Unit tests use an in-memory implementation of the same repository interface, so they run with no database. Evaluation runs only on PostgreSQL, and the manifest records the backend. Decided by Claude, delegated by Ashu on 21 October 2026.

**Why:** At 200–300 documents the JSON stores fail. Every write rewrites a whole file, every search reads one, and every POST copies whole files into Postgres. PostgreSQL is already in production and already in `docker-compose.yml`, so no new hosted service is added. Searching inside the database keeps the API's memory use low on Render. ADR-001 and ADR-004 had already planned this move.

**Alternatives rejected:** LanceDB needs a persistent disk plus pyarrow and would sit beside Supabase as a second store. SQLite with sqlite-vec would make evaluation run on a different engine from production. A hosted vector database is excluded by the brief. Keeping JSON does not scale.

**Trade-off and constraints:** The Supabase free tier is 500 MB, so production holds one chunker's vectors only, and chunker and embedding comparisons run locally. Embedding dimension is a config value. New dependency: the small `pgvector` Python adapter. Enabling the extension on the production database, and the cut-over (with a backup of the current snapshots and preserved approvals), each need Ashu's confirmation at the time.

## ADR-012: Scheduled status checks bracket when a change happened

**Decision:** The existing daily scheduled job (Vercel cron → `POST /monitor/run`) checks every corpus document, not only the 13 curated pages. It runs as a background job that returns immediately and records progress. Each check stores a status observation per document. When status changes, the record keeps the last check before the change and the first check after it. For changes before monitoring began, the replay uses only the dates RBI prints in the documents (issue, effective, and the repealing document's dates). Decided by Ashu on 21 October 2026.

**Why:** RBI does not publish when it applies a Withdrawn watermark. Regular checks are the only honest way to bound that time; a single date would be invented.

**Trade-off:** Timing precision equals the check interval (one day). Checking about 250 pages at a polite rate (at least 1 second apart) takes minutes, hence the background job.

## ADR-013: Corpus inclusion by a written rule, not a manual list review

**Decision:** Documents enter the corpus automatically when they meet all of the following:
1. Published on an RBI-owned domain.
2. One of these types: Master Direction, Directions, Amendment Directions, Master Circular, circular or notification, FAQ.
3. A lending topic match in the title or subject. The topic list in `config/corpus/inclusion.yaml` starts from the brief: NBFC scale-based regulation, KYC, digital lending, fair practices code, interest rate on advances, co-lending, credit information reporting, transfer of loan exposures, and the topics in `docs/rbi-lending-scope.md`.
4. Issued in roughly the last five years. Master Directions and Directions on a listed topic are included whatever their date.

Link closure then adds any document that an included document repeals, supersedes, amends or is replaced by, whatever its title says, so predecessors and successors are always present. Every inclusion and exclusion is written to a log with its reason. The same rule runs in the daily discovery, so new successors join without manual work. Decided by Ashu on 21 October 2026 (no manual list review).

**Why:** A written rule is repeatable, auditable and needs no one's time. Link closure covers the main weakness of keyword matching, which would otherwise miss a successor whose title does not mention lending.

**Trade-off:** Keyword rules can include marginal documents or miss related ones. Misses that matter for answers will show up as evaluation failures and in the exclusion log, and are fixed by changing the written rule, not by hand-picking documents.

## ADR-014: Superseded versions stay as history and never answer current questions

**Decision:** Three behaviours changed (found in the Phase 0 review).
1. Current-guidance search requires a chunk to be both operative and the latest version of its page (`is_current`). Before, a revised page's old and new versions were both eligible, because retirement set `is_current` but search only read the lifecycle.
2. Start-up cleanup no longer deletes retired versions. It removes only an older copy of the same page that was never retired, which is a leftover duplicate from earlier ingestion behaviour.
3. A reviewer cannot approve a document whose status is withdrawn, repealed or superseded; the API answers 409. Automation can remove trust, but only RBI's own evidence can restore the status (a later monitor check).

**Why:** Hard rule: history is kept, current answers use only the rule in force, and a person cannot override an official withdrawal. The old behaviour hid the first problem by deleting history at each restart.

**Trade-off:** Legacy duplicate rows that were retired by an earlier monitor run are now kept rather than cleaned up. Storage grows slightly; nothing is lost.
