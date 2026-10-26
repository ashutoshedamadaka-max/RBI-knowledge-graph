import { useState } from "react";
import { evidenceUrl, headline, ratio, REPORT } from "../quality";
import { Icon, NextPage, PageIntro, SourceNote } from "../components/UI";
import "../evals.css";

/* Results: the current scorecard, in plain language. How the testing works is on the "How we test" tab. */

const TYPE_NAMES: Record<string, [string, string]> = {
  single_fact: ["Simple fact", "find and cite one rule"],
  applies_to: ["Who it applies to", "say which lenders or cases a rule covers"],
  multi_hop: ["Linked evidence", "combine two connected paragraphs"],
  change_over_time: ["Past-date question", "answer with the rule in force on an earlier date"],
  false_premise: ["False premise", "correct a question built on a wrong fact"],
  withdrawn_trap: ["Withdrawn-rule trap", "avoid quoting a withdrawn rule"],
  unanswerable: ["Not in the rulebook", "decline when its sources do not cover the question"],
};
const RUNG_NAMES: Record<string, string> = {
  rung0: "Original search", bm25: "Keyword search", "dense-openai": "Meaning search (OpenAI)", "dense-bge": "Meaning search (local model)",
  hybrid: "Keyword + meaning", "hybrid+as-of": "+ date filter", "rerank-cohere": "+ re-ranking (chosen)", "rerank-bge": "+ local re-ranking",
};
const at = (value: number) => `${Math.round(value * 100)}%`;

/** One dot per question: the result as a picture rather than a percentage. */
function Dots({ total, marked, tone }: { total: number; marked: number; tone: "good" | "bad" }) {
  return (
    <div className={`dot-grid ${tone}`} aria-hidden="true">
      {Array.from({ length: total }, (_, i) => <span key={i} className={i < marked ? "on" : ""} />)}
    </div>
  );
}

function Range({ low, value, high }: { low: number; value: number; high: number }) {
  return (
    <div className="mini-range" aria-hidden="true">
      <span className="range-band" style={{ left: at(low), width: `${(high - low) * 100}%` }} />
      <span className="range-point" style={{ left: at(value) }} />
    </div>
  );
}

function Score({ role, title, metric, tone, sentence, context, status }: {
  role: string; title: string; metric: any; tone: "good" | "bad"; sentence: (k: number, n: number) => string; context: string;
  status: "strong" | "good" | "watch";
}) {
  if (!metric || metric.value == null) return null;
  const k = Math.round(metric.value * metric.n);
  const statusText = { strong: "Strong", good: "Good", watch: "Watch" }[status];
  return (
    <article className="card score-card">
      <div className="score-top"><span className="pm-tag">{role}</span><span className={`status-tag ${status}`}>{statusText}</span></div>
      <h3>{title}</h3>
      <p className="score-sentence">{sentence(k, metric.n)}</p>
      <Dots total={metric.n} marked={k} tone={tone} />
      <div className="score-range">
        <Range low={metric.low} value={metric.value} high={metric.high} />
        <span className="fine-print">{at(metric.value)} · likely between {at(metric.low)} and {at(metric.high)}</span>
      </div>
      <p className="score-context">{context}</p>
    </article>
  );
}

