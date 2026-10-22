import { useEffect, useMemo, useRef, useState } from "react";
import Graph from "graphology";
import Sigma from "sigma";
import { getJson } from "../api";

interface MapNode {
  id: string; type: string; title?: string; label?: string; lifecycle?: string; issued?: string; in_force_from?: string;
  in_force_to?: string; document_id?: string; x: number; y: number; community?: number; degree: number;
}
interface MapData { nodes: MapNode[]; edges: { source: string; target: string; type: string }[]; applies_to_precision: { numerator: number; denominator: number } | null }
interface Detail { id: string; type: string; title?: string; label?: string; text?: string; heading?: string; lifecycle?: string;
  url?: string; issued?: string; in_force_from?: string; in_force_to?: string; provision_count?: number;
  edges: { direction: string; type: string; other: { id: string; type: string; title: string }; quote?: string; method?: string; trust?: string; evidence_url?: string }[] }

// Ten distinguishable hues for communities on the dark canvas.
const PALETTE = ["#7aa2ff", "#5fd3c4", "#f2b65c", "#c792ea", "#7fd36b", "#ff9e7a", "#6cc4ff", "#e6d36a", "#f78fb3", "#9fb3c8"];
const TODAY = new Date().toISOString().slice(0, 10);
const YEARS = Array.from({ length: Number(TODAY.slice(0, 4)) - 2019 }, (_, index) => 2020 + index);

export default function RegulationMap() {
  const [data, setData] = useState<MapData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [year, setYear] = useState(YEARS[YEARS.length - 1]);
  const [search, setSearch] = useState("");
  const container = useRef<HTMLDivElement>(null);
  const sigma = useRef<Sigma | null>(null);

  useEffect(() => { getJson<MapData>("/graph/map").then(setData).catch((exc) => setError(exc.message)); }, []);

  const documents = useMemo(() => new Map((data?.nodes ?? []).filter((n) => n.type === "Document").map((n) => [n.id, n])), [data]);
  const day = year === YEARS[YEARS.length - 1] ? TODAY : `${year}-12-31`;

  // Build the WebGL map once; the time slider and selection only change how nodes are drawn.
  useEffect(() => {
    if (!data || !container.current) return;
    const graph = new Graph({ multi: true });
    const maxDegree = Math.max(...data.nodes.map((node) => node.degree), 1);
    for (const node of data.nodes) {
      graph.addNode(node.id, {
        x: node.x, y: node.y, label: node.type === "Provision" ? undefined : node.title ?? node.label ?? node.id,
        size: 1.5 + 9 * Math.sqrt(node.degree / maxDegree) * (node.type === "Document" ? 1.6 : 1),
        color: PALETTE[(node.community ?? 0) % PALETTE.length], nodeType: node.type,
      });
    }
    for (const edge of data.edges) {
      if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
        graph.addEdge(edge.source, edge.target, { color: edge.type === "SUPERSEDES" || edge.type === "WITHDRAWS" ? "#ff8a8a" : "#6f80b8", size: 0.4, edgeType: edge.type });
      }
    }
    const renderer = new Sigma(graph, container.current, {
      labelColor: { color: "#dfe6ff" }, labelRenderedSizeThreshold: 9, defaultEdgeType: "line", minCameraRatio: 0.05,
    });
    renderer.on("clickNode", ({ node }) => setSelected(node));
    sigma.current = renderer;
    return () => { renderer.kill(); sigma.current = null; };
  }, [data]);

  // Time slider: a document appears from its issue date; once out of force it is dimmed red.
  useEffect(() => {
    const renderer = sigma.current;
    if (!renderer || !data) return;
    const byId = new Map(data.nodes.map((node) => [node.id, node]));
    const statusOf = (node: MapNode | undefined) => {
      const document = node?.type === "Document" ? node : node?.document_id ? documents.get(node.document_id) : undefined;
      if (!document) return "neutral";
      if (document.issued && document.issued > day) return "hidden";
      if (document.in_force_to && document.in_force_to <= day) return "withdrawn";
      return "current";
    };
    renderer.setSetting("nodeReducer", (node, attributes) => {
      const status = statusOf(byId.get(node));
      if (status === "hidden") return { ...attributes, hidden: true };
      const isSelected = node === selected;
      return { ...attributes, color: status === "withdrawn" ? "#7a3b46" : attributes.color,
        size: isSelected ? attributes.size * 2 : attributes.size, highlighted: isSelected, zIndex: isSelected ? 1 : 0 };
    });
    renderer.setSetting("edgeReducer", (_edge, attributes) => ({ ...attributes }));
    renderer.refresh();
  }, [day, data, documents, selected]);

  useEffect(() => {
    if (!selected) return;
    setDetail(null);
    getJson<Detail>(`/graph/node/${encodeURIComponent(selected)}`).then(setDetail).catch((exc) => setError(exc.message));
    const renderer = sigma.current;
    const position = renderer?.getNodeDisplayData(selected);
    if (renderer && position) renderer.getCamera().animate({ x: position.x, y: position.y, ratio: 0.25 }, { duration: 400 });
  }, [selected]);

  const matches = search.length >= 3 ? [...documents.values()].filter((n) => (n.title ?? "").toLowerCase().includes(search.toLowerCase())).slice(0, 8) : [];
  const precision = data?.applies_to_precision;

  return (
    <div>
      <h2>Explore the map</h2>
      <p className="muted">How to read it: each dot is a document, paragraph, term, lender type or loan type. <strong>Colour</strong> groups rules that are closely linked; <strong>size</strong> shows how connected a dot is; <strong>dimmed red</strong> means no longer in force in the chosen year. Drag to move, scroll to zoom, click a dot to see its text and the RBI quotes behind its links, and slide the year to replay how the rulebook changed. Prefer a list? Open "All documents as a list" below the map.</p>
      <div className="map-tools">
        <label>Search documents <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="e.g. digital lending" /></label>
        <label>Year: <strong>{year === YEARS[YEARS.length - 1] ? "today" : year}</strong>
          <input type="range" min={YEARS[0]} max={YEARS[YEARS.length - 1]} value={year} onChange={(event) => setYear(Number(event.target.value))} aria-valuetext={String(year)} />
        </label>
        <div className="legend"><span>● current</span><span style={{ color: "#c06070" }}>● out of force</span><span>red lines = replaced / withdrawn links</span></div>
      </div>
      {matches.length > 0 && <div style={{ marginBottom: 10 }}>{matches.map((node) => (
        <button key={node.id} className="chip" onClick={() => { setSelected(node.id); setSearch(""); }}>{node.title}</button>))}</div>}
      {error && <p className="status-bad" role="alert">{error}</p>}
      <div className="map-layout">
        <div className="canvas map-canvas" ref={container} role="img" aria-label="Knowledge graph of RBI lending rules. Use the list below or the search box to explore it without the visual map." />
        <aside className="card" aria-live="polite">
          {!detail && <p className="muted">Select a node to see its text, status and every link with the RBI text it rests on.</p>}
          {detail && <NodePanel detail={detail} onSelect={setSelected} precision={precision ?? null} />}
        </aside>
      </div>
      <details style={{ marginTop: 16 }} className="card">
        <summary>All documents as a list</summary>
        <div className="table-wrap"><table>
          <thead><tr><th>Document</th><th>Issued</th><th>Status</th><th>In force</th></tr></thead>
          <tbody>{[...documents.values()].sort((a, b) => (b.issued ?? "").localeCompare(a.issued ?? "")).map((node) => (
            <tr key={node.id}><td><button className="chip" onClick={() => setSelected(node.id)}>{node.title}</button></td>
              <td>{node.issued}</td><td className={node.lifecycle === "ACTIVE" ? "status-ok" : "status-bad"}>{node.lifecycle?.toLowerCase()}</td>
              <td>{node.in_force_from ?? "?"} → {node.in_force_to ?? "now"}</td></tr>
          ))}</tbody>
        </table></div>
      </details>
    </div>
  );
}

