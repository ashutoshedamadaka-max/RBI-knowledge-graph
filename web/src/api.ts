// Typed access to the FastAPI service. In production VITE_API_BASE_URL points at the Render API;
// in development Vite proxies these paths to localhost:8000.
const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

export type Verdict = "supported" | "partially_supported" | "not_supported";

export interface Claim { title: string | null; text: string; citation_ids: string[]; support: Verdict | null }
export interface Research {
  status: "grounded" | "insufficient_evidence" | "out_of_scope";
  display_title: string | null;
  direct_answer: Claim | null;
  sections: { id: string; title: string; claims: Claim[] }[];
}
export interface Chunk {
  chunk_id: string; document_id: string; document_title: string; text: string; source_url: string | null;
  paragraph_ref: string | null; heading_path: string | null; lifecycle: string; in_force_from: string | null;
  in_force_to: string | null;
}
export interface Notice { kind: "replaced" | "withdrawn" | "upcoming"; text: string; evidence_excerpt: string | null }
export interface Trace {
  timings_ms?: Record<string, number>;
  candidates?: Record<string, string[]>;
  graph_added?: { from: string; to: string }[];
  filtered_out?: { chunk_id: string; document_title: string; reason: string }[];
  filtered_out_count?: number;
  rerank?: { chunk_id: string; before: number; after: number; score: number }[];
  tokens?: Record<string, number>;
  cost_usd?: Record<string, number>;
}
export interface QueryResult {
  request_id: string; research: Research | null; retrieved_evidence: Chunk[]; as_of: string | null;
  notices: Notice[]; latency_ms: number; estimated_cost_usd: number; in_scope: boolean;
  pipeline: { retrieval_method: string; answer_mode: string; selected_evidence_count: number };
  trace: Trace;
}

export async function streamQuery(query: string, asOf: string | null, onStage: (stage: string) => void,
                                  onAnswer?: (preview: QueryResult) => void): Promise<QueryResult> {
  const response = await fetch(`${BASE}/query/stream`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, ...(asOf ? { as_of: asOf } : {}) }),
  });
  if (!response.ok || !response.body) throw new Error(`The research service answered ${response.status}.`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const kind = /^event: (.+)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1] ?? "{}";
      if (kind === "progress") onStage(JSON.parse(data).stage);
      if (kind === "answer" && onAnswer) {
        // The answer before its claim check: shown at once; the verdicts arrive with the result.
        const body = JSON.parse(data);
        onAnswer({ ...body, request_id: "", trace: {}, latency_ms: 0, estimated_cost_usd: 0, in_scope: true,
          pipeline: { retrieval_method: "", answer_mode: "checking", selected_evidence_count: body.retrieved_evidence.length } });
      }
      if (kind === "result") return JSON.parse(data);
      if (kind === "error") throw new Error(JSON.parse(data).detail);
    }
  }
  throw new Error("The research service closed the connection without an answer.");
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail ?? `Request failed (${response.status}).`);
  return response.json();
}
