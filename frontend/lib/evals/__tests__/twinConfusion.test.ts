/**
 * #12102 S7 — what the judge answered, kind by kind, from Builder B's S0b
 * counts (#12121), held to the S0a record the report card draws.
 *
 * Each row sums to its kind's count; the right answer's count is that kind's
 * "found"; each answer's column adds up to "said so"; and the all-pairs view,
 * the two splits added together, agrees with the record's all-120 numbers.
 */

import EXAM from "@/lib/evals/data/twin-exam-2026-11-05.json";
import RAW from "@/lib/evals/data/twin-confusion-2026-11-05.json";
import { ANSWERS, answersFor, confusionProblem, loadConfusion } from "@/lib/evals/twinConfusion";
import { PASSES, RELATIONS } from "@/lib/evals/twinExam";

type Raw = typeof RAW;
const clone = (): Raw => JSON.parse(JSON.stringify(RAW));
const confusion = loadConfusion();

describe("the confusion counts", () => {
  it("read, for the same run, time and receipt as the exam record", () => {
    expect(confusionProblem(RAW)).toBeNull();
    expect(confusion?.runId).toBe(EXAM.run_id);
    expect(confusion?.recordedAt).toBe(EXAM.recorded_at_pt);
    expect(confusion?.receipt).toBe(EXAM.receipt_url);
  });

  it.each(PASSES)("pass %s: every row is its kind's count; the right answer is 'found'; each column is 'said so'", (p) => {
    for (const s of ["test", "dev"] as const) {
      for (const r of RELATIONS) {
        const row = answersFor(confusion!, p, s, r);
        const metrics = (EXAM.per_pass[p][s].per_relation as Record<string, { recall: { k: number; n: number }; precision: { n: number } }>)[r];
        expect(ANSWERS.reduce((sum, a) => sum + row.counts[a], 0)).toBe(row.n);
        expect([row.n, row.counts[r]]).toEqual([metrics.recall.n, metrics.recall.k]);
        const saidSo = RELATIONS.reduce((sum, truth) => sum + answersFor(confusion!, p, s, truth).counts[r], 0);
        expect({ p, s, r, saidSo }).toEqual({ p, s, r, saidSo: metrics.precision.n });
      }
    }
  });

  it("the all-pairs view is the two halves added, and agrees with the record's all-120 numbers", () => {
    for (const p of PASSES) {
      for (const r of RELATIONS) {
        const all = answersFor(confusion!, p, "all", r);
        const metrics = (EXAM.per_pass[p].all.per_relation as Record<string, { recall: { k: number; n: number } }>)[r];
        expect([all.n, all.counts[r]]).toEqual([metrics.recall.n, metrics.recall.k]);
      }
    }
  });
});

describe("counts that do not add up leave the answers out, never half-shown", () => {
  it.each<[string, (b: Raw) => void, RegExp]>([
    ["a row whose answers miss a pair", (b) => void (b.per_pass["1"].test.rows.twin.counts.twin = 23), /sum to/],
    ["a split whose rows miss a pair", (b) => void (b.per_pass["2"].dev.n = 59), /rows sum to/],
    ["a missing split", (b) => void delete (b.per_pass["3"] as Partial<Raw["per_pass"]["3"]>).test, /pass 3, test/],
    ["another schema version", (b) => void ((b as { schema_version: number }).schema_version = 2), /schema_version/],
  ])("%s", (_label, breakIt, why) => {
    const broken = clone();
    breakIt(broken);
    expect(confusionProblem(broken)).toMatch(why);
    expect(loadConfusion(broken)).toBeNull();
  });
});
