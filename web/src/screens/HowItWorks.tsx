import { useEffect, useState } from "react";
import { Report, count, headline, ratio, useQuality } from "../quality";

interface Step { title: string; short: string; what: string; why: string; term: string; evidence: (r: Report) => string; guard?: boolean }

const ladder = (r: Report, rung: string) => r.ladder?.data?.results?.[rung];
const top5 = (r: Report, rung: string) => ratio(ladder(r, rung)?.["recall@5"]);
const leaks = (r: Report, rung: string) => ratio(ladder(r, rung)?.["withdrawn_trap_leak@5"]);

const STEPS: Step[] = [
  { title: "Question and date", short: "You ask, optionally 'as of' a past date",
    what: "You type a question in plain English. You can also pick a date, for example 1 June 2024, to ask what the rules were then rather than today.",
    why: "Compliance work often looks backwards: was a loan made in 2024 compliant with the rules of 2024? Most tools only know 'now'.",
    term: "Input", evidence: () => "Every answer states the date it answers for." },
  { title: "Search two ways", short: "Exact words and meaning, combined",
    what: "The question is matched against about 2,750 passages cut from the 88 RBI documents, in two ways at once: by exact words (good for legal terms such as 'penal charges') and by meaning (so 'late payment fees' still finds 'penal charges'). The two result lists are merged.",
    why: "Either method alone misses things. Combining them is the single biggest gain in finding the right paragraph.",
    term: "Recall", evidence: (r) => `Right paragraph in the top 5: ${top5(r, "bm25")} with exact words only, ${top5(r, "hybrid")} with both combined (dev set).` },
  { title: "Follow cross-references", short: "Bring in paragraphs the results point to",
    what: "RBI paragraphs often say 'subject to paragraph 12'. The knowledge graph knows these links, so the paragraphs a top result points to are pulled in too.",
    why: "Some answers need two paragraphs together. Without the link, the second one is often missed.",
    term: "Coverage", evidence: (r) => {
      const on = r.graph_on_off?.data?.results;
      const off = on?.["hybrid+as-of"]?.by_type?.multi_hop?.["recall@5"]; const withGraph = on?.graph?.by_type?.multi_hop?.["recall@5"];
      return off && withGraph ? `Questions that need two paragraphs: ${ratio(off)} found without the graph, ${ratio(withGraph)} with it.` : "Measured on the Knowledge graph page.";
    } },
  { title: "Keep only rules in force", short: "Drop anything withdrawn or not yet active on that date", guard: true,
    what: "Every paragraph carries the dates its rule was in force. Anything withdrawn, replaced or not yet in effect on the date asked is removed, and the system notes why.",
    why: "This is the core promise: never answer from a dead rule. It is a guardrail, not a ranking preference.",
    term: "Guardrail", evidence: (r) => `Trick questions where a withdrawn rule reached the top 5: ${leaks(r, "hybrid")} before this filter, ${leaks(r, "hybrid+as-of")} after it.` },
  { title: "Rank the best passages", short: "A specialist model re-reads the top 30",
    what: "A ranking model (Cohere Rerank) reads the 30 best candidates side by side with the question and puts the most relevant first.",
    why: "Search is fast but approximate. A second, careful read puts the paragraph that actually answers the question at the top.",
    term: "Precision", evidence: (r) => `Right paragraph in the top 5: ${top5(r, "hybrid+as-of")} before re-ranking, ${top5(r, "rerank-cohere")} after.` },
  { title: "Decide whether to answer", short: "Decline when the best match is weak", guard: true,
    what: "If even the best passage is a poor match, the product says the indexed RBI rules do not answer the question, instead of writing something plausible.",
    why: "A confident wrong answer is worse than no answer in compliance. Declining is a feature.",
    term: "Guardrail", evidence: (r) => {
      const chosen = r.abstention?.data?.curve_without_scope_guard?.find((p: any) => Math.abs(p.threshold - 0.3431) < 0.001);
      return chosen ? `At the chosen setting (dev set): ${ratio(chosen.unanswerable_refused)} unanswerable questions declined, ${ratio(chosen.answerable_refused)} answerable ones wrongly declined.` : "Tuned on the dev set; see Evals.";
    } },
  { title: "Write the answer", short: "Only from the passages, citing each one",
    what: "A language model (GPT-4o mini) writes a short answer using only the selected passages. Every sentence must point to the paragraph it came from, and answers about a past date say so.",
    why: "Grounding every sentence in a cited paragraph is what makes the answer checkable by a human in seconds.",
    term: "Grounding", evidence: (r) => `Answers that cited the right RBI paragraph: ${count(headline(r).results.question_all_gold_cited)} (${headline(r).split}).` },
  { title: "Check every claim", short: "A second AI reads each sentence against its source", guard: true,
    what: "A separate AI call reads each sentence next to the paragraph it cites and marks it supported, partly supported or not supported. Anything not fully supported is flagged on screen, never silently kept.",
    why: "Even grounded answers can over-generalise. Showing the flag lets the reader decide, rather than hiding uncertainty.",
    term: "Trust & safety", evidence: (r) => {
      const row: any = Object.values(r.claim_checker?.data?.by_source ?? {})[0];
      return row ? `Honest limit: of ${row["unsupported_caught (recall)"].denominator} claims a reviewer marked as not fully supported, the checker flagged ${row["unsupported_caught (recall)"].numerator}. That is why it flags rather than rewrites.` : "Validated on the Evals page.";
    } },
];

