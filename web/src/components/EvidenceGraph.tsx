import { Chunk, QueryResult } from "../api";

interface Props {
  result: QueryResult;
  reveal: number;
  highlighted: Set<string>;
  onOpen: (chunkId: string) => void;
}

const shortTitle = (title: string) =>
  title
    .replace(
      /^Reserve Bank of India \((Non-Banking Financial Companies [–-] )?/,
      "",
    )
    .replace(/\)? ?Directions?, \d{4}.*$/, "")
    .slice(0, 40);

/** The documents and paragraphs this answer used, the cross-references the graph added, and what the
 * in-force filter removed. Drawn as SVG (a handful of nodes), with the same facts as a list beside it. */
export default function EvidenceGraph({
  result,
  reveal,
  highlighted,
  onOpen,
}: Props) {
  const chunks = result.retrieved_evidence;
  const citedIds = new Set(
    [
      result.research?.direct_answer,
      ...(result.research?.sections ?? []).flatMap((s) => s.claims),
    ].flatMap((claim) => claim?.citation_ids ?? []),
  );
  const documents = [
    ...new Map(
      chunks.map((chunk) => [chunk.document_id, chunk.document_title]),
    ).entries(),
  ];
  const removed = [
    ...new Map(
      (result.trace.filtered_out ?? []).map((item) => [
        item.document_title,
        item.reason,
      ]),
    ).entries(),
  ].slice(0, 3);
  const added = (result.trace.graph_added ?? []).filter(
    (edge) =>
      chunks.some((c) => c.chunk_id === edge.from) &&
      chunks.some((c) => c.chunk_id === edge.to),
  );

  const rowHeight = 44;
  const docY = new Map(
    documents.map(([id], index) => [id, 30 + index * rowHeight * 1.6]),
  );
  const chunkPos = new Map<string, { x: number; y: number }>();
  chunks.forEach((chunk, index) =>
    chunkPos.set(chunk.chunk_id, { x: 250, y: 24 + index * rowHeight }),
  );
  const height =
    Math.max(
      30 + documents.length * rowHeight * 1.6,
      24 + chunks.length * rowHeight,
    ) +
    removed.length * 40 +
    20;

  const node = (chunk: Chunk) => {
    const position = chunkPos.get(chunk.chunk_id)!;
    const isCited = citedIds.has(chunk.chunk_id);
    const glow = highlighted.has(chunk.chunk_id);
    return (
      <g
        key={chunk.chunk_id}
        transform={`translate(${position.x},${position.y})`}
        style={{ cursor: "pointer" }}
        onClick={() => onOpen(chunk.chunk_id)}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onOpen(chunk.chunk_id);
          }
        }}
        aria-label={`Open paragraph ${chunk.paragraph_ref ?? "without a recorded number"} from ${chunk.document_title}`}
      >
        <circle
          r={glow ? 9 : 7}
          fill={reveal >= 2 && isCited ? "#8aa6ff" : "#3a4672"}
          stroke={glow ? "#fff0a3" : "none"}
          strokeWidth={3}
          opacity={reveal >= 1 ? 1 : 0.2}
        />
        <text x={14} y={4}>
          para {chunk.paragraph_ref ?? "?"}
          {isCited ? " · cited" : ""}
        </text>
      </g>
    );
  };

  return (
    <>
      <div className="canvas" style={{ padding: 8 }}>
        <svg
          viewBox={`0 0 360 ${height}`}
          width="100%"
          role="group"
          aria-label={`${documents.length} documents and ${chunks.length} paragraphs behind this answer`}
        >
          {reveal >= 1 &&
            chunks.map((chunk) => {
              const from = chunkPos.get(chunk.chunk_id)!;
              return (
                <line
                  key={`l-${chunk.chunk_id}`}
                  x1={22}
                  y1={docY.get(chunk.document_id)}
                  x2={from.x}
                  y2={from.y}
                  stroke="#5f6fa8"
                  strokeOpacity={0.45}
                />
              );
            })}
          {reveal >= 1 &&
            added.map((edge, index) => {
              const a = chunkPos.get(edge.from)!;
              const b = chunkPos.get(edge.to)!;
              return (
                <path
                  key={`g-${index}`}
                  d={`M${a.x},${a.y} C${a.x + 90},${a.y} ${b.x + 90},${b.y} ${b.x},${b.y}`}
                  fill="none"
                  stroke="#8aa6ff"
                  strokeDasharray="4 3"
                />
              );
            })}
          {documents.map(([id, title]) => (
            <g key={id} transform={`translate(22,${docY.get(id)})`}>
              <circle r={11} fill="#1f4fd8" opacity={reveal >= 0 ? 1 : 0} />
              <text x={-14} y={26}>
                {shortTitle(title)}
              </text>
            </g>
          ))}
          {chunks.map(node)}
          {removed.map(([title], index) => (
            <g
              key={title}
              transform={`translate(22,${height - 30 - (removed.length - 1 - index) * 40})`}
              opacity={0.55}
            >
              <circle
                r={10}
                fill="none"
                stroke="#ff8a8a"
                strokeDasharray="3 3"
              />
              <text x={18} y={4}>
                Removed: {shortTitle(title)}
              </text>
            </g>
          ))}
        </svg>
      </div>
      <details style={{ marginTop: 10 }}>
        <summary>Same evidence as a list</summary>
        <ul>
          {documents.map(([id, title]) => (
            <li key={id}>
              {title}
              <ul>
                {chunks
                  .filter((chunk) => chunk.document_id === id)
                  .map((chunk) => (
                    <li key={chunk.chunk_id}>
                      <button
                        className="chip"
                        onClick={() => onOpen(chunk.chunk_id)}
                      >
                        Paragraph {chunk.paragraph_ref}
                      </button>
                      {citedIds.has(chunk.chunk_id)
                        ? " cited by the answer"
                        : " retrieved, not cited"}
                    </li>
                  ))}
              </ul>
            </li>
          ))}
          {added.length > 0 && (
            <li>
              {added.length} paragraph(s) added because a top result cites them
              (knowledge graph).
            </li>
          )}
          {removed.map(([title, reason]) => (
            <li key={title}>
              Removed by the in-force filter: {title}: {reason}.
            </li>
          ))}
        </ul>
      </details>
    </>
  );
}
