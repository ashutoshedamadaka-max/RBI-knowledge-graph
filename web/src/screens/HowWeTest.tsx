import { ReactNode } from "react";
import { REPORT } from "../quality";
import { NextPage, PageIntro, SourceNote } from "../components/UI";
import Info from "../components/Info";
import examples from "../data/question-examples.json";
import "../how-we-test.css";

/* How we test: the evaluation programme, its results and its method, read from the saved runs.
   Compact by design: one row per metric, with a precise definition behind each "i". */

type Count = { k: number; n: number };
const fromRate = (rate: any): Count | null => (rate && rate.value != null ? { k: Math.round(rate.value * rate.n), n: rate.n } : null);
const fromRatio = (m: any): Count | null => (m ? { k: m.numerator, n: m.denominator } : null);
const pct = (c: Count | null) => (c && c.n ? `${Math.round((c.k / c.n) * 100)}%` : "—");
const of = (c: Count | null) => (c ? `${c.k}/${c.n}` : "—");
const range = (rate: any) => (rate?.low != null ? `${Math.round(rate.low * 100)}–${Math.round(rate.high * 100)}%` : "—");
const secs = (ms?: number) => (ms != null ? `${(ms / 1000).toFixed(1)} s` : "—");
const usd = (value?: number, digits = 4) => (value != null ? `$${value.toFixed(digits)}` : "—");

const TEST = REPORT.answers_test?.data ?? {};
const T = TEST.results ?? {};
const DEV = REPORT.answers_dev?.data ?? {};
const DEV_FIRST = REPORT.answers_dev_first_prompt?.data?.results ?? {};
const LADDER = REPORT.ladder?.data?.results ?? {};
const CHOSEN = LADDER["rerank-cohere"] ?? {};
const BEFORE_RERANK = LADDER["hybrid+as-of"] ?? {};
const ON_OFF = REPORT.graph_on_off?.data?.results ?? {};
const GRAPH_Q = REPORT.graph_quality?.data?.results ?? {};
const FRESH: any = Object.entries(GRAPH_Q).find(([key]) => key.startsWith("fresh"))?.[1];
const CHECKER: any = Object.values(REPORT.claim_checker?.data?.by_source ?? {})[0];
const CHUNKERS = REPORT.chunkers?.data?.results ?? {};
const REPLAY = REPORT.replay?.data ?? {};
const COST_CMP = DEV.model_cost_comparison;
const PER_Q = T.cost_usd?.per_question_answer_plus_rerank;

const northStar = fromRate(T.question_all_gold_cited);
const sentences = fromRate(T.gold_sentence_cited);
const withdrawn = fromRate(T.withdrawn_trap_cited_withdrawn);
const declined = fromRate(T.unanswerable_refused);
const wronglyRefused = fromRate(T.answerable_wrongly_refused);
const pastDate = fromRate(T.by_type?.change_over_time?.gold_sentence_cited);
const claims = T["claims_by_checker (not yet validated)"] ?? {};
const checkedClaims = (claims.supported ?? 0) + (claims.partially_supported ?? 0) + (claims.not_supported ?? 0);
const decisions = wronglyRefused && declined
  ? { k: wronglyRefused.n - wronglyRefused.k + declined.k, n: wronglyRefused.n + declined.n } : null;
const caught = fromRatio(CHECKER?.["unsupported_caught (recall)"]);

const RANGE_DEF = "95% bootstrap interval: the test questions were resampled 2,000 times and the score recomputed each time; 95% of those scores fall in this band. It reflects sample size, not labelling error.";

/* ---------- small building blocks ---------- */

function Section({ eyebrow, title, intro, children }: { eyebrow: string; title: string; intro?: ReactNode; children: ReactNode }) {
  return (
    <section className="hwt-section">
      <div className="hwt-section-head">
        <span className="eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        {intro && <p>{intro}</p>}
      </div>
      {children}
    </section>
  );
}

function MetricName({ name, term, def }: { name: string; term?: string; def: ReactNode }) {
  return (
    <span className="hwt-metric">
      <span>{name}</span>
      {term && <code>{term}</code>}
      <Info label={term ?? name}>{def}</Info>
    </span>
  );
}

/* ---------- sections ---------- */

