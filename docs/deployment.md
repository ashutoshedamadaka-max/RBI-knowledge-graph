# Deployment guide

## Backend on Render

Create a Render **Web Service** from the GitHub repository using the included `render.yaml`. Select a Docker runtime and attach the configured persistent disk at `/service/data`. The service health-check URL is `/health`.

After the Vercel site has been created, set the Render environment variable `CORS_ALLOWED_ORIGINS` to the exact Vercel production URL, for example `https://rbi-knowledge-graph.vercel.app`. Add a comma-separated list only when more than one approved frontend domain is needed.

Keep API keys, if enabled, in Render environment variables. Do not put them in GitHub or in Vercel.

## Frontend on Vercel

Import the same repository into Vercel and set its **Root Directory** to `frontend`. Select framework **Other**. Vercel automatically runs `npm run build` and publishes `dist`.

Set `API_BASE_URL` to the public Render URL without a trailing slash, for example `https://rbi-knowledge-graph-api.onrender.com`. It is a public API address, not an API secret.

Each push to `main` will update both services. The backend preserves its runtime data through the attached Render disk; the frontend is rebuilt with the configured API address.
