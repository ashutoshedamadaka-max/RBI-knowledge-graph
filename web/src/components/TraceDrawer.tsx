import { QueryResult } from "../api";

const STEP_NAMES: Record<string, string> = {
  bm25: "Keyword search (BM25)",
  openai_embeddings: "Meaning search (OpenAI embeddings) and fusion",
  graph_cross_references: "Knowledge graph: add cited paragraphs",
  in_force_filter: "In-force filter",
  fused: "Fused ranking (keyword + meaning)",
  cohere_rerank: "Re-ranking (Cohere)",
  answer: "Answer (gpt-4o-mini)",
  claim_check: "Claim check (gpt-4o-mini)",
};

/** Everything the system did for this answer: time per stage, candidates, removals, re-ranking, tokens, cost. */
export default function TraceDrawer({ result }: { result: QueryResult }) {
  const trace = result.trace;
  const titles = new Map(
    result.retrieved_evidence.map((chunk) => [
      chunk.chunk_id,
      `${chunk.document_title.slice(0, 60)} · para ${chunk.paragraph_ref}`,
    ]),
  );
  const label = (id: string) => titles.get(id) ?? id;
  const cost = trace.cost_usd ?? {};
  const tokens = trace.tokens ?? {};

  return (
    <details className="trace">
      <summary>Trace: how this answer was produced</summary>
      <div className="two-col">
        <div>
          <h3>Time per stage</h3>
          <table>
            <tbody>
              {Object.entries(trace.timings_ms ?? {}).map(([step, ms]) => (
                <tr key={step}>
                  <td>{STEP_NAMES[step] ?? step}</td>
                  <td>{ms.toLocaleString()} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3 style={{ marginTop: 14 }}>Tokens and cost</h3>
          <table>
            <tbody>
              <tr>
                <td>Answer</td>
                <td>
                  {tokens.answer_input ?? 0} in · {tokens.answer_output ?? 0}{" "}
                  out
                </td>
                <td>${(cost.answer ?? 0).toFixed(5)}</td>
              </tr>
              <tr>
                <td>Claim check</td>
                <td>
                  {tokens.check_input ?? 0} in · {tokens.check_output ?? 0} out
                </td>
                <td>${(cost.claim_check ?? 0).toFixed(5)}</td>
              </tr>
            </tbody>
          </table>
          <p className="muted">
            Steps run: {result.pipeline.retrieval_method.replaceAll("+", " → ")}
          </p>
        </div>
        <div>
          <h3>Re-ranking: position before → after</h3>
          {trace.rerank?.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Passage</th>
                    <th>Before</th>
                    <th>After</th>
                    <th>Score</th>
                  </tr>
                </thead>
                <tbody>
                  {trace.rerank.map((row) => (
                    <tr key={row.chunk_id}>
                      <td>{label(row.chunk_id)}</td>
                      <td>{row.before}</td>
                      <td>{row.after}</td>
                      <td>{row.score.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">Re-ranking did not run for this answer.</p>
          )}
        </div>
      </div>
      <div className="two-col">
        <div>
          <h3>
            Removed by the in-force filter ({trace.filtered_out_count ?? 0} of
            the top 30)
          </h3>
          {trace.filtered_out?.length ? (
            <ul>
              {trace.filtered_out.map((item) => (
                <li key={item.chunk_id}>
                  {item.document_title}:{" "}
                  <span className="muted">{item.reason}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">
              Nothing among the top candidates was out of force on this date.
            </p>
          )}
        </div>
        <div>
          <h3>Added by the knowledge graph</h3>
          {trace.graph_added?.length ? (
            <ul>
              {trace.graph_added.map((edge, index) => (
                <li key={index}>
                  {label(edge.from)} cites {label(edge.to)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No top result cited another paragraph.</p>
          )}
          <h3>Top candidates per search method</h3>
          {Object.entries(trace.candidates ?? {}).map(([step, ids]) => (
            <p key={step}>
              <strong>{STEP_NAMES[step] ?? step}:</strong>{" "}
              {ids.slice(0, 5).map(label).join("; ")}
            </p>
          ))}
        </div>
      </div>
    </details>
  );
}
