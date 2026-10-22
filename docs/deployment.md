# Deployment guide

The Python API runs on Render, the React/Vite application in `web/` runs on
Vercel, and Supabase stores durable runtime snapshots and PostgreSQL chunks.
The previous Vercel application lives in `frontend/` and remains available for rollback.

For the first deployment of the rebuilt application, follow
[the production cutover checklist](production-cutover.md). Pushing
`rebuild/phase-5` backs up code; merging to `main` is a separate deployment step.

## Backend on Render

The included `render.yaml` describes the Docker web service, its persistent disk
at `/service/data`, and the `/health` health check. Verify the existing service's
actual settings before changing them; the YAML does not provision Supabase,
transfer the corpus, or configure production secrets.

Set `DATA_DIR` to the prepared corpus directory on the persistent disk.
`DATABASE_URL` enables durable JSON snapshots; `VECTOR_BACKEND=postgres` also
enables the separate `chunks` table. These are two parts of the same migration.
The raw/processed documents, `graph/graph.json`, and embedding cache also need
to be transferred to the disk: they are not restored by the snapshot adapter.

Configure `OPENAI_API_KEY`, the paid `COHERE_API_KEY`, `ANSWER_PROVIDER=openai`,
and the other settings in the cutover checklist. Keep model keys in Render.
Set `CORS_ALLOWED_ORIGINS` to the exact Vercel production origin, with any
explicitly approved preview origins separated by commas.

## Frontend on Vercel

Use these settings for the rebuilt application:

| Setting | Value |
| --- | --- |
| Root Directory | `web` |
| Framework Preset | Vite |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Production Branch | `main` |
| `VITE_API_BASE_URL` | Public Render API origin, without a trailing slash |

The previous frontend's `API_BASE_URL` is not read by the new application.
`VITE_API_BASE_URL` is public configuration compiled into the browser bundle.
Vercel root-directory and environment changes apply to subsequent deployments:
see [build settings](https://vercel.com/docs/builds/configure-a-build) and
[environment variables](https://vercel.com/docs/environment-variables).

`web/vercel.json` and `web/api/monitor.js` preserve the previous application's
daily monitoring relay. Keep its existing server-side `CRON_SECRET`,
`BACKEND_MONITOR_URL`, and `BACKEND_MONITOR_SECRET` configured in Vercel.
The backend URL should target `/monitor/run`, and its secret must match
Render's `MONITOR_SECRET`. These variables must not have a `VITE_` prefix.

## Verification

Check the deployed revision via the `X-App-Revision` header on `/health`.
Check corpus counts via `/documents`, graph availability via `/graph/map`, and
saved evaluation results via `/quality`. A successful health probe alone does
not verify retrieval, model credentials, or corpus completeness. Use the query
trace to confirm embeddings, graph expansion, filtering, and Cohere reranking.
