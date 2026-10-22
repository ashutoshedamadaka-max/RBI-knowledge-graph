# Production cutover: rebuild/phase-5

Prepared on 22 October 2026. Selected approach: push the branch first, prepare
the data and hosting settings, then merge to `main` together. Use a paid Cohere
production key. No database migration, hosting change, or merge is part of the
branch-backup step.

## Verified locally

- Handoff commit: `c94a2e5`. GitHub `main` at preparation:
  `2b819e921f44ca9f0f2f36771b78bd8dac29a31f`.
- `data/runtime/corpus-v2` and `data/runtime/serve-v2` each contain 88 documents,
  2,754 chunks, and a graph with 7,777 nodes and 10,424 edges.
- Corpus fingerprint (sorted `document_id:content_hash`, joined without a separator,
  SHA-256): `d9a245a5cf6cf011846c13de4585b4fa7aeca2179994747b898f19083a54da18`.
- Sorted chunk IDs, joined with a newline, SHA-256:
  `f16e1229fc17452ea871227c7e3f0ecdef87e0b014d4325f7b967acaa475fad1`.
- Graph SHA-256 recorded by the held-out evaluation:
  `b3c81dbda4c6f52b7ec5c90d9cca50a1b059c68675d40219a149ab77370a3cc9`.
- Python tests: 234 passed. `web/` TypeScript check and production build passed.

## Production preflight after keys were added

- User confirmed Render workspace `tea-d6t4f76uk2gs738jn7a0` (My Workspace).
- API service: `srv-dahtchbm8hqs73dajd3g`, Singapore, Docker, branch `main`,
  automatic deploys enabled, health path `/health`.
