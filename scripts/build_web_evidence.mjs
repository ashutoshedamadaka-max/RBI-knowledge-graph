// Public-only snapshot. No environment, credentials, or runtime files are read.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join, dirname } from "node:path";
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dir = join(root, "data/evaluation");
const read = (name) => JSON.parse(readFileSync(join(dir, name), "utf8"));
const sources = {
  answers_test: "answers-test-gpt-4o-mini.json",
  answers_dev: "answers-dev-gpt-4o-mini.json",
  answers_dev_first_prompt: "answers-dev-gpt-4o-mini-prompt1.json",
  ladder: "ladder-dev.json",
  graph_on_off: "ladder-graph-dev.json",
  abstention: "abstention-dev.json",
  graph_quality: "graph-quality.json",
  graph_build: "graph-build.json",
  claim_checker: "claim-checker-quality.json",
  replay: "replay-report.json",
  chunkers: "chunker-comparison-provisional.json",
};
const questions = ["dev", "test"].flatMap((split) =>
  readFileSync(join(dir, `v2/${split}.jsonl`), "utf8")
    .trim()
    .split("\n")
    .map(JSON.parse),
);
const byId = new Map(questions.map((q) => [q.id, q]));
const report = Object.fromEntries(
  Object.entries(sources).map(([key, file]) => {
    const { records, ...data } = read(file);
    if (records) {
      data.failures = records
        .filter(
          (r) =>
            r.error ||
            r.gold_cited?.some((v) => !v) ||
            (r.type === "unanswerable" && r.answered) ||
            r.claims?.some(
              (c) => !["supported", "not_checked"].includes(c.verdict),
            ),
        )
        .slice(0, 12)
        .map((r) => ({
          id: r.id,
          type: r.type,
          question: byId.get(r.id)?.question,
          reasons: [
            r.error
              ? "The question failed to run."
              : !r.answered && r.type !== "unanswerable"
                ? "Declined despite expected evidence."
                : r.gold_cited?.some((v) => !v)
                  ? "Missed an expected evidence sentence."
                  : r.type === "unanswerable"
                    ? "Answered a question labelled unanswerable."
                    : "The model checker flagged a claim.",
          ],
          flagged_claims: (r.claims ?? [])
            .filter((c) => !["supported", "not_checked"].includes(c.verdict))
            .slice(0, 2)
            .map((c) => ({ text: c.text, verdict: c.verdict })),
        }));
      const times = records
        .map((r) => r.latency_ms)
        .filter((v) => typeof v === "number")
        .sort((a, b) => a - b);
      data.latency_ms_p95 =
        times[Math.min(times.length - 1, Math.floor(times.length * 0.95))];
    }
    return [key, { status: "measured", file, data }];
  }),
);
const out = join(root, "web/src/data");
mkdirSync(out, { recursive: true });
writeFileSync(join(out, "quality.json"), JSON.stringify(report));
// The saved answer is unedited. It is a replay, never presented as a live run.
const record = read(sources.answers_test).records.find((r) => r.id === "q002");
writeFileSync(
  join(out, "example.json"),
  JSON.stringify({
    file: sources.answers_test,
    question: byId.get(record.id),
    record,
  }),
);
console.log("Wrote public evaluation summary and saved example.");
