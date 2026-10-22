import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the FastAPI service runs on :8000; these paths are proxied to it.
const API_PATHS = ["/query", "/quality", "/graph", "/documents", "/document-links", "/monitoring-status",
  "/regulatory-updates", "/admin", "/health", "/search"];

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(API_PATHS.map((path) => [path, "http://127.0.0.1:8000"])),
  },
});
