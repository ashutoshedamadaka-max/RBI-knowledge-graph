import { useEffect, useState } from "react";
import { Chunk, PipelineStep, QueryResult } from "../api";
import { Icon } from "./UI";
import "../live-pipeline.css";

const STEPS = [
  ["prepare", "Open the corpus", "Prepare the indexed sources"],
  ["bm25", "Find matching words", "Keyword search"],
  ["openai_embeddings", "Search by meaning", "Combine both search rankings"],
  ["graph_cross_references", "Follow references", "Knowledge graph connections"],
  ["in_force_filter", "Check the date", "Exclude ineligible passages"],
  ["cohere_rerank", "Rank the evidence", "Relevance to your question"],
  ["source_selection", "Select the sources", "Check document replacements"],
  ["answer", "Write the answer", "Generate with citations"],
  ["claim_check", "Check the claims", "Compare with cited evidence"],
];
export const duration = (ms: number) => ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
const money = (usd: number) => usd === 0 ? "$0.00000" : usd < 0.00001 ? "<$0.00001" : `$${usd.toFixed(5)}`;
const label = (title: string) => title.replace(/^Reserve Bank of India\s*/, "").replace(/^\(/, "").replace(/Non-Banking Financial Companies\s*[–-]\s*/, "").slice(0, 36);

export default function LivePipeline({ steps, busy, elapsed, firstTextMs, answerMs, result, error, onOpen, highlighted }: {
  steps: PipelineStep[]; busy: boolean; elapsed: number; firstTextMs: number | null; answerMs: number | null;
  result: QueryResult | null; error: string | null; onOpen: (id: string) => void; highlighted: Set<string>;
}) {
  const [expanded, setExpanded] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => { if (busy) { setExpanded(true); setSelected(null); } }, [busy]);
  const running = steps.find(s => s.status === "running");
  const current = steps.find(s => s.id === selected) ?? running ?? steps[steps.length - 1];
  const byId = new Map(steps.map(s => [s.id, s]));
  const costs = steps.filter(s => s.cost_usd != null);
  const subtotal = costs.reduce((total, s) => total + s.cost_usd!, 0);
  const missingCost = steps.some(s => ["openai_embeddings", "cohere_rerank", "answer", "claim_check"].includes(s.id) && s.status !== "skipped" && s.cost_usd == null);
  const snapshot = [...steps].reverse().find(s => s.evidence?.length);
  const selectedSources = byId.get("source_selection")?.evidence;
  const graphChunks = selectedSources ?? snapshot?.evidence ?? result?.retrieved_evidence ?? [];
  const chunks = [...new Map(graphChunks.map(c => [c.chunk_id, c])).values()];
  const edgeStep = byId.get("graph_cross_references");
  const focus = new Set(current?.evidence?.map(c => c.chunk_id) ?? []);
  const totalMs = !busy && result?.request_id ? result.latency_ms : null;
  const stageSum = steps.reduce((total, s) => total + (s.duration_ms ?? 0), 0);
  const status = busy ? "Live execution" : error ? "Interrupted" : "Run complete";
  return <section className={`live-pipeline ${busy ? "is-live" : ""}`} aria-label="Behind this answer">
    <header className="pipeline-header">
      <div><span className="eyebrow">Behind this answer</span><h2>Watch the evidence come together.</h2></div>
      <div className="pipeline-header-actions"><span className={`execution-status ${busy ? "active" : ""}`}><i />{status}</span>
        <button className="icon-button" aria-label={expanded ? "Collapse pipeline" : "Expand pipeline"} aria-expanded={expanded} onClick={() => setExpanded(!expanded)}><Icon name={expanded ? "close" : "plus"} size={18} /></button>
      </div>
    </header>
    <div className="run-metrics">
      <div><span>{busy ? "Elapsed in browser" : "Server processing"}</span><strong>{busy ? `${elapsed}s` : totalMs != null ? duration(totalMs) : "Incomplete"}</strong></div>
      <div><span>First answer text</span><strong>{firstTextMs != null ? duration(firstTextMs) : busy ? "Waiting" : "Not recorded"}</strong></div>
      <div><span>Answer ready</span><strong>{answerMs != null ? duration(answerMs) : busy ? "Writing soon" : "Not recorded"}</strong></div>
      <div><span>{busy || missingCost || error ? "Recorded cost so far" : "Estimated model cost"}</span><strong>{costs.length ? money(subtotal) : busy ? "Pending usage" : "Not recorded"}</strong></div>
    </div>
    <div className="pipeline-announcement" role="status">{busy ? current?.summary ?? "Connecting to the research service. Pipeline events will appear as they arrive." : error ? "This run did not finish. Recorded steps remain available." : "Execution finished. Select a step or a source to inspect it."}</div>
    {expanded && <>
      <div className="pipeline-workbench">
        <div className="pipeline-rail" aria-label="Pipeline steps">
          <div className="rail-heading"><span className="mini-label">The process</span>{selected && busy && <button className="text-link" onClick={() => setSelected(null)}>Follow live</button>}</div>
          {STEPS.map(([id, title, description], index) => {
            const step = byId.get(id);
            const state = step?.status === "running" && !busy ? "interrupted" : step?.status ?? (busy ? "waiting" : "not-run");
            return <button key={id} className={`pipeline-step ${state} ${current?.id === id ? "selected" : ""}`} onClick={() => setSelected(id)} disabled={!step} aria-pressed={current?.id === id}>
              <span className="pipeline-step-marker" aria-hidden="true">{state === "complete" ? "✓" : state === "failed" ? "!" : state === "skipped" ? "–" : String(index + 1).padStart(2, "0")}</span>
              <span className="step-copy"><strong>{title}</strong><small>{step?.status === "skipped" ? "Skipped" : state === "interrupted" ? "Interrupted" : description}</small></span>
              <span className="step-duration">{step?.duration_ms != null ? duration(step.duration_ms) : state === "running" ? <span className="step-pulse">Live</span> : state === "failed" ? "Failed" : "—"}</span>
            </button>;
          })}
        </div>
        <div className="pipeline-evidence">
          <div className="live-graph-heading"><span className="mini-label">Evidence in motion</span><span>{chunks.length ? `${chunks.length} ${selectedSources ? "selected" : "preview"} passages` : "Awaiting sources"}</span></div>
          <RunGraph chunks={chunks} result={result} edges={edgeStep?.edges ?? []} highlighted={highlighted.size ? highlighted : focus} onOpen={onOpen} busy={busy} />
          <div className="graph-key"><span><i className="key-document" />Document</span><span><i className="key-passage" />Passage</span><span><i className="key-claim" />Answer claim</span><span className="reference-key">- - Reference link</span></div>
          <div className="pipeline-step-detail" aria-label="Selected step details">
            <span className="eyebrow">{current ? STEPS.find(s => s[0] === current.id)?.[1] : "A view of this run"}</span>
            <p>{current?.summary ?? "The graph will populate with actual source passages. Claim connections appear when citations arrive."}</p>
            {current?.model && <div className="step-technical"><span>{current.model}</span>{current.input_tokens != null && <span>{current.input_tokens.toLocaleString()} input tokens</span>}{current.output_tokens != null && <span>{current.output_tokens.toLocaleString()} output tokens</span>}{current.search_units != null && <span>{current.search_units} search units</span>}</div>}
            {!!current?.removed?.length && <details><summary>Inspect excluded sources</summary><ul>{current.removed.map(c => <li key={c.chunk_id}><strong>{c.document_title}</strong><br />{c.reason}</li>)}</ul></details>}
            {!!current?.ranking?.length && <details><summary>See ranking changes</summary><ul className="ranking-changes">{current.ranking.map(r => <li key={r.chunk_id}><span>{label(current.evidence?.find(c => c.chunk_id === r.chunk_id)?.document_title ?? "Retrieved passage")}</span><strong>{r.before} → {r.after}</strong></li>)}</ul></details>}
          </div>
        </div>
      </div>
      <details className="run-accounting"><summary>Timing & cost breakdown <span>Measured durations · estimated service charges</span></summary>
        <div className="accounting-grid"><div><h3>Where the time went</h3>{steps.map(s => <div className="time-row" key={s.id}><span>{STEPS.find(x => x[0] === s.id)?.[1] ?? s.id}</span><span className="time-bar"><i style={{width:`${stageSum && s.duration_ms ? s.duration_ms / stageSum * 100 : 0}%`}} /></span><b>{s.duration_ms != null ? duration(s.duration_ms) : s.status === "running" ? busy ? "Running" : "Interrupted" : s.status === "skipped" ? "Skipped" : "Not recorded"}</b></div>)}
          {totalMs != null && <p className="fine-print">Other server work: {duration(Math.max(0, totalMs-stageSum))}. First-text and answer-ready times are measured in your browser and include connection time.</p>}
        </div><div><h3>Model-service estimate</h3>{steps.filter(s => ["openai_embeddings","cohere_rerank","answer","claim_check"].includes(s.id)).map(s => <div className="cost-row" key={s.id}><span>{STEPS.find(x => x[0] === s.id)?.[1]}<small>{s.cost_basis ?? (s.status === "skipped" ? "No call made" : "Usage has not been reported")}</small></span><b>{s.cost_usd != null ? money(s.cost_usd) : s.status === "skipped" ? "—" : "Unknown"}</b></div>)}
          <p className="fine-print">Reported usage × configured rates, not an invoice. Hosting, corpus indexing, and unreported failed-call charges are excluded. {missingCost || error ? "The recorded subtotal is incomplete." : ""}</p>
        </div></div>
      </details>
    </>}
  </section>;
}

