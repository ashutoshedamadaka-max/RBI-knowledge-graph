import RegulationMap from "./RegulationMap";
import { ratio, useQuality } from "../quality";

const NODE_TEXT: [string, string, string][] = [
  ["Document", "An RBI direction or circular", "#7aa2ff"],
  ["Provision", "One numbered paragraph inside a document", "#5fd3c4"],
  ["Obligation", "Something a paragraph requires someone to do", "#f2b65c"],
  ["DefinedTerm", "A term a paragraph defines, such as 'digital lending'", "#c792ea"],
  ["RegulatedEntity", "A kind of lender or party, such as an NBFC or a recovery agent", "#7fd36b"],
  ["Product", "A kind of loan, such as a gold loan or a credit card", "#ff9e7a"],
  ["Authority", "The RBI department that issued a document", "#9fb3c8"],
];
const LINK_TEXT: [string, string, string][] = [
  ["SUPERSEDES", "replaces", "A new document replaces an old one"],
  ["WITHDRAWS", "withdraws", "RBI's register lists a document as withdrawn"],
  ["AMENDS", "amends", "A document changes part of another"],
  ["PART_OF", "is part of", "A paragraph belongs to its document"],
  ["REFERS_TO", "refers to", "A paragraph points to another paragraph or document"],
  ["DEFINES", "defines", "A paragraph defines a term"],
  ["REQUIRES", "requires", "A paragraph imposes an obligation"],
  ["APPLIES_TO", "applies to", "A paragraph governs a kind of lender or loan"],
  ["ISSUED_BY", "issued by", "A document came from an RBI department"],
];

export default function KnowledgeGraph() {
  const { report } = useQuality();
  const build = report?.graph_build?.data;
  const hand: any = report?.graph_quality?.data?.results?.hand;
  const drafted: any = report?.graph_quality?.data?.results?.["model-drafted, reviewed by Ashu"];
  const fresh: any = report && Object.entries(report.graph_quality?.data?.results ?? {}).find(([key]) => key.startsWith("fresh"))?.[1];
  const onOff = report?.graph_on_off?.data?.results;
  const trust = [
    { what: "Which rule replaced which, and which were withdrawn", how: "Read from RBI's own wording and register", use: "Used in answers", score: "Checked in the history replay", ok: true },
    { what: "A paragraph points to another paragraph", how: "Found by pattern ('paragraph 12')", use: "Used in answers: pulls the cited paragraph in",
      score: hand && drafted && fresh ? `Few such links in the labelled samples: ${ratio(hand.REFERS_TO?.precision)} (hand), ${ratio(drafted.REFERS_TO?.precision)} and ${ratio(fresh.REFERS_TO?.precision)} (AI-drafted, checked) were right. Its value is shown by the answer test below.` : "", ok: true },
    { what: "What a paragraph requires", how: "Extracted by AI, with a quote", use: "Shown on the map", score: hand ? `${ratio(hand.REQUIRES?.precision)} right on hand-labelled paragraphs` : "", ok: true },
    { what: "Who a paragraph applies to", how: "Extracted by AI, with a quote", use: "Shown with a warning; never used in answers", score: fresh ? `${ratio(fresh.APPLIES_TO?.precision)} right on fresh paragraphs` : "", ok: false },
  ];
  const multiOff = onOff?.["hybrid+as-of"]?.by_type?.multi_hop?.["recall@5"];
  const multiOn = onOff?.graph?.by_type?.multi_hop?.["recall@5"];

  return (
    <div className="page" style={{ maxWidth: "none" }}>
      <div className="page">
        <section className="hero">
          <div className="eyebrow">Knowledge graph</div>
          <h1>A map of how RBI's rules connect to each other</h1>
          <p className="lead">Search treats every paragraph as a separate page. But rules are connected: one replaces another, one paragraph says "subject to paragraph 12", one defines a term others use. A <strong>knowledge graph</strong> stores those connections explicitly, as dots (things) and lines (relationships), each line backed by a quote from RBI's text.</p>
        </section>

        <section>
          <div className="grid-2">
            <div className="card">
              <h2>The dots{build ? `: ${Object.values(build.nodes as Record<string, number>).reduce((a, b) => a + b, 0).toLocaleString()} in total` : ""}</h2>
              <div style={{ display: "grid", gap: 8 }}>{NODE_TEXT.map(([type, text, color]) => (
                <div className="legend-item" key={type}><span className="swatch" style={{ background: color }} /><div><strong>{text}</strong>{build?.nodes?.[type] ? <span className="muted"> · {build.nodes[type].toLocaleString()}</span> : null}</div></div>
              ))}</div>
            </div>
            <div className="card">
              <h2>The lines{build ? `: ${Object.values(build.edges as Record<string, number>).reduce((a, b) => a + b, 0).toLocaleString()} in total` : ""}</h2>
              <div className="table-wrap"><table><tbody>{LINK_TEXT.map(([type, verb, text]) => (
                <tr key={type}><td><strong>{verb}</strong></td><td className="muted">{text}</td><td>{build?.edges?.[type]?.toLocaleString() ?? "—"}</td></tr>
              ))}</tbody></table></div>
            </div>
          </div>
        </section>

        <section>
          <span className="pm-term">Trust calibration</span>
          <h2>What the graph is trusted for, and what it is not</h2>
          <p className="prose">Not every connection is equally reliable. Each kind was measured against paragraphs labelled by hand, and only the reliable ones are allowed to influence an answer.</p>
          <div className="table-wrap"><table>
            <thead><tr><th>Connection</th><th>How it is found</th><th>How it is used</th><th>Measured</th></tr></thead>
            <tbody>{trust.map((row) => (
              <tr key={row.what}><td>{row.what}</td><td className="muted">{row.how}</td>
                <td className={row.ok ? "status-ok" : "status-warn"}>{row.use}</td><td>{row.score}</td></tr>
            ))}</tbody>
          </table></div>
          {multiOff && multiOn && <p>On questions that need two linked paragraphs, following the graph's cross-references raised the right paragraph in the top 5 from <span className="num">{ratio(multiOff)}</span> to <span className="num">{ratio(multiOn)}</span>. It made no difference to other kinds of question, so it is used for exactly that job.</p>}
        </section>
      </div>
      <RegulationMap />
    </div>
  );
}