- Service plan is **free**, with no persistent disk returned by Render.
  The original disk-based approach has been replaced by the image package below.
  Free services cannot attach disks and lose filesystem changes on restart:
  [Render free-service storage limitations](https://render.com/docs/free).
- Deployment `dep-dbd00ami0phs73878qag` is live at the old revision
  `2b819e921f44ca9f0f2f36771b78bd8dac29a31f`. The keys were followed by a manual
  deployment, rather than only being saved for the next deployment.
- Public `/health` confirms that revision and `/documents` confirms **13**
  documents. A copy of the public document response is saved under
  `data/runtime/cutover-backups/public-baseline/`; this is **not** a database backup.
- No production database connection is available in the local environment.
  Put `DATABASE_URL=...` in the ignored `data/runtime/production.env` for the
  backup/migration operator; never commit or paste it into chat.
- No browser is available through Computer Use, and the Opera connector requires
  reauthentication. Vercel settings and Render secret values were not inspected.

User selected **keep Render free and package the evaluated corpus with the app**.
`data/releases/corpus-v2.zip` contains 275 verified files (41,681,738 bytes).
SHA-256: `f199024c360f4bc8ddb2278c05fc475a798052916ccf7fc2b1b7fc78305f8836`.
The Docker build verifies it with `scripts/install_corpus_release.py` and seeds
`/service/data`, including the graph and embedding cache. Installation was
verified in an isolated local directory; five installer tests passed, and local
startup served 88 documents, 2,754 chunks, a populated map, and `/quality`.
`render.yaml` passes Render's current official JSON Schema; no live Blueprint
was applied. The CLI is unavailable. A Docker image build has not been run
locally because the daemon is not running. The database backup remains pending.

## 1. Agent: back up code to GitHub

- [x] Scan every new historical blob, rather than only the current working tree,
  for credentials and private file paths. Report locations, never secret values.
- [x] Commit only the deployment documentation and monitoring relay carried into
  `web/`. Leave the four pre-existing untracked case-study/review files untouched.
- [x] Push only `rebuild/phase-5`, without force, and verify the remote commit:

  ```powershell
  git push --set-upstream origin rebuild/phase-5
  git ls-remote --heads origin main rebuild/phase-5
  ```

- [x] Confirm `main` still has its original revision. A branch push can create
  a Vercel preview; it does not change production when production tracks `main`.

## 2. User: prepare hosting settings without deploying

- [ ] Identify the production Render workspace/service and Vercel project.
  Confirm both deploy production from `main`; record their current deployment
  revisions, Vercel deployment URL, root/build settings, Render data directory,
  vector backend, disk mount, and environment variable names. Keep secret values
  in their existing secret stores.
- [ ] In Render > service > Environment, add the keys yourself:
  `OPENAI_API_KEY` and the **paid production** `COHERE_API_KEY`.
  Choose **Save only**. This saves them for the next deploy without restarting
  the old service ([Render save options](https://render.com/docs/configure-environment-variables)).
- [ ] Prepare the remaining Render values for that next deploy:

  | Variable | Intended value |
  | --- | --- |
  | `ANSWER_PROVIDER` | `openai` |
  | `OPENAI_ANSWER_MODEL` | `gpt-4o-mini` |
  | `OPENAI_EXTRACTION_MODEL` | `gpt-4o-mini` (claim checker) |
  | `EXTRACTION_PROVIDER` | `deterministic` |
  | `CHUNKER` | `structure` |
  | `VECTOR_BACKEND` | `postgres` after chunk migration |
  | `DATABASE_URL` | Existing production Supabase connection, verified privately |
  | `DATA_DIR` | `/service/data`, seeded from the verified image package |
  | `RERANK_CANDIDATES` | `30` |
  | `ABSTAIN_BELOW` | `0.34` |
  | `CORS_ALLOWED_ORIGINS` | Exact production frontend origin(s) |

  Keep the existing `ADMIN_API_KEY` and `MONITOR_SECRET`. Do not change the
  production database URL to the development URL in `.env`.
- [ ] In Vercel > project > Settings > Build and Deployment, set Root Directory
  to `web`, Framework Preset to Vite, install to `npm ci`, build to
  `npm run build`, and output to `dist`. Save without starting a deployment.
- [ ] In Vercel Environment Variables, add `VITE_API_BASE_URL` with the public
  Render origin for Production. For a preview, use an explicitly chosen backend
  and approved CORS origin. Keep the existing monitoring relay's three variables
  listed in [deployment.md](deployment.md). Model API keys belong in Render.

## 3. Agent: inspect, back up, and stage data

This is the next execution phase, not an operation already performed. Use a
production connection supplied through a local secret store or environment;
never paste it into chat or commit it. Inspect the actual schema before writing
a migration. The checked-in application uses `rbi_runtime_state` for snapshots
and `chunks` for the PostgreSQL chunk index; do not assume production already
has both tables.

- [ ] Read production snapshot keys and document count; inspect whether `chunks`
  exists and its schema. Compare production approvals with the candidate corpus.
  Preserve reviewer decisions for matching source versions; surface conflicts
  for review rather than promoting withdrawn/repealed material to active.
- [ ] Export a database backup to an ignored, private local directory. Configure
  libpq connection settings privately first, then use a client compatible with
  the production PostgreSQL version:

  ```powershell
  New-Item -ItemType Directory -Force data/runtime/cutover-backups
  pg_dump --format=custom --file=data/runtime/cutover-backups/pre-v2.dump
  pg_restore --list data/runtime/cutover-backups/pre-v2.dump
  ```

  A readable archive index is only the first check. Restore it into an isolated
  scratch database and verify the snapshot document count and any chunk rows
  before approving the swap. Never restore the test backup into production.
- [ ] Determine whether production has any unarchived original files. The free
  service has no SSH/shell or persistent disk; database snapshots do not contain
  original bytes. Preserve anything recoverable before restart. Keep the frozen
  corpus package and the database backup as separate recovery artifacts.
- [ ] Freeze the evaluated corpus from `data/runtime/corpus-v2`; do not rebuild
  it from live RBI pages during deployment. Verify the counts and fingerprints
  above, raw-file content hashes, chunk-to-document references, and graph hash.
- [x] Package `raw/`, `processed/`, `graph/graph.json`, corpus runtime manifests,
  and `runtime/embedding-cache/` with the app image. Verify the package and its
  extraction by SHA-256. No transfer to a nonexistent persistent disk is needed.
- [ ] Prepare staging snapshot and chunk tables in Supabase. Replace the corpus
  payloads (`documents.json`, `vectors.json`, `knowledge_graph.json`,
  `document_links.json`, `monitoring.json`) with the verified candidate. Preserve
  production `cost_events.json`; exclude evaluation cost history and stale
  `extraction_repair_backup.json` from the new state.
- [ ] Load exactly 2,754 rows into the staging chunk table, with the shape used
  by `PostgresVectorStore`: `chunk_id`, `document_id`, `chunk` JSONB, and
  `embedding` double precision array. These are the hashing embeddings from
  `vectors.json`; the OpenAI dense embedding cache is a separate disk asset.
  No pgvector extension is required by the current store.
- [ ] Validate staging counts, references, lifecycle/approval fields and
  fingerprints. Retain a filesystem snapshot of the same vectors for fallback.
  Test the transactional table swap and its reversal in the scratch database.

Do not write directly to the active tables while the old API runs. It retains
runtime files in memory/on disk and can sync stale state back to Supabase on
mutating requests or startup. Staging is preparation; the active migration
belongs in the maintenance window below.

## 4. Together: maintenance window, data swap, and merge

- [ ] Confirm the verified backup, staging results, keys, hosting settings, and
  exact branch commit. Agree to begin the production cutover.
- [ ] Pause the Vercel monitoring schedule and other ingestion/admin writers.
  Stop or suspend the old Render service and drain in-flight requests. Show a
  maintenance message if available. This procedure has a brief outage; it does
  not promise uninterrupted service across three independently deployed systems.
- [ ] Take a final backup after writers stop. Atomically switch both snapshot
  and chunk tables to the staged versions, retaining the old tables under
  versioned backup names. Verify 88 documents and 2,754 chunks before commit.
- [ ] Ensure the next Render deployment uses `DATA_DIR=/service/data`,
  `VECTOR_BACKEND=postgres`, and the saved keys. The old service must remain
  stopped until the new revision starts.
- [ ] Merge the reviewed branch into `main` and push `main` only now. Let the
  configured hosting integrations deploy that revision; if service suspension
  prevents deployment, resume it under operator control with the new revision.
- [ ] Check both deployment records. Record the actual merged SHA; a merge
  commit can differ from the branch head. Keep monitoring paused until verified.

## 5. Agent and user: verify, then reopen

- [ ] Render `/health` returns OK and `X-App-Revision` matches the deployed SHA.
- [ ] `/documents` returns 88 documents; SQL confirms 2,754 chunk rows.
- [ ] `/graph/map` has nodes/edges, and `/quality` reports the saved held-out run
  of 63 questions. Saved evaluation results do not prove live credentials work.
- [ ] After retrieval warm-up, make a small number of live smoke queries, with
  expected paid API usage. Check the trace includes `openai_embeddings`,
  `graph_cross_references`, `in_force_filter`, and `cohere_rerank`. Key presence
  alone is insufficient: the code falls back when a provider call fails.
- [ ] Test an ordinary answer with citations, a past-date query, a withdrawn-rule
  trap, and an unanswerable question. Check refusal behavior and the claim
  checker's verdicts. Do not rerun the held-out evaluation as a deployment test.
- [ ] Open Home, How this works, How I built this, Evals, Sources, and Knowledge
  graph on the production domain. Verify streaming, source links, browser CORS,
  and the intended API origin in network requests.
- [ ] Restore the monitoring schedule. Verify the authenticated `/api/monitor`
  relay and a subsequent scheduled run without exposing its secrets. Monitoring
  may legitimately change corpus counts after the initial deployment baseline.

## Rollback

If any gate fails, keep writers paused. Stop the new service, reverse the
snapshot/chunk table swap (or restore the tested backup), restore Render's
previous data-directory setting and environment, and redeploy its recorded old
revision. Restore Vercel's prior deployment and settings (`frontend` root and
the prior API variable). Verify the old corpus and query behavior before
reenabling monitoring. A code revert alone does not restore the data or hosting
settings. Keep the new tables and files for diagnosis; do not delete backups
until the cutover has been accepted.
