import saved from "./data/quality.json";
// Results travel with the release; reading the case study never waits for a sleeping API.
export type Report = Record<string, any>;
export const REPORT: Report = saved;
export const REPO =
  "https://github.com/ashutoshedamadaka-max/RBI-knowledge-graph";
export const evidenceUrl = (file: string) =>
  `${REPO}/blob/main/data/evaluation/${file.replace(/^data\/evaluation\//, "")}`;
export function useQuality() {
  return { report: REPORT, error: null };
}
export const pct = (value: number | null | undefined) =>
  value == null ? "Not measured" : `${Number((value * 100).toFixed(2))}%`;
export const ratio = (
  m: { numerator: number; denominator: number } | undefined,
) => (m ? `${m.numerator} of ${m.denominator}` : "Not measured");
export function headline(report: Report) {
  const test = report.answers_test?.status === "measured";
  const source = test ? report.answers_test : report.answers_dev;
  return {
    results: source?.data?.results ?? {},
    data: source?.data ?? {},
    split: test ? "held-out test set" : "development set",
    file: source?.file,
  };
}
/** Recover the integer count from the saved rounded rate: evidence coverage, not correctness. */
export const count = (rate: { value: number | null; n: number } | undefined) =>
  rate && rate.value !== null
    ? `${Math.round(rate.value * rate.n)} of ${rate.n}`
    : "Not measured";
