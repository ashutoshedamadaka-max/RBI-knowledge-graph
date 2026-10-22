import { useEffect, useState } from "react";
import { getJson } from "../api";

/* Every number on this screen comes from a saved evaluation run served by /quality. Nothing is computed
   here except formatting; a run that does not exist shows "not yet measured". */
const RUNG_NAMES: Record<string, string> = {
  rung0: "Original search", bm25: "Exact words", "dense-openai": "Meaning (OpenAI)", "dense-bge": "Meaning (free model)",
  hybrid: "Both combined", "hybrid+as-of": "+ in-force filter", "rerank-cohere": "+ re-ranking (chosen)", "rerank-bge": "+ free re-ranker",
};
const TYPE_NAMES: Record<string, string> = {
  single_fact: "Simple fact", applies_to: "Who it applies to", multi_hop: "Needs two paragraphs", change_over_time: "About a past date",
  false_premise: "False premise", withdrawn_trap: "Trick: withdrawn rule", unanswerable: "Not answerable from the rulebook",
};
const EDGE_NAMES: Record<string, string> = {
  APPLIES_TO: "Who a rule applies to", REQUIRES: "What a rule requires", DEFINES: "Defines a term", REFERS_TO: "Refers to another paragraph",
};
const SOURCE_NAMES: Record<string, string> = {
  hand: "Labelled by hand", "model-drafted, reviewed by Ashu": "AI-drafted, checked by hand", "fresh: model-drafted, reviewed by Ashu": "Fresh paragraphs, AI-drafted, checked",
};

type Rate = { value: number | null; low?: number; high?: number; n: number; numerator?: number; denominator?: number };
type Source = { status: "measured" | "not yet measured"; file: string; data?: any };
type Report = Record<string, any>; // sources by name (each a Source), plus "spend"

const pct = (value: number | null | undefined) => (value === null || value === undefined ? "—" : `${Math.round(value * 1000) / 10}%`);

function Tile({ title, rate, note, file, lowerIsBetter }: { title: string; rate?: Rate; note?: string; file?: string; lowerIsBetter?: boolean }) {
  return (
    <div className="card tile">
      <div className="muted">{title}</div>
      {rate && rate.value !== null ? (
        <>
          <div className="value"><span className="num">{pct(rate.value)}</span></div>
          {rate.low !== undefined && <div className="range">95% range {pct(rate.low)} – {pct(rate.high)} · n = {rate.n}{lowerIsBetter ? " · lower is better" : ""}</div>}
        </>
      ) : <div className="value muted">not yet measured</div>}
      {note && <div className="range">{note}</div>}
      {file && <div className="range">Source: <code>{file}</code></div>}
    </div>
  );
}

function Bars({ rows, max = 1, format = pct }: { rows: [string, number | null][]; max?: number; format?: (v: number) => string }) {
  return <div>{rows.map(([label, value]) => (
    <div className="bar-row" key={label}>
      <span>{label}</span>
      <div className="bar" role="img" aria-label={`${label}: ${value === null ? "not measured" : format(value)}`}><span style={{ width: `${value === null ? 0 : (value / max) * 100}%` }} /></div>
      <span className="num">{value === null ? "—" : format(value)}</span>
    </div>
  ))}</div>;
}

