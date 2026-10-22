export default async function handler(request, response) {
  if (request.headers.authorization !== `Bearer ${process.env.CRON_SECRET}`) {
    return response.status(401).json({ error: "Unauthorized" });
  }

  if (!process.env.BACKEND_MONITOR_URL || !process.env.BACKEND_MONITOR_SECRET) {
    return response.status(503).json({ error: "Monitoring is not configured" });
  }

  try {
    const upstream = await fetch(process.env.BACKEND_MONITOR_URL, {
      method: "POST",
      headers: { "X-Monitor-Secret": process.env.BACKEND_MONITOR_SECRET },
    });
    const body = await upstream.text();
    return response.status(upstream.status).send(body);
  } catch {
    return response.status(502).json({ error: "Backend monitoring service is unavailable" });
  }
}
