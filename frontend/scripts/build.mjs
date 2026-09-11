import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const output = path.join(root, "dist");
const apiBaseUrl = (process.env.API_BASE_URL ?? "").trim().replace(/\/+$/, "");

if (!apiBaseUrl) {
  throw new Error("API_BASE_URL must be set before deploying the frontend.");
}

await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
await Promise.all([
  cp(path.join(root, "index.html"), path.join(output, "index.html")),
  cp(path.join(root, "assets"), path.join(output, "assets"), { recursive: true }),
]);
await writeFile(
  path.join(output, "api-config.js"),
  `window.RBI_API_BASE_URL = ${JSON.stringify(apiBaseUrl)};\n`,
);

const html = await readFile(path.join(output, "index.html"), "utf8");
if (!html.includes("api-config.js")) {
  throw new Error("The frontend entry page must load api-config.js.");
}
