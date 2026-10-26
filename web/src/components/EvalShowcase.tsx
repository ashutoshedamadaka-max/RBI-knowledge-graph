import { REPORT } from "../quality";
import { SourceNote } from "./UI";
import "../eval-showcase.css";

/* The evaluation programme as a product manager would present it: the headline, the metric tree, the
   experiments that moved the numbers, and the next bets. Every value is read from the saved runs. */

type Count = { k: number; n: number };
const fromRate = (rate: any): Count | null => (rate && rate.value != null ? { k: Math.round(rate.value * rate.n), n: rate.n } : null);
const fromRatio = (m: any): Count | null => (m ? { k: m.numerator, n: m.denominator } : null);
const pctOf = (c: Count | null) => (c && c.n ? `${Math.round((c.k / c.n) * 100)}%` : "—");
const of = (c: Count | null) => (c ? `${c.k} of ${c.n}` : "—");

const test = REPORT.answers_test?.data?.results ?? {};
const devFirst = REPORT.answers_dev_first_prompt?.data?.results ?? {};
const dev = REPORT.answers_dev?.data?.results ?? {};
const ladder = REPORT.ladder?.data?.results ?? {};
const onOff = REPORT.graph_on_off?.data?.results ?? {};
const graphQuality = REPORT.graph_quality?.data?.results ?? {};
const fresh: any = Object.entries(graphQuality).find(([key]) => key.startsWith("fresh"))?.[1];
const checker: any = Object.values(REPORT.claim_checker?.data?.by_source ?? {})[0];
const chunkers = REPORT.chunkers?.data?.results ?? {};
const replay = REPORT.replay?.data ?? {};
const costCompare = REPORT.answers_dev?.data?.model_cost_comparison;
const perThousand = test.cost_usd?.per_question_answer_plus_rerank ? test.cost_usd.per_question_answer_plus_rerank * 1000 : null;
const top5 = (rung: string) => fromRatio(ladder[rung]?.["recall@5"]);
const leaks = (rung: string) => fromRatio(ladder[rung]?.["withdrawn_trap_leak@5"]);

const northStar = fromRate(test.question_all_gold_cited);
const withdrawn = fromRate(test.withdrawn_trap_cited_withdrawn);
const declined = fromRate(test.unanswerable_refused);
const wronglyRefused = fromRate(test.answerable_wrongly_refused);
const pastDate = fromRate(test.by_type?.change_over_time?.gold_sentence_cited);

export function EvalHeadline() {
  const testQuestions = REPORT.answers_test?.data?.questions;
  return (
    <section className="eval-headline">
      <p className="eval-headline-sentence">
        On <strong>{testQuestions}</strong> locked test questions the product never saw during tuning, it cited the right RBI
        paragraph in <strong>{of(northStar)}</strong> answerable questions, never quoted a withdrawn rule
        ({of(withdrawn)} trick questions), and wrongly refused only <strong>{of(wronglyRefused)}</strong>, at
        {perThousand ? <> <strong>${perThousand.toFixed(2)}</strong> per 1,000 questions</> : " a measured cost"}.
      </p>
      <div className="big-numbers">
        <div><strong>{pctOf(northStar)}</strong><span>cited the right paragraph</span><em>North-star</em></div>
        <div><strong>{withdrawn?.k ?? "—"}</strong><span>withdrawn rules quoted</span><em>Guardrail{withdrawn?.k === 0 ? " · target met" : ""}</em></div>
        <div><strong>{pctOf(wronglyRefused)}</strong><span>fair questions refused</span><em>Counter-metric</em></div>
        <div><strong>{perThousand ? `$${perThousand.toFixed(2)}` : "—"}</strong><span>per 1,000 questions</span><em>Unit economics</em></div>
      </div>
      <SourceNote file="answers-test-gpt-4o-mini.json">Locked test set, run once</SourceNote>
    </section>
  );
}

