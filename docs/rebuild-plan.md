# RBI Lending Intelligence — rebuild plan (Phase 0)

For: Ashu (product owner), as the Phase 0 gate review. Also the working reference for later phases.
Date: 20 October 2026 · Baseline: `main` at `2b819e9` · Scope: read-only review. No feature code has been written.

What I read: all of `app/`, `scripts/`, `config/`, `tests/`, `frontend/`, `docs/`, the three evaluation reports
and both question sets, and the stored isolated evaluation corpus in `data/runtime/review-evaluation-final/`
(13 documents' extracted text, manifest, vector index and graph). I ran the test suites against a scratch data directory.

---

## 1. Summary

1. **Withdrawal handling works; succession does not exist yet.** RBI's Withdrawn watermark and explicit withdrawal
   wording are detected, and withdrawn passages are kept out of current answers. Nothing links a new document to the
   one it replaces. Three further gaps in the same area (section 3, items 1–3) can let an old version stay
   "current" or let history be lost.
2. **The weak benchmark number is mostly a corpus problem, not a retrieval problem.** In the current report, 6 of the 7
   documents the questions are labelled with are now withdrawn by RBI and the 7th is awaiting review. The
   current-guidance filter therefore *correctly* removes every labelled source. The 5 passes out of 25 are exactly the
   5 "what changed" questions, which bypass the filter. The documents that replaced these rules are not in the corpus.
   This is the brief's section 2 problem, showing up in our own data.
3. **Forward links are recoverable from RBI text, but naive matching would be wrong.** The Digital Lending Directions,
   2025 contain "Annex III: List of circulars to be repealed", which extracts as a clean table (3 circulars, with
   numbers, dates and subjects). The same document also cites the Key Facts Statement circular and the penal-charges
   circular "as amended from time to time". It does *not* repeal those. A successor finder that matches any circular
   number would retire two live rules. Restricting matches to repeal sections is the main precision control.
4. **Backward links will be rare.** None of the five withdrawn notification pages I checked say what replaced them; the
   withdrawal is signalled only by the watermark image. Expect nearly all successor evidence to come from the new
   document.
5. **Plumbing comes before successor logic.** Issue dates are empty for all 13 documents, the monitor does not keep raw
   HyperText Markup Language (HTML) pages, every module reads the real system clock (so a replay cannot pretend to be
   in 2023), and the JSON-file stores will not hold 200–300 documents. Phase 1 starts by fixing these.
6. **Test baseline.** 65 Python tests pass. The 4 API test files do not load locally because Starlette 1.6.0 is
   installed next to FastAPI 0.115.6, which needs Starlette below 0.42. All 6 frontend behaviour tests pass. There is no
   continuous integration (CI), so nothing currently catches this.

---

## 2. Baseline, as verified

| Item | Today | Where it comes from |
|---|---|---|
| Corpus | 13 documents: 6 active, 6 withdrawn, 1 review required; 92 chunks | `data/evaluation/current-report.json` run manifest; stored evaluation corpus |
| Monitored sources | 16 = 3 RBI listing pages + 13 individual documents | `config/regulatory_sources.yaml` |
| How the 6 active documents became active | All 6 through `approved_lifecycle: ACTIVE` in the registry file, with a generic approval sentence rather than an RBI quote | `config/regulatory_sources.yaml` |
| Issue dates stored | 0 of 13 (`publication_date` empty); effective dates 2 of 13 | stored `documents.json` |
| Graph | 548 nodes, 1,425 edges: APPLIES_TO 730, REQUIRES 642, ISSUED_BY 53. **0** SUPERSEDES / AMENDS / REPLACES | stored `knowledge_graph.json` |
| Source retrieval | 5 of 25. Temporal-change 5/5; single-hop 0/5, two-hop 0/5, multi-hop 0/5, comparison 0/5 | `current-report.json` per-case results |
| Citation traceability | 22 of 22 answers with citations | same |
| Abstention (out of scope) | 5 of 5 | same |
| Routing | 23 of 30 | same |
| Report provenance | commit `6a23eac`, working tree dirty = true, deterministic answers (no model calls) | same |
| Python tests | 65 passed; 4 files fail to import (environment); 19 test files in total | local run |
| Frontend behaviour tests | 6 of 6 passed | `node --test tests/frontend-behavior.test.cjs` |

---

## 3. Where the brief and the code disagree

| # | The brief says or assumes | What the code actually does | Proposed handling |
|---|---|---|---|
| 1 | `mark_previous` retires an old document's chunks | It runs only when the **same URL** gets new content. It sets `is_current=False` / `valid_to`, but retrieval never reads either field. Current search filters on `authority_current`, which follows lifecycle only ([vector_store.py:62](../app/retrieval/vector_store.py#L62), [query_service.py:76](../app/retrieval/query_service.py#L76)). After an in-place revision, old and new versions are **both** eligible for current answers. | Phase 1: eligibility becomes an "in force on date X" check; regression test for in-place revisions |
| 2 | Old passages are kept for history | `cleanup_duplicate_sources()` runs at every start-up and deletes all older versions of a URL from the manifest, vectors and graph ([main.py:43](../app/main.py#L43), [ingestion/service.py:146](../app/ingestion/service.py#L146)). This also hides bug 1 after each restart. | Stop deleting; drop only byte-identical duplicates; record in `docs/decisions.md` |
| 3 | "A person cannot override an official withdrawal (existing behaviour — keep the test)" | The existing test only checks that an admin cannot *set* WITHDRAWN. Nothing stops an admin approving ACTIVE on a document RBI has watermarked as withdrawn ([manifest.py:89](../app/ingestion/manifest.py#L89) has no check; the endpoint accepts any document ID). The next monitor check puts WITHDRAWN back, so the override is temporary. | Add the guard and a test that attempts the override |
| 4 | Documents carry type, circular numbers, issue date, successor | `successor_document_id` and `document_type` exist on the model, but nothing writes them. The identifier pattern misses department-infixed numbers such as `RBI/FIDD/2025-26/196` and stores only one of the two numbers RBI prints on each circular. | Phase 1 header parser and identifier normaliser |
| 5 | The text search is "a hashing embedder — lexical" | The score is 0.55 × hashed-vector similarity + 0.45 × keyword overlap with a document-title boost ([vector_store.py:44-68](../app/retrieval/vector_store.py#L44-L68)). It is not BM25. | Keep it as "rung 0" for continuity; BM25 is a separate rung in Phase 3 |
| 6 | Source retrieval of 0.2 is the retrieval baseline | See summary point 2: it mostly measures the status filter removing withdrawn sources. | Freeze the 30-question set and its report as "legacy v1". Do not relabel it, and do not use it as a gate. |
| 7 | Evaluation data goes through the approval path (rule 6) | `publish_evaluation.py` does. `scripts/run_evaluation.py --bootstrap-curated` still ingests directly (the old bug path), and `tests/test_evaluation.py` tests that path. Another test checks `questions.json`, an older 39-question file with non-RBI URLs (`systemhealth.rbi.org.in/...html`), not the benchmark set. | Retire `run_evaluation.py`; keep one evaluation entry point; a test asserts that evaluation corpora are built only through the monitor |
| 8 | Phase 1 maps old paragraphs to new ones ("what changed") | Numbered paragraphs only exist once the structure-aware chunker lands in Phase 2 | Phase 1 links and retires documents. Paragraph mapping moves to the end of Phase 2. |
| 9 | Phase 1 reports a stale-answer rate | That needs current-guidance questions; the main question set is built in Phase 2 | A small replay question set (1–2 per replaced document), written by Ashu or templated from the old document's own headings. Kept separate from the 200 questions. |
| 10 | Trust and "in force" both follow the issue date | Penal charges: issued 18 August 2023, effective 1 January 2024. Between issue and effective date the old rule is arguably still in force. (Corrected 21 October 2026: this row first cited the Digital Lending Directions as effective 1 November 2025; they were in force on issue except two paragraphs.) | **Decision D1** (regulatory interpretation; I won't guess) |
| 11 | pgvector arrives in Phase 3 | At 200–300 documents the JSON stores break down. Each write rewrites the whole file, each search reads the whole file, and every POST copies whole files into Postgres. ADR-001/ADR-004 already planned PostgreSQL + pgvector, and `docker-compose.yml` already runs `pgvector/pgvector:pg16`. | Move storage in Phase 1 (**Decision D2**) |
| 12 | "RBI's own repeal lists are the answer key" | The successor finder reads those same lists. Scoring it against an automatic parse of them would grade the parser against itself (hard rule 2). | Gold links are verified by Ashu from the source annexes. The labelling helper shows the annex, never the system's guess. Include negative cases (references that are not repeals), amendments, and withdrawals with no successor. |
| 13 | Replay feeds changes "in the order they happened" | RBI pages show only their current state. The watermark has no date in the text (one test fixture's image name, `Withdrawn04122025.jpg`, looks like a date, but that is unconfirmed). | **Decision D3.** Replay is keyed on issue and effective dates. Watermarks stay hidden until their simulated time, so the future does not leak into the past. |
| 14 | The ontology has an Authority node, and every edge type needs a tested query | No listed edge type uses Authority (ISSUED_BY is not in the brief's list) | **Decision D10** |
| 15 | The graph is evidence | Today there is one Regulation node per *title* (two versions with the same title merge), Requirement nodes are raw sentences up to 300 characters, and every entity in a chunk is linked to every "must/shall" sentence. Precision has never been measured. | Replaced in Phase 4; until then no claim relies on graph edges |
| 16 | Time to switch over: within one daily check | A replay can measure this only in simulated check cycles. A live number needs real RBI changes after deployment. | Replay reports cycles; the live figure shows "not yet measured" until it is observed |
| 17 | Answers say "withdrawn on <date>" | We know the successor's issue and effective dates, and the date we *detected* the watermark. Neither is a withdrawal date that RBI states. | **Decision D7** |

---

## 4. Keep, change, add

### Keep

- Provenance-first ingestion and content-addressed document IDs (ADR-002).
- HTML extraction that selects the notification body and drops struck-out text ([parser.py](../app/ingestion/parser.py)).
- Lifecycle detection: only negative findings are automated ([lifecycle.py](../app/monitoring/lifecycle.py)). Also the
  rule that a curated approval never overrides a withdrawal ([monitoring/service.py:51-66](../app/monitoring/service.py#L51-L66)), with its tests.
- Fail-closed citation checking ([citations.py](../app/llm/citations.py)), strict-schema model output and truncation handling.
- Monitoring history: versions, de-duplicated update events, deterministic diff, alert de-dup.
- The run manifest in [publish_evaluation.py](../scripts/publish_evaluation.py) (extended, not replaced).
- Secrets from environment variables only, plus the admin and monitor secret checks.
- All existing tests. Where behaviour changes on purpose, the test is updated in the same commit and the reason goes in `docs/decisions.md`.

### Change (file by file)

| File | Change | Phase |
|---|---|---|
| `requirements.txt` | Pin Starlette (or rely on a project virtual environment) so the 4 API test files load; add only dependencies approved in section 8 | 1 |
| `app/models/documents.py` | Add `document_type`, `circular_numbers[]`, `issuing_department`, in-force interval, and a `DocumentLink` list (relation, evidence quote, evidence URL, method, trust decision, decided by/at). Replace the unused `successor_document_id`. Keep `publication_date` as the issue date. | 1 |
| `app/models/chunks.py` | Separate *regulatory time* (`in_force_from` / `in_force_to`) from *system time* (`observed_at`, `retired_at`). Today `valid_from` is the ingestion timestamp, not legal validity. | 1 |
| `app/monitoring/fetcher.py` | Save raw HTML with fetch time and hash; polite rate limit; better listing discovery | 1 |
| `app/monitoring/processor.py` | Ingest raw HTML, not `rbi_monitor_source.txt`; after ingestion, call the successor finder and trust rule | 1 |
| `app/monitoring/service.py`, `lifecycle.py` | Inject a clock instead of calling `datetime.now`; emit switch-over events; retire the old version on in-place revisions | 1 |
| `app/monitoring/metadata.py` | Becomes a full header parser: title, both circular numbers, issue date, department, addressees, document type, effective date | 1 |
| `app/ingestion/service.py`, `manifest.py` | Stop deleting history at start-up; guard approvals against official withdrawal; store and query links | 1 |
| `app/retrieval/vector_store.py`, `query_service.py` | Replace lifecycle-only filtering and the "historical intent" regex with an **as-of date** filter (default today). Change questions fetch predecessors through SUPERSEDES links and label them as historical. | 1 |
| `app/api/routes.py` | Review queue shows suggested links with evidence; one-click approve or reject link; approval guard; `as_of` on `/query` | 1 |
| `app/persistence/runtime_state.py` | Whole-file JSON snapshots replaced by tables for documents, links, chunks and monitoring (D2). Small files can stay as snapshots. | 1 |
| `config/regulatory_sources.yaml` | Keep listing sources here; move ~200–300 curated documents to `config/corpus/documents.yaml` after Ashu reviews the candidate list (D6). Re-review the 6 config-approved documents with real RBI quotes (D8). | 1 |
| `app/ingestion/chunking.py` | Becomes one of three chunkers behind one interface; chunk IDs become document + page + paragraph path | 2 |
| `app/evaluation/harness.py`, `models.py` | New case schema (7 question types, gold paragraph reference + quoted span, reference answer, split, as-of date); new metrics; the legacy v1 path kept intact | 2–3 |
| `app/retrieval/router.py`, `scope.py` | Router measured as a classifier; scope guard kept as the first refusal path | 3 |
| `app/graph/*`, `app/models/graph.py` | New ontology, pattern-first extraction, quoted-evidence LLM extraction, canonical entities, layout and communities | 4 |
| `app/llm/generation.py`, `app/models/research.py` | Atomic claims, per-claim citations, as-of date, status warnings, refusal reasons | 5 |
| `frontend/` | Replaced by a React + TypeScript app (Phase 6, after the Phase 5 numbers exist) | 6 |
| `README.md`, `docs/architecture.md` | Rewritten from saved runs only (`architecture.md` still says "36 labelled questions") | 7 |

### Add

| New file(s) | Purpose | Phase |
|---|---|---|
| `app/clock.py` | Injectable clock, so the replay can run "as of" a past date | 1 |
| `app/corpus/identifiers.py` | Parse and normalise `RBI/yyyy-yy/n` (with or without department infix) and department references such as `DOR.CRE.REC.66/21.07.001/2022-23`, including stray spaces (`DOR.CRE.REC .66/…`) and dates in `May 8, 2025` / `24.06.2020` form | 1 |
| `app/monitoring/successors.py` | Forward links (repeal-annex tables; "stand repealed", "superseded", "in supersession of" wording, scoped to repeal sections), backward links, and candidates (department + later date + similar title/content; never automatic) | 1 |
| `app/monitoring/trust.py` | The trust rule as a pure function, so every branch is unit tested | 1 |
| `app/monitoring/switchover.py` | Apply a confirmed switch: retire the old chunks, add a SUPERSEDES edge carrying the quote, record lifecycle evidence and the event | 1 |
| `app/replay/` + `scripts/run_replay.py` | Replay fetcher (serves stored snapshots at simulated times through the real monitor), gold timeline, metrics, report with manifest | 1 |
| `scripts/build_corpus_candidates.py`, `scripts/snapshot_sources.py` | Candidate list for Ashu's review; one-time raw HTML snapshots with fetch time and hash | 1 |
| `data/replay/gold_links.yaml`, `data/replay/questions.yaml` | Ashu-verified answer key and replay questions | 1 |
| `app/ingestion/structure.py`, `app/ingestion/chunkers/{fixed,recursive,structure}.py` | HTML structure (headings, numbered paragraphs, tables with captions, footnotes) and the three chunkers | 2 |
| `data/evaluation/v2/{template.yaml,dev.jsonl,test.jsonl}`, `scripts/label_questions.py` | Question template, labelling helper (shows documents, never system answers), fixed-seed stratified split | 2 |
| `app/retrieval/{bm25,dense,hybrid,rerank,abstain}.py`, `scripts/run_ladder.py` | Retrieval ladder, with an embedding cache keyed by model + text hash | 3 |
| `config/graph/entities.yaml`, `app/graph/layout.py` | Canonical entities with aliases; layout via NetworkX 3.4's built-in `forceatlas2_layout` and `louvain_communities` (no new dependency) | 4 |
| `app/llm/claim_checker.py`, `app/evaluation/stats.py` | Separate-call claim checker; 95% bootstrap intervals (standard library) | 5 |
| `.github/workflows/tests.yml` (if you agree) | Run pytest and the Node tests on every push | 1 |

### Retire

- `app/static/`: a legacy UI that is no longer served ([main.py](../app/main.py) serves `frontend/`).
- `scripts/run_evaluation.py` (the approval-bypassing bootstrap) and the test that exercises it.
- `data/evaluation/questions.json` (39 older questions) → `data/evaluation/legacy/`.
- `docs/phase-1-plan.md` … `phase-9-plan.md` → `docs/history/`, because their phase numbers clash with this plan's.

---

## 5. Phase plan

Each step is a small commit with tests green. Each phase works on its own branch (`rebuild/phase-N`) and stops at its gate.

### Phase 1 — corpus, change handling, replay

1. **1a Environment.** Project virtual environment, Starlette pin, CI (if agreed). Gate check: 4 API test files load and pass.
2. **1b Clock and raw HTML.** Inject a clock; store raw HTML; ingest HTML rather than extracted text.
3. **1c Metadata.** Header parser and identifier normaliser, tested on the 13 real documents already on disk.
4. **1d Storage** (after D2).
5. **1e Fixes** for section 3 items 1–3, each with a failing test written first.
6. **1f Successor finder** (rules below).
7. **1g Trust rule, switch-over, review queue** with one-click approve.
8. **1h Answer behaviour.** Current questions never cite a passage that is not in force. When a retired passage
   outranks eligible ones, answer from the successor and add a notice (wording per D7).
9. **1i Corpus expansion.** Rule-based inclusion (D6, ADR-013) → generated registry with logged reasons → snapshots → ingestion through the monitor.
10. **1j Replay harness.** Window of about 2–3 years back (D3); report and manifest.

**Successor evidence and trust decisions**

| What the evidence shows | Result |
|---|---|
| The new document repeals or supersedes the whole old one (repeal annex row or explicit sentence); RBI domain; new issue date later than old | **Auto-trust** (behind an `AUTO_TRUST_ENABLED` switch). Quote, URL and method stored. |
| The old page names the new one ("superseded by circular dated …"); same conditions | **Auto-trust** |
| Explicit but partial ("paragraph 5 of … stands repealed") | Review required, with the suggested link. Never retire the whole document. (D4) |
| Amendment ("The Amendment Directions modify the Directions as below") | AMENDS link. The base document stays in force; paragraph-level effects go to review. (D4) |
| Reference only ("as amended from time to time", "Please refer to") | REFERS_TO. Never a successor. |
| Yearly Master Circular re-issue ("Please refer to the Master Circular … dated April 2, 2024 … Attached is the revised Master Circular") | Review required (no repeal wording). Flagged for Ashu. |
| Candidate only (same department, later date, similar title/content) | Review required |
| One old document repealed by several new ones (for example, one per entity type) | Every link is recorded. The answer picks the successor by applicability, and says so. |
| Any trust condition fails | Review required |
| RBI later withdraws the new document | Trust is removed automatically, whatever any approval said |

**On a confirmed switch:** the old document's chunks get `in_force_to` and `retired_at`; the graph gets a SUPERSEDES
edge carrying the quote; a monitoring event records what replaced what; the old passages stay in storage for history
and "as of" questions.

**Phase 1 gate: replay report**, with manifest (git commit, dirty flag, corpus fingerprint, counts by status, replay
window, tick size, gold-file hash, the auto-trust setting). It reports withdrawal detection (recall, false alarms),
successor-link precision and recall **reported separately for auto-trusted and suggested links**, auto-trust precision
(if below 100%, auto-trust is switched off), stale-answer rate, time to switch over in check cycles, and the number of
review items created (Ashu's workload).

### Phase 2 — chunking and the question set

- Three chunkers behind one interface. Structure-aware chunks hold 100–600 tokens, have the heading path prepended,
  keep tables whole with captions and attach footnotes. RBI pages put footnotes at the end of the page, as seen in the
  Digital Lending text. Small chunks are retrieved; the parent section goes to the answer step. Token counts use a real
  tokenizer.
- **Gold labels are chunker-independent:** canonical URL + RBI paragraph reference + quoted span. Content-addressed
  document IDs change when a page changes, and fixed-size chunks have no paragraph numbers. A chunk "hits" when it
  contains the gold span. Boundary accuracy = share of gold spans contained whole in a single chunk.
- Question tooling: template, labelling helper, a fixed-seed stratified dev/test split (2:1) made before any run, the
  test split in its own file, and a ledger recording every run against the test split.
- Old→new paragraph mapping for replaced documents. Its precision is measured on a sample Ashu labels; until then it
  shows as "automatic match, not yet measured".
- Gate: chunker comparison on dev (boundary accuracy, recall@5 with the rung 0 retriever).

### Phase 3 — retrieval ladder

BM25 → dense (OpenAI `text-embedding-3-small`, plus one open model) → hybrid with reciprocal rank fusion (RRF) →
re-ranking over the top 30 (Cohere, plus one open cross-encoder) → graph expansion (after Phase 4). Plus the as-of
status filter, the router measured as a classifier, and an abstention threshold tuned on dev only, with its trade-off
curve. Each step changes exactly one thing; the runner refuses a comparison whose configs differ in more than one key.
Metrics per step and per question type: recall@5, recall@10, mean reciprocal rank (MRR), normalised discounted
cumulative gain (nDCG@10), latency p50/p95, cost per query. Gate: the ladder table.

### Phase 4 — knowledge graph

Map today's 11 entity types and 11 relation types onto the brief's 7 node types and 8 edge types. Document links come
from Phase 1; structure edges come from the chunker; cross-references use patterns. The large language model (LLM)
extracts only APPLIES_TO, REQUIRES and DEFINES, and any edge whose quote is not an exact substring of its source is
dropped. Entities resolve through `config/graph/entities.yaml`. Extraction failures are counted and shown on the Sources
screen. Ashu labels about 50 paragraphs to give precision and recall per edge type. Gate: extraction quality, plus a
graph on/off table. If the graph doesn't help, it leaves the default path and the README says so.

### Phase 5 — answers and hallucination control

Structured answers (atomic claims, citations per claim, as-of date, status warnings, refusal with reason). A claim
checker that is a separate model call, validated against about 50 claims Ashu labels. A failure policy (flag vs
regenerate once) chosen by measurement. A small model compared with a larger one. Every headline number gets a 95%
bootstrap interval and is broken down by question type. Gate: the full results table on the held-out test.

### Phase 6 — product

React + TypeScript, Sigma.js + graphology, layout precomputed on the server, styled to the design spec. The Vercel
build settings will change (a Vite project instead of the current static copy); I'll ask before changing them. The
`api/monitor.js` cron function stays.

### Phase 7 — write-up

The README is rebuilt from saved runs only, keeping the current honest framing.

---

## 6. How the hard rules are enforced in code

| Rule | Mechanism |
|---|---|
| 1 Never invent a metric | The product and README read numbers only from saved run files. A missing value renders "not yet measured". A test checks that the quality endpoint returns only values present in saved runs. |
| 2 Gold never comes from system output | Gold files are separate and hashed into every manifest. Labelling helpers never show system predictions. |
| 3 One change at a time | The comparison runner takes a base config plus exactly one override, and checks that question IDs, filters and corpus fingerprint match. |
| 4 Manifest on every run | Extends the existing manifest with: link counts by trust decision, model names, split, gold-file hashes and spend. |
| 6 Evaluation data uses the real path | Evaluation and replay corpora are built only through `RegulatoryMonitor`. A test fails if an evaluation script ingests directly. |
| Held-out test | Run ledger; the harness runs the test split only with an explicit `--final` flag, and records each run. |

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| RBI site blocks or rate-limits crawling, or page layouts differ by section (Master Direction pages may not use the `NotificationUser` container) | Polite rate (≥1 s between requests), one-time snapshots, extraction tests per page type, failures surfaced rather than skipped |
| Historical page state is unknowable (watermark timing) | Replay is labelled a simulation keyed on issue and effective dates (D3) |
| Answer key circularity | Ashu verifies gold links from the annexes; negative and amendment cases included |
| Regulatory semantics: effective dates, partial repeals, amendments, one-to-many successors | Decisions D1, D4 and D7; anything ambiguous goes to review, never to automatic trust |
| Storage capacity: Supabase free tier is 500 MB; three chunkers × 1,536-dimension vectors | Production keeps one chunker's vectors; comparisons run locally against the Docker Postgres; embedding size can be reduced (a config change, measured as one step) |
| Daily monitoring of ~250 pages outlasts the Vercel cron call | The endpoint returns immediately and runs checks as a background job, recording progress |
| Labelling load on Ashu: gold links, replay questions, ~200 questions, ~50 graph paragraphs, ~50 claims | Helpers that make each label a short decision; dev split labelled first |
| Small samples: about 67 held-out questions, so per-type intervals will be wide | Report the intervals; don't over-read differences inside them |
| Changing chunk IDs breaks existing production citations and links | Rebuild in an isolated data directory; planned cut-over with a backup of the current Supabase state; existing approvals preserved |
| Budget | Section 9 caps and a spend ledger |

---

## 8. Decisions needed from Ashu

### Decided (20 October 2026; recorded as ADR-010 to ADR-013 in `docs/decisions.md`)

| # | Decision | Outcome |
|---|---|---|
| D1 | Issue date vs effective date | **Ashu:** the answer must quote the future effective date. A rule is in force from its effective date, or from its issue date if none is stated. Between issue and effective date, the answer comes from the rule in force today. It also quotes the new rule and says it "takes effect from <date>". |
| D2 | Storage for 200–300 documents | **Decided by Claude (delegated):** PostgreSQL + pgvector. In production this runs on the existing Supabase database; locally and for evaluation it runs on the existing Docker `pgvector/pgvector:pg16` service. Moved into Phase 1. See ADR-011 for alternatives and constraints. |
| D3 | Unknown withdrawal timing | **Ashu:** check on a fixed schedule which documents are in force. Every corpus document is checked by the scheduled job, and the job records the last check before a status change and the first check after it, which brackets when the change happened. For past events the replay uses the dates RBI prints in the documents. |
| D2a | No Docker or Postgres on the development machine | **Ashu (20 October 2026):** install Docker Desktop and use the repo's pgvector container, so ADR-011 stands unchanged. |
| D9a | Answer key for successor links | **Ashu:** a short yes/no pass in a helper that shows each RBI repeal-list row beside the document it names, never the system's guess. |
| D6 | Corpus scope without a manual list review | **Ashu:** no list to review. Inclusion follows a written rule applied automatically (ADR-013). Every inclusion and exclusion is logged with its reason. |

### Still open (needed before the step named)

| # | Decision | Recommendation |
|---|---|---|
| D4 | Partial repeals and paragraph-level amendments | Never retire a whole document on a partial repeal. Record AMENDS links and send them to review. Retire individual paragraphs only on explicit "substituted" / "deleted" wording, from Phase 2. |
| D5 | Open models (bge embeddings and re-ranker) need PyTorch, a heavy dependency | Put them in an evaluation-only `requirements-eval.txt` that is never deployed. If not, compare OpenAI/Cohere only and record the skipped rung. |
| D7 | Wording when a rule was replaced | "<Old> was repealed by <New>, issued <date>, in force from <date>; this is the current rule." Use "Withdrawn (detected <date>)" only when no successor is known. |
| D8 | The 6 documents approved through the config file | Re-approve them through the review path with an RBI quote as evidence |
| D9 | Labelling you'll provide | Gold links, replay questions, ~200 questions with reference answers, ~50 graph paragraphs, ~50 claims |
| D10 | Authority node has no edge type | **Decided 22 October 2026: keep ISSUED_BY** (Document → issuing department), with a tested query |
| — | CI on GitHub Actions | Add it in Phase 1a |

---

## 9. Spend plan

These are caps I'm proposing, not cost estimates. Actual spend is recorded per run from API usage fields in a spend
ledger and included in manifests. Tests and the default mode make no paid calls.

| Phase | Cap (USD) |
|---|---|
| 1 | 0 (no model calls; rung 0 retrieval) |
| 2 | 1 |
| 3 | 5 |
| 4 | 6 |
| 5 | 6 |
| Reserve | 2 |
| **Total** | **20** |

A phase that reaches its cap stops and reports. It does not continue.

---

## 10. Next step

D1, D2, D3 and D6 are decided, so nothing in Phase 1 is blocked. On Ashu's go: Phase 1 step 1a (environment, then CI if agreed), then 1b onwards in order.
Enabling the pgvector extension on the production Supabase database and deploying are separate steps, and need Ashu's confirmation at the time.

---

## 11. Gate log

**Phase 1 — approved by Ashu on 21 October 2026.** Replay report `data/evaluation/replay-report.json` (commit `22f4c30`): withdrawal detection 72/72 with 0 false alarms; successor-link precision and recall 2/2; auto-trust precision 2/2 (auto-trust stays on); stale answers 0/142; switch-over within 0 days. Decisions at the gate:
- **Corpus scope stays NBFC-only** (88 documents, below the 200–300 target). README and portfolio copy must state this scope plainly.
- **The 47 inferred successor suggestions for the 2025 consolidation and labelling Part 3 are deferred.** Suggestion accuracy is reported as "not yet measured" until they are done.

**Found during Phase 2 (21 October 2026), for Phase 3:** the "as of" filter still requires a document's *current* status to be operative, so a withdrawn rule asked about at a past date when it was in force cannot be retrieved. The Phase 3 status-filter step must judge eligibility by the in-force window on that date (with the withdrawal date bracketed by the scheduled checks, ADR-012). The Phase 2 chunker comparison runs with the status filter off for every chunker, so it is unaffected.

**Phase 2 — approved by Ashu on 21 October 2026,** on the provisional chunker comparison (`data/evaluation/chunker-comparison-provisional.json`, commit `5cedfdc`): structure-aware chunking becomes the default (ADR-023). Deferred: a 30-question random review of the drafts (to measure their quality), and the full dev and test review before Phase 5.

**Phase 3 — gate open (not yet approved).** The ladder ran on the provisional dev questions (`data/evaluation/ladder-dev.json`, commit `b89613b`); the as-of fix is ADR-024. Still to do before the gate: router accuracy and the abstention threshold, and Ashu's 30-question review sample. **Phase 4 work started on 22 October 2026 at Ashu's instruction ("continue with phase 4") while the Phase 3 gate is open.** Phase 4's first commit (`b89613b`) is on `rebuild/phase-3`; later Phase 4 work is on `rebuild/phase-4`.

**Phase 3 and Phase 4 gate decisions — 22 October 2026.** Ashu accepted every recommendation (ADR-026, ADR-027). Label provenance: the 30-question review sample (30 kept; the 20 edits were drafted by Claude and checked by Ashu, tagged `edit_source`), and 50 graph paragraphs (23 by hand, 27 drafted by Claude and checked by Ashu, scored separately). Still open for Phase 4: measuring the APPLIES_TO filter on 20 fresh paragraphs (`data/evaluation/gold/graph-labels-fresh-to-fill.md`).

**Phase 3 — approved by Ashu on 22 October 2026** (ADR-026; ladder `data/evaluation/ladder-dev.json`, abstention and router `data/evaluation/abstention-dev.json`).

**Phase 4 — approved by Ashu on 22 October 2026** (ADR-027; quality `data/evaluation/graph-quality.json`, graph on/off `data/evaluation/ladder-graph-dev.json`). Optional follow-up: 20 fresh paragraphs to measure the APPLIES_TO filter. Until they are labelled, its fresh-label precision is reported as "not yet measured".
