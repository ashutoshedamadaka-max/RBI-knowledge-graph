import { REPORT } from "../quality";
import { SourceNote } from "./UI";
import "../eval-showcase.css";

/* The model's vital signs, as an AI product team tracks them: retrieval quality, answer accuracy, latency,
   cost and reliability. Every value is read from the saved runs; the technical name sits beside the plain one. */

type Count = { k: number; n: number };
const fromRate = (rate: any): Count | null => (rate && rate.value != null ? { k: Math.round(rate.value * rate.n), n: rate.n } : null);
const fromRatio = (m: any): Count | null => (m ? { k: m.numerator, n: m.denominator } : null);
const pctOf = (c: Count | null) => (c && c.n ? `${Math.round((c.k / c.n) * 100)}%` : "—");
const of = (c: Count | null) => (c ? `${c.k} of ${c.n}` : "—");
const seconds = (ms?: number) => (ms != null ? `${(ms / 1000).toFixed(1)} s` : "—");
const usd = (value?: number) => (value != null ? `$${value.toFixed(4)}` : "—");

interface Health { name: string; term: string; value: string; meaning: string; set: string; tone?: "good" | "watch" }

export default function SystemHealth() {
  const testData = REPORT.answers_test?.data ?? {};
  const test = testData.results ?? {};
  const ladder = REPORT.ladder?.data?.results ?? {};
  const chosen = ladder["rerank-cohere"] ?? {};
  const beforeRerank = ladder["hybrid+as-of"] ?? {};
  const replay = REPORT.replay?.data ?? {};
  const costCompare = REPORT.answers_dev?.data?.model_cost_comparison;
  const questions = testData.questions ?? 0;

  const sentences = fromRate(test.gold_sentence_cited);
  const fullyCovered = fromRate(test.question_all_gold_cited);
  const withdrawn = fromRate(test.withdrawn_trap_cited_withdrawn);
  const declined = fromRate(test.unanswerable_refused);
  const wronglyRefused = fromRate(test.answerable_wrongly_refused);
  const claims = test["claims_by_checker (not yet validated)"] ?? {};
  const checked = (claims.supported ?? 0) + (claims.partially_supported ?? 0) + (claims.not_supported ?? 0);
  // Answerable questions it answered, plus out-of-scope questions it declined, over both groups.
  const decisions = wronglyRefused && declined
    ? { k: wronglyRefused.n - wronglyRefused.k + declined.k, n: wronglyRefused.n + declined.n } : null;
  const perQuestion = test.cost_usd?.per_question_answer_plus_rerank;

  const groups: { title: string; intro: string; items: Health[] }[] = [
    {
      title: "Retrieval quality",
      intro: "Does search put the right RBI paragraph in front of the answer model? Development questions, chosen pipeline.",
      items: [
        { name: "Right paragraph in the top 5", term: "Recall@5", value: pctOf(fromRatio(chosen["recall@5"])), tone: "good", set: "Development",
          meaning: `${of(fromRatio(chosen["recall@5"]))} answer-key sentences were among the five passages handed to the model.` },
        { name: "Right paragraph in the top 10", term: "Recall@10", value: pctOf(fromRatio(chosen["recall@10"])), set: "Development",
          meaning: `${of(fromRatio(chosen["recall@10"]))}: what a wider net would add.` },
        { name: "How high the first right paragraph ranks", term: "MRR", value: chosen.mrr != null ? chosen.mrr.toFixed(2) : "—", set: "Development",
          meaning: "1.00 means it is always ranked first; 0.50 means second on average." },
        { name: "Quality of the whole ranking", term: "nDCG@10", value: chosen["ndcg@10"] != null ? chosen["ndcg@10"].toFixed(2) : "—", set: "Development",
          meaning: "Rewards putting every right paragraph near the top; 1.00 is a perfect order." },
      ],
    },
    {
      title: "Answer accuracy",
      intro: "Is the answer grounded in the right evidence, and does it know when not to answer? Locked test questions.",
      items: [
        { name: "Expected evidence cited", term: "Citation recall", value: pctOf(sentences), tone: "good", set: "Locked test",
          meaning: `${of(sentences)} answer-key sentences were inside the passages the answers cited; ${of(fullyCovered)} questions fully covered.` },
        { name: "Sentences supported by their source", term: "Groundedness (checker)", value: checked ? `${Math.round(((claims.supported ?? 0) / checked) * 100)}%` : "—", tone: "watch", set: "Locked test",
          meaning: `${claims.supported ?? "—"} of ${checked} checked sentences fully supported, ${claims.partially_supported ?? "—"} partly, ${claims.not_supported ?? "—"} not. The checker itself is imperfect.` },
        { name: "Right call: answer or decline", term: "Decision accuracy", value: pctOf(decisions), tone: "good", set: "Locked test",
          meaning: `${of(decisions)} questions handled correctly: answering those it could, declining those outside the rulebook.` },
        { name: "Withdrawn rules quoted", term: "Stale-rule rate", value: withdrawn ? String(withdrawn.k) : "—", tone: "good", set: "Locked test",
          meaning: `${of(withdrawn)} trick questions. Target: zero.` },
      ],
    },
    {
      title: "Latency",
      intro: "How long a question takes, end to end and by stage. Testing used a free, rate-limited re-ranking key, which inflates the slowest cases.",
      items: [
        { name: "Typical question", term: "p50 latency", value: seconds(test.latency_ms_p50), set: "Locked test",
          meaning: "Half of all questions got a complete, checked answer faster than this." },
        { name: "Slow questions", term: "p95 latency", value: seconds(testData.latency_ms_p95), tone: "watch", set: "Locked test",
          meaning: "19 in every 20 questions finished within this time." },
        { name: "Search, before re-ranking", term: "Retrieval p50 / p95", value: `${seconds(beforeRerank.latency_ms?.p50)} / ${seconds(beforeRerank.latency_ms?.p95)}`, set: "Development",
          meaning: "Keyword and meaning search, cross-references and the date filter." },
        { name: "Search, including re-ranking", term: "Retrieval p50 / p95", value: `${seconds(chosen.latency_ms?.p50)} / ${seconds(chosen.latency_ms?.p95)}`, set: "Development",
          meaning: "The wide spread comes from the trial key's rate limit; a paid key removes the waits." },
      ],
    },
    {
      title: "Cost",
      intro: "Model-service charges from reported usage at list prices. Hosting is excluded.",
      items: [
        { name: "Per question, all model services", term: "Cost per query", value: usd(perQuestion), tone: "good", set: "Locked test",
          meaning: "Search, re-ranking, writing the answer and checking every sentence." },
        { name: "Per 1,000 questions", term: "Unit cost", value: perQuestion ? `$${(perQuestion * 1000).toFixed(2)}` : "—", set: "Locked test",
          meaning: "The figure to budget against." },
        { name: "Re-ranking share", term: "Retrieval cost per query", value: usd(chosen.cost_per_query_usd), set: "Development",
          meaning: "The largest single cost per question, at the paid list price." },
        { name: "Answer model: mini vs larger", term: "Model cost per query", set: "Development",
          value: costCompare ? `${usd(costCompare.per_question?.["gpt-4o-mini"])} vs ${usd(costCompare.per_question?.["gpt-4o (projected)"])}` : "—",
          meaning: "GPT-4o mini measured; GPT-4o projected from the same tokens." },
      ],
    },
    {
      title: "Reliability",
      intro: "Did the pipeline run as designed on every question?",
      items: [
        { name: "Questions that failed to run", term: "Error rate", value: `${(testData.failed_questions ?? []).length} of ${questions}`, tone: "good", set: "Locked test",
          meaning: "Errors, timeouts or crashes during the locked test run." },
        { name: "Questions that skipped re-ranking", term: "Degraded runs", value: `${(testData.questions_without_rerank ?? []).length} of ${questions}`, tone: "good", set: "Locked test",
          meaning: "Every question went through the full pipeline, including re-ranking and the refusal rule." },
        { name: "Withdrawals caught in a history replay", term: "Change-detection recall", value: of(fromRatio(replay.withdrawal_detection?.recall)), tone: "good", set: "Replay",
          meaning: `${replay.withdrawal_detection?.false_alarms ?? "—"} false alarms; ${of(fromRatio(replay.stale_answer_rate?.evidence))} replayed answers used a rule already out of force.` },
      ],
    },
  ];

  return (
    <section className="section-block">
      <div className="section-heading"><div><div className="eyebrow">System health</div><h2>How the model is performing, stage by stage.</h2></div></div>
      <p className="prose muted">
        The vital signs an AI product team tracks: is the right evidence found, is the answer grounded in it, how fast, at what
        cost, and how reliably. Technical names are shown beside the plain ones for reviewers who know them.
      </p>
      <div className="health-groups">
        {groups.map((group) => (
          <div className="health-group" key={group.title}>
            <div className="health-group-head"><h3>{group.title}</h3><p>{group.intro}</p></div>
            <div className="health-grid">
              {group.items.map((item) => (
                <div className={`health-card ${item.tone ?? ""}`} key={item.name}>
                  <div className="health-top"><span className="tech-term">{item.term}</span><span className="health-set">{item.set}</span></div>
                  <strong>{item.value}</strong>
                  <span className="health-name">{item.name}</span>
                  <p>{item.meaning}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <SourceNote file="answers-test-gpt-4o-mini.json">Locked test run</SourceNote>
      <SourceNote file="ladder-dev.json">Retrieval experiments, development set</SourceNote>
    </section>
  );
}
