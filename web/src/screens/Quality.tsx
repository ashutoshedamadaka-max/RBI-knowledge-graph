import { useState } from "react";
import { count, evidenceUrl, headline, ratio, REPORT } from "../quality";
import { Icon, NextPage, PageIntro, SourceNote } from "../components/UI";
const TYPE_NAMES: Record<string, string> = {
  single_fact: "Simple fact",
  applies_to: "Who it applies to",
  multi_hop: "Linked evidence",
  change_over_time: "Past-date question",
  false_premise: "False premise",
  withdrawn_trap: "Withdrawn-rule trap",
  unanswerable: "Unanswerable",
};
const RUNG_NAMES: Record<string, string> = {
  rung0: "Original search",
  bm25: "Keyword search",
  "dense-openai": "OpenAI meaning search",
  "dense-bge": "Local meaning search",
  hybrid: "Hybrid search",
  "hybrid+as-of": "+ Date filtering",
  "rerank-cohere": "+ Cohere re-ranking",
  "rerank-bge": "+ Local re-ranking",
};
const interval = (m: any) =>
  m?.low == null
    ? "No interval computed"
    : `95% interval [${m.low}, ${m.high}]`;
function RateCard({
  title,
  metric,
  note,
}: {
  title: string;
  metric: any;
  note: string;
}) {
  return (
    <div className="metric-card">
      <span className="metric-label">{title}</span>
      <strong>{count(metric)}</strong>
      <p>{note}</p>
      <SourceNote file="answers-test-gpt-4o-mini.json">
        n = {metric.n} questions · {interval(metric)}
      </SourceNote>
    </div>
  );
}
export default function Quality() {
  const [split, setSplit] = useState<"test" | "dev">("test");
  const h = headline(REPORT);
  const r = h.results;
  const source = REPORT[`answers_${split}`];
  const shown = source.data.results;
  const ladder = REPORT.ladder.data.results;
  const graph = REPORT.graph_quality.data.results;
  const replay = REPORT.replay.data;
  return (
    <div className="page">
      <PageIntro
        eyebrow="Results & limits"
        title="Inspect the evidence. Keep the limits in view."
      >
        Saved experiments show what this prototype did on its test questions.
        They do not establish legal correctness, production reliability, or
        business impact.
      </PageIntro>
      <nav className="section-nav" aria-label="Results sections">
        {[
          ["overview-results", "Headline results"],
          ["search-results", "Search comparisons"],
          ["failure-results", "Failure cases"],
          ["method-results", "Method & limits"],
        ].map(([id, label]) => (
          <button
            key={id}
            onClick={() =>
              document.getElementById(id)?.scrollIntoView({ block: "start" })
            }
          >
            {label}
          </button>
        ))}
      </nav>
      <section id="overview-results">
        <div className="quality-callout">
          <div>
            <div className="eyebrow">Held-out evidence coverage</div>
            <h2>
              {count(r.gold_sentence_cited)} expected evidence sentences cited.
            </h2>
            <p>
              A filled square means an expected evidence sentence appeared
              inside a cited passage. An empty square means it did not.
            </p>
            <div
              className="squares"
              role="img"
              aria-label="51 of 57 expected evidence sentences present in cited passages"
            >
              {Array.from({ length: 57 }, (_, i) => (
                <span key={i} className={i < 51 ? "" : "miss"} />
              ))}
            </div>
            <SourceNote file={h.file}>
              n = 57 evidence sentences · {interval(r.gold_sentence_cited)}
            </SourceNote>
          </div>
          <div>
            <h3>What that proves</h3>
            <p>
              The answer cited a passage containing expected source evidence.
            </p>
            <h3 style={{ marginTop: 24 }}>What it does not prove</h3>
            <p>
              That the answer understood the rule, included every condition, or
              applied it to the right kind of lender. Answer correctness and
              hallucination rate are not independently measured.
            </p>
          </div>
        </div>
        <div className="result-grid">
          <RateCard
            title="All expected evidence cited"
            metric={r.question_all_gold_cited}
            note="Answerable questions whose citations contained all expected evidence."
          />
          <RateCard
            title="Withdrawn evidence cited"
            metric={r.withdrawn_trap_cited_withdrawn}
            note="Trap questions citing a withdrawn rule. Lower is better."
          />
          <RateCard
            title="Unanswerable questions refused"
            metric={r.unanswerable_refused}
            note="Questions labelled unanswerable that the system declined."
          />
          <RateCard
            title="Answerable questions refused"
            metric={r.answerable_wrongly_refused}
            note="Missed opportunities to answer. Lower is better."
          />
        </div>
      </section>
      <section className="section-block">
        <div className="section-heading">
          <div>
            <div className="eyebrow">Look beyond the average</div>
            <h2>Results by question type.</h2>
          </div>
          <div
            className="segmented"
            aria-label="Question results dataset"
            style={{ margin: 0 }}
          >
            <button
              aria-pressed={split === "test"}
              onClick={() => setSplit("test")}
            >
              Held-out test
            </button>
            <button
              aria-pressed={split === "dev"}
              onClick={() => setSplit("dev")}
            >
              Development
            </button>
          </div>
        </div>
        <div
          className="table-wrap"
          tabIndex={0}
          role="region"
          aria-label="Scrollable data table"
        >
          <table>
            <caption className="sr-only">
              Evidence citation results by question type on the {split} set
            </caption>
            <thead>
              <tr>
                <th>Question type</th>
                <th>Questions</th>
                <th>Answered</th>
                <th>Expected evidence cited</th>
                <th>95% interval</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(shown.by_type).map(
                ([type, row]: [string, any]) => (
                  <tr key={type}>
                    <td>{TYPE_NAMES[type] ?? type}</td>
                    <td>{row.questions}</td>
                    <td>{row.answered}</td>
                    <td>
                      {row.gold_sentence_cited
                        ? count(row.gold_sentence_cited)
                        : "No positive evidence target"}
                    </td>
                    <td>
                      {row.gold_sentence_cited
                        ? `[${row.gold_sentence_cited.low}, ${row.gold_sentence_cited.high}]`
                        : "Not computed"}
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
        <SourceNote file={source.file}>
          Each rate uses evidence sentences as its denominator; question counts
          are shown separately.
        </SourceNote>
      </section>
      <section className="section-block" id="search-results">
        <div className="section-heading">
          <div>
            <div className="eyebrow">Development experiments</div>
            <h2>Improve the evidence before the answer.</h2>
          </div>
        </div>
        <div className="grid-2">
          <div className="card">
            <h3>Expected evidence in the top five</h3>
            <p className="fine-print">
              Each bar uses the same development evidence targets. These are
              retrieval results, not correct-answer rates.
            </p>
            <div className="chart-bars">
              {Object.entries(ladder).map(([key, row]: [string, any]) => (
                <div
                  className={`bar-row ${key === "rerank-cohere" ? "chosen" : ""}`}
                  key={key}
                >
                  <span>{RUNG_NAMES[key] ?? key}</span>
                  <div className="bar" aria-hidden="true">
                    <span
                      style={{
                        width: `${(row["recall@5"].numerator / row["recall@5"].denominator) * 100}%`,
                      }}
                    />
                  </div>
                  <strong>
                    {row["recall@5"].numerator}/{row["recall@5"].denominator}
                  </strong>
                </div>
              ))}
            </div>
            <SourceNote file="ladder-dev.json">
              n = 105 evidence spans · no intervals computed
            </SourceNote>
          </div>
          <div className="card">
            <h3>Complexity has to earn its place.</h3>
            <p>
              The date filter removed withdrawn evidence from the tested traps.
              Cohere improved ranking. Graph cross-references recovered some
              linked evidence in a separate comparison.
            </p>
            <p className="muted">
              The full retrieval ladder was not measured on the held-out set.
              The graph comparison did not include Cohere, so the graph’s
              incremental benefit in the final answering path remains unproven.
            </p>
            <a className="text-link" href="#built">
              Explore the design decisions <Icon name="arrow" size={16} />
            </a>
          </div>
        </div>
        <details className="disclosure">
          <summary>Open retrieval metrics, timings, and costs</summary>
          <div>
            <div
              className="table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Scrollable data table"
            >
              <table>
                <thead>
                  <tr>
                    <th>Approach</th>
                    <th>Recall at 5</th>
                    <th>Recall at 10</th>
                    <th>Mean reciprocal rank</th>
                    <th>Median / 95th percentile (ms)</th>
                    <th>Estimated cost / query (USD)</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(ladder).map(([name, row]: [string, any]) => (
                    <tr key={name}>
                      <td>{RUNG_NAMES[name] ?? name}</td>
                      <td>{ratio(row["recall@5"])}</td>
                      <td>{ratio(row["recall@10"])}</td>
                      <td>
                        {typeof row.mrr === "object"
                          ? row.mrr.value
                          : (row.mrr ?? row.MRR ?? "Not measured")}
                      </td>
                      <td>
                        {row.latency_ms.p50} / {row.latency_ms.p95}
                      </td>
                      <td>{row.cost_per_query_usd}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <SourceNote file="ladder-dev.json">
              Development set · n = 118 questions; recall denominator = 105
              spans · no intervals computed
            </SourceNote>
          </div>
        </details>
        <details className="disclosure">
          <summary>Open graph extraction quality</summary>
          <div>
            <p className="fine-print">
              Precision: correct predicted links / predicted links. Recall:
              correct links found / gold links. Each label source is reported
              separately. Non-entity edge metrics compare sentences, not every
              endpoint.
            </p>
            <div
              className="table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Scrollable data table"
            >
              <table>
                <thead>
                  <tr>
                    <th>Label source</th>
                    <th>Relationship</th>
                    <th>Precision</th>
                    <th>Recall</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(graph).flatMap(
                    ([label, types]: [string, any]) =>
                      Object.entries(types)
                        .filter(([key]) => key !== "provisions")
                        .map(([type, m]: [string, any]) => (
                          <tr key={`${label}-${type}`}>
                            <td>{label}</td>
                            <td>{type.toLowerCase().replaceAll("_", " ")}</td>
                            <td>
                              {m.precision.denominator
                                ? ratio(m.precision)
                                : "Undefined: no predictions"}
                            </td>
                            <td>{ratio(m.recall)}</td>
                          </tr>
                        )),
                  )}
                </tbody>
              </table>
            </div>
            <SourceNote file="graph-quality.json">
              Denominators shown in each cell · no intervals computed
            </SourceNote>
            <p className="fine-print">
              “Applies to” links are shown for exploration but do not filter
              answers. Only paragraph cross-reference expansion participates in
              retrieval.
            </p>
          </div>
        </details>
        <details className="disclosure">
          <summary>Open withdrawal and replacement replay</summary>
          <div>
            <p>
              A deterministic historical replay, using templated questions and
              immediate approval assumptions. It does not test generated-answer
              correctness or live monitoring delay.
            </p>
            <div
              className="table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Scrollable data table"
            >
              <table>
                <thead>
                  <tr>
                    <th>Replay measure</th>
                    <th>Observed result</th>
                    <th>Scope</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Withdrawals detected</td>
                    <td>{ratio(replay.withdrawal_detection.recall)}</td>
                    <td>Retired-document cases</td>
                  </tr>
                  <tr>
                    <td>Stale evidence used</td>
                    <td>{ratio(replay.stale_answer_rate.evidence)}</td>
                    <td>Templated replay answers</td>
                  </tr>
                  <tr>
                    <td>Automatically trusted successors correct</td>
                    <td>{ratio(replay.auto_trust_precision)}</td>
                    <td>Explicit replacement statements only</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <SourceNote file="replay-report.json">
              Denominators shown in each row · no intervals computed
            </SourceNote>
            <p className="fine-print">
              Full successor recall, live time to switch, and a before/after
              stale-answer baseline are not measured.
            </p>
          </div>
        </details>
      </section>
      <section className="section-block" id="failure-results">
        <div className="section-heading">
          <div>
            <div className="eyebrow">Failure analysis</div>
            <h2>Real cases that still need work.</h2>
          </div>
        </div>
        <p className="prose muted">
          These are saved held-out failures or model flags. A checker flag is a
          signal to inspect, not an independent verdict.
        </p>
        <div className="card">
          {h.data.failures.slice(0, 4).map((failure: any) => (
            <article className="failure-card" key={failure.id}>
              <div className="eyebrow">
                {TYPE_NAMES[failure.type]} · {failure.id}
              </div>
              <h3>{failure.question}</h3>
              <p>{failure.reasons.join(" ")}</p>
              {failure.flagged_claims.slice(0, 1).map((c: any, i: number) => (
                <blockquote key={i}>
                  “{c.text}”<br />
                  <span className="fine-print">
                    Model checker: {c.verdict.replaceAll("_", " ")}
                  </span>
                </blockquote>
              ))}
            </article>
          ))}
          <SourceNote file={h.file} />
        </div>
      </section>
      <section className="section-block" id="method-results">
        <div className="section-heading">
          <div>
            <div className="eyebrow">Method & limits</div>
            <h2>What to keep in mind.</h2>
          </div>
        </div>
        <div className="grid-2">
          <div className="card">
            <h3>A small, mostly drafted benchmark</h3>
            <p>
              118 development questions and 63 held-out questions share the same
              corpus. Questions were model-drafted; the held-out set remains
              marked drafted. Some development labels were reviewed, edited, or
              rejected.
            </p>
            <SourceNote file="answers-test-gpt-4o-mini.json">
              n = 63 test questions
            </SourceNote>
            <SourceNote file="answers-dev-gpt-4o-mini.json">
              n = 118 development questions
            </SourceNote>
            <p className="fine-print" style={{ marginTop: 16 }}>
              Rejected development questions remained in the published runs. An
              aborted test attempt was discarded after a startup data mutation.
              The published test is the restored rerun.
            </p>
          </div>
          <div className="card">
            <h3>The checker needs stronger validation</h3>
            <p>
              The checker caught only 6 of 21 claims labelled not fully
              supported. Exact agreement was 29 of 50 claims. These labels were
              drafted by Claude; confirmed independent human correctness labels
              are missing.
            </p>
            <SourceNote file="claim-checker-quality.json">
              n = 21 not-fully-supported claims / 50 total claims · no intervals
              computed
            </SourceNote>
          </div>
          <div className="card">
            <h3>Cost is an estimate, not a bill</h3>
            <p>
              $
              {Number(
                (r.cost_usd.per_question_answer_plus_rerank * 1000).toFixed(5),
              )}{" "}
              per 1,000 questions, scaled from the saved mean for answering,
              checking, and re-ranking at the recorded list price. Hosting and
              initial corpus preparation are excluded.
            </p>
            <SourceNote file={h.file}>
              n = 63 questions · no cost interval computed
            </SourceNote>
            <p className="fine-print" style={{ marginTop: 14 }}>
              Total actual project spend and production cost per question are
              not measured. The spend ledger is incomplete.
            </p>
          </div>
          <div className="card">
            <h3>Uncertainty stays visible</h3>
            <p>
              The saved confidence intervals come from resampling this dataset.
              They do not cover label errors, new domains, or new users.
              Evidence-span intervals do not account for clustering within
              questions.
            </p>
            <ul className="quality-limits">
              <li>Independent answer correctness: not measured.</li>
              <li>Hallucination rate: not measured.</li>
              <li>Semantic citation precision: not measured.</li>
              <li>Customer time saved and adoption: not measured.</li>
            </ul>
          </div>
        </div>
      </section>
      <details className="disclosure">
        <summary>Browse the saved report files</summary>
        <div>
          <div
            className="table-wrap"
            tabIndex={0}
            role="region"
            aria-label="Scrollable data table"
          >
            <table>
              <thead>
                <tr>
                  <th>Report</th>
                  <th>Saved file</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(REPORT).map(([name, s]: [string, any]) => (
                  <tr key={name}>
                    <td>{name.replaceAll("_", " ")}</td>
                    <td>
                      <a
                        href={evidenceUrl(s.file)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {s.file}
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </details>
      <NextPage
        href="#ask"
        title="See the evidence in an answer."
        text="Explore a saved example, or research your own question."
      />
    </div>
  );
}
