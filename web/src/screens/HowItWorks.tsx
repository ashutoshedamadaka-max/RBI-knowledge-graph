import { useEffect, useState } from "react";
import { Icon, NextPage, PageIntro, SourceNote } from "../components/UI";

const STEPS = [
  {
    title: "Question & date",
    icon: "ask",
    input: "A lending question",
    middle: ["The question", "The research date"],
    output: "A research request",
    what: "A question starts with a scope and a date.",
    body: "A rule can be valid for a past loan and withdrawn today. You can ask about the latest indexed rules or choose a historical date.",
    why: "The date is part of the question, not an afterthought.",
    evidence:
      "The same question can be researched at different dates. This is a product capability, not a measured accuracy claim.",
  },
  {
    title: "Search two ways",
    icon: "search",
    input: "Your question",
    middle: ["Exact words", "Meaning"],
    output: "Combined candidates",
    what: "Find precise terms and the meaning behind them.",
    body: "Keyword search finds exact regulatory language. OpenAI embeddings find similar meaning. Reciprocal rank fusion merges the lists without asking either method to do every job.",
    why: "Different search methods have different blind spots.",
    evidence:
      "Expected evidence in the top five: 62 of 105 with keyword search; 81 of 105 with combined search. Development set; no confidence interval computed.",
    file: "ladder-dev.json",
  },
  {
    title: "Follow references",
    icon: "graph",
    input: "A source paragraph",
    middle: ["“See paragraph…”", "Linked provision"],
    output: "Related evidence",
    what: "Follow the links a paragraph already contains.",
    body: "The knowledge graph adds provisions referenced by search results. It helps recover evidence that matters because of a relationship, even when the wording is different.",
    why: "Use the graph for a specific retrieval job.",
    evidence:
      "Linked-question evidence in the top five: 22 of 26 without the graph, 24 of 26 with it. Development comparison without re-ranking; no interval computed.",
    file: "ladder-graph-dev.json",
  },
  {
    title: "Check validity",
    icon: "sources",
    input: "Retrieved candidates",
    middle: ["Out of force", "Valid on date"],
    output: "Eligible evidence",
    what: "Remove evidence that did not apply on the date.",
    body: "Document status and in-force dates determine whether a passage can be used. Withdrawn documents remain available for historical questions when their recorded dates allow it.",
    why: "A relevant paragraph can still be the wrong version.",
    guard: true,
    evidence:
      "Withdrawn evidence reached the top five on 12 of 13 traps before filtering and 0 of 13 after filtering. Development set; no interval computed.",
    file: "ladder-dev.json",
  },
  {
    title: "Re-rank evidence",
    icon: "evals",
    input: "Eligible passages",
    middle: ["Read with question", "Reorder by relevance"],
    output: "Strongest matches",
    what: "Give the strongest evidence a second look.",
    body: "Cohere Rerank reads the candidate passages with the question and moves the strongest matches to the top. This adds a model call and cost.",
    why: "Judge quality, latency, and cost together.",
    evidence:
      "Expected evidence in the top five: 92 of 105 before re-ranking, 94 of 105 after. Development set; no interval computed.",
    file: "ladder-dev.json",
  },
  {
    title: "Answer or decline",
    icon: "ask",
    input: "Best evidence match",
    middle: ["Enough evidence?", "Too weak?"],
    output: "Answer or decline",
    what: "Make room for “I cannot answer that.”",
    body: "A weak best match can trigger a refusal before generation. The answer model may also decline. This helps contain unsupported answers, but the decision is imperfect.",
    why: "Evaluate both missed answers and unwanted answers.",
    guard: true,
    evidence:
      "5 of 7 unanswerable held-out questions were refused (95% interval [0.2857, 1]); 1 of 49 answerable questions was wrongly refused (95% interval [0, 0.0612]).",
    file: "answers-test-gpt-4o-mini.json",
  },
  {
    title: "Write & cite",
    icon: "sources",
    input: "Selected evidence",
    middle: ["A concise answer", "Passage citations"],
    output: "Inspectable claims",
    what: "Keep the answer connected to its sources.",
    body: "GPT-4o mini writes from selected passages and attaches citations. Each citation opens the source text so the reader can check conditions and scope.",
    why: "Citations make inspection possible; they do not prove correct interpretation.",
    evidence:
      "51 of 57 expected evidence sentences appeared in cited passages on the held-out set. 95% interval [0.807, 0.9649].",
    file: "answers-test-gpt-4o-mini.json",
  },
  {
    title: "Check the claims",
    icon: "check",
    input: "Answer + citations",
    middle: ["Compare to source", "Attach check labels"],
    output: "Answer with limits",
    what: "Show a second opinion, with its limitations.",
    body: "Another GPT-4o mini call labels each claim supported, partly supported, or unsupported by its citations. These labels are shown to the reader; they do not automatically rewrite the answer.",
    why: "A checker needs to be evaluated as carefully as the system it checks.",
    guard: true,
    evidence:
      "The checker caught 6 of 21 claims labelled not fully supported. Labels were model-drafted; no confirmed personal-review ground truth or confidence interval.",
    file: "claim-checker-quality.json",
  },
];
export default function HowItWorks({ active = true }: { active?: boolean }) {
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!active) setPlaying(false);
  }, [active]);
  const [reduced, setReduced] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const m = matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => setReduced(m.matches);
    m.addEventListener("change", change);
    return () => m.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    if (!playing || reduced) return;
    const timer = setInterval(
      () =>
        setStep((s) => {
          if (s === STEPS.length - 1) {
            setPlaying(false);
            return s;
          }
          return s + 1;
        }),
      6500,
    );
    const hide = () => {
      if (document.hidden) setPlaying(false);
    };
    document.addEventListener("visibilitychange", hide);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", hide);
    };
  }, [playing, reduced]);
  const chosen = STEPS[step];
  const select = (i: number) => {
    setStep(i);
    setPlaying(false);
  };
  return (
    <div className="page">
      <PageIntro
        eyebrow="How it works"
        title="From a question to evidence you can inspect."
      >
        A visual tour of the research pipeline. Choose a step to explore it, or
        play the walkthrough at your own pace.
      </PageIntro>
      <section
        className="walkthrough"
        aria-label="Interactive research pipeline"
      >
        <div className="step-nav" aria-label="Pipeline steps">
          {STEPS.map((s, i) => (
            <button
              key={s.title}
              aria-pressed={step === i}
              aria-controls="pipeline-detail"
              onClick={() => select(i)}
            >
              <span className="step-number">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span>{s.title}</span>
              {s.guard && <span className="guard-marker">Check</span>}
            </button>
          ))}
        </div>
        <div className="walkthrough-stage" id="pipeline-detail">
          <div
            className="diagram-stage"
            key={step}
            aria-label={`Illustration: ${chosen.input} to ${chosen.middle.join(" and ")} to ${chosen.output}`}
          >
            <div className="diagram-node">
              <Icon name={chosen.icon} size={26} />
              <strong>{chosen.input}</strong>
            </div>
            <span className="diagram-flow">
              <Icon name="arrow" />
            </span>
            <div className="diagram-stack">
              {chosen.middle.map((label, i) => (
                <div
                  className={`diagram-node ${step === 3 && i === 0 ? "struck" : "accent"}`}
                  key={label}
                  style={{ animationDelay: `${i * 120}ms` }}
                >
                  {label}
                </div>
              ))}
            </div>
            <span className="diagram-flow">
              <Icon name="arrow" />
            </span>
            <div className="diagram-node">
              <Icon name={step === 7 ? "check" : "sources"} size={26} />
              <strong>{chosen.output}</strong>
            </div>
          </div>
          <div className="eyebrow">
            Step {step + 1} / {STEPS.length}
            {chosen.guard ? " · Quality check" : ""}
          </div>
          <h2>{chosen.what}</h2>
          <p>{chosen.body}</p>
          <p>
            <strong>{chosen.why}</strong>
          </p>
          <div className="step-evidence">
            <p>{chosen.evidence}</p>
            {chosen.file && <SourceNote file={chosen.file} />}
          </div>
          <div className="step-controls">
            <button
              className="secondary"
              disabled={step === 0}
              onClick={() => select(step - 1)}
            >
              Previous
            </button>
            {!reduced && (
              <button
                className="text-link"
                onClick={() => {
                  if (step === STEPS.length - 1) setStep(0);
                  setPlaying(!playing);
                }}
              >
                <Icon name="play" size={14} />
                {playing ? "Pause tour" : "Play tour"}
              </button>
            )}
            <button
              className="secondary"
              disabled={step === STEPS.length - 1}
              onClick={() => select(step + 1)}
            >
              Next <Icon name="arrow" size={14} />
            </button>
            <span className="fine-print">
              {playing
                ? "Playing · select a step to pause"
                : "Explore at your own pace"}
            </span>
          </div>
        </div>
      </section>
      <section className="section-block">
        <div className="section-heading">
          <div>
            <div className="eyebrow">A separate workflow</div>
            <h2>Keep the source history connected.</h2>
          </div>
          <a className="text-link" href="#sources">
            Inspect the library <Icon name="arrow" size={15} />
          </a>
        </div>
        <div className="loop">
          {[
            [
              "Observe",
              "Check official pages for withdrawal notices and replacement statements.",
            ],
            [
              "Compare",
              "Detect changes to source content and recorded status.",
            ],
            [
              "Resolve",
              "Trust explicit replacement evidence. Queue uncertain matches for review.",
            ],
            [
              "Retain",
              "Retire the old rule for current questions and preserve it for history.",
            ],
          ].map(([title, text], i) => (
            <div className="loop-step" key={title}>
              <span>{String(i + 1).padStart(2, "0")}</span>
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
          ))}
        </div>
        <p className="fine-print" style={{ marginTop: 18 }}>
          The monitoring schedule is configured. A historical replay tests the
          logic; it does not establish a live detection-time guarantee.
          Published replacement links and inferred suggestions have different
          trust levels.
        </p>
        <SourceNote file="replay-report.json">
          Replay results and assumptions
        </SourceNote>
      </section>
      <NextPage
        href="#built"
        title="Why build it this way?"
        text="Explore the choices, experiments, and trade-offs behind the system."
      />
    </div>
  );
}
