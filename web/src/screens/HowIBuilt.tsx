import { Report, count, headline, pct, ratio, useQuality } from "../quality";

const PHASES = [
  { phase: "0", title: "Plan", question: "What exists, what is broken, what should the product promise?",
    result: "A written rebuild plan, a decision log and eight phases, each ending at a review gate." },
  { phase: "1", title: "Rulebook and change handling", question: "Can the system tell when RBI replaces a rule?",
    result: "88 RBI documents, a daily monitor and a replay of real history: every withdrawal detected, no stale answers." },
  { phase: "2", title: "Cutting documents and writing the test", question: "How should documents be split so a rule is never cut in half?",
    result: "Four splitting methods compared; splitting along RBI's own numbered paragraphs won. A 181-question test set with dev and held-out parts." },
  { phase: "3", title: "Finding the right paragraph", question: "Which search approach finds the right paragraph most often?",
    result: "Eight approaches compared one change at a time. Combined search, the in-force filter and re-ranking were kept." },
  { phase: "4", title: "Knowledge graph", question: "Does a map of how rules connect improve answers?",
    result: "Built and measured. It helps on questions that need two linked paragraphs; one weak part is kept out of answers." },
  { phase: "5", title: "Answers and hallucination control", question: "Are answers grounded, and does the product decline when it should?",
    result: "Per-sentence citations and checks, measured on held-out questions. A prompt flaw found and fixed on the dev set." },
  { phase: "6", title: "The product", question: "Can someone outside the project understand and trust it?",
    result: "This site: the live product plus the story behind it." , open: true },
  { phase: "7", title: "Write-up", question: "What should the README and portfolio say?", result: "Next.", open: true },
];

function Decisions({ report }: { report: Report | null }) {
  const ladder = report?.ladder?.data?.results;
  const chunkers = report?.chunkers?.data?.results;
  const comparison = report?.answers_dev?.data?.model_cost_comparison;
  const fresh: any = report && Object.entries(report.graph_quality?.data?.results ?? {}).find(([key]) => key.startsWith("fresh"))?.[1];
  const checker: any = report && Object.values(report.claim_checker?.data?.by_source ?? {})[0];
  const cards = [
    { title: "How to split documents", chosen: "Along RBI's numbered paragraphs, with headings attached", rejected: "Fixed-size chunks of ~500 tokens",
      why: chunkers ? `Both found the right piece about equally often, but only paragraph-based splitting never cut a rule in half (${ratio(chunkers.structure?.boundary_accuracy)} kept whole vs ${ratio(chunkers.fixed?.boundary_accuracy)}). It also gives the paragraph numbers that citations need.` : "" },
    { title: "How to search", chosen: "Exact-word plus meaning search, merged, then re-ranked", rejected: "A single search method",
      why: ladder ? `Right paragraph in the top 5 rose from ${ratio(ladder.bm25?.["recall@5"])} (exact words) to ${ratio(ladder["rerank-cohere"]?.["recall@5"])} with the full combination.` : "" },
    { title: "Which answer model", chosen: "GPT-4o mini", rejected: "GPT-4o (the larger model)",
      why: comparison ? `Same work, measured on mini: $${comparison["gpt-4o-mini_measured_usd"]} vs $${comparison["gpt-4o_projected_usd"]} projected for GPT-4o, about ${Math.round(comparison["gpt-4o_projected_usd"] / comparison["gpt-4o-mini_measured_usd"])}× more. Retrieval drives most of the quality, so the larger model was costed but not run.` : "" },
    { title: "What to do with a weak claim", chosen: "Flag it on screen", rejected: "Rewrite the answer automatically",
      why: checker ? `The checker caught ${checker["unsupported_caught (recall)"].numerator} of ${checker["unsupported_caught (recall)"].denominator} weak claims. Rewriting on such a signal would cost more and fix little; a visible flag lets the reader judge.` : "" },
    { title: "How far to trust the knowledge graph", chosen: "Use it to follow cross-references only", rejected: "Use it to decide who a rule applies to",
      why: fresh ? `Its 'who does this apply to' links were right only ${fresh.APPLIES_TO.precision.numerator} times in ${fresh.APPLIES_TO.precision.denominator} on fresh paragraphs, so they are shown with a warning and never used in answers.` : "" },
    { title: "How wide the rulebook is", chosen: "NBFC lending only: 88 documents, done well", rejected: "All of RBI's rules at once",
      why: "A narrow scope made it possible to label answers by hand, replay real history and measure everything. Widening it is the next step, not the first." },
  ];
  return (
    <div className="grid-2">
      {cards.map((card) => (
        <div className="decision" key={card.title}>
          <span className="pm-term">Trade-off</span>
          <h3 style={{ marginTop: 6 }}>{card.title}</h3>
          <div className="choice"><div className="chosen"><strong>Chosen</strong><br />{card.chosen}</div><div className="rejected"><strong>Not chosen</strong><br />{card.rejected}</div></div>
          <p className="why">{card.why}</p>
        </div>
      ))}
    </div>
  );
}

