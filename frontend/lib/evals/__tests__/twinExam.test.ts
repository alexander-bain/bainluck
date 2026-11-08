/**
 * #12102 S2 — the twin exam renders its scorer's record and never re-grades it.
 *
 * `data/twin-exam-2026-11-05.json` is Builder B's S0a export (#12118). These
 * tests hold the page's reading of it to the record: the nine gates with their
 * stored verdicts pass by pass (four passed, five failed), a license per kind
 * of pair, the scorer's own 95% ranges (and `wilson95` reproduces every one of
 * them, and the receipt's rounding), and the timeline's run-1 row agrees with
 * the record it was transcribed beside.
 */

import RAW from "@/lib/evals/data/twin-exam-2026-11-05.json";
import { loadRuns } from "@/lib/evals/runs";
import { EVALS_SOURCES } from "@/lib/evals/sources";
import {
  GATE_WORDS,
  PASSES,
  RELATIONS,
  RELATION_WORDS,
  SPLITS,
  acrossPasses,
  examProblem,
  examTruth,
  loadExam,
} from "@/lib/evals/twinExam";
import { pacificDayLabel } from "@/lib/evals/truth";
import { rangeText, wilson95 } from "@/lib/evals/wilson";

type Raw = typeof RAW;
const clone = (): Raw => JSON.parse(JSON.stringify(RAW));

describe("wilson95", () => {
  it.each([
    [24, 25, "80.5–99.3%"],
    [0, 3, "0.0–56.1%"],
    [12, 14, "60.1–96.0%"],
    [3, 3, "43.9–100.0%"],
    [7, 13, "29.1–76.8%"],
    [0, 5, "0.0–43.4%"],
  ])("%i/%i reproduces the published range %s", (k, n, published) => {
    const range = wilson95(k, n);
    expect(range).not.toBeNull();
    expect(rangeText(range as [number, number])).toBe(published);
  });

  it("reproduces every range in the scorer's record to six places, and has none where the record has none", () => {
    let checked = 0;
    for (const p of PASSES) {
      for (const s of SPLITS) {
        for (const r of RELATIONS) {
          for (const metric of ["recall", "precision"] as const) {
            const c = (RAW.per_pass[p][s].per_relation as Record<string, Record<string, { k: number; n: number; wilson95: number[] | null }>>)[r][metric];
            const mine = wilson95(c.k, c.n);
            if (c.wilson95 === null) {
              expect({ p, s, r, metric, mine }).toEqual({ p, s, r, metric, mine: null });
            } else {
              expect(mine?.map((x) => Number(x.toFixed(6)))).toEqual(c.wilson95);
              checked += 1;
            }
          }
        }
      }
    }
    expect(checked).toBeGreaterThan(100);
  });

  it("has nothing to estimate at 0/0 or for an impossible count", () => {
    expect(wilson95(0, 0)).toBeNull();
    expect(wilson95(4, 3)).toBeNull();
    expect(wilson95(-1, 3)).toBeNull();
  });
});