export default function Quality() {
  const [split, setSplit] = useState<"test" | "dev">("test");
  const h = headline(REPORT);
  const r = h.results;
  const shown = REPORT[`answers_${split}`].data.results;
  const ladder = REPORT.ladder.data.results;
  const graph = REPORT.graph_quality.data.results;
  const replay = REPORT.replay.data;
  const checker: any = Object.values(REPORT.claim_checker?.data?.by_source ?? {})[0];
  const perThousand = r.cost_usd?.per_question_answer_plus_rerank * 1000;
  const types = Object.entries(shown.by_type).filter(([, row]: [string, any]) => row.gold_sentence_cited) as [string, any][];
  const weakest = types.reduce((low, entry) => (!low || entry[1].gold_sentence_cited.value < low[1].gold_sentence_cited.value ? entry : low), null as any);
  const maxRecall = Math.max(...Object.values(ladder).map((row: any) => row["recall@5"].numerator / row["recall@5"].denominator));

  return (
    <div className="page">
      <PageIntro eyebrow="Results" title="Where it is strong, and where it still fails.">
        The current scorecard, measured on {REPORT.answers_test?.data?.questions ?? "the"} locked test questions the product
        never saw during tuning. New to these measures? <a href="#testing">How we test</a> explains each one in plain terms.
      </PageIntro>

      <section className="section-block" id="scorecard">
        <div className="section-heading"><div><div className="eyebrow">Scorecard</div><h2>Four results that matter most.</h2></div></div>
        <div className="score-grid">
          <Score role="North-star" title="Cites the right paragraph" metric={r.question_all_gold_cited} tone="good" status="good"
            sentence={(k, n) => `In ${k} of ${n} answerable questions, the answer cited the RBI paragraph that answers it.`}
            context={weakest ? `Strongest on simple facts and scope questions; weakest on ${TYPE_NAMES[weakest[0]][0].toLowerCase()}s (see below).` : ""} />
          <Score role="Guardrail" title="Never quotes a withdrawn rule" metric={r.withdrawn_trap_cited_withdrawn} tone="bad" status="strong"
            sentence={(k, n) => k === 0 ? `On all ${n} trick questions about withdrawn rules, the dead rule was never cited.` : `${k} of ${n} trick questions cited a withdrawn rule.`}
            context="Target met: zero. The date filter is what achieves it. Only a handful of trap questions, so the range is wide." />
          <Score role="Guardrail" title="Declines when it cannot know" metric={r.unanswerable_refused} tone="good" status="watch"
            sentence={(k, n) => `It declined ${k} of ${n} questions the rulebook does not cover.`}
            context="The two it answered have unreviewed labels; in development, two such labels proved wrong because the rulebook partly covered the topic." />
          <Score role="Counter-metric" title="Rarely refuses a fair question" metric={r.answerable_wrongly_refused} tone="bad" status="strong"
            sentence={(k, n) => `It wrongly declined ${k} of ${n} questions it could have answered.`}
            context="The balance to caution: a product that refuses everything would pass the guardrail above and fail here." />
        </div>
        <div className="ops-strip">
          <div><span className="pm-tag">Operational</span><strong>{perThousand ? `$${perThousand.toFixed(2)}` : "—"}</strong><span>per 1,000 questions (model charges at list price)</span></div>
          <div><span className="pm-tag">Operational</span><strong>{r.latency_ms_p50 ? `${(r.latency_ms_p50 / 1000).toFixed(0)} s` : "—"}</strong><span>typical time to a complete, checked answer in testing</span></div>
          <div><span className="pm-tag">Tool validation</span><strong>{checker ? `${checker["unsupported_caught (recall)"].numerator} of ${checker["unsupported_caught (recall)"].denominator}` : "—"}</strong><span>weak sentences the automatic checker caught: why it flags rather than rewrites</span></div>
        </div>
        <SourceNote file={h.file}>Locked test set · ranges are 95% bootstrap intervals</SourceNote>
      </section>

      <section className="section-block">
        <div className="section-heading">
          <div><div className="eyebrow">By kind of question</div><h2>Not every question is equally hard.</h2></div>
          <div className="segmented" aria-label="Question set" style={{ margin: 0 }}>
            <button aria-pressed={split === "test"} onClick={() => setSplit("test")}>Locked test</button>
            <button aria-pressed={split === "dev"} onClick={() => setSplit("dev")}>Development</button>
          </div>
        </div>
        <p className="prose muted">Share of expected answer-key sentences found in the cited paragraphs, with the likely range as a band.</p>
        <div className="type-bars">
          {types.map(([type, row]) => {
            const m = row.gold_sentence_cited;
            return (
              <div className={`type-bar ${weakest && weakest[0] === type && split === "test" ? "weakest" : ""}`} key={type}>
                <div className="type-bar-label"><strong>{TYPE_NAMES[type]?.[0] ?? type}</strong><span>Can it {TYPE_NAMES[type]?.[1] ?? "answer"}?</span></div>
                <div className="type-bar-track" aria-label={`${at(m.value)}, likely ${at(m.low)} to ${at(m.high)}`} role="img">
                  <span className="type-bar-fill" style={{ width: at(m.value) }} />
                  <span className="type-bar-band" style={{ left: at(m.low), width: `${(m.high - m.low) * 100}%` }} />
                </div>
                <span className="type-bar-value">{Math.round(m.value * m.n)} of {m.n}</span>
              </div>
            );
          })}
        </div>
        <p className="fine-print">Traps and out-of-scope questions are scored by the scorecard above, not by citations. {split === "test" && weakest ? `Weakest here: ${TYPE_NAMES[weakest[0]][0].toLowerCase()}s, the next area to improve.` : ""}</p>
      </section>

      <section className="section-block">
        <div className="section-heading"><div><div className="eyebrow">How the design was chosen</div><h2>Each step had to earn its place.</h2></div></div>
        <div className="grid-2">
          <div className="card">
            <h3>Right paragraph in the top 5 searched results</h3>
            <p className="fine-print">Development questions, one change per row. This measures finding the evidence, before any answer is written.</p>
            <div className="chart-bars">
              {Object.entries(ladder).map(([key, row]: [string, any]) => (
                <div className={`bar-row ${key === "rerank-cohere" ? "chosen" : ""}`} key={key}>
                  <span>{RUNG_NAMES[key] ?? key}</span>
                  <div className="bar" aria-hidden="true"><span style={{ width: `${(row["recall@5"].numerator / row["recall@5"].denominator) / maxRecall * 100}%` }} /></div>
                  <strong>{row["recall@5"].numerator}/{row["recall@5"].denominator}</strong>
                </div>
              ))}
            </div>
            <SourceNote file="ladder-dev.json">105 answer-key sentences</SourceNote>
          </div>
          <div className="card">
            <h3>What each step added</h3>
            <ul className="step-gains">
              <li><strong>Combining keyword and meaning search</strong> found more of the right paragraphs than either alone.</li>
              <li><strong>The date filter</strong> took withdrawn rules in the top results on trick questions from {ladder.hybrid?.["withdrawn_trap_leak@5"]?.numerator ?? "—"} of 13 to {ladder["hybrid+as-of"]?.["withdrawn_trap_leak@5"]?.numerator ?? "—"}.</li>
              <li><strong>Re-ranking</strong> moved the right paragraph higher: the final, chosen design.</li>
            </ul>
            <p className="fine-print">Design choices were made on development questions only; the locked test was run once at the end.</p>
            <a className="text-link" href="#built">See the trade-offs behind each choice <Icon name="arrow" size={16} /></a>
          </div>
        </div>
      </section>

      <section className="section-block" id="failure-results">
        <div className="section-heading"><div><div className="eyebrow">Failure analysis</div><h2>Real cases that still need work.</h2></div></div>
        <p className="prose muted">Shown on purpose: knowing how it fails is how the next improvement is chosen. A checker flag is a prompt to read the source, not a final verdict.</p>
        <div className="card">
          {h.data.failures.slice(0, 4).map((failure: any) => (
            <article className="failure-card" key={failure.id}>
              <div className="eyebrow">{TYPE_NAMES[failure.type]?.[0] ?? failure.type}</div>
              <h3>{failure.question}</h3>
              <p>{failure.reasons.join(" ") || "Answered, but the checker flagged a sentence."}</p>
              {failure.flagged_claims.slice(0, 1).map((c: any, i: number) => (
                <blockquote key={i}>“{c.text}”<br /><span className="fine-print">Checker: {c.verdict.replaceAll("_", " ")}</span></blockquote>
              ))}
            </article>
          ))}
          <SourceNote file={h.file} />
        </div>
      </section>

      <section className="section-block">
        <div className="card limits-card">
          <h3>Keep in mind</h3>
          <ul>
            <li>Citing the right paragraph is evidence the answer is grounded, not proof it is fully correct.</li>
            <li>The test set is small ({REPORT.answers_test?.data?.questions ?? "—"} questions) and AI-drafted; the ranges show the sample-size uncertainty.</li>
            <li>Independent legal correctness, a full hallucination rate and real-user time saved are not measured. <a href="#testing">More on the method</a>.</li>
          </ul>
        </div>
      </section>

      <details className="disclosure">
        <summary>Open the detailed tables (search metrics, graph accuracy, change-handling replay, saved files)</summary>
        <div>
          <h3>Search experiments: all measures</h3>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Search experiment table">
            <table>
              <thead><tr><th>Approach</th><th>Top 5</th><th>Top 10</th><th>Median / 95th percentile time (ms)</th><th>Cost per query (USD)</th></tr></thead>
              <tbody>{Object.entries(ladder).map(([name, row]: [string, any]) => (
                <tr key={name}><td>{RUNG_NAMES[name] ?? name}</td><td>{ratio(row["recall@5"])}</td><td>{ratio(row["recall@10"])}</td>
                  <td>{row.latency_ms.p50} / {row.latency_ms.p95}</td><td>{row.cost_per_query_usd}</td></tr>
              ))}</tbody>
            </table>
          </div>
          <SourceNote file="ladder-dev.json" />
          <h3 style={{ marginTop: 20 }}>Knowledge graph link accuracy</h3>
          <p className="fine-print">Precision: of the links it made, how many were right. Recall: of the links that exist, how many it found.</p>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Graph accuracy table">
            <table>
              <thead><tr><th>Labels</th><th>Link type</th><th>Precision</th><th>Recall</th></tr></thead>
              <tbody>{Object.entries(graph).flatMap(([label, linkTypes]: [string, any]) => Object.entries(linkTypes).filter(([key]) => key !== "provisions").map(([type, m]: [string, any]) => (
                <tr key={`${label}-${type}`}><td>{label}</td><td>{type.toLowerCase().replaceAll("_", " ")}</td>
                  <td>{m.precision.denominator ? ratio(m.precision) : "No links made"}</td><td>{ratio(m.recall)}</td></tr>
              )))}</tbody>
            </table>
          </div>
          <SourceNote file="graph-quality.json" />
          <h3 style={{ marginTop: 20 }}>Change handling: a replay of real RBI history</h3>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Replay table">
            <table>
              <thead><tr><th>Measure</th><th>Result</th></tr></thead>
              <tbody>
                <tr><td>Withdrawals detected</td><td>{ratio(replay.withdrawal_detection.recall)}</td></tr>
                <tr><td>Answers that used a rule already out of force</td><td>{ratio(replay.stale_answer_rate.evidence)}</td></tr>
                <tr><td>Automatically trusted replacements that were right</td><td>{ratio(replay.auto_trust_precision)}</td></tr>
              </tbody>
            </table>
          </div>
          <SourceNote file="replay-report.json" />
          <h3 style={{ marginTop: 20 }}>Saved report files</h3>
          <ul>{Object.entries(REPORT).map(([name, s]: [string, any]) => s.file && (
            <li key={name}><a href={evidenceUrl(s.file)} target="_blank" rel="noreferrer">{s.file}</a></li>
          ))}</ul>
        </div>
      </details>

      <NextPage href="#ask" title="See the evidence in an answer." text="Ask a question and watch the pipeline produce and check it." />
    </div>
  );
}
