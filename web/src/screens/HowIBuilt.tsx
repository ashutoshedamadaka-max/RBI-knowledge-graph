import { useState } from "react";
import { Icon, NextPage, PageIntro, SourceNote } from "../components/UI";
const DECISIONS = [
  {
    tab: "Chunking",
    title: "Keep a rule together before asking a model to interpret it.",
    body: "Splitting documents along numbered paragraphs preserves conditions and citation locations. I chose structure-aware chunks for evidence integrity, even though another strategy scored better on some retrieval measures.",
    lesson:
      "Design source preparation around the unit a reader needs to verify.",
    label: "Expected evidence spans kept intact",
    before: "Fixed-size splitting",
    after: "Paragraph-based splitting",
    a: 101,
    b: 105,
    n: 105,
    file: "chunker-comparison-provisional.json",
    caveat:
      "Provisional development comparison. All chunkers used the same legacy search setup. No confidence interval computed; this is not an answer-quality test.",
    trade:
      "The chosen strategy did not win every metric: recursive splitting had the higher mean reciprocal rank, and fixed-size splitting had higher recall at ten.",
  },
  {
    tab: "Retrieval",
    title: "Fix evidence eligibility before optimizing relevance.",
    body: "Combined keyword and meaning search found more expected passages, but it also retrieved withdrawn rules. Date filtering resolved that failure; re-ranking improved the order of eligible evidence.",
    lesson: "Treat source validity as a constraint, then optimize the search.",
    label: "Withdrawn evidence in the top five · lower is better",
    before: "Hybrid search",
    after: "With date filter",
    a: 12,
    b: 0,
    n: 13,
    file: "ladder-dev.json",
    caveat:
      "Development withdrawal-trap questions. No confidence interval computed. A zero count in a small test is not a guarantee.",
    trade:
      "The final re-ranked path found 94 of 105 expected evidence spans in the top five, but added latency and a paid model call.",
  },
  {
    tab: "Knowledge graph",
    title: "Give a complex component a narrow, measurable job.",
    body: "Following paragraph references recovered additional evidence on linked questions. Extracted “applies to” relationships were too unreliable to filter answers, so those relationships stay out of the answering path.",
    lesson:
      "Keep only the graph behavior whose contribution you can explain and test.",
    label: "Linked-question evidence in the top five",
    before: "Without graph expansion",
    after: "With graph expansion",
    a: 22,
    b: 24,
    n: 26,
    file: "ladder-graph-dev.json",
    caveat:
      "Development comparison without Cohere re-ranking. Graph-shaped questions favor this task. No confidence interval computed; combined-path held-out uplift is not measured.",
    trade:
      "The graph is useful for navigation and cross-references. Its size alone is not evidence that it improves answers.",
  },
  {
    tab: "Answer behavior",
    title: "Measure what an improvement makes worse.",
    body: "Past-date evidence was labelled with its present-day withdrawn status, which encouraged unnecessary refusals. Making the date context clearer reduced this failure on the development set.",
    lesson: "Pair every success metric with the failure it could hide.",
    label: "Answerable questions wrongly refused · lower is better",
    before: "First answer instructions",
    after: "Revised instructions",
    a: 21,
    b: 1,
    n: 92,
    file: "answers-dev-gpt-4o-mini.json",
    second: "answers-dev-gpt-4o-mini-prompt1.json",
    caveat:
      "Development comparison. Before 95% interval [0.1413, 0.3152]; after [0, 0.0326].",
    trade:
      "Refusals on truly unanswerable questions fell from 12 of 13 to 9 of 13. The improvement came with a real trade-off.",
  },
  {
    tab: "Claim checking",
    title: "Evaluate the evaluator before you trust its labels.",
    body: "A cited answer can still overgeneralize. A second model call was intended to catch this, but it missed many claims labelled not fully supported. Its labels remain advisory.",
    lesson:
      "Separate evidence coverage, answer correctness, and checker agreement.",
    label: "Not-fully-supported claims caught",
    before: "Claims labelled not fully supported",
    after: "Caught by the checker",
    a: 21,
    b: 6,
    n: 21,
    file: "claim-checker-quality.json",
    caveat:
      "Model-drafted labels; personal review not confirmed. This is checker recall, not a before/after improvement. No confidence interval computed.",
    trade:
      "A “supported” label is not human validation. I expose the source text and avoid automatically rewriting an answer on this weak signal.",
  },
];
export default function HowIBuilt() {
  const [selected, setSelected] = useState(0);
  const d = DECISIONS[selected];
  return (
    <div className="page">
      <PageIntro
        eyebrow="How I built it"
        title="Every component needed a reason to exist."
      >
        A product engineering case study: define a narrow problem, compare
        approaches, expose failure modes, and ship an experience people can
        inspect.
      </PageIntro>
      <section className="build-strip" aria-label="Build approach">
        {[
          [
            "ask",
            "Frame the problem",
            "Lending research needs source history as well as relevant text.",
          ],
          [
            "sources",
            "Build the evidence base",
            "Preserve document status, paragraph structure, and original sources.",
          ],
          [
            "evals",
            "Test the trade-offs",
            "Compare search, graph expansion, refusals, and claim checks.",
          ],
          [
            "built",
            "Deliver the product",
            "Connect a React interface, Python service, and versioned data release.",
          ],
        ].map(([icon, title, text]) => (
          <div key={title}>
            <Icon name={icon} size={24} />
            <h3>{title}</h3>
            <p>{text}</p>
          </div>
        ))}
      </section>
      <section className="section-block">
        <div className="section-heading">
          <div>
            <div className="eyebrow">The decisions</div>
            <h2>What the experiments changed.</h2>
          </div>
        </div>
        <div className="decision-tabs" aria-label="Engineering decisions">
          {DECISIONS.map((item, i) => (
            <button
              key={item.tab}
              aria-pressed={i === selected}
              aria-controls="decision-detail"
              onClick={() => setSelected(i)}
            >
              {item.tab}
            </button>
          ))}
        </div>
        <div className="decision-content" id="decision-detail">
          <div className="decision-copy rise" key={`copy-${selected}`}>
            <h2>{d.title}</h2>
            <p>{d.body}</p>
            <div className="decision-lesson">
              <strong>The transferable lesson</strong>
              {d.lesson}
            </div>
          </div>
          <div className="decision-visual" key={`visual-${selected}`}>
            <span className="eyebrow">{d.label}</span>
            {[
              [d.before, d.a],
              [d.after, d.b],
            ].map(([name, value]) => (
              <div className="compare-row" key={String(name)}>
                <div>
                  <span>{name}</span>
                  <strong>
                    {value} of {d.n}
                  </strong>
                </div>
                <div className="comparison-track" aria-hidden="true">
                  <span style={{ width: `${(Number(value) / d.n) * 100}%` }} />
                </div>
              </div>
            ))}
            <p className="fine-print">{d.caveat}</p>
            <SourceNote file={d.file}>
              n = {d.n}{" "}
              {selected === 0 || selected === 2
                ? "evidence spans"
                : selected === 4
                  ? "claims"
                  : "questions"}
            </SourceNote>
            {d.second && <SourceNote file={d.second}>Earlier run</SourceNote>}
          </div>
        </div>
        <div className="trade-off">
          <strong>The trade-off to keep in view</strong>
          <p>{d.trade}</p>
          {selected === 1 && (
            <SourceNote file="ladder-dev.json">
              n = 105 evidence spans; no interval computed
            </SourceNote>
          )}
          {selected === 3 && (
            <SourceNote file="answers-dev-gpt-4o-mini-prompt1.json">
              n = 13 unanswerable questions; before 95% interval [0.7692, 1],
              after [0.3846, 0.9231] in the revised run
            </SourceNote>
          )}
        </div>
      </section>
      <section className="section-block">
        <div className="section-heading">
          <div>
            <div className="eyebrow">System design</div>
            <h2>A small stack, with visible boundaries.</h2>
          </div>
        </div>
        <div
          className="diagram-stage architecture-diagram"
          aria-label="React frontend calls a Python research service connected to PostgreSQL storage and model providers"
        >
          <div className="diagram-node">
            <Icon name="home" size={25} />
            <strong>React + Vite</strong>
            <small>Vercel · interface</small>
          </div>
          <span className="diagram-flow">
            <Icon name="arrow" />
          </span>
          <div className="diagram-node accent">
            <Icon name="how" size={25} />
            <strong>Python + FastAPI</strong>
            <small>Render · research service</small>
          </div>
          <span className="diagram-flow">
            <Icon name="arrow" />
          </span>
          <div className="diagram-stack">
            <div className="diagram-node">
              Supabase / PostgreSQL<small>Source data</small>
            </div>
            <div className="diagram-node">
              OpenAI + Cohere<small>Embeddings, ranking, answers</small>
            </div>
          </div>
        </div>
        <div className="grid-2">
          <div className="card">
            <h3>Design for the hosting constraint</h3>
            <p className="muted">
              The evaluated corpus and graph are packaged with the application
              so restarts on a service without persistent disks can recover the
              release. Database-backed reads avoid loading unused vector
              snapshots.
            </p>
          </div>
          <div className="card">
            <h3>Keep the evidence reproducible</h3>
            <p className="muted">
              Saved runs, source manifests, and a decision log make results
              inspectable. A test attempt affected by a startup mutation was
              discarded, the corpus restored, and the incident recorded before
              the completed run.
            </p>
          </div>
        </div>
      </section>
      <section className="section-block">
        <div className="section-heading">
          <div>
            <div className="eyebrow">Next iteration</div>
            <h2>What I would validate next.</h2>
          </div>
        </div>
        <div className="grid-3">
          {[
            [
              "Independent labels",
              "Have domain reviewers grade correctness and citation scope, then resolve ambiguous test questions.",
            ],
            [
              "Controlled graph test",
              "Compare graph on and off inside the final re-ranked pipeline on new questions.",
            ],
            [
              "Operational reliability",
              "Measure live change-detection delay, concurrency, and recovery over time.",
            ],
          ].map(([title, text]) => (
            <div className="card" key={title}>
              <h3>{title}</h3>
              <p className="muted">{text}</p>
            </div>
          ))}
        </div>
      </section>
      <NextPage
        href="#testing"
        title="See how it is tested."
        text="The test process, the kinds of question, and what each measure means."
      />
    </div>
  );
}