function RunGraph({ chunks, result, edges, highlighted, onOpen, busy }: {chunks:Chunk[]; result:QueryResult|null; edges:{from:string;to:string}[]; highlighted:Set<string>; onOpen:(id:string)=>void; busy:boolean}) {
  const visible = chunks.slice(0, 8);
  const docs = [...new Map(visible.map(c=>[c.document_id,c.document_title])).entries()];
  const claims = [result?.research?.direct_answer, ...(result?.research?.sections ?? []).flatMap(s=>s.claims)].filter(c=>c && c.citation_ids.length).slice(0, 8);
  const height = Math.max(240, visible.length * 45 + 65, claims.length * 45 + 65);
  const py = new Map(visible.map((c,i)=>[c.chunk_id,62+i*45]));
  const dy = new Map(docs.map(([id],i)=>[id,70+i*(height-115)/Math.max(1,docs.length-1)]));
  return <div className="run-graph canvas">
    {!visible.length ? <div className="graph-awaiting"><span className={`graph-seed ${busy ? "breathing" : ""}`}><Icon name="graph" size={28}/></span><strong>{busy ? "Finding the first connections" : "No source graph for this run"}</strong><p>Real documents and passages will appear here.<br/>Every connection has a source.</p></div> : <>
      <svg viewBox={`0 0 640 ${height}`} role="group" aria-label="Live evidence graph">
        <text className="graph-column-label" x="24" y="24">DOCUMENTS</text><text className="graph-column-label" x="287" y="24">PASSAGES</text><text className="graph-column-label" x="506" y="24">CLAIMS</text>
        {visible.map(c=><path key={`source-${c.chunk_id}`} d={`M42 ${dy.get(c.document_id)} C170 ${dy.get(c.document_id)} 200 ${py.get(c.chunk_id)} 303 ${py.get(c.chunk_id)}`} className="graph-source-edge" />)}
        {edges.filter(e=>py.has(e.from)&&py.has(e.to)).map((e,i)=><path key={`ref-${i}`} d={`M303 ${py.get(e.from)} C410 ${py.get(e.from)} 410 ${py.get(e.to)} 303 ${py.get(e.to)}`} className="graph-reference-edge" />)}
        {claims.flatMap((c,i)=>c!.citation_ids.filter(id=>py.has(id)).map(id=><path key={`${i}-${id}`} d={`M303 ${py.get(id)} C405 ${py.get(id)} 440 ${62+i*45} 528 ${62+i*45}`} className="graph-claim-edge" />))}
        {docs.map(([id,title])=><g key={id} transform={`translate(42,${dy.get(id)})`}><rect x="-10" y="-10" width="20" height="20" rx="5" className="graph-document-node"/><text x="-20" y="28" className="graph-node-label">{label(title).slice(0,28)}</text><title>{title}</title></g>)}
        {visible.map((c,i)=><g key={c.chunk_id} transform={`translate(303,${py.get(c.chunk_id)})`} role="button" tabIndex={0} aria-label={`Read source ${i+1}: ${c.document_title}`} onClick={()=>onOpen(c.chunk_id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onOpen(c.chunk_id);}}} className={`graph-passage-node ${highlighted.has(c.chunk_id)?"highlighted":""}`}><circle r="17" className="graph-hit-ring"/><circle r="7"/><text x="17" y="4">{c.paragraph_ref ? `§ ${c.paragraph_ref.slice(0,12)}` : `Source ${i+1}`}</text><title>{c.document_title}</title></g>)}
        {claims.map((c,i)=><g key={i} transform={`translate(528,${62+i*45})`}><circle r="8" className={`graph-claim-node ${c!.support ?? "pending"}`}/><text x="16" y="4">Claim {i+1}</text><title>{c!.text} — {c!.support ?? "Check pending"}</title></g>)}
        {!claims.length && <text x="505" y="65" className="graph-pending-label">Awaiting citations</text>}
      </svg>
      <span className="graph-scope-note">{chunks.length>8 ? "Showing the first 8 passages. " : ""}Select a passage to read its source.</span>
    </>}
    {!!chunks.length && <details className="graph-text-list"><summary>Browse the passages as a list</summary>{chunks.map((c,i)=><button key={c.chunk_id} onClick={()=>onOpen(c.chunk_id)}><span>{String(i+1).padStart(2,'0')}</span>{c.document_title}{c.paragraph_ref ? ` · ${c.paragraph_ref}` : ''}</button>)}</details>}
  </div>;
}

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

