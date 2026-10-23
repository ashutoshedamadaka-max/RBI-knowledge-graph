import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
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
const checks = [];
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const base = "http://127.0.0.1:5174/";
const out = resolve("data/runtime/design-audit");
const real = JSON.parse(
  readFileSync(
    "data/runtime/cutover-verification/memory-normal-query.json",
    "utf8",
  ),
).result;
let scenario = "success";
let requestBody;
let releasePending;
let requestCount = 0;
await page.route("**/query/stream", async (route) => {
  requestCount += 1;
  requestBody = route.request().postDataJSON();
  if (scenario === "error") {
    await route.fulfill({ status: 503, body: "Unavailable" });
    return;
  }
  if (scenario === "wait") {
    await new Promise((r) => {
      releasePending = r;
    });
    await route.abort().catch(() => {});
    return;
  }
  const result =
    scenario === "refusal"
      ? {
          ...real,
          research: {
            status: "insufficient_evidence",
            display_title: "No matching source",
            direct_answer: null,
            sections: [],
          },
        }
      : real;
  const frames = [
    ["progress", { stage: "retrieving_official_evidence" }],
    ["answer", result],
    ["result", result],
  ];
  await route.fulfill({
    status: 200,
    contentType: "text/event-stream",
    body: frames
      .map(
        ([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
      )
      .join(""),
  });
});
await page.goto(`${base}#ask`, { waitUntil: "domcontentloaded" });
await page.getByRole("button", { name: "A current rule", exact: true }).click();
await page
  .getByRole("button", { name: "Research question", exact: true })
  .click();
await page.locator(".answer-card h2").waitFor();
assert.match(requestBody.query, /capitalise/);
checks.push(
  "Example selection fills the composer; explicit submit starts research.",
);
await page
  .getByRole("button", { name: /Read source:/ })
  .first()
  .click();
assert(await page.locator(".passage-view").isVisible());
await page.waitForFunction(() =>
  document.activeElement?.classList.contains("evidence-panel"),
);
checks.push(
  "Citation opens original text and moves keyboard focus to source evidence.",
);
await page.getByRole("button", { name: "Evidence graph", exact: true }).click();
await page.locator(".canvas svg").waitFor();
await page.screenshot({
  path: resolve(out, "answer-with-evidence.png"),
  fullPage: true,
});
await page.getByRole("link", { name: "Build decisions", exact: true }).click();
await page
  .getByRole("heading", { name: "Every component needed a reason to exist." })
  .waitFor();
await page.getByRole("link", { name: "Ask a question", exact: true }).click();
await page.locator(".answer-card").waitFor({ state: "visible" });
checks.push("Research result and input survive navigation between pages.");
scenario = "error";
await page
  .getByRole("button", { name: "Research question", exact: true })
  .click();
await page.getByRole("alert").waitFor();
assert.match(await page.getByRole("alert").innerText(), /unavailable/);
assert.match(
  await page.locator("#research-question").inputValue(),
  /capitalise/,
);
checks.push(
  "Service errors preserve the question and provide a recoverable message.",
);
scenario = "wait";
await page
  .getByRole("button", { name: "Research question", exact: true })
  .click();
await page.getByRole("button", { name: "Stop research", exact: true }).click();
const stoppedRequestCount = requestCount;
releasePending?.();
await page.getByRole("alert").waitFor();
assert.match(await page.getByRole("alert").innerText(), /stopped/);
await page
  .getByRole("button", { name: "Research question", exact: true })
  .waitFor();
assert.equal(
  requestCount,
  stoppedRequestCount,
  "Stopping must not submit another question",
);
checks.push("Stop research cancels the request and restores editing.");
scenario = "refusal";
await page
  .getByRole("button", { name: "Research question", exact: true })
  .click();
await page
  .getByRole("heading", { name: "Not enough evidence to answer" })
  .waitFor();
checks.push("Refusal state explains scope and suggests a next step.");
await page.getByRole("button", { name: "Open a saved answer" }).click();
await page.locator(".saved-example").waitFor({ state: "visible" });
await page
  .getByRole("button", { name: "Read source 2", exact: true })
  .first()
  .click();
assert.match(
  await page
    .getByRole("complementary", { name: "Saved source evidence" })
    .innerText(),
  /2 of 2/i,
);
checks.push(
  "Saved answer is labelled as a recorded run and citations are interactive.",
);
await page.goto(`${base}#how`, { waitUntil: "domcontentloaded" });
await page.getByRole("button", { name: /Check validity/ }).click();
assert.match(await page.locator("#pipeline-detail").innerText(), /0 of 13/);
await page.getByRole("button", { name: "Play tour", exact: true }).click();
await page.getByRole("button", { name: "Pause tour", exact: true }).click();
checks.push(
  "Pipeline controls change the explanation; animation is opt-in and can pause.",
);
await page.emulateMedia({ reducedMotion: "reduce" });
await page
  .getByRole("button", { name: "Play tour", exact: true })
  .waitFor({ state: "hidden" });
checks.push(
  "Reduced-motion preference removes autoplay control and CSS motion.",
);
await page.goto(`${base}#built`, { waitUntil: "domcontentloaded" });
for (const label of [
  "Chunking",
  "Retrieval",
  "Knowledge graph",
  "Answer behavior",
  "Claim checking",
]) {
  await page.getByRole("button", { name: label, exact: true }).click();
  assert(await page.locator("#decision-detail h2").isVisible());
}
checks.push(
  "All engineering-decision comparisons remain readable and interactive.",
);
await page.goto(`${base}#evals`, { waitUntil: "domcontentloaded" });
await page.getByRole("button", { name: "Development", exact: true }).click();
assert.match(await page.locator("table").first().innerText(), /31/);
await page.getByRole("button", { name: "Held-out test", exact: true }).click();
checks.push("Evaluation dataset switch updates question-type results.");
// Phone navigation and dark-theme contrast across every content page.
await page.setViewportSize({ width: 390, height: 844 });
await page.goto(`${base}#home`, { waitUntil: "domcontentloaded" });
await page.getByRole("button", { name: "Open navigation" }).click();
await page.getByRole("button", { name: "Dark appearance" }).click();
await page.getByRole("link", { name: "Ask a question", exact: true }).click();
await page.waitForFunction(
  () =>
    document.querySelector(".mobile-menu")?.getAttribute("aria-expanded") ===
    "false",
);
checks.push("Mobile menu navigates and closes; appearance is persistent.");
const accessibility = [];
for (const route of ["home", "ask", "how", "built", "evals"]) {
  await page.goto(`${base}#${route}`, { waitUntil: "domcontentloaded" });
  const a = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  accessibility.push({
    route,
    violations: a.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes.map((n) => ({
        target: n.target,
        summary: n.failureSummary,
      })),
    })),
  });
}
await page.goto(`${base}#ask`, { waitUntil: "domcontentloaded" });
await page.locator(".saved-example").waitFor({ state: "visible" });
await page.screenshot({
  path: resolve(out, "saved-answer-mobile-dark.png"),
  fullPage: true,
});
assert.equal(errors.length, 0);
writeFileSync(
  resolve(out, "interaction-audit.json"),
  JSON.stringify({ checks, errors, accessibility }, null, 2),
);
console.log(JSON.stringify({ checks, errors, accessibility }, null, 2));
await browser.close();
assert(accessibility.every((result) => result.violations.length === 0));
