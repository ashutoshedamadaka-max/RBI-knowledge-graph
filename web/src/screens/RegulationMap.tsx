import { useCallback, useEffect, useMemo, useState } from "react";
import { getJson } from "../api";
import { liveOrSaved, savedNode } from "../snapshot";
import GraphScene, { COLORS, MapEdge, MapNode } from "../components/GraphScene";
import { EmptyState, Icon } from "../components/UI";
interface MapData {
  nodes: MapNode[];
  edges: MapEdge[];
  applies_to_precision: { numerator: number; denominator: number } | null;
}
interface Detail {
  id: string;
  type: string;
  title?: string;
  label?: string;
  text?: string;
  heading?: string;
  lifecycle?: string;
  url?: string;
  issued?: string;
  in_force_from?: string;
  in_force_to?: string;
  provision_count?: number;
  edges: {
    direction: string;
    type: string;
    other: { id: string; type: string; title: string };
    quote?: string;
    method?: string;
    trust?: string;
    evidence_url?: string;
  }[];
}
const TODAY = new Date().toISOString().slice(0, 10);
const edgeLabel = (s: string) => s.toLowerCase().replaceAll("_", " ");
export default function RegulationMap() {
  const [data, setData] = useState<MapData | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [snapshot, setSnapshot] = useState(false);
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState<"documents" | "all" | "neighbors">(
    "documents",
  );
  const [flat, setFlat] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [detailError, setDetailError] = useState(false);
  const [detailAttempt, setDetailAttempt] = useState(0);
  const [trail, setTrail] = useState<string[]>([]);
  const [year, setYear] = useState(Number(TODAY.slice(0, 4)));
  const [linksShown, setLinksShown] = useState(15);
  useEffect(() => {
    const abort = new AbortController();
    setError(false);
    liveOrSaved<MapData>("/graph/map", "graph-map.json", abort.signal)
      .then((v) => {
        setData(v.data);
        setSnapshot(v.snapshot);
      })
      .catch(() => {
        if (!abort.signal.aborted) setError(true);
      });
    return () => abort.abort();
  }, [attempt]);
  const select = useCallback((id: string) => {
    setSelected(id);
    setTrail((t) => (t[t.length - 1] === id ? t : [...t, id]));
    setSearch("");
    setLinksShown(15);
  }, []);
  useEffect(() => {
    if (!selected) return;
    const abort = new AbortController();
    setDetail(null);
    setDetailError(false);
    (snapshot
      ? savedNode(selected)
      : getJson<Detail>(
          `/graph/node/${encodeURIComponent(selected)}`,
          abort.signal,
        )
    )
      .then((v) => {
        if (!abort.signal.aborted) setDetail(v);
      })
      .catch(() => {
        if (!abort.signal.aborted) setDetailError(true);
      });
    return () => abort.abort();
  }, [selected, detailAttempt, snapshot]);
  const documents = useMemo(
    () => data?.nodes.filter((n) => n.type === "Document") ?? [],
    [data],
  );
  const minYear = useMemo(
    () =>
      Math.min(
        Number(TODAY.slice(0, 4)),
        ...documents
          .map((n) => Number(n.issued?.slice(0, 4)))
          .filter((y) => y > 1900),
      ),
    [documents],
  );
  const day = year === Number(TODAY.slice(0, 4)) ? TODAY : `${year}-12-31`;
  const byId = useMemo(
    () => new Map(data?.nodes.map((n) => [n.id, n]) ?? []),
    [data],
  );
  const available = useMemo(
    () =>
      data?.nodes.filter((n) => {
        const doc = n.type === "Document" ? n : byId.get(n.document_id ?? "");
        return !doc?.issued || doc.issued <= day;
      }) ?? [],
    [data, byId, day],
  );
  const nodes = useMemo(() => {
    if (scope === "documents")
      return available.filter((n) => n.type === "Document");
    if (scope === "all") return available;
    const ids = new Set([selected]);
    data?.edges.forEach((e) => {
      if (e.source === selected) ids.add(e.target);
      if (e.target === selected) ids.add(e.source);
    });
    return available.filter((n) => ids.has(n.id));
  }, [available, scope, selected, data]);
  const edges = useMemo(() => {
    const ids = new Set(nodes.map((n) => n.id));
    return (
      data?.edges.filter((e) => ids.has(e.source) && ids.has(e.target)) ?? []
    );
  }, [data, nodes]);
  const matches =
    search.trim().length >= 2
      ? (data?.nodes
          .filter((n) =>
            (n.title ?? n.label ?? "")
              .toLowerCase()
              .includes(search.toLowerCase()),
          )
          .slice(0, 8) ?? [])
      : [];
  const selectedHidden = selected && !nodes.some((n) => n.id === selected);
  const children = selected
    ? available.filter((n) => n.document_id === selected)
    : [];
  if (error && !data)
    return (
      <EmptyState
        title="The graph could not load"
        retry={() => setAttempt((a) => a + 1)}
      >
        The service may be waking up. The explanation and saved graph results
        below remain available.
      </EmptyState>
    );
  if (!data)
    return (
      <div className="loading-state" role="status">
        <span className="spinner" /> Loading the graph. The service may need a
        moment to wake up.
      </div>
    );
  return (
    <section aria-label="Graph explorer">
      <p className="fine-print snapshot-status" role="status">
        {snapshot
          ? "Browsing the evaluated release snapshot. Live graph data is unavailable."
          : "Browsing the graph served by the research service."}{" "}
        <button className="text-link" onClick={() => setAttempt((a) => a + 1)}>
          Refresh data
        </button>
      </p>
      <div className="graph-toolbar">
        <label className="field">
          Find a document or paragraph
          <input
            type="search"
            placeholder="Try digital lending or microfinance"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label className="field">
          Show
          <select
            aria-label="Graph view scope"
            value={scope}
            onChange={(e) => setScope(e.target.value as typeof scope)}
          >
            <option value="documents">Document overview</option>
            <option value="all">All available connections</option>
            <option value="neighbors" disabled={!selected}>
              Selected neighborhood
            </option>
          </select>
        </label>
        <div className="segmented" aria-label="Graph dimension">
          <button aria-pressed={!flat} onClick={() => setFlat(false)}>
            3D explorer
          </button>
          <button aria-pressed={flat} onClick={() => setFlat(true)}>
            2D map
          </button>
        </div>
      </div>
      <div className="example-row graph-starts">
        <span className="mini-label">Start exploring</span>
        {["Digital lending", "Microfinance", "Withdrawn"].map((term) => (
          <button
            className="example-pill"
            key={term}
            onClick={() => {
              const node =
                documents.find(
                  (n) =>
                    (n.title ?? ".")
                      .toLowerCase()
                      .includes(term.toLowerCase()) && n.lifecycle === "ACTIVE",
                ) ??
                documents.find((n) =>
                  (n.title ?? ".").toLowerCase().includes(term.toLowerCase()),
                );
              if (node) {
                select(node.id);
                setScope("neighbors");
              }
            }}
          >
            {term}
            <Icon name="arrow" size={13} />
          </button>
        ))}
      </div>
      {search.trim().length >= 2 && (
        <div
          className="graph-search-results"
          role="region"
          aria-label="Graph search results"
        >
          {matches.length ? (
            matches.map((n) => (
              <button
                key={n.id}
                onClick={() => {
                  select(n.id);
                  setScope("neighbors");
                }}
              >
                <span className="mini-label">{n.type}</span>
                <br />
                {n.title ?? n.label}
              </button>
            ))
          ) : (
            <p role="status">No nodes match. Try another title or term.</p>
          )}
        </div>
      )}
      <div className="graph-layout">
        <div>
          {nodes.length ? (
            <GraphScene
              nodes={nodes}
              edges={edges}
              selected={selected}
              day={day}
              flat={flat}
              onSelect={select}
            />
          ) : (
            <EmptyState title="No nodes in this view">
              Try a later year or return to the document overview.
            </EmptyState>
          )}
          <p className="graph-help">
            {flat ? "Drag to pan." : "Drag to orbit; right-drag to pan."} Scroll
            or use + / − to zoom. Select a node to inspect it. Keyboard: arrows
            rotate, + / − zoom, Home resets.
          </p>
          <div className="graph-legend">
            {Object.entries(COLORS)
              .filter(([type]) => scope !== "documents" || type === "Document")
              .map(([type, color]) => (
                <span key={type}>
                  <i className="swatch" style={{ background: color }} />
                  {type === "Provision"
                    ? "Paragraph"
                    : type === "RegulatedEntity"
                      ? "Entity"
                      : type === "DefinedTerm"
                        ? "Defined term"
                        : type}
                </span>
              ))}
            <span>
              <i className="swatch" style={{ background: "#b87879" }} />
              Out of force on date
            </span>
          </div>
        </div>
        <aside
          className="card graph-inspector"
          aria-label="Selected graph node"
        >
          {!selected ? (
            <EmptyState title="Start with a document">
              Select a dot, search by name, or use the list below. Then explore
              its neighborhood to reveal linked paragraphs.
            </EmptyState>
          ) : detailError ? (
            <EmptyState
              title="Node details unavailable"
              retry={() => setDetailAttempt((a) => a + 1)}
            >
              Try loading this node again.
            </EmptyState>
          ) : !detail ? (
            <p role="status">Loading node evidence…</p>
          ) : (
            <>
              <div className="node-navigation">
                <button
                  className="text-link"
                  disabled={trail.length < 2}
                  onClick={() => {
                    const earlier = trail.slice(0, -1);
                    setTrail(earlier);
                    setSelected(earlier[earlier.length - 1] ?? null);
                    setLinksShown(15);
                  }}
                >
                  ← Previous node
                </button>
                <button
                  className="text-link"
                  onClick={() => {
                    setSelected(null);
                    setTrail([]);
                    setScope("documents");
                  }}
                >
                  Overview
                </button>
              </div>
              <div className="eyebrow">{detail.type}</div>
              <h2>
                {detail.type === "Provision"
                  ? `Paragraph ${detail.label ?? ""}`
                  : (detail.title ?? detail.label ?? detail.id)}
              </h2>
              {detail.lifecycle && (
                <p className="fine-print">
                  Recorded status today: {edgeLabel(detail.lifecycle)}
                  <br />
                  In force: {detail.in_force_from ?? "start unknown"} →{" "}
                  {detail.in_force_to ?? "no end recorded"}
                </p>
              )}
              {selectedHidden && (
                <p className="notice">
                  This node is outside the current view or was not yet published
                  on the selected date.
                </p>
              )}
              <div className="cta-row" style={{ margin: "15px 0" }}>
                <button
                  className="secondary"
                  onClick={() => setScope("neighbors")}
                >
                  Focus neighborhood
                </button>
              </div>
              {detail.heading && <p>{detail.heading}</p>}
              {detail.text && <div className="passage">{detail.text}</div>}
              {detail.url && (
                <a
                  className="text-link"
                  href={detail.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Official source <Icon name="external" size={13} />
                </a>
              )}
              {children.length > 0 && (
                <details className="disclosure">
                  <summary>Browse paragraphs ({children.length})</summary>
                  <div>
                    {children.slice(0, linksShown).map((n) => (
                      <button
                        className="chip"
                        key={n.id}
                        onClick={() => {
                          select(n.id);
                          setScope("neighbors");
                        }}
                      >
                        Paragraph {n.label ?? n.title}
                      </button>
                    ))}
                    {linksShown < children.length && (
                      <button
                        className="text-link"
                        onClick={() => setLinksShown((v) => v + 20)}
                      >
                        Show more paragraphs
                      </button>
                    )}
                  </div>
                </details>
              )}
              <h3 style={{ marginTop: 24 }}>
                Relationships ({detail.edges.length})
              </h3>
              <ul>
                {detail.edges.slice(0, linksShown).map((e, i) => (
                  <li key={i}>
                    <span className="mini-label">
                      {e.direction === "in" ? "Incoming · " : ""}
                      {edgeLabel(e.type)}
                    </span>
                    <br />
                    <button
                      className="text-link"
                      onClick={() => {
                        select(e.other.id);
                        setScope("neighbors");
                      }}
                    >
                      {e.other.title ?? e.other.id}
                    </button>
                    {e.type === "APPLIES_TO" && (
                      <p className="flag">
                        Machine-extracted; not used to filter answers.
                      </p>
                    )}
                    {e.trust &&
                      !["APPROVED", "AUTO_TRUSTED"].includes(e.trust) && (
                        <p className="flag">
                          Suggested relationship · awaiting review
                        </p>
                      )}
                    {e.quote && (
                      <details>
                        <summary>Read relationship evidence</summary>
                        <p>“{e.quote}”</p>
                        {e.evidence_url && (
                          <a
                            href={e.evidence_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Open evidence source
                          </a>
                        )}
                      </details>
                    )}
                  </li>
                ))}
              </ul>
              {linksShown < detail.edges.length && (
                <button
                  className="secondary"
                  onClick={() => setLinksShown((v) => v + 20)}
                >
                  Show more relationships
                </button>
              )}
            </>
          )}
        </aside>
      </div>
      <div className="time-control">
        <label htmlFor="graph-year">Explore the recorded timeline</label>
        <input
          id="graph-year"
          type="range"
          min={minYear}
          max={Number(TODAY.slice(0, 4))}
          value={year}
          onChange={(e) => setYear(Number(e.target.value))}
          aria-valuetext={day}
        />
        <output htmlFor="graph-year">{day}</output>
      </div>
      <p className="fine-print">
        Nodes appear from their recorded publication date; expired documents
        turn muted red. The timeline does not reconstruct historical graph
        extraction. Depth and spacing are visual layout choices, not regulatory
        meaning. The full graph includes obligations that appear in node details
        rather than this overview.
      </p>
      <details className="disclosure">
        <summary>
          Browse all documents without the canvas ({documents.length})
        </summary>
        <div>
          <p className="fine-print">
            This list includes documents from all years. Selecting one updates
            the inspector; the timeline still controls the map.
          </p>
          <div
            className="table-wrap"
            tabIndex={0}
            role="region"
            aria-label="Scrollable data table"
          >
            <table>
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Published</th>
                  <th>Recorded status today</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((n) => (
                  <tr key={n.id}>
                    <td>
                      <button
                        className="text-link"
                        onClick={() => {
                          select(n.id);
                          setScope("neighbors");
                        }}
                      >
                        {n.title}
                      </button>
                    </td>
                    <td>{n.issued ?? "Not recorded"}</td>
                    <td>{edgeLabel(n.lifecycle ?? "unknown")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </details>
    </section>
  );
}