/** Bring the live pipeline into view (instantly when the reader prefers reduced motion). */
export function revealPipeline(target: HTMLElement | null) {
  target?.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
}

/** Before a question is asked: set the expectation that the work behind the answer will be visible. */
export function PipelinePreview() {
  return <div className="pipeline-preview" aria-label="What happens when you ask">
    <div className="pipeline-preview-copy">
      <span className="mini-label">Behind every answer</span>
      <p>When you ask, you can watch each step run live: the search, the date check, the ranking, the writing and the claim check, with the real sources, timings and cost.</p>
    </div>
    <ol className="pipeline-preview-steps">
      {STEPS.map(([id, title]) => <li key={id}>{title}</li>)}
    </ol>
  </div>;
}

/** The facts a reader cares about once a run is done, for the answer header and the floating pill. */
export function runFacts(steps: PipelineStep[]) {
  const byId = new Map(steps.map(s => [s.id, s]));
  const done = steps.filter(s => s.status === "complete").length;
  const filter = byId.get("in_force_filter");
  const check = byId.get("claim_check");
  const cost = steps.reduce((total, s) => total + (s.cost_usd ?? 0), 0);
  const parts = [`${done} steps`];
  if (filter?.inspected_count) parts.push(`${filter.inspected_count} passages checked for date`);
  if (filter?.count) parts.push(`${filter.count} excluded`);
  if (check?.status === "complete" && check.count != null) parts.push(`${check.count} claims checked`);
  if (cost > 0) parts.push(money(cost));
  return parts.join(" · ");
}