export default function HowIBuilt() {
  const { report } = useQuality();
  const spend = report?.spend;
  const answers = report ? headline(report) : null;
  const perQuestion = answers?.results?.cost_usd?.per_question_answer_plus_rerank;
  const first = report?.answers_dev_first_prompt?.data?.results;
  const fixed = report?.answers_dev?.data?.results;
  const maxPhase = spend ? Math.max(...(Object.values(spend.by_phase_usd) as number[]), 0.01) : 1;

  return (
    <div className="page">
      <section className="hero">
        <div className="eyebrow">How I built this</div>
        <h1>A product built like a product: a clear problem, measurable goals, and a decision at every gate</h1>
        <p className="lead">I treated this as a product launch, not a coding exercise. I defined who it serves and what "good" means, shipped it in phases with a review at each one, compared options one change at a time, and kept a written log of every decision and its trade-off.</p>
      </section>

      <section>
        <h2>The brief I set myself</h2>
        <div className="grid-3">
          <div className="card kicker-card"><span className="pm-term">North-star metric</span><h3>Right rule, right paragraph</h3><p>The share of answers that cite the paragraph that actually answers the question, from the rule in force on that date.</p></div>
          <div className="card kicker-card"><span className="pm-term">Guardrail metrics</span><h3>Never quote a dead rule; decline when unsure</h3><p>Withdrawn rules cited (target: zero), and correct refusals on questions the rulebook cannot answer.</p></div>
          <div className="card kicker-card"><span className="pm-term">Constraints</span><h3>Small budget, honest numbers</h3><p>Under $20 of AI spend for the whole build and every test. No metric shown unless it comes from a saved run.</p></div>
        </div>
      </section>

      <section>
        <h2>Delivered in phases, each ending at a gate</h2>
        <p className="prose">Each phase answered one question. At every gate I reviewed the numbers and decided whether to continue, change course, or cut scope.</p>
        <ol className="timeline">
          {PHASES.map((item) => (
            <li key={item.phase} className={item.open ? "open" : ""}>
              <h3>Phase {item.phase}: {item.title}</h3>
              <div><em>{item.question}</em></div>
              <div className="result">{item.result}</div>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <h2>The decisions that shaped it</h2>
        <p className="prose">Every choice had a cheaper or simpler alternative. These are the ones that mattered most, with the evidence behind each.</p>
        <Decisions report={report} />
      </section>

      <section>
        <h2>Cost analysis</h2>
        <div className="grid-2">
          <div className="card">
            <span className="pm-term">Build cost</span>
            <h3>Total AI spend: <span className="num">{spend ? `$${spend.total_usd.toFixed(2)}` : "—"}</span> of a $20 budget</h3>
            <p className="muted">Every paid call is logged. Re-ranking ran on a free trial key during testing.</p>
            {spend && Object.entries(spend.by_phase_usd as Record<string, number>).map(([phase, usd]) => (
              <div className="bar-row" key={phase}><span>Phase {phase}</span><div className="bar" role="img" aria-label={`Phase ${phase}: $${usd.toFixed(3)}`}><span style={{ width: `${(usd / maxPhase) * 100}%` }} /></div><span className="num">${usd.toFixed(2)}</span></div>
            ))}
            <p className="muted">The largest single cost was building the knowledge graph: one AI call for each of about 1,950 paragraphs.</p>
          </div>
          <div className="card">
            <span className="pm-term">Unit economics</span>
            <h3>Running cost: <span className="num">{perQuestion ? `$${(perQuestion * 1000).toFixed(2)}` : "—"}</span> per 1,000 questions</h3>
            <p>That covers writing the answer, checking every sentence, and re-ranking at the paid list price. Search itself costs a fraction of a cent per question; the one-off cost of preparing the whole rulebook for meaning search was about two cents.</p>
            <p className="muted">Speed is the trade-off still being worked on: an answer currently appears in roughly 10 to 13 seconds, most of it the answer model reading its evidence.</p>
          </div>
        </div>
      </section>

      <section>
        <h2>What went wrong, and what I changed</h2>
        <p className="prose">Testing exists to find problems. These are real ones, each found by a measurement and fixed with another.</p>
        <div className="grid-2">
          <div className="card">
            <span className="pm-term">Iteration</span>
            <h3>It refused too often</h3>
            <p>The first full test showed the product declining questions it could answer. The cause: evidence for past dates was labelled "withdrawn" (true today, not then), so the AI refused to use it. One change to how evidence is labelled fixed it.</p>
            {first && fixed && <div className="before-after">
              <div className="side"><div className="muted">Before</div><div className="big"><span className="num">{pct(first.answerable_wrongly_refused.value)}</span></div><div className="muted">wrongly declined</div></div>
              <div aria-hidden>→</div>
              <div className="side"><div className="muted">After</div><div className="big"><span className="num">{pct(fixed.answerable_wrongly_refused.value)}</span></div><div className="muted">wrongly declined</div></div>
            </div>}
            {first && fixed && <p className="muted">The cost of the fix: it declined slightly fewer truly unanswerable questions ({pct(first.unanswerable_refused.value)} → {pct(fixed.unanswerable_refused.value)} on the dev set). A deliberate, measured trade-off.</p>}
          </div>
          <div className="card">
            <span className="pm-term">Performance</span>
            <h3>It was slow</h3>
            <p>Early answers took over 30 seconds. Measuring each step showed the search indexes were rebuilt for every question. Building them once at start-up, and showing the answer while it is still being written, brought the first words to about 10 seconds.</p>
            <div className="before-after">
              <div className="side"><div className="muted">Before</div><div className="big"><span className="num">~33 s</span></div><div className="muted">to an answer</div></div>
              <div aria-hidden>→</div>
              <div className="side"><div className="muted">After</div><div className="big"><span className="num">~10 s</span></div><div className="muted">to first words</div></div>
            </div>
          </div>
          <div className="card">
            <span className="pm-term">Risk management</span>
            <h3>A test run was nearly contaminated</h3>
            <p>An old start-up routine silently rewrote part of the rulebook while the final test was running. I stopped the run, discarded it unseen, restored the data from its backup, fixed the cause and logged it. The published test result comes from a clean rerun.</p>
          </div>
          <div className="card">
            <span className="pm-term">Honest limits</span>
            <h3>Two parts are weaker than I wanted</h3>
            <p>The claim checker misses most over-generalised sentences, and the graph's "who does this apply to" links are right only about a third of the time. Both are measured, both are shown openly, and neither is relied on to produce an answer.</p>
          </div>
        </div>
      </section>

      <section>
        <h2>How I kept it honest</h2>
        <div className="grid-3">
          <div className="card kicker-card"><span className="pm-term">Experiment design</span><h3>One change at a time</h3><p>Every comparison changed exactly one thing, so each gain can be credited to its cause.</p></div>
          <div className="card kicker-card"><span className="pm-term">Held-out test</span><h3>A test the system never saw</h3><p>A third of the questions were locked away and used once, at the end. Tuning happened only on the rest.</p></div>
          <div className="card kicker-card"><span className="pm-term">Data provenance</span><h3>Labels are traceable</h3><p>Answer keys come from RBI's own text. Labels I wrote by hand and labels an AI drafted and I checked are kept and reported separately.</p></div>
        </div>
      </section>

      <section>
        <h2>What's next</h2>
        <ol className="prose">
          <li><strong>Faster first words:</strong> give the answer model less surrounding text, after measuring that quality holds.</li>
          <li><strong>A stronger claim checker:</strong> a stricter prompt or a larger model, re-measured on fresh labels.</li>
          <li><strong>A wider rulebook:</strong> banks and co-operative banks, now that the method is proven on NBFC rules.</li>
          <li><strong>"What changed" views:</strong> paragraph-by-paragraph comparison of a replaced rule and its successor.</li>
        </ol>
        <p className="muted">Answers on the held-out test: {answers ? count(answers.results.question_all_gold_cited) : "—"} cited the right paragraph. Every number on this page is read from the saved evaluation runs when the page loads.</p>
      </section>
    </div>
  );
}