export default function Quality() {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { getJson<Report>("/quality").then(setReport).catch((exc) => setError(exc.message)); }, []);
  if (error) return <p className="status-bad" role="alert">{error}</p>;
  if (!report) return <p className="muted">Loading saved evaluation runs…</p>;

  const answers = report.answers_test.status === "measured" ? report.answers_test : report.answers_dev;
  const split = report.answers_test.status === "measured" ? "held-out test set" : "dev set (test not yet run)";
  const results = answers.data?.results ?? {};
  const ladder = report.ladder.data?.results ?? {};
  const chosen = ladder["rerank-cohere"];
  const perQuestion = results.cost_usd?.per_question_answer_plus_rerank;
  const checker = report.claim_checker.data?.by_source ?? {};
  const checkerRow = Object.entries(checker)[0] as [string, any] | undefined;
  const replay = report.replay.data;
  const graphQuality = report.graph_quality.data?.results ?? {};
  const comparison = report.answers_dev.data?.model_cost_comparison;
  const firstPrompt = report.answers_dev_first_prompt.data?.results;

  return (
    <div className="page">
      <section className="hero">
        <div className="eyebrow">Evals</div>
        <h1>How I know it works, and where it doesn't</h1>
        <p className="lead">"It seems to answer well" is not evidence. Every claim about quality on this site comes from an automated test run against an answer key, with the run saved so the number can be traced back.</p>
      </section>
      <section>
        <h2>How quality is measured</h2>
        <div className="grid-2">
          <div className="card kicker-card"><span className="pm-term">Answer key</span><h3>181 questions with known answers</h3><p>Each question comes with the exact RBI sentence that answers it, copied from the source document. A question passes only if the answer cites a passage containing that sentence. No AI grades its own work.</p></div>
          <div className="card kicker-card"><span className="pm-term">Held-out set</span><h3>Tune on two thirds, test on one third</h3><p>The questions were split before any testing. Everything was tuned on the larger part; the smaller part was run once, at the end, so the headline numbers are not flattered by tuning.</p></div>
          <div className="card kicker-card"><span className="pm-term">Coverage</span><h3>Seven kinds of question</h3><p>Simple facts, "who does this apply to", two-paragraph questions, questions about a past date, trick questions about withdrawn rules, questions with a false premise, and questions the rulebook cannot answer.</p></div>
          <div className="card kicker-card"><span className="pm-term">Confidence</span><h3>Ranges, not just averages</h3><p>With dozens of questions, results carry uncertainty. Each headline number shows a 95% range: the true rate very likely lies inside it.</p></div>
        </div>
        <p className="muted" style={{ marginTop: 10 }}>Questions were drafted by an AI from RBI paragraphs and spot-checked by me (all 30 sampled questions kept). Measured on the {split}.</p>
      </section>
      <h2>Headline results</h2>
      <div className="tiles">
        <Tile title="Answers that cite the right RBI paragraph" rate={results.question_all_gold_cited} file={answers.file}
          note={results.gold_sentence_cited ? `Counting every answer sentence in the key: ${Math.round(results.gold_sentence_cited.value * results.gold_sentence_cited.n)} of ${results.gold_sentence_cited.n}` : undefined} />
        <Tile title="Withdrawn rules cited on trap questions" rate={results.withdrawn_trap_cited_withdrawn} lowerIsBetter file={answers.file} />
        <Tile title="Unanswerable questions refused" rate={results.unanswerable_refused} file={answers.file} />
        <Tile title="Answerable questions wrongly refused" rate={results.answerable_wrongly_refused} lowerIsBetter file={answers.file} />
        <Tile title="Right paragraph in the top 5 (retrieval)" rate={chosen ? { value: chosen["recall@5"].value, n: chosen["recall@5"].denominator } : undefined}
          note={chosen ? `${chosen["recall@5"].numerator} of ${chosen["recall@5"].denominator} gold sentences, dev set` : undefined} file={report.ladder.file} />
        <div className="card tile">
          <div className="muted">Cost per 1,000 questions</div>
          <div className="value">{perQuestion ? <span className="num">${(perQuestion * 1000).toFixed(2)}</span> : "not yet measured"}</div>
          <div className="range">Answer + claim check (gpt-4o-mini) + re-ranking at Cohere list price</div>
        </div>
        <div className="card tile">
          <div className="muted">Answer time, 95th percentile</div>
          <div className="value">{answers.data?.latency_ms_p95 ? <span className="num">{(answers.data.latency_ms_p95 / 1000).toFixed(1)} s</span> : "not yet measured"}</div>
          <div className="range">Median {results.latency_ms_p50 ? `${(results.latency_ms_p50 / 1000).toFixed(1)} s` : "—"} · includes a rate-limited trial re-ranking key</div>
        </div>
      </div>

      <div className="two-col">
        <section className="card">
          <span className="pm-term">Experiment</span>
          <h2>Finding the right paragraph: eight approaches, one change at a time</h2>
          <p className="muted">How often the paragraph that answers the question is in the top 5 results (105 answer sentences, dev set). Each bar changes one thing from an earlier one.</p>
          <Bars rows={Object.entries(ladder).map(([name, row]: [string, any]) => [RUNG_NAMES[name] ?? name, row["recall@5"]?.value ?? null])} />
          <p className="muted">Withdrawn rules reaching the top 5 on 13 trick questions: {Object.entries(ladder).map(([name, row]: [string, any]) => `${RUNG_NAMES[name] ?? name} ${row["withdrawn_trap_leak@5"].numerator}`).join(" · ")}. The in-force filter is what takes this to zero.</p>
        </section>
        <section className="card">
          <span className="pm-term">Segmentation</span>
          <h2>Results by kind of question</h2>
          <p className="muted">Where the product is strong and where it is weaker. Ranges in brackets.</p>
          <div className="table-wrap"><table>
            <thead><tr><th>Type</th><th>Questions</th><th>Answered</th><th>Right sentence cited</th></tr></thead>
            <tbody>{Object.entries(results.by_type ?? {}).map(([type, row]: [string, any]) => (
              <tr key={type}><td>{TYPE_NAMES[type] ?? type.replaceAll("_", " ")}</td><td>{row.questions}</td><td>{row.answered}</td>
                <td>{row.gold_sentence_cited ? <><span className="num">{pct(row.gold_sentence_cited.value)}</span> <span className="muted">({pct(row.gold_sentence_cited.low)}–{pct(row.gold_sentence_cited.high)})</span></> : "—"}</td></tr>
            ))}</tbody>
          </table></div>
        </section>
      </div>

      <div className="two-col">
        <section className="card">
          <span className="pm-term">Validation</span>
          <h2>Can the claim checker be trusted?</h2>
          <p className="muted">The checker is itself an AI, so it was tested against 50 claims labelled separately.</p>
          {checkerRow ? (
            <>
              <p>Of <span className="num">{checkerRow[1]["unsupported_caught (recall)"].denominator}</span> claims the labels mark as not fully supported, the checker flagged <span className="num">{checkerRow[1]["unsupported_caught (recall)"].numerator}</span>; <span className="num">{checkerRow[1]["flags_correct (precision)"].numerator}</span> of its {checkerRow[1]["flags_correct (precision)"].denominator} flags were right.</p>
              <p className="muted">Label source: {checkerRow[0]}. A weak checker is why unsupported claims are flagged on screen, not rewritten (ADR-030).</p>
            </>
          ) : <p className="muted">not yet measured</p>}
        </section>
        <section className="card">
          <span className="pm-term">Simulation</span>
          <h2>Handling rule changes: a replay of real history</h2>
          <p className="muted">RBI's real withdrawals and replacements were replayed day by day, and the product was asked questions along the way.</p>
          {replay ? <ReplaySummary replay={replay} /> : <p className="muted">not yet measured</p>}
        </section>
      </div>

      <div className="two-col">
        <section className="card">
          <span className="pm-term">Precision and recall</span>
          <h2>Knowledge graph accuracy</h2>
          <p className="muted"><strong>Precision</strong>: of the links it made, how many were right. <strong>Recall</strong>: of the links that exist, how many it found. Checked on hand-labelled paragraphs.</p>
          <div className="table-wrap"><table>
            <thead><tr><th>Labels</th><th>Link type</th><th>Precision</th><th>Recall</th></tr></thead>
            <tbody>{Object.entries(graphQuality).flatMap(([source, edges]: [string, any]) =>
              Object.entries(edges).filter(([key]) => key !== "provisions").map(([edge, m]: [string, any]) => (
                <tr key={source + edge}><td>{SOURCE_NAMES[source] ?? source}</td><td>{EDGE_NAMES[edge] ?? edge}</td>
                  <td>{m.precision.numerator}/{m.precision.denominator}</td><td>{m.recall.numerator}/{m.recall.denominator}</td></tr>
              )))}</tbody>
          </table></div>
        </section>
        <section className="card">
          <span className="pm-term">Unit economics</span>
          <h2>Cost</h2>
          <p>Total model spend for the whole build and every evaluation run: <span className="num">${report.spend.total_usd.toFixed(2)}</span> (budget $20).</p>
          <Bars rows={Object.entries(report.spend.by_phase_usd as Record<string, number>).map(([phase, usd]): [string, number] => [`Phase ${phase}`, usd])} max={Math.max(...(Object.values(report.spend.by_phase_usd) as number[]), 0.01)} format={(v) => `$${v.toFixed(3)}`} />
          {comparison && <p>Answer model on the dev set: gpt-4o-mini <span className="num">${comparison["gpt-4o-mini_measured_usd"]}</span> measured, gpt-4o <span className="num">${comparison["gpt-4o_projected_usd"]}</span> projected from the same tokens (about {Math.round(comparison["gpt-4o_projected_usd"] / comparison["gpt-4o-mini_measured_usd"] * 10) / 10}×). gpt-4o was not run, for cost (ADR-029).</p>}
        </section>
      </div>

      {firstPrompt && (
        <section className="card" style={{ marginTop: 16 }}>
          <span className="pm-term">Iteration</span>
          <h2>One fix, measured: the answer instructions</h2>
          <p>The first dev run wrongly refused <span className="num">{pct(firstPrompt.answerable_wrongly_refused.value)}</span> of answerable questions: passages for past dates were labelled with today's "withdrawn" status, so the model would not use them. After labelling each passage as in force on the question's date: <span className="num">{pct(report.answers_dev.data.results.answerable_wrongly_refused.value)}</span>. The cost: unanswerable questions refused fell from {pct(firstPrompt.unanswerable_refused.value)} to {pct(report.answers_dev.data.results.unanswerable_refused.value)}.</p>
        </section>
      )}

      <section className="card" style={{ marginTop: 16 }}>
        <span className="pm-term">Failure analysis</span>
        <h2>Where it still fails: real cases from the {split}</h2>
        <p className="muted">Questions where the answer missed the expected paragraph, or where the checker flagged a sentence. Shown on purpose: knowing the failure modes is how the next iteration is chosen.</p>
        <div className="table-wrap"><table>
          <thead><tr><th>Question</th><th>Type</th><th>What went wrong</th></tr></thead>
          <tbody>{(answers.data?.failures ?? []).map((item: any) => (
            <tr key={item.id}><td>{item.question ?? item.id}</td><td>{TYPE_NAMES[item.type] ?? item.type.replaceAll("_", " ")}</td>
              <td>{[...item.reasons, ...item.flagged_claims.map((c: any) => `claim ${c.verdict.replaceAll("_", " ")}: “${c.text.slice(0, 120)}”`)].join("; ")}</td></tr>
          ))}</tbody>
        </table></div>
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <h2>Run history</h2>
        <p className="muted">Each number on this page traces to one of these saved runs and the code version that produced it.</p>
        <div className="table-wrap"><table>
          <thead><tr><th>Run</th><th>File</th><th>Generated</th><th>Commit</th></tr></thead>
          <tbody>{Object.entries(report).filter(([name]) => name !== "spend").map(([name, source]) => (
            <tr key={name}><td>{name.replaceAll("_", " ")}</td><td><code>{source.file}</code></td>
              <td>{source.data?.generated_at?.slice(0, 16).replace("T", " ") ?? source.data?.run_manifest?.built_at?.slice(0, 16) ?? (source.status === "measured" ? "—" : "not yet measured")}</td>
              <td><code>{((source as Source).data?.run_manifest?.git_commit ?? "").slice(0, 7)}</code></td></tr>
          ))}</tbody>
        </table></div>
      </section>
    </div>
  );
}

function ReplaySummary({ replay }: { replay: any }) {
  const ratio = (m: any) => (m ? `${m.numerator}/${m.denominator}` : "—");
  const rows: [string, string, string?][] = [
    ["Withdrawals detected", ratio(replay.withdrawal_detection?.recall), `${replay.withdrawal_detection?.false_alarms ?? "—"} false alarms`],
    ["Successor links from RBI text: precision", ratio(replay.successor_links_from_rbi_text?.precision)],
    ["Auto-trusted links that were right", ratio(replay.auto_trust_precision)],
    ["Stale answers (a retired rule used)", ratio(replay.stale_answer_rate?.evidence), "lower is better"],
    ["Days to switch to the new rule", String(replay.time_to_switch_days?.max ?? "—"), "worst case"],
    ["Inferred successor suggestions", "not yet measured", replay.candidate_suggestions?.note],
  ];
  return (
    <table><tbody>{rows.map(([name, value, note]) => (
      <tr key={name}><td>{name}</td><td><span className={value === "not yet measured" ? "muted" : "num"}>{value}</span></td><td className="muted">{note}</td></tr>
    ))}</tbody></table>
  );
}
