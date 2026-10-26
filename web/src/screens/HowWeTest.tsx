import { useEffect, useState } from "react";
import { REPORT } from "../quality";
import { NextPage, PageIntro, SourceNote } from "../components/UI";
import examples from "../data/question-examples.json";
import { EvalHeadline, ExperimentLog, MetricTree, NextBets } from "../components/EvalShowcase";
import SystemHealth from "../components/SystemHealth";
import "../evals.css";

/* How the product is tested: the method only. The numbers themselves live on the Results tab. */

const FLOW = [
  { title: "Write test questions", text: "Questions are drafted from real RBI paragraphs, the way an analyst would ask them.", icon: "?" },
  { title: "Attach the answer key", text: "Each question carries the exact RBI sentence that answers it, copied from the source document.", icon: "✓" },
  { title: "Lock away a test set", text: "A third of the questions are set aside before any tuning. The product is improved only on the rest.", icon: "◼" },
  { title: "Run the product", text: "Every question goes through the full live pipeline, exactly as a user's question would.", icon: "▶" },
  { title: "Score automatically", text: "A script checks each answer against its key. No AI grades its own work.", icon: "=" },
  { title: "Report with ranges", text: "Each result is shown with a 95% range, so a small sample is never mistaken for certainty.", icon: "↔" },
];

const TYPES: Record<string, { name: string; tests: string; passes: string }> = {
  single_fact: { name: "Simple fact", tests: "Can it find and cite one specific rule?", passes: "The answer cites the paragraph holding the expected sentence." },
  applies_to: { name: "Who it applies to", tests: "Can it tell which lenders, loans or cases a rule covers?", passes: "The answer cites the paragraph that sets the scope." },
  multi_hop: { name: "Linked evidence", tests: "Can it combine two paragraphs that refer to each other?", passes: "The answer cites both expected paragraphs." },
  change_over_time: { name: "Past-date question", tests: "Can it answer with the rule that applied on an earlier date?", passes: "The answer cites the paragraph in force on that date." },
  withdrawn_trap: { name: "Withdrawn-rule trap", tests: "Does it avoid quoting a rule RBI has withdrawn?", passes: "The withdrawn sentence is never cited." },
  false_premise: { name: "False premise", tests: "Does it correct a question built on a wrong fact?", passes: "The answer cites the paragraph with the true fact." },
  unanswerable: { name: "Not in the rulebook", tests: "Does it decline when its sources do not cover the question?", passes: "The product declines instead of answering." },
};

function TestFlow() {
  const [lit, setLit] = useState(0);
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  useEffect(() => {
    if (reduced) return;
    const timer = window.setInterval(() => setLit((step) => (step + 1) % FLOW.length), 1800);
    return () => window.clearInterval(timer);
  }, [reduced]);
  return (
    <ol className="test-flow" aria-label="How a test run works">
      {FLOW.map((step, index) => (
        <li key={step.title} className={!reduced && index === lit ? "lit" : ""}>
          <span className="test-flow-icon" aria-hidden="true">{step.icon}</span>
          <strong>{index + 1}. {step.title}</strong>
          <span>{step.text}</span>
        </li>
      ))}
    </ol>
  );
}

function RangeExplainer() {
  const rate = REPORT.answers_test?.data?.results?.question_all_gold_cited;
  if (!rate) return null;
  const passed = Math.round(rate.value * rate.n);
  const at = (value: number) => `${(value * 100).toFixed(0)}%`;
  return (
    <div className="card range-explainer">
      <div>
        <h3>Reading a result like "{passed} of {rate.n}"</h3>
        <p>On the locked test set, {passed} of {rate.n} answerable questions cited the right paragraph: {at(rate.value)}. With only {rate.n} questions, a different sample of similar questions could easily give a somewhat different score.</p>
        <p>So every headline result also shows a <strong>95% range</strong>: the band the true rate very likely falls in. Here, between <strong>{at(rate.low)}</strong> and <strong>{at(rate.high)}</strong>. A narrow band means the result is firm; a wide one means "promising, needs more questions".</p>
      </div>
      <div className="range-visual" role="img" aria-label={`Measured ${at(rate.value)}, likely range ${at(rate.low)} to ${at(rate.high)}`}>
        <div className="range-track">
          <span className="range-band" style={{ left: at(rate.low), width: `${(rate.high - rate.low) * 100}%` }} />
          <span className="range-point" style={{ left: at(rate.value) }} />
        </div>
        <div className="range-scale"><span>0%</span><span>50%</span><span>100%</span></div>
        <p className="fine-print">Dot: what was measured. Band: where the true rate very likely lies.</p>
      </div>
    </div>
  );
}