describe("the exam record", () => {
  const exam = loadExam();

  it("reads, FAIL as FAIL, stamped with the scorer's own time and receipt", () => {
    expect(examProblem(RAW)).toBeNull();
    expect(exam?.result).toBe("fail");
    expect(exam && examTruth(exam)).toEqual({
      kind: "last_run",
      asOf: RAW.recorded_at_pt,
      source: { label: "Matcher exam results", href: RAW.receipt_url },
    });
    expect(pacificDayLabel(RAW.recorded_at_pt)).toBe("Nov 5");
  });

  it("nine gates, in the record's order: four passed and five failed, each pass's verdict as stored", () => {
    expect(exam?.gates.map((g) => g.id)).toEqual(RAW.gate_results.map((g) => g.id));
    expect(exam?.gates.filter((g) => g.result === "pass")).toHaveLength(4);
    expect(exam?.gates.filter((g) => g.result === "fail")).toHaveLength(5);
    for (const [i, g] of (exam?.gates ?? []).entries()) {
      const raw = RAW.gate_results[i] as { by_pass?: Record<string, { result: string }>; observed?: { result: string } };
      if (raw.by_pass) {
        for (const p of PASSES) expect(g.perPass?.[p].result.toUpperCase()).toBe(raw.by_pass[p].result);
        expect(g.observed).toBeNull();
      } else {
        expect(g.perPass).toBeNull();
        expect(g.observed?.result.toUpperCase()).toBe(raw.observed?.result);
      }
    }
  });

  it("a gate counts as passed only when every pass passed it", () => {
    const broken = clone();
    (broken.gate_results[0] as { by_pass: Record<string, { result: string }> }).by_pass["2"].result = "FAIL";
    const g = loadExam(broken)?.gates[0];
    expect(g?.perPass?.["1"].result).toBe("pass");
    expect(g?.result).toBe("fail");
  });

  it("every gate and every count has plain words; every relation has a name", () => {
    for (const g of exam?.gates ?? []) {
      expect({ gate: g.id, words: !!GATE_WORDS[g.id] }).toEqual({ gate: g.id, words: true });
      const cells = g.perPass ? PASSES.map((p) => g.perPass![p]) : [g.observed!];
      for (const c of cells) for (const count of c.counts) expect(GATE_WORDS[g.id].units[count.key]).toBeTruthy();
    }
    expect(Object.keys(GATE_WORDS).sort()).toEqual(RAW.gate_results.map((g) => g.id).sort());
    for (const r of RELATIONS) expect(RELATION_WORDS[r]).toBeTruthy();
  });

  it("licenses: HELD for twins and same number, FAIL for the three-label group, NOT ELIGIBLE for the rest", () => {
    expect(exam?.licences).toEqual({
      twin: "held",
      same_number: "held",
      related: "fail",
      unrelated: "fail",
      uncheckable: "fail",
      implies: "not_eligible",
      path_step: "not_eligible",
      by_when: "not_eligible",
      grouping: "not_eligible",
      same_decision: "not_eligible",
    });
  });

  it("the hero tile's figures come from the held-out split, across the passes", () => {
    expect(exam && acrossPasses(exam, (p) => p.test.perRelation.twin.recall.k)).toEqual([24, 24]);
    expect(exam && acrossPasses(exam, (p) => p.test.wrongMerges)).toEqual([2, 3]);
    expect(exam?.perPass["1"].test.expected).toBe(60);
  });

  it("the page links the record at the commit that merged it, never at a moving branch", () => {
    const source = EVALS_SOURCES.find((x) => x.id === "exam-record");
    expect(source?.href).toMatch(/\/blob\/[0-9a-f]{10,40}\/frontend\/lib\/evals\/data\/twin-exam-2026-11-05\.json$/);
  });

  it("the timeline's run-1 row agrees with the record: replies, cost, model, verdict and day", () => {
    const row = loadRuns().find((r) => r.id === "twin-judge-exam-run-1");
    expect(row?.figures.replies.value).toBe(RAW.received_results);
    expect(row?.cost?.value).toBe(RAW.cost.total_usd);
    expect(row?.model).toBe(RAW.model);
    expect(row?.result).toBe(RAW.result.toLowerCase());
    expect(row?.date).toBe("2026-11-05");
    expect(row?.receipt.href).toBe(RAW.receipt_url);
  });
});

describe("a record that cannot be read leaves both exam sections absent", () => {
  it.each<[string, (b: Raw) => void, RegExp]>([
    ["another schema version", (b) => void ((b as { schema_version: number }).schema_version = 2), /schema_version/],
    ["no receipt", (b) => void (b.receipt_url = ""), /receipt/],
    ["a pass with no verdict", (b) => void ((b.gate_results[0] as { by_pass: Record<string, { result: string }> }).by_pass["3"].result = "MAYBE"), /pass 3/],
    ["an unknown licence", (b) => void ((b.licences as Record<string, string>).twin = "GRANTED?"), /licence for twin/],
    ["more found than exist", (b) => void (b.per_pass["1"].test.per_relation.twin.recall.k = 26), /unreadable counts/],
    ["a missing split", (b) => void delete (b.per_pass["2"] as Partial<Raw["per_pass"]["2"]>).dev, /pass 2, dev/],
    [
      "a gate cell with one malformed named count (refused, never repaired by dropping it)",
      (b) => void ((b.gate_results[0] as unknown as { by_pass: Record<string, Record<string, { k: number }>> }).by_pass["1"].false_twins.k = 36),
      /twin_detection: pass 1 is unreadable/,
    ],
    ["a gate cell whose own count is more than its total", (b) => void ((b.gate_results[1] as { by_pass: Record<string, { k: number }> }).by_pass["2"].k = 13), /pass 2 is unreadable/],
    ["a misspelled scope", (b) => void ((b.gate_results[5] as { scope: string }).scope = "al"), /scope is not test or all/],
    ["a missing scope", (b) => void delete (b.gate_results[0] as { scope?: string }).scope, /scope is not test or all/],
  ])("%s", (_label, breakIt, why) => {
    const broken = clone();
    breakIt(broken);
    expect(examProblem(broken)).toMatch(why);
    expect(loadExam(broken)).toBeNull();
  });
});