/** A small floating pill while the pipeline is off-screen: live status during a run, a way back afterwards. */
export function PipelinePill({ steps, busy, target }: { steps: PipelineStep[]; busy: boolean; target: { current: HTMLElement | null } }) {
  const [hidden, setHidden] = useState(true);
  useEffect(() => {
    const node = target.current;
    if (!node || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setHidden(entry.isIntersecting), { threshold: 0.15 });
    observer.observe(node);
    return () => observer.disconnect();
  }, [target, steps.length > 0]);
  if (hidden || (!busy && !steps.length)) return null;
  const running = steps.find(s => s.status === "running");
  const title = running ? STEPS.find(s => s[0] === running.id)?.[1] : null;
  return <button className={`pipeline-pill ${busy ? "live" : ""}`} onClick={() => revealPipeline(target.current)}>
    <i aria-hidden="true" />
    <span>{busy ? <>Live · {title ?? "Starting"}</> : <>How this answer was made</>}</span>
    <Icon name="arrow" size={14} />
  </button>;
}

/** A one-line live status that sits right above the answer: the steps ticking along, and a link to the detail. */
export function LiveStrip({ steps, busy, error, onDetails }: { steps: PipelineStep[]; busy: boolean; error: string | null; onDetails: () => void }) {
  const byId = new Map(steps.map(s => [s.id, s]));
  const running = steps.find(s => s.status === "running");
  const title = running ? STEPS.find(s => s[0] === running.id)?.[1] : null;
  const label = busy ? (title ? `${title}…` : "Starting the research…") : error ? "This run did not finish" : `Done · ${runFacts(steps)}`;
  return <div className={`live-strip ${busy ? "live" : ""}`} role="status" aria-live="polite">
    <ol className="live-strip-steps" aria-hidden="true">
      {STEPS.map(([id]) => <li key={id} className={byId.get(id)?.status ?? "waiting"} />)}
    </ol>
    <span className="live-strip-label">{label}</span>
    <button className="text-link" onClick={onDetails}>{busy ? "Watch it live" : "See how"} <Icon name="arrow" size={14} /></button>
  </div>;
}