const LOOP = [
  { title: "Check RBI every day", tag: "Scheduled job", text: "A daily job visits RBI's pages for every rule in the library and RBI's official register of withdrawn circulars." },
  { title: "Spot what changed", tag: "Detection", text: "It notices RBI's 'Withdrawn' stamp, a listing in the register, or a new rule that says it replaces older ones." },
  { title: "Link old to new", tag: "Trust rule", text: "A replacement is trusted automatically only when RBI's own text says so explicitly. Anything less goes to a human review queue." },
  { title: "Retire the old rule", tag: "Lifecycle", text: "The old rule stays in the library for history, but stops being used for questions about dates after it ended." },
];

export default function HowItWorks() {
  const { report } = useQuality();
  const [lit, setLit] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

  useEffect(() => {
    if (selected !== null || reduced) return;
    const timer = window.setInterval(() => setLit((step) => (step + 1) % STEPS.length), 1500);
    return () => window.clearInterval(timer);
  }, [selected, reduced]);

  const shown = selected ?? lit;
  const step = STEPS[shown];
  const replay = report?.replay?.data;

  return (
    <div className="page">
      <section className="hero">
        <div className="eyebrow">How this works</div>
        <h1>From a question to a checked answer in eight steps</h1>
        <p className="lead">The product is a pipeline: each step either finds better evidence or removes a way to be wrong. Steps with a dashed border are <strong>guardrails</strong>: they exist to stop a bad answer, not to make a good one better. Click any step to pause the animation and read about it.</p>
      </section>

      <section>
        <div className="pipeline" role="list" aria-label="The answer pipeline">
          {STEPS.map((item, index) => (
            <button key={item.title} role="listitem" className={`pipe-step ${item.guard ? "guard" : ""} ${index === lit && selected === null ? "lit" : ""}`}
              aria-pressed={selected === index} onClick={() => setSelected(selected === index ? null : index)}>
              <strong>{item.title}</strong><span>{item.short}</span>
            </button>
          ))}
        </div>
        <p className="muted" style={{ fontSize: 13 }}>"Dev set" numbers come from the questions used while tuning the product; the final results on questions it never saw are on the Evals page.</p>
        <p className="flow-arrow">Question → search → cross-references → in-force filter → ranking → answer-or-decline → answer → claim check → shown with its evidence, time and cost.</p>
        <div className="step-detail card rise" key={shown} aria-live="polite">
          <div>
            <span className="pm-term">{step.term}</span>
            <h2 style={{ marginTop: 8 }}>{shown + 1}. {step.title}</h2>
            <p>{step.what}</p>
            <p><strong>Why it matters.</strong> {step.why}</p>
          </div>
          <div>
            <h3>Evidence</h3>
            <p>{report ? step.evidence(report) : "Loading the saved results…"}</p>
            {selected !== null && <button className="chip" onClick={() => setSelected(null)}>Resume the animation</button>}
          </div>
        </div>
      </section>

      <section>
        <div className="eyebrow">Keeping the rulebook current</div>
        <h2>The daily monitoring loop</h2>
        <p className="prose">Answering from the rule in force only works if the product knows when a rule stops being in force. This loop runs every day, separately from the questions.</p>
        <div className="loop">
          {LOOP.map((item, index) => (
            <div key={item.title} className={`loop-step ${index === lit % LOOP.length && selected === null ? "lit" : ""}`}>
              <div className="tag">{index + 1} · {item.tag}</div>
              <h3>{item.title}</h3>
              <p style={{ margin: 0, fontSize: 14 }}>{item.text}</p>
            </div>
          ))}
        </div>
        {replay && (
          <div className="stat-strip">
            <div className="stat"><div className="big"><span className="num">{ratio(replay.withdrawal_detection?.recall)}</span></div><div className="label">withdrawals detected in a replay of real RBI history ({replay.withdrawal_detection?.false_alarms} false alarms)</div></div>
            <div className="stat"><div className="big"><span className="num">{ratio(replay.stale_answer_rate?.evidence)}</span></div><div className="label">replayed answers that used a rule already out of force</div></div>
            <div className="stat"><div className="big"><span className="num">{ratio(replay.auto_trust_precision)}</span></div><div className="label">automatically trusted replacements that were right</div></div>
          </div>
        )}
      </section>

      <section>
        <h2>What you see on screen</h2>
        <div className="grid-3">
          <div className="card kicker-card"><h3>Every sentence has a source</h3><p>Click a citation to read the RBI paragraph, with the words that support the sentence highlighted.</p></div>
          <div className="card kicker-card"><h3>Every sentence has a status</h3><p>Green: the cited text supports it. Amber: only partly. Red: it does not. Flags are shown, never hidden.</p></div>
          <div className="card kicker-card"><h3>Every answer has a receipt</h3><p>The trace shows what each step found and removed, how long it took and what it cost, typically a fraction of a cent.</p></div>
        </div>
      </section>
    </div>
  );
}
