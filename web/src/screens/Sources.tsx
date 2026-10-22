import { useEffect, useState } from "react";
import { getJson } from "../api";

interface Document { document_id: string; title: string; lifecycle: string; document_type: string | null; publication_date: string | null;
  in_force_from: string | null; in_force_to: string | null; source_url: string | null; status_evidence_excerpt: string | null;
  status_evidence_url: string | null; status_resolution_method: string }
interface ChunkRow { chunk_id: string; paragraph_ref: string | null; heading_path: string | null; token_count: number | null; text: string; page_number: number }
interface Update { update_id?: string; title?: string; detected_at?: string; materiality?: string; change_summary?: string; current_lifecycle?: string; canonical_url?: string }
interface Link { link_id: string; relation: string; old_document_id: string; new_document_id: string; method: string; evidence_quote: string; evidence_url: string | null; trust: string }

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

export default function Sources() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [status, setStatus] = useState<any>(null);
  const [updates, setUpdates] = useState<Update[]>([]);
  const [links, setLinks] = useState<Link[]>([]);
  const [chunksOf, setChunksOf] = useState<string>("");
  const [chunks, setChunks] = useState<ChunkRow[]>([]);
  const [adminKey, setAdminKey] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const load = () => {
    getJson<{ documents: Document[] }>("/documents").then((body) => setDocuments(body.documents)).catch((exc) => setMessage(exc.message));
    getJson("/monitoring-status").then(setStatus).catch(() => undefined);
    getJson<Update[]>("/regulatory-updates").then(setUpdates).catch(() => undefined);
    getJson<Link[]>("/document-links").then(setLinks).catch(() => undefined);
  };
  useEffect(load, []);
  useEffect(() => {
    if (chunksOf) getJson<ChunkRow[]>(`/documents/${chunksOf}/chunks`).then(setChunks).catch((exc) => setMessage(exc.message));
  }, [chunksOf]);

  const titles = new Map(documents.map((document) => [document.document_id, document.title]));
  const pending = links.filter((link) => link.trust === "REVIEW_REQUIRED");
  const byType = Object.entries(documents.reduce<Record<string, number>>((acc, document) => {
    const key = `${document.document_type ?? "document"} · ${document.lifecycle.toLowerCase()}`;
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {})).sort();

  async function review(link: Link, action: "approve" | "reject") {
    setMessage(null);
    const response = await fetch(`${BASE}/admin/links/${link.link_id}/${action}`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Key": adminKey },
      body: action === "approve" ? JSON.stringify({ evidence_url: link.evidence_url, evidence_excerpt: link.evidence_quote.slice(0, 1200) }) : undefined,
    });
    setMessage(response.ok ? `Link ${action}d.` : `Not ${action}d: ${(await response.json().catch(() => ({}))).detail ?? response.status}`);
    if (response.ok) load();
  }

  return (
    <div>
      <h1>Sources and monitoring</h1>
      {message && <p role="status">{message}</p>}
      <div className="two-col" style={{ marginTop: 0 }}>
        <section className="card">
          <h2>Corpus</h2>
          <p><span className="num">{documents.length}</span> documents: RBI's NBFC lending directions and the circulars they replaced. Scope is NBFC lending only.</p>
          <table><tbody>{byType.map(([key, count]) => <tr key={key}><td>{key}</td><td>{count}</td></tr>)}</tbody></table>
        </section>
        <section className="card">
          <h2>Monitoring</h2>
          {status ? <p>Health: <strong className={status.health === "healthy" ? "status-ok" : "status-warn"}>{status.health}</strong> · {status.tracked_source_count} RBI sources checked daily · last check {status.last_checks?.[0]?.checked_at?.slice(0, 16).replace("T", " ") ?? "—"}</p>
            : <p className="muted">Monitoring status unavailable.</p>}
          <h3>Recent changes detected on RBI's site</h3>
          {updates.length ? <ul>{updates.slice(0, 10).map((update, index) => (
            <li key={update.update_id ?? index}>{update.detected_at?.slice(0, 10)} · {update.title} · <span className="muted">{update.change_summary?.slice(0, 140)}</span>
              {update.current_lifecycle && <> · now <strong>{update.current_lifecycle.toLowerCase()}</strong></>}</li>
          ))}</ul> : <p className="muted">No changes recorded yet.</p>}
        </section>
      </div>

      <section className="card" style={{ marginTop: 16 }}>
        <h2>Pending approvals ({pending.length})</h2>
        <p className="muted">Links the system suggested but did not trust on its own. Each shows the RBI text it rests on. Approving needs the admin key; it is kept only in this page.</p>
        <label className="field" style={{ maxWidth: 320 }}>Admin key <input type="password" value={adminKey} onChange={(event) => setAdminKey(event.target.value)} autoComplete="off" /></label>
        <div className="table-wrap"><table>
          <thead><tr><th>Old rule</th><th>New rule</th><th>Evidence</th><th /></tr></thead>
          <tbody>{pending.slice(0, 25).map((link) => (
            <tr key={link.link_id}><td>{titles.get(link.old_document_id) ?? link.old_document_id}</td><td>{titles.get(link.new_document_id) ?? link.new_document_id}</td>
              <td><span className="muted">{link.relation.toLowerCase()} · {link.method}</span><br />“{link.evidence_quote.slice(0, 200)}”</td>
              <td><button className="chip" disabled={!adminKey || !link.evidence_url} onClick={() => review(link, "approve")}>Approve</button>
                <button className="chip" disabled={!adminKey} onClick={() => review(link, "reject")}>Reject</button></td></tr>
          ))}</tbody>
        </table></div>
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <h2>Documents and how they were cut</h2>
        <label className="field" style={{ maxWidth: 560 }}>Show chunks for
          <select value={chunksOf} onChange={(event) => setChunksOf(event.target.value)}>
            <option value="">Choose a document…</option>
            {documents.map((document) => <option key={document.document_id} value={document.document_id}>{document.title.slice(0, 110)}</option>)}
          </select>
        </label>
        {chunksOf && <div className="table-wrap"><table>
          <thead><tr><th>Paragraph</th><th>Heading path</th><th>Tokens</th><th>Page</th><th>Text</th></tr></thead>
          <tbody>{chunks.map((chunk) => (
            <tr key={chunk.chunk_id}><td>{chunk.paragraph_ref}</td><td className="muted">{chunk.heading_path}</td><td>{chunk.token_count}</td><td>{chunk.page_number}</td>
              <td><details><summary>{chunk.text.replace(/^\[[^\]]*\]\s*/, "").slice(0, 90)}…</summary><div className="passage">{chunk.text}</div></details></td></tr>
          ))}</tbody>
        </table></div>}
        <h3 style={{ marginTop: 16 }}>Status of every document</h3>
        <div className="table-wrap"><table>
          <thead><tr><th>Document</th><th>Status</th><th>In force</th><th>Evidence</th></tr></thead>
          <tbody>{documents.map((document) => (
            <tr key={document.document_id}><td>{document.source_url ? <a href={document.source_url} target="_blank" rel="noreferrer">{document.title}</a> : document.title}</td>
              <td className={document.lifecycle === "ACTIVE" ? "status-ok" : document.lifecycle === "REVIEW_REQUIRED" ? "status-warn" : "status-bad"}>{document.lifecycle.toLowerCase()}</td>
              <td>{document.in_force_from ?? "?"} → {document.in_force_to ?? "now"}</td>
              <td className="muted">{document.status_resolution_method.toLowerCase().replaceAll("_", " ")}{document.status_evidence_excerpt ? `: “${document.status_evidence_excerpt.slice(0, 120)}”` : ""}</td></tr>
          ))}</tbody>
        </table></div>
      </section>
    </div>
  );
}