function Headline() {
  const kpis = [
    { value: pct(northStar), label: "cited the right paragraph", def: "North-star. Share of answerable locked-test questions where every answer-key sentence appears inside a passage the answer cites." },
    { value: String(withdrawn?.k ?? "—"), label: "withdrawn rules quoted", def: "Guardrail, target zero (set before testing). Trick questions where any cited passage contains the withdrawn rule's sentence." },
    { value: pct(wronglyRefused), label: "fair questions refused", def: "Counter-metric. Answerable questions the system declined: the cost of being cautious." },
    { value: PER_Q ? `$${(PER_Q * 1000).toFixed(2)}` : "—", label: "per 1,000 questions", def: "Model-service charges per 1,000 questions at list prices: search embedding, re-ranking, answer generation and claim check. Hosting excluded." },
  ];
  return (
    <div className="hwt-headline">
      <p>
        On <strong>{TEST.questions}</strong> locked test questions it never saw during tuning, the product cited the right RBI
        paragraph in <strong>{of(northStar)}</strong> answerable questions, quoted <strong>no</strong> withdrawn rule, and wrongly
        refused <strong>{of(wronglyRefused)}</strong>.
      </p>
      <dl className="hwt-kpis">
        {kpis.map((kpi) => (
          <div key={kpi.label}>
            <dt>{kpi.label} <Info label={kpi.label}>{kpi.def}</Info></dt>
            <dd>{kpi.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Scorecard() {
  const rows = [
    { role: "North-star", name: "Right paragraph cited", term: "question-level citation recall", rate: T.question_all_gold_cited, value: of(northStar), target: "Baseline",
      def: "A locked-test question passes only if every sentence in its answer key appears inside at least one passage the answer cites. Measures grounding in the right evidence, not full legal correctness." },
    { role: "Guardrail", name: "Withdrawn rule quoted", term: "stale-rule rate", rate: T.withdrawn_trap_cited_withdrawn, value: of(withdrawn), target: "0 · met",
      def: "On trick questions about rules RBI has withdrawn, the share where any cited passage contains the withdrawn sentence. The only target set before testing: zero." },
    { role: "Guardrail", name: "Declines out-of-scope questions", term: "abstention recall", rate: T.unanswerable_refused, value: of(declined), target: "Baseline",
      def: "Share of questions the rulebook does not cover that received no grounded answer. Wide range: only a handful of such questions in the locked set." },
    { role: "Counter-metric", name: "Refuses a fair question", term: "false-refusal rate", rate: T.answerable_wrongly_refused, value: of(wronglyRefused), target: "Baseline",
      def: "Share of answerable questions the system declined. Balances the guardrail above: a system that refuses everything would pass it and fail here." },
  ];
  return (
    <Section eyebrow="Metric framework" title="One success metric, protected by guardrails."
      intro="The north-star defines success; guardrails stop it being gamed; the counter-metric stops caution from becoming uselessness. Locked test set.">
      <div className="hwt-table hwt-scorecard" role="table" aria-label="Scorecard">
        <div className="hwt-row hwt-head" role="row">
          <span role="columnheader">Role</span><span role="columnheader">Metric</span><span role="columnheader">Result</span>
          <span role="columnheader">Rate</span><span role="columnheader">95% range <Info label="95% range">{RANGE_DEF}</Info></span>
          <span role="columnheader">Target</span>
        </div>
        {rows.map((row) => (
          <div className={`hwt-row ${row.role === "North-star" ? "north" : ""}`} role="row" key={row.name}>
            <span role="cell"><span className={`hwt-role ${row.role === "North-star" ? "north" : ""}`}>{row.role}</span></span>
            <span role="cell"><MetricName name={row.name} term={row.term} def={row.def} /></span>
            <span role="cell" className="num">{row.value}</span>
            <span role="cell" className="num strong">{row.rate?.value != null ? `${Math.round(row.rate.value * 100)}%` : "—"}</span>
            <span role="cell" className="num muted">{range(row.rate)}</span>
            <span role="cell" className={row.target.includes("met") ? "hwt-met" : "muted"}>{row.target}</span>
          </div>
        ))}
      </div>
      <p className="hwt-note">Only the withdrawn-rule guardrail had a target before testing. The others are baselines for the next iteration, not targets chosen after seeing the results.</p>
    </Section>
  );
}

function HealthTable({ title, set, rows }: { title: string; set: string; rows: { name: string; term: string; value: string; detail: string; def: string }[] }) {
  return (
    <div className="hwt-health">
      <div className="hwt-health-head"><h3>{title}</h3><span>{set}</span></div>
      {rows.map((row) => (
        <div className="hwt-health-row" key={row.name}>
          <MetricName name={row.name} term={row.term} def={row.def} />
          <span className="num strong">{row.value}</span>
          <span className="hwt-detail">{row.detail}</span>
        </div>
      ))}
    </div>
  );
}

function SystemHealth() {
  return (
    <Section eyebrow="System health" title="How the model performs, stage by stage."
      intro="The vital signs an AI product team tracks: is the evidence found, is the answer grounded in it, how fast, at what cost, how reliably.">
      <div className="hwt-health-grid">
        <HealthTable title="Retrieval" set="Development · chosen pipeline" rows={[
          { name: "Evidence in top 5", term: "Recall@5", value: pct(fromRatio(CHOSEN["recall@5"])), detail: of(fromRatio(CHOSEN["recall@5"])),
            def: "Share of answer-key sentences found in the 5 passages handed to the answer model. Computed per answer-key sentence (n = 105)." },
          { name: "Evidence in top 10", term: "Recall@10", value: pct(fromRatio(CHOSEN["recall@10"])), detail: of(fromRatio(CHOSEN["recall@10"])),
            def: "As Recall@5, over the top 10 passages: what a wider retrieval window would add." },
          { name: "Rank of first hit", term: "MRR", value: CHOSEN.mrr != null ? CHOSEN.mrr.toFixed(2) : "—", detail: "1.00 = always first",
            def: "Mean reciprocal rank: the average of 1/rank of the first passage containing the answer-key sentence, scoring 0 when it is not retrieved." },
          { name: "Ranking quality", term: "nDCG@10", value: CHOSEN["ndcg@10"] != null ? CHOSEN["ndcg@10"].toFixed(2) : "—", detail: "1.00 = perfect order",
            def: "Normalised discounted cumulative gain over the top 10: relevant passages count for more the higher they rank, normalised so an ideal order scores 1.0." },
        ]} />
        <HealthTable title="Answer quality" set="Locked test" rows={[
          { name: "Evidence cited", term: "citation recall", value: pct(sentences), detail: of(sentences) + " sentences",
            def: "Share of answer-key sentences contained in at least one passage the answer cites. Evidence coverage, not a judgement of correctness." },
          { name: "Grounded sentences", term: "groundedness", value: checkedClaims ? `${Math.round(((claims.supported ?? 0) / checkedClaims) * 100)}%` : "—",
            detail: `${claims.supported ?? "—"}/${checkedClaims} checked`,
            def: `Share of answer sentences that an independent model call, reading only the sentence and its cited passages, judged fully supported. The checker caught ${of(caught)} weak sentences in validation, so treat this as an upper bound.` },
          { name: "Answer-or-decline", term: "decision accuracy", value: pct(decisions), detail: of(decisions),
            def: "Correct decisions over answerable and out-of-scope questions together: answerable questions answered, plus out-of-scope questions declined." },
          { name: "Withdrawn rules quoted", term: "stale-rule rate", value: String(withdrawn?.k ?? "—"), detail: of(withdrawn) + " traps",
            def: "Trap questions where a cited passage contains a withdrawn rule's sentence. Target zero." },
        ]} />
        <HealthTable title="Latency" set="Locked test · trial re-ranking key" rows={[
          { name: "Typical question", term: "p50", value: secs(T.latency_ms_p50), detail: "end to end",
            def: "Median wall-clock time from question to the final, claim-checked answer, per question in the locked test run." },
          { name: "Slow questions", term: "p95", value: secs(TEST.latency_ms_p95), detail: "end to end",
            def: "95th percentile: 19 in 20 questions finished within this time. Inflated by the free re-ranking key's rate limit." },
          { name: "Retrieval", term: "p50 / p95", value: `${secs(BEFORE_RERANK.latency_ms?.p50)} / ${secs(BEFORE_RERANK.latency_ms?.p95)}`, detail: "before re-ranking",
            def: "Search stages only (keyword, meaning, cross-references, date filter), development set." },
          { name: "Retrieval + re-rank", term: "p50 / p95", value: `${secs(CHOSEN.latency_ms?.p50)} / ${secs(CHOSEN.latency_ms?.p95)}`, detail: "trial-key waits",
            def: "Search including Cohere re-ranking. The wide p95 is rate-limit waiting on the free trial key; a paid key removes it." },
        ]} />
        <HealthTable title="Cost" set="List prices · hosting excluded" rows={[
          { name: "Per question", term: "cost/query", value: usd(PER_Q), detail: "all model services",
            def: "Search embedding, re-ranking, answer generation and claim check, from reported usage at list prices (gpt-4o-mini $0.15 / $0.60 per million tokens; Cohere $2 per 1,000 searches)." },
          { name: "Per 1,000 questions", term: "unit cost", value: PER_Q ? `$${(PER_Q * 1000).toFixed(2)}` : "—", detail: "budget figure",
            def: "Cost per question × 1,000." },
          { name: "Re-ranking share", term: "rerank/query", value: usd(CHOSEN.cost_per_query_usd), detail: "largest component",
            def: "Cohere re-ranking of 30 candidates, one search unit per question at the paid list price." },
          { name: "Answer model", term: "mini vs 4o", value: COST_CMP ? `${usd(COST_CMP.per_question?.["gpt-4o-mini"])} / ${usd(COST_CMP.per_question?.["gpt-4o (projected)"])}` : "—",
            detail: "per question", def: "GPT-4o mini measured; GPT-4o projected from the same tokens at its list price. The larger model was costed, not run." },
        ]} />
        <HealthTable title="Reliability" set="Locked test · replay" rows={[
          { name: "Failed runs", term: "error rate", value: `${(TEST.failed_questions ?? []).length}/${TEST.questions ?? "—"}`, detail: "errors or timeouts",
            def: "Questions that errored, timed out or crashed during the locked test run." },
          { name: "Degraded runs", term: "fallbacks", value: `${(TEST.questions_without_rerank ?? []).length}/${TEST.questions ?? "—"}`, detail: "skipped re-ranking",
            def: "Questions where a pipeline stage fell back (for example re-ranking unavailable), which would also disable the refusal rule." },
          { name: "Withdrawals detected", term: "change recall", value: of(fromRatio(REPLAY.withdrawal_detection?.recall)), detail: `${REPLAY.withdrawal_detection?.false_alarms ?? "—"} false alarms`,
            def: "Replay of real RBI history: share of withdrawn documents the monitor flagged; false alarms counted on the documents still in force." },
        ]} />
      </div>
      <SourceNote file="answers-test-gpt-4o-mini.json">Locked test run</SourceNote>
      <SourceNote file="ladder-dev.json">Retrieval experiments</SourceNote>
    </Section>
  );
}

interface Experiment { area: string; hypothesis: string; measure: string; lower?: boolean; before: [string, Count | null]; after: [string, Count | null]; decision: "Adopted" | "Limited"; note: string }

const EXPERIMENTS: Experiment[] = [
  { area: "Document splitting", hypothesis: "Cutting along RBI's numbered paragraphs keeps each rule whole.", measure: "answer-key sentences kept in one piece",
    before: ["Fixed-size", fromRatio(CHUNKERS.fixed?.boundary_accuracy)], after: ["Paragraphs", fromRatio(CHUNKERS.structure?.boundary_accuracy)], decision: "Adopted",
    note: "Also gives every citation a paragraph number." },
  { area: "Search", hypothesis: "Exact words and meaning miss different things; combined they find more.", measure: "Recall@5",
    before: ["Keyword", fromRatio(LADDER.bm25?.["recall@5"])], after: ["Combined", fromRatio(LADDER.hybrid?.["recall@5"])], decision: "Adopted",
    note: "Largest single retrieval gain." },
  { area: "Date filter", hypothesis: "Filtering by in-force dates stops withdrawn rules reaching the answer.", measure: "traps with a withdrawn rule in top 5", lower: true,
    before: ["No filter", fromRatio(LADDER.hybrid?.["withdrawn_trap_leak@5"])], after: ["Filtered", fromRatio(LADDER["hybrid+as-of"]?.["withdrawn_trap_leak@5"])], decision: "Adopted",
    note: `Recall@5 also rose to ${of(fromRatio(LADDER["hybrid+as-of"]?.["recall@5"]))}.` },
  { area: "Re-ranking", hypothesis: "A specialist re-ranker puts the answering paragraph first.", measure: "Recall@5",
    before: ["Before", fromRatio(LADDER["hybrid+as-of"]?.["recall@5"])], after: ["Cohere", fromRatio(CHOSEN["recall@5"])], decision: "Adopted",
    note: `Local alternative: ${of(fromRatio(LADDER["rerank-bge"]?.["recall@5"]))} at ~${Math.round((LADDER["rerank-bge"]?.latency_ms?.p50 ?? 0) / 1000)} s per query; rejected.` },
  { area: "Knowledge graph", hypothesis: "Following cross-references helps questions that need two paragraphs.", measure: "linked-evidence Recall@5",
    before: ["Without", fromRatio(ON_OFF["hybrid+as-of"]?.by_type?.multi_hop?.["recall@5"])], after: ["With graph", fromRatio(ON_OFF.graph?.by_type?.multi_hop?.["recall@5"])], decision: "Limited",
    note: `Cross-references only; 'applies to' links were right ${of(fromRatio(FRESH?.APPLIES_TO?.precision))} on fresh labels, so they never touch answers.` },
  { area: "Answer instructions", hypothesis: "Refusals came from labelling past-date evidence with today's 'withdrawn' status.", measure: "answerable questions refused", lower: true,
    before: ["First prompt", fromRate(DEV_FIRST.answerable_wrongly_refused)], after: ["Fixed", fromRate(DEV.results?.answerable_wrongly_refused)], decision: "Adopted",
    note: `Accepted trade-off: out-of-scope declines fell ${of(fromRate(DEV_FIRST.unanswerable_refused))} → ${of(fromRate(DEV.results?.unanswerable_refused))}.` },
  { area: "Claim checking", hypothesis: "An independent check can catch sentences their source does not support.", measure: "weak sentences caught",
    before: ["Weak", caught ? { k: caught.n, n: caught.n } : null], after: ["Caught", caught], decision: "Limited",
    note: "Too weak to rewrite answers; it flags sentences for the reader instead." },
];

function MiniBars({ e }: { e: Experiment }) {
  return (
    <span className="hwt-mini">
      {[e.before, e.after].map(([label, value], index) => (
        <span className={`hwt-mini-row ${index ? "after" : ""}`} key={label}>
          <span className="hwt-mini-label">{label}</span>
          <span className="hwt-mini-track"><span className={e.lower ? "bad" : ""} style={{ width: `${value && value.n ? (value.k / value.n) * 100 : 0}%` }} /></span>
          <span className="num">{of(value)}</span>
        </span>
      ))}
    </span>
  );
}

function Experiments() {
  return (
    <Section eyebrow="Experiment log" title="Every design choice was a measured bet."
      intro="Each experiment changed one thing on the development questions and was kept or limited on the evidence. The locked test ran once, at the end.">
      <div className="hwt-table hwt-experiments" role="table" aria-label="Experiment log">
        <div className="hwt-row hwt-head" role="row">
          <span role="columnheader">Area and hypothesis</span><span role="columnheader">Before → after</span><span role="columnheader">Decision</span>
        </div>
        {EXPERIMENTS.map((e) => (
          <div className="hwt-row" role="row" key={e.area}>
            <span role="cell"><strong>{e.area}</strong><span className="hwt-detail">{e.hypothesis}</span></span>
            <span role="cell"><MiniBars e={e} /><span className="hwt-detail">{e.measure}{e.lower ? " · lower is better" : ""}</span></span>
            <span role="cell"><span className={`hwt-decision ${e.decision === "Adopted" ? "adopted" : "limited"}`}>{e.decision}</span><span className="hwt-detail">{e.note}</span></span>
          </div>
        ))}
      </div>
      {COST_CMP && (
        <p className="hwt-note">
          <strong>Model choice:</strong> the larger answer model was costed, not run. Same development work: GPT-4o mini
          ${COST_CMP["gpt-4o-mini_measured_usd"]} measured vs GPT-4o ${COST_CMP["gpt-4o_projected_usd"]} projected,
          about {Math.round(COST_CMP["gpt-4o_projected_usd"] / COST_CMP["gpt-4o-mini_measured_usd"])}× more, while retrieval drives most of the quality.
        </p>
      )}
    </Section>
  );
}

function NextBets() {
  const bets = [
    ["Past-date questions are the weakest type", of(pastDate), "Date-aware ranking; more past-date test questions."],
    ["The claim checker misses most weak sentences", of(caught), "Stricter checker prompt or larger checker model, re-measured on fresh labels."],
    ["Some out-of-scope labels may be wrong", of(declined), "Hand-review the locked labels; two such development labels proved wrong."],
    ["Graph 'applies to' links are unreliable", of(fromRatio(FRESH?.APPLIES_TO?.precision)), "Better extraction before they influence answers."],
    ["The test set is small and AI-drafted", `${TEST.questions ?? "—"} questions`, "Grow and hand-review it so the ranges narrow."],
  ];
  return (
    <Section eyebrow="Prioritised backlog" title="Where it falls short, and the next bet.">
      <ol className="hwt-bets">
        {bets.map(([gap, now, next]) => (
          <li key={gap}><span><strong>{gap}</strong><span className="num hwt-now">{now}</span></span><span className="hwt-detail">{next}</span></li>
        ))}
      </ol>
    </Section>
  );
}

const TYPES: Record<string, [string, string]> = {
  single_fact: ["Simple fact", "Finds and cites one specific rule"],
  applies_to: ["Who it applies to", "Identifies which lenders or cases a rule covers"],
  multi_hop: ["Linked evidence", "Combines two paragraphs that refer to each other"],
  change_over_time: ["Past-date question", "Answers with the rule in force on an earlier date"],
  withdrawn_trap: ["Withdrawn-rule trap", "Avoids quoting a rule RBI has withdrawn"],
  false_premise: ["False premise", "Corrects a question built on a wrong fact"],
  unanswerable: ["Not in the rulebook", "Declines when its sources do not cover the question"],
};

function Method() {
  const steps = ["Draft questions from RBI paragraphs", "Attach the exact answer-key sentence", "Lock away a test set", "Run the full live pipeline", "Score by script, not by AI", "Report with 95% ranges"];
  const devN = DEV.questions;
  const testN = TEST.questions;
  return (
    <Section eyebrow="Method" title="How the numbers were produced.">
      <ol className="hwt-steps">{steps.map((step, index) => <li key={step}><span>{index + 1}</span>{step}</li>)}</ol>
      <div className="hwt-split" aria-label="Question split">
        <span style={{ flex: devN ?? 2 }}>{devN} development · tuning</span>
        <span style={{ flex: testN ?? 1 }}>{testN} locked test · run once</span>
      </div>
      <div className="hwt-table hwt-types" role="table" aria-label="Question types">
        <div className="hwt-row hwt-head" role="row"><span role="columnheader">Question type</span><span role="columnheader">Tests that it…</span><span role="columnheader">Real example (development set)</span></div>
        {examples.examples.map((example) => (
          <div className="hwt-row" role="row" key={example.type}>
            <span role="cell"><strong>{TYPES[example.type][0]}</strong></span>
            <span role="cell" className="hwt-detail">{TYPES[example.type][1]}</span>
            <span role="cell" className="hwt-example">
              “{example.question}”{example.as_of ? ` (as of ${example.as_of})` : ""}
              {example.evidence && example.type !== "unanswerable" && (
                <Info label={example.type === "withdrawn_trap" ? "the withdrawn sentence" : "the answer key"}>
                  {example.type === "withdrawn_trap" ? "Must not cite: " : "Answer key: "}{example.evidence.document}, paragraph {example.evidence.paragraph}: “{example.evidence.span.slice(0, 220)}{example.evidence.span.length > 220 ? "…" : ""}”
                </Info>
              )}
            </span>
          </div>
        ))}
      </div>
      <ul className="hwt-limits">
        <li><strong>Citing the right paragraph is not the same as a fully correct answer.</strong> No human graded answer correctness; groundedness comes from an imperfect automatic checker.</li>
        <li><strong>Small, AI-drafted question set.</strong> A sample was reviewed by hand; the ranges reflect sample size, not label error.</li>
        <li><strong>Not measured:</strong> independent legal correctness, a full hallucination rate, user time saved, rules outside NBFC lending.</li>
      </ul>
    </Section>
  );
}

export default function HowWeTest() {
  return (
    <div className="page hwt">
      <PageIntro eyebrow="How we test" title="An evaluation programme, run like a product launch.">
        A defined success metric, guardrails that stop it being gamed, a locked test set the product never saw during tuning,
        and a log of every experiment that changed it. Hover or tap any <span className="hwt-i-hint">i</span> for the exact definition.
      </PageIntro>
      <Headline />
      <Scorecard />
      <SystemHealth />
      <Experiments />
      <NextBets />
      <Method />
      <NextPage href="#evals" title="Explore the full results." text="Results by question type, real failure cases and the detailed tables." />
    </div>
  );
}