function Node({ label, name, question, value, detail, chip, tone = "plain" }: {
  label: string; name: string; question: string; value: string; detail?: string; chip?: string; tone?: "north" | "guard" | "plain";
}) {
  return (
    <div className={`tree-node ${tone}`}>
      <div className="tree-node-top"><span className="pm-tag">{label}</span>{chip && <span className="status-tag strong">{chip}</span>}</div>
      <strong className="tree-value">{value}</strong>
      <h3>{name}</h3>
      <p>{question}</p>
      {detail && <span className="fine-print">{detail}</span>}
    </div>
  );
}

export function MetricTree() {
  return (
    <section className="section-block">
      <div className="section-heading"><div><div className="eyebrow">The metric framework</div><h2>One goal, protected by guardrails.</h2></div></div>
      <p className="prose muted">A single north-star metric defines success. Guardrails stop it being gamed: a system that quotes anything would score
        well on citations and badly on safety; one that refuses everything would be safe and useless. Below them sit the leading indicators
        that explain why the top line moves, and the operating costs.</p>
      <div className="metric-tree" role="list" aria-label="Metric tree">
        <div className="tree-row single" role="listitem">
          <Node tone="north" label="North-star" name="Cites the right paragraph" value={pctOf(northStar)}
            question="Did the answer point to the RBI paragraph that actually answers the question?" detail={`${of(northStar)} answerable test questions`} />
        </div>
        <div className="tree-row" role="listitem">
          <Node tone="guard" label="Guardrail" name="Never quotes a withdrawn rule" value={String(withdrawn?.k ?? "—")} chip={withdrawn?.k === 0 ? "Target met" : undefined}
            question="On trick questions about withdrawn rules, was the dead rule ever cited?" detail={`${of(withdrawn)} trap questions · target was zero`} />
          <Node tone="guard" label="Guardrail" name="Declines when it cannot know" value={pctOf(declined)}
            question="When the rulebook does not cover the question, did it decline instead of guessing?" detail={`${of(declined)} out-of-scope questions`} />
          <Node tone="guard" label="Counter-metric" name="Rarely refuses a fair question" value={pctOf(wronglyRefused)}
            question="Did caution make it refuse questions it could have answered?" detail={`${of(wronglyRefused)} answerable questions`} />
        </div>
        <div className="tree-row" role="listitem">
          <Node label="Leading indicator" name="Search finds the paragraph" value={pctOf(top5("rerank-cohere"))}
            question="Before any answer is written, is the right paragraph in the top 5 results?" detail={`${of(top5("rerank-cohere"))} answer-key sentences (development)`} />
          <Node label="Leading indicator" name="Change detection" value={of(fromRatio(replay.withdrawal_detection?.recall))}
            question="Replaying real RBI history, was every withdrawal caught?" detail={`${of(fromRatio(replay.stale_answer_rate?.evidence))} replayed answers used an out-of-force rule`} />
          <Node label="Tool health" name="Claim checker catch rate" value={of(fromRatio(checker?.["unsupported_caught (recall)"]))}
            question="When a sentence is not fully supported, does the automatic check flag it?" detail="Weak: so claims are flagged, never auto-rewritten" />
        </div>
        <div className="tree-row" role="listitem">
          <Node label="Unit economics" name="Cost per 1,000 questions" value={perThousand ? `$${perThousand.toFixed(2)}` : "—"}
            question="What does answering, checking and ranking cost at list prices?" detail="Model charges only; hosting excluded" />
          <Node label="Unit economics" name="Answer model cost avoided" value={costCompare ? `${Math.round(costCompare["gpt-4o_projected_usd"] / costCompare["gpt-4o-mini_measured_usd"])}×` : "—"}
            question="How much cheaper is the chosen model than the larger one for the same work?"
            detail={costCompare ? `$${costCompare["gpt-4o-mini_measured_usd"]} measured vs $${costCompare["gpt-4o_projected_usd"]} projected (development set)` : ""} />
        </div>
      </div>
      <p className="fine-print">Only the withdrawn-rule guardrail had a target set before testing (zero). The other results are baselines for the next iteration, not targets chosen after the fact.</p>
    </section>
  );
}

interface Experiment {
  area: string; hypothesis: string; change: string; measure: string; lowerIsBetter?: boolean;
  before: { label: string; value: Count | null }; after: { label: string; value: Count | null };
  decision: "Adopted" | "Adopted, limited" | "Not pursued"; result: string;
}

