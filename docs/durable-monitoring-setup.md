# Durable monitoring setup

## What this release adds

The hosted service can persist its manifest, chunk/vector index, provenance graph, monitoring history, and cost events in Postgres. When `DATABASE_URL` is configured, it restores that state at startup and stores the latest snapshot after every request. Local development still works without a database.

## Supabase

1. Create a free Supabase project.
2. In the project dashboard, open **Connect** and copy the Postgres connection string suitable for a persistent backend connection.
3. In Render, add `DATABASE_URL` with that connection string. Keep it secret.
4. Create long random values for `ADMIN_API_KEY` and `MONITOR_SECRET`, then add both to Render.
5. Redeploy Render. The first startup creates the `rbi_runtime_state` table automatically.

## Vercel daily monitor

In Vercel, add these private environment variables:

- `CRON_SECRET`: a long random value used only by Vercel to invoke the cron function.
- `BACKEND_MONITOR_URL`: `https://rbi-knowledge-graph-api.onrender.com/monitor/run`
- `BACKEND_MONITOR_SECRET`: the same value as Render's `MONITOR_SECRET`.

The checked-in `vercel.json` runs `/api/monitor` once each day at 03:00 UTC. Vercel Hobby scheduling is daily and may run at any time within that hour.

## Operational checks

- Confirm `GET /documents` still shows the seeded corpus after a Render restart.
- Confirm `POST /monitor/run` rejects requests without `X-Monitor-Secret`.
- In Vercel, inspect **Settings → Cron Jobs** after deployment.
- Add documents through `POST /ingest` only with `X-Admin-Key` after `ADMIN_API_KEY` is configured.
