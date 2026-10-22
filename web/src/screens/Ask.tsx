import { useEffect, useMemo, useState } from "react";
import { Chunk, Claim, QueryResult, streamQuery } from "../api";
import EvidenceGraph from "../components/EvidenceGraph";
import TraceDrawer from "../components/TraceDrawer";

const EXAMPLES = [
  { label: "Answered, with citations", query: "Can an NBFC capitalise penal charges on a loan?", asOf: "" },
  { label: "Correctly refused", query: "What is the role of CareEdge Global IFSC Limited as an External Credit Assessment Institution under Basel III?", asOf: "" },
  { label: "A rule that has since been replaced", query: "What were the rules on default loss guarantee in digital lending?", asOf: "2024-06-01" },
];
const STAGES: Record<string, string> = {
  understanding_question: "Reading the question",
  retrieving_official_evidence: "Searching RBI paragraphs (keywords, meaning, cross-references)",
  checking_regulatory_validity: "Keeping only rules in force on the date",
  selecting_authoritative_evidence: "Ranking the best passages",
  building_grounded_answer: "Writing the answer from those passages",
  checking_claims: "Checking each claim against its cited text",
};
const VERDICT_TEXT = { supported: "Supported by the cited text", partially_supported: "Only partly supported by the cited text",
  not_supported: "Not supported by the cited text" } as const;
const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

function claimsOf(result: QueryResult): Claim[] {
  const research = result.research;
  if (!research) return [];
  return [...(research.direct_answer ? [research.direct_answer] : []), ...research.sections.flatMap((section) => section.claims)];
}

/** The passage with the claim's distinctive words marked, so a reader can check the claim at a glance. */
function Highlighted({ text, claim }: { text: string; claim: string | null }) {
  const words = new Set((claim ?? "").toLowerCase().match(/[a-z0-9]{5,}/g) ?? []);
  const parts = text.split(/(\b[\w-]+\b)/);
  return <div className="passage">{parts.map((part, index) =>
    words.has(part.toLowerCase()) ? <mark key={index}>{part}</mark> : <span key={index}>{part}</span>)}</div>;
}

