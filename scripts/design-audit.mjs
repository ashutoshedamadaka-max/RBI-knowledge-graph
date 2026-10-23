// Browser audit against a local preview. Fixtures are public saved corpus/API data, not live model calls.
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
const require = createRequire(
  resolve("data/runtime/design-audit/package.json"),
);
const { chromium } = require("playwright");
const AxeBuilder = require("@axe-core/playwright").default;
const out = resolve("data/runtime/design-audit");
mkdirSync(out, { recursive: true });
const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  deviceScaleFactor: 1,
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const backend = "https://rbi-knowledge-graph-api.onrender.com";
const cache = new Map();
await page.route(
  /\/(graph\/map|graph\/node\/[^?]+|documents(?:\/[^?]+)?|document-links|monitoring-status|regulatory-updates)(?:\?.*)?$/,
  async (route) => {
    if (process.env.AUDIT_LIVE_API !== "1") {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: '{"detail":"Offline mode for snapshot fallback testing."}',
      });
      return;
    }
    const url = new URL(route.request().url());
    const path = url.pathname;
    try {
      if (!cache.has(path)) {
        const response = await fetch(`${backend}${path}`, {
          signal: AbortSignal.timeout(90000),
        });
        if (!response.ok) throw new Error(String(response.status));
        cache.set(path, await response.text());
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: cache.get(path),
      });
    } catch {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: '{"detail":"Audit could not load public source data."}',
      });
    }
  },
);
const summary = [];
for (const width of [1440, 390]) {
  await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
  for (const route of [
    "home",
    "ask",
    "how",
    "built",
    "evals",
    "sources",
    "graph",
  ]) {
    await page.goto(`http://127.0.0.1:5174/#${route}`, {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
    await page.waitForTimeout(1000);
    if (route === "sources")
      await page
        .getByRole("button", { name: /Reserve Bank/ })
        .first()
        .waitFor({ timeout: 95000 })
        .catch(() => {});
    if (route === "graph")
      await page
        .locator(".graph-stage")
        .waitFor({ timeout: 95000 })
        .catch(() => {});
    await page.screenshot({
      path: resolve(out, `${route}-${width}.png`),
      fullPage: true,
    });
    const overflow = await page.evaluate(() => ({
      viewport: innerWidth,
      scroll: document.documentElement.scrollWidth,
    }));
    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    summary.push({
      route,
      width,
      overflow,
      violations: axe.violations.map((v) => ({
        id: v.id,
        impact: v.impact,
        nodes: v.nodes.map((n) => ({
          target: n.target,
          summary: n.failureSummary,
        })),
      })),
    });
    console.log(
      `${route} at ${width}px: ${axe.violations.length} accessibility findings; width ${overflow.scroll}/${overflow.viewport}`,
    );
  }
}
writeFileSync(
  resolve(out, "visual-audit.json"),
  JSON.stringify({ errors, summary }, null, 2),
);
writeFileSync(
  resolve(out, "public-api.json"),
  JSON.stringify(Object.fromEntries(cache)),
);
console.log(JSON.stringify({ errors, summary }, null, 2));
await browser.close();
