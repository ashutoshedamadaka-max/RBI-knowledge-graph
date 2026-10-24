import { useEffect, useMemo, useRef, useState } from "react";
import { Claim, PipelineStep, QueryResult, streamQuery } from "../api";
import LivePipeline from "../components/LivePipeline";
import { Icon, PageIntro, SourceNote } from "../components/UI";
import saved from "../data/example.json";
const EXAMPLES = [
  {
    label: "A current rule",
    query:
      "Can a non-banking financial company capitalise penal charges on a loan?",
    date: "",
  },
  {
    label: "A past date",
    query: "What were the rules on default loss guarantee in digital lending?",
    date: "2024-06-01",
  },
  {
    label: "Outside this corpus",
    query:
      "What is the role of CareEdge Global IFSC Limited as an External Credit Assessment Institution under Basel III?",
    date: "",
  },
];
const STAGES: Record<string, string> = {
  understanding_question: "Reading your question",
  retrieving_official_evidence: "Finding source passages",
  checking_regulatory_validity: "Checking which rules applied",
  selecting_authoritative_evidence: "Ranking the evidence",
  building_grounded_answer: "Writing a cited answer",
  checking_claims: "Checking claims against sources",
};
const VERDICTS = {
  supported: "Model check: supported",
  partially_supported: "Model check: partly supported",
  not_supported: "Model check: not supported",
};
export default function Ask({ active = true }: { active?: boolean }) {
  const [query, setQuery] = useState("");
  const [date, setDate] = useState("");
  const [history, setHistory] = useState(false);
  const [mode, setMode] = useState<"live" | "saved">("live");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [submitted, setSubmitted] = useState("");
  const [stage, setStage] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const [openChunk, setOpenChunk] = useState<string | null>(null);
  const [activeClaim, setActiveClaim] = useState<Claim | null>(null);
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  const [firstTextMs, setFirstTextMs] = useState<number | null>(null);
  const [answerMs, setAnswerMs] = useState<number | null>(null);
  const controller = useRef<AbortController | null>(null);
  const citationTrigger = useRef<HTMLElement | null>(null);
  const passageRef = useRef<HTMLElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const evidence = useMemo(
    () =>
      new Map([...steps.flatMap(s => s.evidence ?? []), ...(result?.retrieved_evidence ?? [])].map((c) => [c.chunk_id, c])),
    [result, steps],
  );
  const openPassage = openChunk ? evidence.get(openChunk) : undefined;
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (!busy) return;
    const started = Date.now();
    const id = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    return () => clearInterval(id);
  }, [busy]);
  useEffect(() => {
    if (!active) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && openChunk) {
        setOpenChunk(null);
        citationTrigger.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [active, openChunk]);
  async function ask() {
    if (controller.current || query.trim().length < 3) return;
    const abort = new AbortController();
    const requestedAt = performance.now();
    controller.current = abort;
    const timer = window.setTimeout(() => abort.abort("timeout"), 180000);
    setMode("live");
    setBusy(true);
    setElapsed(0);
    setError(null);
    setResult(null);
    setDraft(null);
    setOpenChunk(null);
    setActiveClaim(null);
    setSteps([]);
    setFirstTextMs(null);
    setAnswerMs(null);
    setSubmitted(query.trim());
    setStage("understanding_question");
    try {
      const answer = await streamQuery(
        query.trim(),
        history && date ? date : null,
        (next) => {
          if (controller.current === abort) setStage(next);
        },
        (preview) => {
          if (controller.current !== abort) return;
          setDraft(null);
          setResult(preview);
          setAnswerMs(performance.now() - requestedAt);
        },
        (next) => {
          if (controller.current === abort) {
            setDraft(next);
            if (next.trim()) setFirstTextMs(value => value ?? performance.now() - requestedAt);
          }
        },
        abort.signal,
        (step) => {
          if (controller.current !== abort) return;
          setSteps(previous => previous.some(s => s.id === step.id) ? previous.map(s => s.id === step.id ? step : s) : [...previous, step]);
        },
      );
      if (controller.current === abort) {
        setResult(answer);
        if (answer.trace.stages) setSteps(answer.trace.stages);
      }
    } catch (e) {
      if (controller.current !== abort) return;
      setError(
        abort.signal.aborted
          ? abort.signal.reason === "timeout"
            ? "This request took too long. Please retry, or explore the saved example."
            : "Research stopped. You can edit your question and try again."
          : e instanceof TypeError
            ? "Could not connect to the research service. Please retry, or explore the saved example while it is unavailable."
            : e instanceof Error
              ? e.message
              : "Research could not finish. Please try again.",
      );
    } finally {
      clearTimeout(timer);
      if (controller.current === abort) {
        setBusy(false);
        controller.current = null;
      }
    }
  }
  function stopResearch() {
    const pending = controller.current;
    controller.current = null;
    pending?.abort();
    setBusy(false);
    setError("Research stopped. You can edit your question and try again.");
  }
  function openCitation(id: string, claim?: Claim) {
    citationTrigger.current = document.activeElement as HTMLElement;
    setOpenChunk(id);
    if (claim) setActiveClaim(claim);
    requestAnimationFrame(() => {
      passageRef.current?.focus({ preventScroll: true });
      if (passageRef.current)
        passageRef.current?.scrollIntoView({
          behavior: "instant",
          block: "start",
        });
    });
  }
  function renderClaim(claim: Claim, key: string) {
    return (
      <div
        className={`claim ${activeClaim === claim ? "active" : ""}`}
        key={key}
      >
        <p>{claim.text}</p>
        <div className={`claim-verdict ${claim.support ?? "unchecked"}`}>
          <span className={`dot ${claim.support ?? ""}`} />
          {claim.support
            ? VERDICTS[claim.support]
            : busy
              ? "Model check pending"
              : "Not checked"}
        </div>
        <div className="citation-list">
          {claim.citation_ids.map((id) => {
            const c = evidence.get(id);
            return (
              <button
                key={id}
                className="citation"
                onClick={() => openCitation(id, claim)}
                aria-label={`Read source: ${c?.document_title ?? "passage"}, paragraph ${c?.paragraph_ref ?? "unavailable"}`}
              >
                <Icon name="sources" size={14} />
                {c?.paragraph_ref
                  ? `Paragraph ${c.paragraph_ref}`
                  : "Read source"}
                <Icon name="arrow" size={13} />
              </button>
            );
          })}
        </div>
      </div>
    );
  }
  return (
    <div className="page research-page">
      <PageIntro eyebrow="Research workspace" title="Start with a question.">
        Find the rule, read the cited passage, and judge the answer for
        yourself. The corpus focuses on non-banking financial company (NBFC)
        lending.
      </PageIntro>
      <div className="research-composer card">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask();
          }}
        >
          <label htmlFor="research-question" className="input-label">
            What would you like to understand?
          </label>
          <textarea
            ref={input}
            id="research-question"
            className="question"
            maxLength={4000}
            placeholder="For example, can a lender add interest to penal charges?"
            value={query}
            disabled={busy}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="composer-actions">
            <div className="date-control">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={history}
                  disabled={busy}
                  onChange={(e) => setHistory(e.target.checked)}
                />
                Research a past date
              </label>
              {history ? (
                <label className="field date-field">
                  <span className="sr-only">Research date</span>
                  <input
                    type="date"
                    required
                    max={new Date().toISOString().slice(0, 10)}
                    value={date}
                    disabled={busy}
                    onChange={(e) => setDate(e.target.value)}
                  />
                </label>
              ) : (
                <span className="fine-print">
                  Uses the latest indexed status
                </span>
              )}
            </div>
            {busy ? (
              <button
                className="secondary"
                type="button"
                onClick={(event) => {
                  event.preventDefault();
                  stopResearch();
                }}
              >
                Stop research
              </button>
            ) : (
              <button className="primary" disabled={query.trim().length < 3}>
                Research question <Icon name="arrow" size={18} />
              </button>
            )}
          </div>
        </form>
        <div className="example-row">
          <span className="mini-label">Try a question</span>
          {EXAMPLES.map((ex) => (
            <button
              className="example-pill"
              key={ex.label}
              disabled={busy}
              onClick={() => {
                setQuery(ex.query);
                setDate(ex.date);
                setHistory(Boolean(ex.date));
                input.current?.focus();
              }}
            >
              {ex.label}
              <Icon name="arrow" size={13} />
            </button>
          ))}
        </div>
      </div>
      <div className="saved-example-bar">
        <span>
          <Icon name="play" size={16} />
          Want to explore without waiting?
        </span>
        <button
          className="text-link"
          disabled={busy}
          onClick={() => setMode(mode === "saved" ? "live" : "saved")}
        >
          {mode === "saved" ? "Return to live research" : "Open a saved answer"}
          <Icon name="arrow" size={16} />
        </button>
      </div>
      {mode === "saved" ? (
        <SavedExample />
      ) : (
        <>
          {submitted && <LivePipeline steps={steps} busy={busy} elapsed={elapsed} firstTextMs={firstTextMs} answerMs={answerMs} result={result} error={error} onOpen={openCitation} highlighted={new Set(activeClaim?.citation_ids ?? [])} />}
          {busy && !steps.length && (
            <div className="research-progress">
              <div className="progress-heading" role="status">
                <span className="spinner" />
                {STAGES[stage] ?? "Researching"}
                <span className="elapsed">{elapsed}s elapsed</span>
              </div>
              <p>
                {elapsed >= 25
                  ? "The service may be waking up or processing a longer answer. You can explore other pages; your research stays here."
                  : "Sources arrive first. Model-check labels follow when the check finishes."}
              </p>
            </div>
          )}
          {error && (
            <div className="notice error-notice" role="alert">
              <strong>{result ? "The answer is incomplete. " : ""}</strong>
              {error}
            </div>
          )}
          {!result && !draft && !busy && !error && (
            <div className="research-empty">
              <div className="empty-orbit" aria-hidden="true">
                <Icon name="ask" size={32} />
              </div>
              <h2>Your answer begins with evidence.</h2>
              <p>
                Enter a question above, or open a saved answer to explore how
                citations and checks work.
              </p>
              <div className="research-steps">
                <span>
                  <b>01</b> Ask about a rule
                </span>
                <span>
                  <b>02</b> Inspect its sources
                </span>
                <span>
                  <b>03</b> Review the limits
                </span>
              </div>
            </div>
          )}
          {draft && !result && (
            <article className="card answer-card">
              <span className="eyebrow">Draft · not yet checked</span>
              <h2>{submitted}</h2>
              <p>{draft}</p>
            </article>
          )}
          {(result || openPassage) && (
            <div className={`answer-layout ${!result ? "source-preview-layout" : ""}`}>
              {result && <article className="card answer-card">
                <div className="eyebrow">
                  {busy || error
                    ? "Answer · checks incomplete"
                    : "Research result"}
                </div>
                <h2>{result.research?.display_title ?? submitted}</h2>
                <p className="answer-meta">
                  Research date: {result.as_of ?? "latest indexed status"} ·{" "}
                  {result.pipeline.selected_evidence_count} retrieved passages
                </p>
                <details className="question-detail">
                  <summary>Your question</summary>
                  <p>{submitted}</p>
                </details>
                {result.notices.map((notice, i) => (
                  <div key={i} className={`notice ${notice.kind}`}>
                    <strong>
                      {notice.kind === "upcoming"
                        ? "Not yet in force"
                        : notice.kind === "replaced"
                          ? "Replacement found"
                          : "Withdrawal found"}
                    </strong>
                    <p>{notice.text}</p>
                  </div>
                ))}
                {result.research?.status === "grounded" ? (
                  <>
                    {result.research.direct_answer &&
                      renderClaim(result.research.direct_answer, "direct")}
                    {result.research.sections.map((s) => (
                      <section className="answer-section" key={s.id}>
                        <h3>{s.title}</h3>
                        {s.claims.map((c, i) => renderClaim(c, `${s.id}-${i}`))}
                      </section>
                    ))}
                  </>
                ) : (
                  <div className="refusal">
                    <h3>Not enough evidence to answer</h3>
                    <p>
                      {result.research?.direct_answer?.text ??
                        "The indexed sources did not provide enough evidence for this question."}
                    </p>
                    <p className="muted">
                      Try a narrower question about NBFC lending, or choose
                      another research date. A refusal can also be mistaken.
                    </p>
                  </div>
                )}
                <div className="answer-caution">
                  Model checks can miss errors. Read the cited text and its
                  scope before relying on the answer.
                </div>
              </article>}
              <aside
                className="card evidence-panel"
                ref={passageRef}
                tabIndex={-1}
                aria-label="Source evidence"
              >
                <div className="panel-heading">
                  <h2>Source evidence</h2>
                  {openChunk && (
                    <button
                      className="icon-button"
                      aria-label="Close selected passage"
                      onClick={() => {
                        setOpenChunk(null);
                        citationTrigger.current?.focus();
                      }}
                    >
                      <Icon name="close" size={18} />
                    </button>
                  )}
                </div>
                {openPassage ? (
                  <div className="passage-view">
                    <span className="eyebrow">
                      {openPassage.paragraph_ref
                        ? `Paragraph ${openPassage.paragraph_ref}`
                        : "Source passage"}
                    </span>
                    <h3>{openPassage.document_title}</h3>
                    {openPassage.heading_path && (
                      <p className="fine-print">{openPassage.heading_path}</p>
                    )}
                    <div
                      className="passage"
                      role="region"
                      aria-label="Original passage"
                      tabIndex={0}
                    >
                      {openPassage.text}
                    </div>
                    {openPassage.source_url && (
                      <a
                        className="text-link"
                        href={openPassage.source_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open official source <Icon name="external" size={14} />
                      </a>
                    )}
                  </div>
                ) : (
                  <div className="evidence-prompt">
                    <Icon name="sources" size={30} />
                    <h3>Follow a citation</h3>
                    <p>
                      Select a paragraph below an answer claim to read its
                      original source here.
                    </p>
                    <div className="passage-options">
                      {(result?.retrieved_evidence ?? []).map((c, i) => (
                        <button
                          key={c.chunk_id}
                          onClick={() => openCitation(c.chunk_id)}
                        >
                          <span className="mini-label">
                            Source {i + 1}
                            {c.paragraph_ref
                              ? ` · paragraph ${c.paragraph_ref}`
                              : ""}
                          </span>
                          <span>{c.document_title}</span>
                          <Icon name="arrow" size={14} />
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </aside>
            </div>
          )}
        </>
      )}
    </div>
  );
}
function SavedExample() {
  const [selected, setSelected] = useState(0);
  const target = useRef<HTMLElement>(null);
  const passages = [
    ...new Map(
      saved.record.claims.flatMap((c) => c.cited).map((c) => [c.chunk_id, c]),
    ).values(),
  ];
  const passage = passages[selected];
  return (
    <section className="saved-example">
      <div className="notice">
        <strong>Saved evaluation answer · not live research</strong>
        <p>
          This is the original answer and evidence from a saved test. Its claims
          were not model-checked. Explore the citations, then try your own
          question above.
        </p>
        <SourceNote file={saved.file}>Question {saved.record.id}</SourceNote>
      </div>
      <div className="answer-layout">
        <article className="card answer-card">
          <div className="eyebrow">Recorded question</div>
          <h2>{saved.question.question}</h2>
          {saved.record.claims.map((claim, i) => (
            <div className="claim" key={i}>
              <p>{claim.text}</p>
              <span className="claim-verdict unchecked">
                Not checked in this run
              </span>
              <div className="citation-list">
                {claim.cited.map((c) => (
                  <button
                    className="citation"
                    key={c.chunk_id}
                    onClick={() => {
                      setSelected(
                        passages.findIndex((p) => p.chunk_id === c.chunk_id),
                      );
                      target.current?.focus({ preventScroll: true });
                      if (innerWidth < 1150)
                        target.current?.scrollIntoView({ block: "start" });
                    }}
                  >
                    <Icon name="sources" size={14} />
                    Read source{" "}
                    {passages.findIndex((p) => p.chunk_id === c.chunk_id) + 1}
                    <Icon name="arrow" size={13} />
                  </button>
                ))}
              </div>
            </div>
          ))}
        </article>
        <aside
          className="card evidence-panel"
          ref={target}
          tabIndex={-1}
          aria-label="Saved source evidence"
        >
          <div className="eyebrow">
            Original source text · {selected + 1} of {passages.length}
          </div>
          <h3>{passage.title}</h3>
          <div
            className="passage"
            role="region"
            aria-label="Saved original passage"
            tabIndex={0}
          >
            {passage.text}
          </div>
          <a
            className="text-link"
            href={saved.question.gold[0].url}
            target="_blank"
            rel="noreferrer"
          >
            Open official source <Icon name="external" size={14} />
          </a>
          <p className="fine-print">
            A cited passage can contain the expected evidence even when the
            answer leaves out important conditions. Evidence coverage is not
            answer completeness.
          </p>
        </aside>
      </div>
    </section>
  );
}