export default function Ask() {
  const [query, setQuery] = useState(EXAMPLES[0].query);
  const [asOf, setAsOf] = useState("");
  const [stages, setStages] = useState<string[]>([]);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<string | null>(null); // the direct answer while it is being written
  const [activeClaim, setActiveClaim] = useState<number | null>(null);
  const [openChunk, setOpenChunk] = useState<string | null>(null);
  const [reveal, setReveal] = useState(4); // 0 documents, 1 links, 2 cited passages, 3 answer, 4 claim dots

  const evidence = useMemo(() => new Map((result?.retrieved_evidence ?? []).map((chunk) => [chunk.chunk_id, chunk])), [result]);
  const claims = result ? claimsOf(result) : [];
  const cited = new Set(activeClaim !== null ? claims[activeClaim]?.citation_ids ?? [] : []);

  useEffect(() => {
    if (!result || reducedMotion()) { setReveal(4); return; }
    setReveal(0);
    const timers = [1, 2, 3, 4].map((step) => window.setTimeout(() => setReveal(step), step * 650));
    return () => timers.forEach(window.clearTimeout);
  }, [result]);

  async function ask(text = query, date = asOf) {
    setBusy(true); setError(null); setResult(null); setDraft(null); setStages([]); setActiveClaim(null); setOpenChunk(null);
    try {
      setResult(await streamQuery(text, date || null, (stage) => setStages((done) => [...done, stage]),
        (preview) => { setDraft(null); setResult(preview); }, setDraft));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setBusy(false);
    }
  }

  const openPassage: Chunk | undefined = openChunk ? evidence.get(openChunk) : undefined;
  const refused = result && result.research?.status !== "grounded";

  return (
    <div className="grid-ask">
      <section className="card" aria-labelledby="ask-heading">
        <h3 id="ask-heading">Your question</h3>
        <form onSubmit={(event) => { event.preventDefault(); ask(); }}>
          <label className="sr-only" htmlFor="question">Question</label>
          <textarea id="question" className="question" value={query} onChange={(event) => setQuery(event.target.value)} />
          <label className="field">As of (optional: answer with the rules in force on this date)
            <input type="date" value={asOf} max={new Date().toISOString().slice(0, 10)} onChange={(event) => setAsOf(event.target.value)} />
          </label>
          <button className="primary" disabled={busy || query.trim().length < 3}>{busy ? "Researching…" : "Ask"}</button>
        </form>
        <div className="examples">
          <span className="muted">Try one:</span>
          {EXAMPLES.map((example) => (
            <button key={example.label} className="example" disabled={busy}
              onClick={() => { setQuery(example.query); setAsOf(example.asOf); ask(example.query, example.asOf); }}>
              <span>{example.label}{example.asOf ? ` · as of ${example.asOf}` : ""}</span>{example.query}
            </button>
          ))}
        </div>
        {(busy || stages.length > 0) && (
          <ol className="stages" aria-live="polite">
            {stages.map((stage) => <li key={stage} className="done">{STAGES[stage] ?? stage}</li>)}
          </ol>
        )}
      </section>

      <section className="card" aria-labelledby="answer-heading" aria-live="polite">
        <h2 id="answer-heading">{result?.research?.display_title ?? "Answer"}</h2>
        {!result && !error && <p className="muted">Answers come only from RBI paragraphs in force on the date you ask about. Each claim shows whether its cited text supports it.</p>}
        {error && <p className="status-bad" role="alert">{error}</p>}
        {!result && draft && <p><strong>Direct answer. </strong>{draft}<span className="muted"> …</span></p>}
        {result && reveal >= 3 && (
          <>
            <p className="muted">As of {result.as_of} · {result.pipeline.selected_evidence_count} passages · {result.pipeline.answer_mode === "checking"
              ? "checking each claim…" : `${Math.round(result.latency_ms / 100) / 10} s · $${result.estimated_cost_usd.toFixed(4)}`}</p>
            {result.notices.map((notice, index) => (
              <div key={index} className={`notice ${notice.kind}`}><strong>{notice.kind === "upcoming" ? "Not yet in force" : notice.kind === "replaced" ? "Replaced" : "Withdrawn"}:</strong> {notice.text}</div>
            ))}
            {refused ? (
              <div className="refusal">
                <p>{result.research?.direct_answer?.text ?? "The indexed RBI rules do not contain a passage that answers this question, so it was not answered."}</p>
                <p className="muted">Refusing is deliberate: the system answers only when an RBI passage is a strong enough match.</p>
              </div>
            ) : claims.map((claim, index) => (
              <div key={index} className={`claim ${activeClaim === index ? "active" : ""}`}
                onMouseEnter={() => setActiveClaim(index)} onFocus={() => setActiveClaim(index)} tabIndex={0}>
                <span className={`dot ${reveal >= 4 ? claim.support ?? "" : ""}`} role="img"
                  aria-label={claim.support ? VERDICT_TEXT[claim.support] : "Not checked"} title={claim.support ? VERDICT_TEXT[claim.support] : "Not checked"} />
                <div>
                  {index === 0 && <strong>Direct answer. </strong>}{claim.text}
                  {claim.support && claim.support !== "supported" && <div className="flag">{VERDICT_TEXT[claim.support]}</div>}
                  <div>{claim.citation_ids.map((id) => {
                    const chunk = evidence.get(id);
                    return <button key={id} className="chip" onClick={() => setOpenChunk(id)}>
                      {chunk ? `${chunk.document_title.replace(/^Reserve Bank of India \(|\)$/g, "").slice(0, 48)} · para ${chunk.paragraph_ref ?? "?"}` : id}
                    </button>;
                  })}</div>
                </div>
              </div>
            ))}
          </>
        )}
        {openPassage && (
          <div style={{ marginTop: 12 }}>
            <h3>{openPassage.document_title} · paragraph {openPassage.paragraph_ref}</h3>
            {openPassage.heading_path && <p className="muted">{openPassage.heading_path}</p>}
            <Highlighted text={openPassage.text} claim={activeClaim !== null ? claims[activeClaim]?.text ?? null : null} />
            {openPassage.source_url && <p><a href={openPassage.source_url} target="_blank" rel="noreferrer">Open on rbi.org.in</a></p>}
          </div>
        )}
      </section>

      <section className="card evidence" aria-labelledby="evidence-heading">
        <h2 id="evidence-heading">Evidence graph</h2>
        {result ? (
          <>
            {reveal < 4 && !reducedMotion() && <button className="chip" onClick={() => setReveal(4)}>Skip animation</button>}
            <EvidenceGraph result={result} reveal={reveal} highlighted={cited} onOpen={setOpenChunk} />
          </>
        ) : <p className="muted">The documents and paragraphs behind the answer appear here, including what the in-force filter removed.</p>}
      </section>

      {result && <section className="card" style={{ gridColumn: "1 / -1" }}><TraceDrawer result={result} /></section>}
    </div>
  );
}