const EDGE_TEXT: Record<string, string> = {
  PART_OF: "part of", REFERS_TO: "refers to", DEFINES: "defines", REQUIRES: "requires", APPLIES_TO: "applies to",
  SUPERSEDES: "replaces", AMENDS: "amends", WITHDRAWS: "withdraws", ISSUED_BY: "issued by",
};

function NodePanel({ detail, onSelect, precision }: { detail: Detail; onSelect: (id: string) => void; precision: MapData["applies_to_precision"] }) {
  const out = detail.edges.filter((edge) => edge.type !== "PART_OF" || detail.type !== "Document");
  return (
    <div>
      <h2>{detail.type === "Provision" ? `Paragraph ${detail.label}` : detail.title ?? detail.id}</h2>
      <p className="muted">{detail.type}{detail.lifecycle ? ` · ${detail.lifecycle.toLowerCase()}` : ""}{detail.issued ? ` · issued ${detail.issued}` : ""}
        {detail.in_force_from ? ` · in force ${detail.in_force_from} → ${detail.in_force_to || "now"}` : ""}{detail.provision_count ? ` · ${detail.provision_count} paragraphs` : ""}</p>
      {detail.heading && <p className="muted">{detail.heading}</p>}
      {detail.text && <div className="passage">{detail.text}</div>}
      {detail.url && <p><a href={detail.url} target="_blank" rel="noreferrer">Open on rbi.org.in</a></p>}
      <h3 style={{ marginTop: 12 }}>Links ({out.length})</h3>
      <ul>{out.slice(0, 40).map((edge, index) => (
        <li key={index} style={{ marginBottom: 8 }}>
          {edge.direction === "in" ? <><button className="chip" onClick={() => onSelect(edge.other.id)}>{edge.other.title}</button> {EDGE_TEXT[edge.type] ?? edge.type} this</>
            : <>{EDGE_TEXT[edge.type] ?? edge.type} <button className="chip" onClick={() => onSelect(edge.other.id)}>{edge.other.title}</button></>}
          {edge.type === "APPLIES_TO" && precision && <div className="flag">Machine-extracted: about {precision.numerator} in {precision.denominator} such links were right when checked.</div>}
          {edge.trust && edge.trust !== "APPROVED" && edge.trust !== "AUTO_TRUSTED" && <div className="flag">Suggested link, awaiting review</div>}
          {edge.quote && <div className="muted" style={{ fontSize: 13 }}>“{edge.quote.slice(0, 220)}”</div>}
        </li>
      ))}</ul>
    </div>
  );
}
