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
- Python tests: 250 passed after schema isolation, the Supabase precision fix,
  and credential-handling regression tests.
  The `web/` TypeScript check and production build also passed.

## Production preflight after keys were added

- User confirmed Render workspace `tea-d6t4f76uk2gs738jn7a0` (My Workspace).
- API service: `srv-dahtchbm8hqs73dajd3g`, Singapore, Docker, branch `main`,
  automatic deploys enabled, health path `/health`.
- Service plan is **free**, with no persistent disk returned by Render.
  The original disk-based approach has been replaced by the image package below.
  Free services cannot attach disks and lose filesystem changes on restart:
  [Render free-service storage limitations](https://render.com/docs/free).
- The initial keys deployment `dep-dbd00ami0phs73878qag` used the old revision
  `2b819e921f44ca9f0f2f36771b78bd8dac29a31f`. The keys were followed by a manual
  deployment, rather than only being saved for the next deployment.
- Public `/health` confirms that revision and `/documents` confirms **13**
  documents. A copy of the public document response is saved under
  `data/runtime/cutover-backups/public-baseline/`; this is **not** a database backup.
- The production connection is saved only in ignored `data/runtime/production.env`.
  Supabase runs PostgreSQL 17.6. The active `public.rbi_runtime_state` contains
  13 documents and 92 vectors, with no `public.chunks` table.
- Application backup: `data/runtime/cutover-backups/20261022T125558Z/application-state.json.gz`.
  SHA-256: `d463be7b1bb2fdbf6d228276713cebb11ee090ae2106030b1579766bcdde202c`.
  All six snapshots were exported in one read-only transaction, checksum-verified,
  and restored exactly in a scratch database. This is an application-data backup,
  not a backup of the entire Supabase project.
- Two old source URLs also occur in the new corpus with different captured
  content; both remain withdrawn. The six old curated approvals cover sources
  outside the new NBFC corpus and remain preserved in the old schema/backup.
- The scratch rehearsal served 88 documents, 2,754 chunks, graph and quality
  endpoints through PostgreSQL, with no model calls. Old snapshots remained
  unchanged. Its report is under `data/runtime/cutover-rehearsal/`.
- Saving settings through the Render connector triggered deployment
  `dep-dbd0mqivcj2c7399jv80` of existing main, despite the REST API documentation
  saying updates do not deploy. It became live. Do not use that connector for
  settings-only saves when redeployment must be avoided.
- No browser is available through Computer Use, and the Opera connector requires
  reauthentication. The user confirmed Vercel build/environment settings saved
  without redeploying. Render secret values were not inspected.
- Supabase staging is committed in `rbi_corpus_v2`: 88 documents and 2,754
  chunks, with both fingerprints matching the release. Both tables have RLS
  enabled; public/anon/authenticated roles have no schema/table grants. The old
  13-document public snapshot and live API remain intact. The verification report
  is `data/runtime/cutover-rehearsal/supabase-staging-report.json`.

User selected **keep Render free and package the evaluated corpus with the app**.
`data/releases/corpus-v2.zip` contains 275 verified files (41,681,738 bytes).
SHA-256: `f199024c360f4bc8ddb2278c05fc475a798052916ccf7fc2b1b7fc78305f8836`.
The Docker build verifies it with `scripts/install_corpus_release.py` and seeds
`/service/data`, including the graph and embedding cache. Installation was
verified in an isolated local directory; five installer tests passed, and local
startup served 88 documents, 2,754 chunks, a populated map, and `/quality`.
`render.yaml` passes Render's current official JSON Schema; no live Blueprint
was applied. The CLI is unavailable. A Docker image build has not been run
locally because the daemon is not running. The image selects the isolated
database schema through `POSTGRES_SCHEMA=rbi_corpus_v2`.

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

- [x] Identify the production Render workspace/service and Vercel project.
  Confirm both deploy production from `main`; record their current deployment
  revisions, Vercel deployment URL, root/build settings, Render data directory,
  vector backend, disk mount, and environment variable names. Keep secret values
  in their existing secret stores.
- [x] In Render > service > Environment, add the keys yourself:
  `OPENAI_API_KEY` and the **paid production** `COHERE_API_KEY`.
  Choose **Save only**. This saves them for the next deploy without restarting
  the old service ([Render save options](https://render.com/docs/configure-environment-variables)).
- [x] Save the remaining Render values (connector accepted the merge update;
  the next rebuilt deployment verifies their behavior):

  | Variable | Intended value |
  | --- | --- |
  | `ANSWER_PROVIDER` | `openai` |
  | `OPENAI_ANSWER_MODEL` | `gpt-4o-mini` |
  | `OPENAI_EXTRACTION_MODEL` | `gpt-4o-mini` (claim checker) |
  | `EXTRACTION_PROVIDER` | `deterministic` |
  | `CHUNKER` | `structure` |
  | `VECTOR_BACKEND` | `postgres` after chunk migration |
  | `DATABASE_URL` | Existing production Supabase connection, verified privately |
  | `POSTGRES_SCHEMA` | `rbi_corpus_v2`; the old API continues using public |
  | `DATA_DIR` | `/service/data`, seeded from the verified image package |
  | `RERANK_CANDIDATES` | `30` |
  | `ABSTAIN_BELOW` | `0.34` |
  | `CORS_ALLOWED_ORIGINS` | Exact production frontend origin(s) |

  Keep the existing `ADMIN_API_KEY` and `MONITOR_SECRET`. Do not change the
  production database URL to the development URL in `.env`.
- [x] In Vercel > project > Settings > Build and Deployment, set Root Directory
  to `web`, Framework Preset to Vite, build to `npm run build`, and output to
  `dist`. The user confirmed saving without redeploying.
- [x] In Vercel Environment Variables, add `VITE_API_BASE_URL` with the public
  Render origin for Production. For a preview, use an explicitly chosen backend
  and approved CORS origin. Keep the existing monitoring relay's three variables
  listed in [deployment.md](deployment.md). Model API keys belong in Render.

## 3. Agent: back up, rehearse, and stage data

- [x] Inspect production tables and compare source versions/approvals.
- [x] Export, checksum and restore the application backup in a scratch database.
  Compare every restored payload. Keep it and the frozen release archive separate;
  neither contains previously lost ephemeral original files.
- [x] Freeze and verify the evaluated release without refetching live RBI pages.
- [x] Rehearse staging/startup against the actual backup. Test rollback on failure
  and verify old snapshots remain unchanged.
- [x] Run the staging script against Supabase:

  ```powershell
  .venv/Scripts/python.exe scripts/stage_corpus_cutover.py --database-env data/runtime/production.env --backup data/runtime/cutover-backups/20261022T125558Z/application-state.json.gz
  ```

  It creates `rbi_corpus_v2.rbi_runtime_state` and `rbi_corpus_v2.chunks` in one
  transaction, preserves production cost history, replaces five corpus snapshots,
  excludes stale repair backups, and loads 2,754 chunks. It refuses existing
  target schemas and never replaces public tables.
- [x] Verify every staged snapshot, chunk and embedding against the release.
  Supabase has `extra_float_digits=0`; binary PostgreSQL results preserve exact
  float8 values despite rounded text output. The first staging attempt detected
  this difference and rolled back completely before the fix.
- [x] Verify staged tables have RLS enabled and no schema/table grants to
  public/anonymous/authenticated API roles. The app connects as table owner.
  No pgvector extension is required.

The rebuilt API explicitly qualifies SQL identifiers using `POSTGRES_SCHEMA`.
The old API continues using public, so its cached snapshots cannot overwrite
staged data. No active-table rename or destructive swap is needed. Cost events
arriving after staging remain in public for later reconciliation.

## 4. Together: deploy the backend, then merge

The first branch deployment (`682fc10`) reached live and served the 88-document
corpus, but the paid smoke test failed: pasted provider keys contained trailing
newlines. Provider exception messages also exposed authorization headers in logs.
Both keys were revoked and replacements saved in Render without deploying.
Deploy the subsequent credential-handling fix before another paid smoke test.
It trims surrounding whitespace, rejects embedded whitespace, hides secrets in
settings diagnostics, and records only failure types and HTTP statuses. Old log
entries refer to revoked credentials; do not copy their contents into reports.

- [ ] Confirm staging, tested backup, saved Vercel settings, keys and the exact
  pushed branch SHA. Render must select `/service/data`, PostgreSQL,
  `rbi_corpus_v2`, OpenAI answers, and the approved models/chunker/reranking.
- [ ] In Render use **Manual Deploy > Deploy a specific commit** with that
  branch SHA. The connector cannot select an arbitrary commit, so use the
  Dashboard. The existing frontend stays available while the compatible rebuilt
  backend is checked.
- [ ] Monitor the deployment to `live`, then verify revision, corpus, graph,
  saved evaluation and the paid retrieval path below.
- [ ] After backend checks pass, fast-forward main to the reviewed branch and
  push it. Vercel can now build `web/` against the ready backend. A specific-commit
  Dashboard deploy disables Render auto-deploys: keep them disabled until main
  reaches this SHA, then restore **On Commit**.
- [ ] Check both production deployment records and the public frontend. Do not
  issue a duplicate manual deploy after an automatic deploy is triggered.

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

If a release gate fails, manually deploy the old revision
`2b819e921f44ca9f0f2f36771b78bd8dac29a31f`. That old code uses the retained public
snapshots with the original corpus. Restore Vercel's previous deployment and
settings (`frontend` root and previous API variable) if the new UI was published.
Keep auto-deploys disabled while diagnosing a failed release. Verify the old
corpus/query behavior before reopening traffic. If public data was independently
damaged, restore the tested backup under operator control. Keep both schemas
and artifacts for diagnosis; do not delete either corpus during rollback.
