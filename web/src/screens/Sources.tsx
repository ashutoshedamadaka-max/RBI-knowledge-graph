import { useEffect, useMemo, useState } from "react";
import { getJson } from "../api";
import { liveOrSaved, saved } from "../snapshot";
import { EmptyState, Icon, NextPage, PageIntro } from "../components/UI";
interface Document {
  document_id: string;
  title: string;
  lifecycle: string;
  document_type: string | null;
  publication_date: string | null;
  in_force_from: string | null;
  in_force_to: string | null;
  source_url: string | null;
  status_evidence_excerpt: string | null;
  status_resolution_method: string;
}
interface ChunkRow {
  chunk_id: string;
  paragraph_ref: string | null;
  heading_path: string | null;
  token_count: number | null;
  text: string;
  page_number: number;
}
interface Link {
  link_id: string;
  relation: string;
  old_document_id: string;
  new_document_id: string;
  method: string;
  evidence_quote: string;
  evidence_url: string | null;
  trust: string;
}
const label = (s: string) =>
  s === "ACTIVE"
    ? "In force"
    : s === "REVIEW_REQUIRED"
      ? "Awaiting review"
      : s.toLowerCase().replaceAll("_", " ");
export default function Sources() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState<any>(null);
  const [updates, setUpdates] = useState<any[] | null>(null);
  const [links, setLinks] = useState<Link[] | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setError(null);
    liveOrSaved<{ documents: Document[] }>(
      "/documents",
      "documents.json",
      abort.signal,
    )
      .then((v) => {
        setDocuments(v.data.documents);
        setSnapshot(v.snapshot);
      })
      .catch(() => {
        if (!abort.signal.aborted)
          setError("The source library could not load. Please try again.");
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    getJson("/monitoring-status", abort.signal)
      .then(setStatus)
      .catch(() => {});
    getJson<any[]>("/regulatory-updates", abort.signal)
      .then(setUpdates)
      .catch(() => {});
    getJson<Link[]>("/document-links", abort.signal)
      .then(setLinks)
      .catch(() => {});
    return () => abort.abort();
  }, [attempt]);
  const filtered = useMemo(
    () =>
      documents.filter(
        (d) =>
          (filter === "all" || d.lifecycle === filter) &&
          d.title.toLowerCase().includes(search.toLowerCase()),
      ),
    [documents, filter, search],
  );
  const active = documents.filter((d) => d.lifecycle === "ACTIVE").length;
  const visible = filtered.slice(page * 10, page * 10 + 10);
  return (
    <div className="page">
      <PageIntro
        eyebrow="Source library"
        title="The source should never be a mystery."
      >
        Browse the selected Reserve Bank of India (RBI) documents. Read their
        recorded status, original text, and paragraph-sized search passages.
      </PageIntro>
      <div className="inventory-strip" aria-label="Live library inventory">
        <div>
          <strong>{loading || error ? "—" : documents.length}</strong>
          <span>indexed documents</span>
        </div>
        <div>
          <strong>{loading || error ? "—" : active}</strong>
          <span>recorded in force</span>
        </div>
        <div>
          <strong>
            {loading || error
              ? "—"
              : documents.filter((d) => d.lifecycle === "WITHDRAWN").length}
          </strong>
          <span>recorded withdrawn</span>
        </div>
        <div>
          <strong>Official sources</strong>
          <span>Selected NBFC lending corpus</span>
        </div>
      </div>
      <p className="fine-print" style={{ marginTop: 14 }}>
        {snapshot
          ? "Saved evaluated release; the live library is unavailable."
          : "Live library inventory."}{" "}
        This is not a claim of complete sector coverage. Non-banking financial
        companies (NBFCs) are the focus. Status reflects the last recorded
        evidence, not a live legal opinion.
      </p>
      <div className="library-toolbar">
        <label className="field">
          Find a document
          <input
            type="search"
            placeholder="Search titles, e.g. digital lending"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
          />
        </label>
        <label className="field">
          Recorded status
          <select
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value);
              setPage(0);
            }}
          >
            <option value="all">All statuses</option>
            {[...new Set(documents.map((d) => d.lifecycle))].sort().map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {loading ? (
        <div className="loading-state" role="status">
          <span className="spinner" /> Loading source records. The service may
          need a moment to wake up.
        </div>
      ) : error ? (
        <EmptyState
          title="Library unavailable"
          retry={() => setAttempt((a) => a + 1)}
        >
          {error}
        </EmptyState>
      ) : (
        <>
          <p className="library-count" role="status">
            {filtered.length
              ? `${page * 10 + 1}–${Math.min((page + 1) * 10, filtered.length)} of ${filtered.length} documents`
              : "No matching documents"}
          </p>
          {!filtered.length ? (
            <EmptyState title="No documents match">
              Try a broader title or select all statuses.
            </EmptyState>
          ) : (
            <div className="document-list">
              {visible.map((d) => (
                <article className="document-row" key={d.document_id}>
                  <button
                    aria-expanded={selected === d.document_id}
                    aria-controls={`doc-${d.document_id}`}
                    onClick={() =>
                      setSelected(
                        selected === d.document_id ? null : d.document_id,
                      )
                    }
                  >
                    <Icon name="sources" size={22} />
                    <div>
                      <h3>{d.title}</h3>
                      <p>
                        {d.document_type?.replaceAll("_", " ") ?? "Document"} ·
                        published {d.publication_date ?? "date not recorded"}
                      </p>
                    </div>
                    <span
                      className={`status-pill ${d.lifecycle === "ACTIVE" ? "active" : "withdrawn"}`}
                    >
                      {label(d.lifecycle)}
                    </span>
                  </button>
                  {selected === d.document_id && (
                    <div
                      id={`doc-${d.document_id}`}
                      className="document-content"
                    >
                      <DocumentDetail document={d} snapshot={snapshot} />
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
          {filtered.length > 10 && (
            <div className="pagination">
              <button
                className="secondary"
                disabled={page === 0}
                onClick={() => {
                  setPage((p) => p - 1);
                  setSelected(null);
                }}
              >
                Previous
              </button>
              <span>
                Page {page + 1} of {Math.ceil(filtered.length / 10)}
              </span>
              <button
                className="secondary"
                disabled={(page + 1) * 10 >= filtered.length}
                onClick={() => {
                  setPage((p) => p + 1);
                  setSelected(null);
                }}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
      <section className="section-block">
        <div className="section-heading">
          <div>
            <div className="eyebrow">Source history</div>
            <h2>Old rules remain inspectable.</h2>
          </div>
        </div>
        <div className="grid-3">
          <div className="card">
            <span className="status-pill active">In force</span>
            <h3 style={{ marginTop: 18 }}>Eligible for the date</h3>
            <p className="muted">
              A passage can be used when its recorded in-force period covers the
              research date.
            </p>
          </div>
          <div className="card">
            <span className="status-pill withdrawn">Withdrawn</span>
            <h3 style={{ marginTop: 18 }}>Kept for history</h3>
            <p className="muted">
              Retired documents stay available for earlier dates, with their
              status evidence attached.
            </p>
          </div>
          <div className="card">
            <span className="status-pill">Awaiting review</span>
            <h3 style={{ marginTop: 18 }}>Uncertainty is explicit</h3>
            <p className="muted">
              A plausible replacement is a suggestion until the evidence meets
              the trust rule.
            </p>
          </div>
        </div>
      </section>
      <details className="disclosure">
        <summary>Monitoring status and recent changes</summary>
        <div>
          {status ? (
            <p>
              Recorded health: <strong>{status.health}</strong>. Latest recorded
              check:{" "}
              {status.last_checks?.[0]?.checked_at
                ?.replace("T", " ")
                .slice(0, 19) ?? "not available"}
              .
            </p>
          ) : (
            <p>Monitoring status is unavailable.</p>
          )}
          <p className="fine-print">
            A daily schedule is configured; this display reports stored
            observations. Live detection delay has not been measured.
          </p>
          {updates === null ? (
            <p className="muted">Recent changes could not be loaded.</p>
          ) : updates.length ? (
            <ul>
              {updates.slice(0, 10).map((u, i) => (
                <li key={u.update_id ?? i}>
                  <strong>{u.title}</strong>
                  <p className="fine-print">
                    {u.detected_at?.slice(0, 10)} · {u.change_summary}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No changes recorded.</p>
          )}
        </div>
      </details>
      <details className="disclosure">
        <summary>Maintainer tools · replacement review</summary>
        <div>
          <p className="fine-print">
            For the project maintainer. Suggested links are not approved simply
            because they appear here. The credential stays in this page and is
            never saved to browser storage.
          </p>
          {links === null ? (
            <p>Review data unavailable.</p>
          ) : (
            <ReviewQueue
              links={links.filter((l) => l.trust === "REVIEW_REQUIRED")}
              documents={documents}
              reload={() => setAttempt((a) => a + 1)}
            />
          )}
        </div>
      </details>
      <NextPage
        href="#graph"
        title="Follow the connections between sources."
        text="Explore document history and paragraph relationships in the graph."
      />
    </div>
  );
}
function DocumentDetail({
  document: d,
  snapshot,
}: {
  document: Document;
  snapshot: boolean;
}) {
  const [chunks, setChunks] = useState<ChunkRow[] | null>(null);
  const [error, setError] = useState(false);
  const [show, setShow] = useState(5);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    setChunks(null);
    setError(false);
    (snapshot
      ? saved<ChunkRow[]>(`chunks/${d.document_id}.json`)
      : getJson<ChunkRow[]>(
          `/documents/${encodeURIComponent(d.document_id)}/chunks`,
          abort.signal,
        )
    )
      .then((v) => {
        if (!abort.signal.aborted) setChunks(v);
      })
      .catch(() => {
        if (!abort.signal.aborted) setError(true);
      });
    return () => abort.abort();
  }, [d.document_id, attempt, snapshot]);
  return (
    <>
      <div className="grid-2">
        <div>
          <span className="eyebrow">Recorded in-force period</span>
          <p>
            {d.in_force_from ?? "Start unknown"} →{" "}
            {d.in_force_to ?? "No end recorded"}
          </p>
        </div>
        <div>
          <span className="eyebrow">Status evidence</span>
          <p className="fine-print">
            {d.status_resolution_method?.toLowerCase().replaceAll("_", " ")}
            {d.status_evidence_excerpt && ` · “${d.status_evidence_excerpt}”`}
          </p>
        </div>
      </div>
      {d.source_url && (
        <a
          className="text-link"
          href={d.source_url}
          target="_blank"
          rel="noreferrer"
        >
          Read the official source <Icon name="external" size={14} />
        </a>
      )}
      <h4>Searchable passages</h4>
      <p className="fine-print">
        Numbered paragraphs retain headings and document status. Open a passage
        to read its full text.
      </p>
      {error ? (
        <EmptyState
          title="Passages unavailable"
          retry={() => setAttempt((a) => a + 1)}
        >
          Please retry loading this document.
        </EmptyState>
      ) : chunks === null ? (
        <p role="status">Loading passages…</p>
      ) : !chunks.length ? (
        <p>No passages available for this document.</p>
      ) : (
        <>
          {chunks.slice(0, show).map((c) => (
            <details className="chunk-band" key={c.chunk_id}>
              <summary>
                Paragraph {c.paragraph_ref ?? "not recorded"} ·{" "}
                {c.heading_path || c.text.slice(0, 70)}
              </summary>
              <div className="passage">{c.text}</div>
            </details>
          ))}
          {show < chunks.length && (
            <button
              className="secondary"
              onClick={() => setShow((s) => s + 10)}
            >
              Show more passages ({show} of {chunks.length} shown)
            </button>
          )}
        </>
      )}
    </>
  );
}
function ReviewQueue({
  links,
  documents,
  reload,
}: {
  links: Link[];
  documents: Document[];
  reload: () => void;
}) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function review(link: Link, action: "approve" | "reject") {
    setBusy(true);
    setMessage("");
    try {
      const base = (import.meta.env.VITE_API_BASE_URL ?? "").replace(
        /\/+$/,
        "",
      );
      const response = await fetch(
        `${base}/admin/links/${link.link_id}/${action}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Admin-Key": key },
          body:
            action === "approve"
              ? JSON.stringify({
                  evidence_url: link.evidence_url,
                  evidence_excerpt: link.evidence_quote.slice(0, 1200),
                })
              : undefined,
        },
      );
      if (!response.ok)
        throw new Error(
          "The review could not be saved. Check your credential and try again.",
        );
      setMessage(action === "approve" ? "Link approved." : "Link rejected.");
      reload();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Review failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <label className="field">
        Maintainer credential
        <input
          type="password"
          autoComplete="off"
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
      </label>
      <p role="status">{message}</p>
      {!links.length ? (
        <p>No replacement suggestions await review.</p>
      ) : (
        links.slice(0, 25).map((l) => (
          <article className="failure-card" key={l.link_id}>
            <h3>
              {documents.find((d) => d.document_id === l.old_document_id)
                ?.title ?? l.old_document_id}{" "}
              →{" "}
              {documents.find((d) => d.document_id === l.new_document_id)
                ?.title ?? l.new_document_id}
            </h3>
            <p>{l.evidence_quote}</p>
            <button
              className="chip"
              disabled={!key || !l.evidence_url || busy}
              onClick={() => review(l, "approve")}
            >
              Approve
            </button>
            <button
              className="chip"
              disabled={!key || busy}
              onClick={() => review(l, "reject")}
            >
              Reject
            </button>
          </article>
        ))
      )}
    </>
  );
}
