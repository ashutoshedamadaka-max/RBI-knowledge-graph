// The fallback is generated only from the committed evaluated release. Callers label it as saved data.
import { getJson } from "./api";
export async function saved<T>(file: string): Promise<T> {
  const r = await fetch(`/evidence/${file}`);
  if (!r.ok) throw new Error("The saved release could not load.");
  return r.json();
}
export async function liveOrSaved<T>(
  path: string,
  file: string,
  signal?: AbortSignal,
): Promise<{ data: T; snapshot: boolean }> {
  const abort = new AbortController();
  const cancel = () => abort.abort();
  signal?.addEventListener("abort", cancel, { once: true });
  const timer = setTimeout(() => abort.abort(), 4500);
  try {
    const data = await getJson<T>(path, abort.signal);
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    return { data, snapshot: false };
  } catch (e) {
    if (signal?.aborted) throw e;
    const data = await saved<T>(file);
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    return { data, snapshot: true };
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
}
let graph: Promise<{ nodes: any[]; edges: any[] }> | null = null;
export async function savedNode(id: string) {
  graph ??= saved<{ nodes: any[]; edges: any[] }>("graph.json").catch((e) => {
    graph = null;
    throw e;
  });
  const data = await graph;
  const node = data.nodes.find((n) => n.id === id);
  if (!node) throw new Error("Node absent from the saved release.");
  const byId = new Map(data.nodes.map((n) => [n.id, n]));
  const describe = (key: string) => {
    const n = byId.get(key);
    return { id: key, type: n?.type, title: n?.title ?? n?.label ?? key };
  };
  const edges = data.edges
    .filter((e) => e.source === id || e.target === id)
    .filter(
      (e) =>
        !(
          e.target === id &&
          e.type === "PART_OF" &&
          byId.get(e.source)?.type === "Provision"
        ),
    )
    .map((e) => ({
      ...e,
      direction: e.source === id ? "out" : "in",
      other: describe(e.source === id ? e.target : e.source),
    }));
  return {
    ...node,
    edges,
    provision_count:
      node.type === "Document"
        ? data.edges.filter((e) => e.target === id && e.type === "PART_OF")
            .length
        : undefined,
  };
}