const EXPERIMENTS: Experiment[] = [
  { area: "Splitting documents", hypothesis: "Cutting along RBI's own numbered paragraphs keeps rules whole.",
    change: "Paragraph-based splitting vs fixed-size chunks", measure: "Answer-key sentences kept whole in one piece",
    before: { label: "Fixed size", value: fromRatio(chunkers.fixed?.boundary_accuracy) }, after: { label: "Paragraphs", value: fromRatio(chunkers.structure?.boundary_accuracy) },
    decision: "Adopted", result: "The only method that never split a rule from its conditions, and it gives citations a paragraph number." },
  { area: "Search", hypothesis: "Exact words and meaning catch different things, so combining them finds more.",
    change: "Keyword search alone vs keyword + meaning, merged", measure: "Right paragraph in the top 5",
    before: { label: "Keywords", value: top5("bm25") }, after: { label: "Combined", value: top5("hybrid") },
    decision: "Adopted", result: "The largest single gain in finding the evidence." },
  { area: "Safety", hypothesis: "Filtering by the date a rule was in force stops withdrawn rules leaking into answers.",
    change: "Add the in-force date filter", measure: "Trick questions with a withdrawn rule in the top 5", lowerIsBetter: true,
    before: { label: "No filter", value: leaks("hybrid") }, after: { label: "Date filter", value: leaks("hybrid+as-of") },
    decision: "Adopted", result: `Leaks fell to zero, and finding the right paragraph rose from ${of(top5("hybrid"))} to ${of(top5("hybrid+as-of"))}.` },
  { area: "Ranking", hypothesis: "A specialist re-ranker puts the paragraph that actually answers the question first.",
    change: "Add Cohere re-ranking over the top 30", measure: "Right paragraph in the top 5",
    before: { label: "Before", value: top5("hybrid+as-of") }, after: { label: "Re-ranked", value: top5("rerank-cohere") },
    decision: "Adopted", result: `Best overall. A free local re-ranker scored ${of(top5("rerank-bge"))} and took about ${Math.round((ladder["rerank-bge"]?.latency_ms?.p50 ?? 0) / 1000)} s per question, so it was rejected.` },
  { area: "Knowledge graph", hypothesis: "Following 'see paragraph 12' links helps questions that need two paragraphs.",
    change: "Add the paragraphs that top results cite", measure: "Linked-evidence questions: right paragraphs in the top 5",
    before: { label: "Without", value: fromRatio(onOff["hybrid+as-of"]?.by_type?.multi_hop?.["recall@5"]) },
    after: { label: "With graph", value: fromRatio(onOff.graph?.by_type?.multi_hop?.["recall@5"]) },
    decision: "Adopted, limited", result: `Used only for cross-references. Its 'who does this apply to' links were right ${of(fromRatio(fresh?.APPLIES_TO?.precision))} times on fresh paragraphs, so they never influence answers.` },
  { area: "Answer instructions", hypothesis: "The model refused past-date questions because it saw today's 'withdrawn' label on evidence that was valid then.",
    change: "Label each passage as in force on the question's date", measure: "Answerable questions wrongly refused", lowerIsBetter: true,
    before: { label: "First prompt", value: fromRate(devFirst.answerable_wrongly_refused) }, after: { label: "Fixed", value: fromRate(dev.answerable_wrongly_refused) },
    decision: "Adopted", result: `Trade-off accepted: unanswerable questions declined fell from ${of(fromRate(devFirst.unanswerable_refused))} to ${of(fromRate(dev.unanswerable_refused))} (development set).` },
  { area: "Claim checking", hypothesis: "An automatic check can catch sentences the cited text does not fully support.",
    change: "A separate model reads each sentence against its source", measure: "Weak sentences caught",
    before: { label: "Weak sentences", value: checker ? { k: checker["unsupported_caught (recall)"].denominator, n: checker["unsupported_caught (recall)"].denominator } : null },
    after: { label: "Caught", value: fromRatio(checker?.["unsupported_caught (recall)"]) },
    decision: "Adopted, limited", result: "Too weak to rewrite answers on its own signal, so it flags sentences on screen for the reader to judge." },
];