export default function HowWeTest() {
  const dev = REPORT.answers_dev?.data?.questions;
  const test = REPORT.answers_test?.data?.questions;
  return (
    <div className="page">
      <PageIntro eyebrow="How we test" title="An evaluation programme, run like a product launch.">
        A confident-sounding AI is not evidence of anything. This product has a defined success metric, guardrails that stop it
        being gamed, a locked test set it never saw during tuning, and a log of every experiment that changed it. Here is
        what was measured, what it showed, and what comes next.
      </PageIntro>

      <EvalHeadline />
      <MetricTree />
      <SystemHealth />
      <ExperimentLog />
      <NextBets />

      <section className="section-block">
        <div className="section-heading"><div><div className="eyebrow">Method · the test process</div><h2>How every number above was produced.</h2></div></div>
        <TestFlow />
        <div className="split-visual" aria-label="How the questions are split">
          <div className="split-bar">
            <span className="split-dev" style={{ flex: dev ?? 2 }}><strong>{dev ?? "—"}</strong> development questions · used to tune</span>
            <span className="split-test" style={{ flex: test ?? 1 }}><strong>{test ?? "—"}</strong> locked test · run once, at the end</span>
          </div>
          <p className="fine-print">The split was made before any testing. Headline results come only from the locked set, so they are not flattered by tuning.</p>
        </div>
      </section>

      <section className="section-block">
        <div className="section-heading"><div><div className="eyebrow">Coverage</div><h2>Seven kinds of question, each testing a different risk.</h2></div></div>
        <p className="prose muted">Each card shows a real question from the development set and how it is judged.</p>
        <div className="type-grid">
          {examples.examples.map((example) => {
            const type = TYPES[example.type];
            return (
              <article className="card type-card" key={example.type}>
                <span className="mini-label">{type.name}</span>
                <h3>{type.tests}</h3>
                <blockquote>“{example.question}”{example.as_of ? <span className="fine-print"> (asked as of {example.as_of})</span> : null}</blockquote>
                <p className="type-pass"><strong>Passes when:</strong> {type.passes}</p>
                {example.evidence && example.type !== "unanswerable" && (
                  <details><summary>{example.type === "withdrawn_trap" ? "The withdrawn sentence it must not cite" : "The answer key"}</summary>
                    <p className="fine-print">{example.evidence.document}, paragraph {example.evidence.paragraph}</p>
                    <p className="key-span">“{example.evidence.span}”</p>
                  </details>
                )}
              </article>
            );
          })}
        </div>
        <SourceNote file="v2/dev.jsonl">Example questions</SourceNote>
      </section>

      <section className="section-block">
        <div className="section-heading"><div><div className="eyebrow">Uncertainty</div><h2>Why every result has a range.</h2></div></div>
        <RangeExplainer />
      </section>

      <section className="section-block">
        <div className="section-heading"><div><div className="eyebrow">Fair comparisons</div><h2>One change at a time.</h2></div></div>
        <div className="grid-2">
          <div className="card">
            <h3>How design choices were made</h3>
            <p>Every option (a search method, a filter, a re-ranker) was tested by changing exactly one thing and re-running the same development questions. If the score moved, the change caused it.</p>
          </div>
          <div className="card">
            <h3>Checking the checkers</h3>
            <p>Automatic tools are tested too. The claim checker was compared with hand-checked labels, and the knowledge graph's links with paragraphs labelled by hand, before deciding how much to rely on them.</p>
          </div>
        </div>
      </section>

      <section className="section-block">
        <div className="section-heading"><div><div className="eyebrow">Honest limits</div><h2>What these tests do not prove.</h2></div></div>
        <div className="card limits-card">
          <ul>
            <li><strong>Citing the right paragraph is not the same as a fully correct answer.</strong> The answer could still miss a condition or misstate a detail. That is why each sentence is checked against its source, and the check is shown.</li>
            <li><strong>The question set is small and drafted by an AI.</strong> A sample was reviewed by hand; the ranges reflect sample size, not label errors.</li>
            <li><strong>Not measured:</strong> independent legal correctness, a full hallucination rate, time saved for real users, or results outside NBFC lending rules.</li>
          </ul>
        </div>
      </section>

      <NextPage href="#evals" title="See the results." text="The current scorecard, where it is strong, and where it still fails." />
    </div>
  );
}
