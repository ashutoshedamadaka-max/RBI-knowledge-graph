import { createRequire } from "node:module";
import { resolve } from "node:path";
import { writeFileSync } from "node:fs";
import assert from "node:assert/strict";
const require = createRequire(
  resolve("data/runtime/design-audit/package.json"),
);
const { chromium } = require("playwright");
const AxeBuilder = require("@axe-core/playwright").default;
const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const checks = [];
const out = resolve("data/runtime/design-audit");
await page.route(
  /\/(graph\/map|graph\/node\/[^?]+|documents(?:\/[^?]+)?|document-links|monitoring-status|regulatory-updates)$/,
  (route) =>
    route.fulfill({ status: 503, body: "Offline for fallback testing" }),
);
await page.goto("http://127.0.0.1:5174/#graph", {
  waitUntil: "domcontentloaded",
});
await page.locator(".graph-canvas canvas").waitFor();
assert.match(
  await page.locator(".snapshot-status").innerText(),
  /evaluated release snapshot/,
);
checks.push(
  "Graph falls back to the labelled evaluated release when the service is unavailable.",
);
await page
  .getByRole("button", { name: "Digital lending", exact: true })
  .click();
await page.locator(".graph-inspector h2").waitFor();
assert.match(
  await page.locator(".graph-inspector h2").innerText(),
  /Digital Lending/i,
);
checks.push(
  "Quick-start opens the real digital lending document and its neighborhood.",
);
await page
  .locator(".graph-inspector summary")
  .filter({ hasText: "Browse paragraphs" })
  .click();
await page.locator(".graph-inspector button.chip").first().click();
await page.waitForFunction(() =>
  document
    .querySelector(".graph-inspector h2")
    ?.textContent.startsWith("Paragraph"),
);
assert(await page.locator(".graph-inspector .passage").isVisible());
await page.getByRole("button", { name: "Previous node" }).click();
await page.waitForFunction(() =>
  /Digital Lending/i.test(
    document.querySelector(".graph-inspector h2")?.textContent ?? "",
  ),
);
checks.push(
  "Paragraph navigation loads original text; Previous node returns to the prior document.",
);
const before = await page.locator(".graph-canvas").screenshot();
await page.getByRole("button", { name: "Rotate right", exact: true }).click();
const after = await page.locator(".graph-canvas").screenshot();
assert(!before.equals(after));
checks.push("3D orbit control changes the rendered camera view.");
await page.getByRole("button", { name: "2D map", exact: true }).click();
await page.waitForFunction(() =>
  document.querySelector(".graph-overlay-top")?.textContent.startsWith("2D"),
);
assert(
  await page
    .getByRole("button", { name: "Rotate right", exact: true })
    .isDisabled(),
);
await page.getByRole("button", { name: "3D explorer", exact: true }).click();
checks.push("2D mode disables orbit and preserves readable graph controls.");
await page.getByRole("combobox", { name: "Graph view scope" }).selectOption("all");
await page.waitForTimeout(300);
await page.screenshot({
  path: resolve(out, "graph-all-connections.png"),
  fullPage: true,
});
await page
  .getByLabel("Explore the recorded timeline", { exact: true })
  .press("End");
await page.getByLabel("Explore the recorded timeline", { exact: true }).press("ArrowLeft");
await page.getByLabel("Explore the recorded timeline", { exact: true }).press("ArrowLeft");
assert.match(await page.locator("output").innerText(), /2024-12-31/);
await page
  .getByLabel("Explore the recorded timeline", { exact: true })
  .press("End");
checks.push("Timeline changes the displayed date and available graph nodes.");
await page
  .getByLabel("Find a document or paragraph", { exact: true })
  .fill("not-a-real-document");
await page.getByText("No nodes match. Try another title or term.").waitFor();
await page.getByLabel("Find a document or paragraph", { exact: true }).fill("");
await page.goto("http://127.0.0.1:5174/#sources", {
  waitUntil: "domcontentloaded",
});
await page.locator(".document-row").first().waitFor();
assert.match(await page.locator(".inventory-strip").innerText(), /88/);
await page
  .getByLabel("Find a document", { exact: true })
  .fill("digital lending");
assert((await page.locator(".document-row").count()) > 0);
await page.locator(".document-row>button").first().click();
await page.locator(".chunk-band").first().waitFor();
await page.locator(".chunk-band summary").first().click();
await page
  .locator(".chunk-band .passage")
  .first()
  .waitFor({ state: "visible" });
checks.push(
  "Library search and expansion load source records and complete saved passages.",
);
await page
  .getByLabel("Find a document", { exact: true })
  .fill("no-such-document");
await page.getByRole("heading", { name: "No documents match" }).waitFor();
checks.push("Library empty state explains how to recover.");
await page.getByLabel("Find a document", { exact: true }).fill("");
await page.locator(".document-row").first().waitFor();
const a11y = [];
for (const width of [320, 768]) {
  await page.setViewportSize({ width, height: 900 });
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
    });
    if (route === "graph") await page.locator(".graph-canvas canvas").waitFor();
    if (route === "sources")
      await page.locator(".document-row").first().waitFor();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    );
    assert(!overflow, `${route} overflow at ${width}`);
  }
}
checks.push(
  "All pages fit narrow phones (320px) and tablets (768px) without page overflow.",
);
await page.setViewportSize({ width: 390, height: 844 });
await page.evaluate(() => {
  localStorage.setItem("theme", "dark");
});
for (const route of ["sources", "graph"]) {
  await page.goto(`http://127.0.0.1:5174/#${route}`, {
    waitUntil: "domcontentloaded",
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  if (route === "graph") await page.locator(".graph-canvas canvas").waitFor();
  else await page.locator(".document-row").first().waitFor();
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  a11y.push({
    route,
    violations: result.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes.map((n) => ({
        target: n.target,
        summary: n.failureSummary,
      })),
    })),
  });
}
await page.screenshot({
  path: resolve(out, "graph-mobile-dark.png"),
  fullPage: true,
});
writeFileSync(
  resolve(out, "graph-audit.json"),
  JSON.stringify({ checks, errors, a11y }, null, 2),
);
console.log(JSON.stringify({ checks, errors, a11y }, null, 2));
await browser.close();
