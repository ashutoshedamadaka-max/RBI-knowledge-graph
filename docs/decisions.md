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

**Why:** RBI often issues rules months ahead of their effective date (for example the penal-charges circular: issued 18 August 2023, effective 1 January 2024). Answering from the new rule early would describe an obligation that does not yet apply. Hiding the new rule would leave the analyst unprepared. Decided by Ashu on 20 October 2026.

**Trade-off:** Two dates per document must be extracted reliably. When the effective date cannot be parsed, the issue date is used and the answer says so.

**Correction (21 October 2026):** this record first gave the Digital Lending Directions, 2025 as "effective 1 November 2025". That was wrong: they came into force immediately on issue (8 May 2025), except paragraphs 6 and 17. The parser had read a paragraph's date as the document's; it now reads only the document's commencement clause. Paragraph-level start dates are modelled from Phase 2, when paragraphs are separate units.

## ADR-011: PostgreSQL with pgvector for documents, links and chunks

**Decision:** Documents, document links, chunks (with embeddings) and monitoring records move from whole-file JSON stores to PostgreSQL tables with the pgvector extension, in Phase 1. Production uses the existing Supabase database (`DATABASE_URL`). Local development and all evaluation runs use the existing Docker `pgvector/pgvector:pg16` service. BM25 keyword scores are computed in-process from chunk text, because PostgreSQL's full-text ranking is not BM25. Unit tests use an in-memory implementation of the same repository interface, so they run with no database. Evaluation runs only on PostgreSQL, and the manifest records the backend. Decided by Claude, delegated by Ashu on 20 October 2026.

**Why:** At 200–300 documents the JSON stores fail. Every write rewrites a whole file, every search reads one, and every POST copies whole files into Postgres. PostgreSQL is already in production and already in `docker-compose.yml`, so no new hosted service is added. Searching inside the database keeps the API's memory use low on Render. ADR-001 and ADR-004 had already planned this move.

**Alternatives rejected:** LanceDB needs a persistent disk plus pyarrow and would sit beside Supabase as a second store. SQLite with sqlite-vec would make evaluation run on a different engine from production. A hosted vector database is excluded by the brief. Keeping JSON does not scale.

**Trade-off and constraints:** The Supabase free tier is 500 MB, so production holds one chunker's vectors only, and chunker and embedding comparisons run locally. Embedding dimension is a config value. New dependency: the small `pgvector` Python adapter. Enabling the extension on the production database, and the cut-over (with a backup of the current snapshots and preserved approvals), each need Ashu's confirmation at the time.

## ADR-012: Scheduled status checks bracket when a change happened