function Bars({ e }: { e: Experiment }) {
  const rows = [e.before, e.after];
  return (
    <div className="exp-bars">
      {rows.map((row, index) => {
        const share = row.value && row.value.n ? row.value.k / row.value.n : 0;
        return (
          <div className={`exp-bar ${index === 1 ? "after" : ""}`} key={row.label}>
            <span className="exp-bar-label">{row.label}</span>
            <span className="exp-bar-track"><span className={e.lowerIsBetter ? "bad" : ""} style={{ width: `${share * 100}%` }} /></span>
            <span className="exp-bar-value">{of(row.value)}</span>
          </div>
        );
      })}
      <span className="fine-print">{e.measure}{e.lowerIsBetter ? " · lower is better" : ""}</span>
    </div>
  );
}

export function ExperimentLog() {
  return (
    <section className="section-block">
      <div className="section-heading"><div><div className="eyebrow">Experiment log</div><h2>Every design choice was a measured bet.</h2></div></div>
      <p className="prose muted">Each experiment started from a hypothesis, changed one thing, and was kept or dropped on the evidence. All were run on development questions; the locked test was run once, at the end.</p>
      <div className="experiment-grid">
        {EXPERIMENTS.map((e, index) => (
          <article className="card experiment-card" key={e.area}>
            <div className="experiment-top"><span className="mini-label">Experiment {index + 1} · {e.area}</span>
              <span className={`decision-tag ${e.decision === "Adopted" ? "adopted" : "limited"}`}>{e.decision}</span></div>
            <p className="experiment-hypothesis"><strong>Hypothesis.</strong> {e.hypothesis}</p>
            <p className="fine-print"><strong>Change:</strong> {e.change}</p>
            <Bars e={e} />
            <p className="experiment-result">{e.result}</p>
          </article>
        ))}
      </div>
      <div className="card model-bet">
        <div><span className="mini-label">Cost decision · answer model</span>
          <h3>The larger model was costed, not run.</h3>
          <p>Retrieval drives most of the quality, so the question was whether a larger answer model was worth its price. Measured on the same development work:</p></div>
        {costCompare && <div className="model-compare">
          <div><strong>${costCompare["gpt-4o-mini_measured_usd"]}</strong><span>GPT-4o mini, measured</span></div>
          <div className="vs">vs</div>
          <div><strong>${costCompare["gpt-4o_projected_usd"]}</strong><span>GPT-4o, projected from the same tokens</span></div>
        </div>}
      </div>
    </section>
  );
}

export function NextBets() {
  const bets = [
    { gap: "Past-date questions are the weakest type", now: `${of(pastDate)} cited the right paragraph`, next: "Make ranking date-aware and add more past-date test questions." },
    { gap: "The claim checker misses most weak sentences", now: `${of(fromRatio(checker?.["unsupported_caught (recall)"]))} caught`, next: "A stricter checking prompt or a larger checker model, re-measured on fresh labels." },
    { gap: "Some 'unanswerable' labels may be wrong", now: `${of(declined)} declined`, next: "Hand-review the locked test labels; in development, two such labels proved wrong." },
    { gap: "The graph's 'applies to' links are unreliable", now: `${of(fromRatio(fresh?.APPLIES_TO?.precision))} right`, next: "Better extraction before they are allowed near answers; kept out until then." },
    { gap: "The test set is small and AI-drafted", now: `${REPORT.answers_test?.data?.questions ?? "—"} locked questions`, next: "Grow and hand-review it, so the ranges narrow and the results firm up." },
  ];
  return (
    <section className="section-block">
      <div className="section-heading"><div><div className="eyebrow">Prioritised backlog</div><h2>Where it falls short, and the next bet for each.</h2></div></div>
      <ol className="next-bets">
        {bets.map((bet) => (
          <li key={bet.gap} className="card">
            <div><strong>{bet.gap}</strong><span className="bet-now">{bet.now}</span></div>
            <p>{bet.next}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
