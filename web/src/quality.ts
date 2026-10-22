import { useEffect, useState } from "react";
import { getJson } from "./api";

/* Every number in the story pages comes from the saved evaluation runs served by /quality.
   Fetched once per visit and shared by every page. */
export type Report = Record<string, any>;

let pending: Promise<Report> | null = null;

export function useQuality(): { report: Report | null; error: string | null } {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    pending ??= getJson<Report>("/quality");
    pending.then(setReport).catch((exc) => { pending = null; setError(exc.message); });
  }, []);
  return { report, error };
}

export const pct = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;

export const ratio = (m: { numerator: number; denominator: number } | undefined) => (m ? `${m.numerator} of ${m.denominator}` : "—");

/** The answer results to headline: the held-out test run when it exists, otherwise dev (labelled as such). */
export function headline(report: Report) {
  const test = report.answers_test?.status === "measured";
  const source = test ? report.answers_test : report.answers_dev;
  return { results: source?.data?.results ?? {}, data: source?.data ?? {}, split: test ? "held-out test set" : "dev set", file: source?.file };
}

/** Correct answers among those with an answer key, as "a of b" from a bootstrap rate (value × n). */
export const count = (rate: { value: number | null; n: number } | undefined) =>
  rate && rate.value !== null ? `${Math.round(rate.value * rate.n)} of ${rate.n}` : "—";