**Decision:** The existing daily scheduled job (Vercel cron → `POST /monitor/run`) checks every corpus document, not only the 13 curated pages. It runs as a background job that returns immediately and records progress. Each check stores a status observation per document. When status changes, the record keeps the last check before the change and the first check after it. For changes before monitoring began, the replay uses only the dates RBI prints in the documents (issue, effective, and the repealing document's dates). Decided by Ashu on 20 October 2026.

**Why:** RBI does not publish when it applies a Withdrawn watermark. Regular checks are the only honest way to bound that time; a single date would be invented.

**Trade-off:** Timing precision equals the check interval (one day). Checking about 250 pages at a polite rate (at least 1 second apart) takes minutes, hence the background job.

## ADR-013: Corpus inclusion by a written rule, not a manual list review

**Decision:** Documents enter the corpus automatically when they meet all of the following:
1. Published on an RBI-owned domain.
2. One of these types: Master Direction, Directions, Amendment Directions, Master Circular, circular or notification, FAQ.
3. A lending topic match in the title or subject. The topic list in `config/corpus/inclusion.yaml` starts from the brief: NBFC scale-based regulation, KYC, digital lending, fair practices code, interest rate on advances, co-lending, credit information reporting, transfer of loan exposures, and the topics in `docs/rbi-lending-scope.md`.
4. Issued in roughly the last five years. Master Directions and Directions on a listed topic are included whatever their date.

Link closure then adds any document that an included document repeals, supersedes, amends or is replaced by, whatever its title says, so predecessors and successors are always present. Every inclusion and exclusion is written to a log with its reason. The same rule runs in the daily discovery, so new successors join without manual work. Decided by Ashu on 20 October 2026 (no manual list review).

**Why:** A written rule is repeatable, auditable and needs no one's time. Link closure covers the main weakness of keyword matching, which would otherwise miss a successor whose title does not mention lending.

**Trade-off:** Keyword rules can include marginal documents or miss related ones. Misses that matter for answers will show up as evaluation failures and in the exclusion log, and are fixed by changing the written rule, not by hand-picking documents.

## ADR-014: Superseded versions stay as history and never answer current questions

**Decision:** Three behaviours changed (found in the Phase 0 review).
1. Current-guidance search requires a chunk to be both operative and the latest version of its page (`is_current`). Before, a revised page's old and new versions were both eligible, because retirement set `is_current` but search only read the lifecycle.
2. Start-up cleanup no longer deletes retired versions. It removes only an older copy of the same page that was never retired, which is a leftover duplicate from earlier ingestion behaviour.
3. A reviewer cannot approve a document whose status is withdrawn, repealed or superseded; the API answers 409. Automation can remove trust, but only RBI's own evidence can restore the status (a later monitor check).

**Why:** Hard rule: history is kept, current answers use only the rule in force, and a person cannot override an official withdrawal. The old behaviour hid the first problem by deleting history at each restart.

**Trade-off:** Legacy duplicate rows that were retired by an earlier monitor run are now kept rather than cleaned up. Storage grows slightly; nothing is lost.

## ADR-015: Rules carry an in-force window that search checks against today's date

**Decision:** Documents and chunks have `in_force_from` (the effective date, else the issue date) and `in_force_to` (set when a successor takes over, at the successor's effective date). Current-guidance search keeps a chunk only when today falls inside its window. The window is checked at query time, so a rule that takes effect or ends on a future date changes status without any job running.

**Why:** ADR-010 requires the old rule to keep answering until the new one takes effect. A yes/no "current" flag cannot express that. Regulatory time (the window) is kept apart from system time (`valid_from`/`valid_to`, when a version was ingested or retired).

**Trade-off:** A document with no parsed date has an open-ended window, as before. A later step adds an "as of" parameter and the upcoming-rule notice to answers.

## ADR-016: Successor trust rule and switch-over

**Decision:** After every monitoring run, each document's text is scanned for successor evidence (ADR in `app/monitoring/successors.py`), matched to the latest version of each corpus page by printed reference number (or exact title for amendments), and given a trust decision by one pure function (`app/monitoring/trust.py`). A link is auto-trusted only if all of these hold: an explicit whole-document repeal or supersession statement, quoted; both documents on an RBI-owned domain (exact host match); the new document issued strictly after the old one; exactly one corpus match; the new document not withdrawn; and automatic trust switched on (`AUTO_TRUST_ENABLED`). Anything else is stored for review with every failed condition listed. Amendments, partial repeals, Master Circular re-issues and title-similarity candidates always wait for review.

On a trusted link the successor becomes active, the old rule's `in_force_to` is set to the successor's in-force date (ADR-010, ADR-015), and on that day the old document becomes SUPERSEDED and leaves current answers while staying stored. The graph gets a SUPERSEDES edge carrying the quote. A reviewer can approve a suggestion (with an evidence URL and excerpt) or reject a link; rejection undoes the switch and leaves both documents for review, so it never adds trust. A status set by a reviewer or a trusted link survives routine checks; only a negative finding on the RBI page changes it.

**Why:** This is the brief's section 2 rule. Keeping the rule in one pure function makes every branch testable (23 cases) and auditable. Running the linker after each pass, idempotently, means documents can arrive in any order.

**Alternatives rejected:** Matching any cited circular number (would retire rules a document merely cites, as the Digital Lending Directions do for the KFS and penal-charges circulars). Trusting title similarity (no official evidence). Trusting a link whose target matches several corpus documents.

**Trade-off:** Links are stored in a JSON file for now (moves with ADR-011). The replay report (Phase 1 gate) measures auto-trust precision; below 100%, `AUTO_TRUST_ENABLED` goes off.

## ADR-017: Answers state what changed, with their own quoted evidence

**Decision:** `/query` takes an optional `as_of` date (default today) and answers only from rules in force on that day. Graph-found passages pass the same check as search results. Each answer may carry change notices, kept separate from its citations:
- **replaced:** the status filter removed a passage of a superseded document from the top results the answer would otherwise have used, and its successor is in force. The successor's best passages are added to the evidence. Text: "<Old> was repealed by <New>, issued <date>, in force from <date>; this is the current rule." with the link's RBI quote.
- **withdrawn:** the same, but no successor is known. "<Old> is withdrawn (detected <date>); no replacement was found in the indexed RBI corpus."
- **upcoming:** a trusted rule that takes effect later replaces a source of the answer, or ranks above every eligible passage. "<New>, issued <date>, takes effect from <date>. Until then, the rule in force is <Old>." with a quoted passage (ADR-010).

**Why:** The brief requires current answers never to cite a withdrawn passage and to say what replaced what; Ashu's D1 requires a future effective date to be quoted. A notice can quote a rule that is not yet in force, so it is never mixed into the fail-closed citations.

**Trade-off:** Notices are rank-based with no tuned threshold, so in a small corpus a weakly related withdrawn document can still trigger one; the replay and the Phase 3 trace measure this. The wording follows the plan's recommendation for D7, which Ashu has not confirmed and can change. Answers in the "historical" mode (an explicit history question) are unchanged until Phase 3 measures a replacement.

## ADR-018: Consolidated directions come from hand-downloaded PDFs; validity is tracked from RBI's HTML pages

**Context:** RBI's lending rules for NBFCs now sit in entity-wise consolidated directions ("Reserve Bank of India (Non-Banking Financial Companies – …) Directions, 2025"). Their text exists only as PDFs on rbidocs.rbi.org.in, which shows automated clients a CAPTCHA. We do not try to get around it.

**Decision:**
1. **Scope (amends ADR-013):** consolidated directions are included by entity and topic, per `config/corpus/inclusion.yaml`. The entity is Non-Banking Financial Companies, matching the brief's user; 16 of 40 NBFC directions match a lending topic as of 20 October 2026. Commercial Banks can be added with one line. HTML circulars and notifications for any entity remain automatic.
2. **Download:** `scripts/build_download_list.py` reads the index on www.rbi.org.in (no CAPTCHA), logs every include and exclude decision, and writes `data/source_pdfs/DOWNLOAD.md`. Ashu saves each PDF into `data/source_pdfs/` with its original file name. The PDFs are committed, since they are public RBI documents and the deployed service needs them.
3. **Validity tracking:** the daily check reads each direction's HTML page and the index. A Withdrawn watermark retires the rule automatically (already detected on Master Direction pages). A new PDF file name or "Updated as on" date means an in-place amendment: answers keep using the stored text with a visible "RBI updated this on <date>" warning, and the new PDF goes on the download list. A new index entry in scope goes on the list too. A page that disappears goes to review, not to withdrawn.

**Why:** It keeps every document official and every check automatic except the one step RBI reserves for people.

**Trade-off:** Switching to an updated or new PDF-only direction waits for a manual download. The replay report shows that delay separately from automatic detection.

## ADR-019: Local PostgreSQL without Docker; only the chunk index moves for now (amends ADR-011)

**Decision:** Development and evaluation use `pgserver` (Apache 2.0; bundles PostgreSQL 16.2 and pgvector 0.6.2), installed from `requirements-dev.txt` and never deployed. `scripts/dev_database.py` starts it with data in `data/runtime/postgres`. Approved by Ashu on 21 October 2026 after Docker Desktop could not start (firmware virtualization off, WSL missing).

Only the chunk index moves to PostgreSQL now (`VECTOR_BACKEND=postgres`, `DATABASE_URL`). `PostgresVectorStore` subclasses the file store and changes only how rows are read and written: one row per chunk, metadata as jsonb, the rung-0 hashing embedding as a float8 array. Search and scoring are inherited, so rankings are identical (tested on six search modes, plus an exact embedding round-trip). The document manifest, links and monitoring history stay in JSON files: they stay small at 300 documents.

**Why:** The chunk index is the store that breaks at scale (rewritten in full on every write). Moving only it is the smallest change that fixes that, and keeping rung-0 scores identical respects "one change at a time".

**Alternatives rejected:** Docker (cannot start on this machine without firmware changes). A second Supabase project (network latency, account setup; kept as fallback if pgserver stops being maintained). pgvector's float4 column for rung 0 (would shift scores in the sixth decimal and could reorder near-ties).

**Trade-off:** Search still scans every chunk (fine at about 10,000 chunks); the dense rungs in Phase 3 add a pgvector column and indexed search. pgserver ships an older pgvector than Supabase; evaluation manifests will record the version. The legacy extraction repair, which restores `vectors.json` on failure, is skipped with a log line when the backend is PostgreSQL.

## ADR-020: RBI's register of withdrawn circulars is automatic withdrawal evidence

**Decision:** Each scheduled run reads RBI's register of withdrawn circulars (`NotificationUserWithdrawnCircular.aspx`, HTML, no CAPTCHA): 9,458 circulars withdrawn by the Department of Regulation (including the 9,445 of the 28 November 2025 consolidation, RBI/2025-26/100) and 628 by the Department of Supervision, as of 21 October 2026. A corpus document whose printed number or RBI page address is listed becomes WITHDRAWN, quoting its register row. Documents already withdrawn, repealed or superseded keep their own evidence. Like a reviewer's approval, this status survives routine page checks that find no watermark; an unreachable register is reported in the run result, never treated as "no withdrawals".

**Why:** It is RBI's own list, so it is the strongest withdrawal evidence available, and automation may remove trust on official evidence. It also gives the replay an official answer key for withdrawal detection that does not come from our code.

**Limits:** The register says what was withdrawn, not what replaced it, so it creates no successor links. 3,312 rows carry a parseable number and 3,298 a page link; the rest use older numbering (all rows issued since 2021 parse). The older "RRA 2.0" table, which has no numbers, is not read.

## ADR-021: The question set is drafted by a model and verified by Ashu

**Decision:** Phase 2 questions are drafted by a language model from randomly sampled RBI paragraphs; the gold answer is the source paragraph (from the document, not from the system under test). Ashu accepts, edits or rejects each draft. Decided by Ashu on 21 October 2026, relaxing the brief's "Ashu writes the questions" to save several hours of writing.

**Why:** It keeps gold labels document-derived and human-checked while cutting Ashu's work to a quick review per question.

**Risks and controls:** Drafted questions tend to reuse the paragraph's words, which inflates retrieval scores; the prompt asks for an analyst's own phrasing, and every report states the average word overlap between question and gold paragraph. The drafting model never sees retrieval results. The report says the questions were model-drafted.

## ADR-022: Three chunkers behind one setting; legacy stays the default until measured

**Decision:** `CHUNKER` selects `legacy` (the original word windows, still the default), `fixed` (500 tokens, 50 overlap), `recursive` (headings, then lines, then sentences, up to 500 tokens) or `structure` (one chunk per RBI numbered paragraph with its heading path prepended, 100–600 tokens, tables kept whole when they fit and split with their caption repeated when they do not). Token counts use `tiktoken` cl100k_base (the tokenizer of text-embedding-3-small; MIT licence). Structure chunks carry `paragraph_ref`, `heading_path`, `token_count` and `parent_id` (the section, for passing the parent to the answer step). IDs are built from document, page and paragraph (or position), so re-chunking the same document gives the same IDs.

**Why:** One change at a time: the default changes only if the Phase 2 comparison on the dev questions says so.

**Measured on the 88-document corpus (21 October 2026):** fixed 1,977 chunks, recursive 2,583, structure 2,753 (median 282 tokens, none over 600, 134 under 100 where a section ends). Paragraph numbering is recovered in order on the NBFC directions (for example paragraphs 1–109 with no gaps in Responsible Business Conduct). Contents pages, with or without dot leaders, are kept out of the heading paths.

**Limits, stated rather than hidden:** Tables are detected from extracted text (one cell per line), not from layout: 569 tables found, about 1% of them prose lists that only look like tables. Footnotes are not yet separated and attached to their paragraph (they stay in the page text where they print). Paragraph-level effective dates (ADR-010) are not yet modelled.
