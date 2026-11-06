/**
 * #12102 top screen — the AI reviewer's planted-mistake study, as far as it has got.
 *
 * `reviewer-results-2026-11-06.json` is kept by hand, so every number in it is
 * held to Builder B's own posts, quoted word for word in the test-only receipts
 * file: the plan's size, the latest count and its tallies, and each result's
 * case, try and verdict. Builder B numbers the harmless changes differently
 * from the study record; each such result names Builder B's id, and the
 * mapping to ours is held to the study record's own receipt for that case. The
 * loader's refusals each have a case here, and the tally is checked against
 * the study record's own count of planted mistakes and harmless changes.
 */

import RESULTS from "@/lib/evals/data/reviewer-results-2026-11-06.json";
import RECEIPTS from "@/lib/evals/data/reviewer-results-2026-11-06.receipts.json";
import STUDY_RECEIPTS from "@/lib/evals/data/reviewer-study-2026-11-05.receipts.json";
import { loadReviewerResults, resultsProblem, reviewerTally } from "@/lib/evals/reviewerResults";
import { loadReviewerStudy } from "@/lib/evals/reviewerStudy";
import { caseMarks } from "@/lib/evals/topScreen";

const STUDY = loadReviewerStudy();

const clone = () => JSON.parse(JSON.stringify(RESULTS)) as Record<string, unknown> & { results: Record<string, unknown>[] };

describe("the committed results", () => {
  it("load against the study record", () => {
    expect(STUDY).not.toBeNull();
    expect(loadReviewerResults(STUDY)).not.toBeNull();
  });

  it("the plan's size is the one Builder B's plan post names, and every case gets the same tries", () => {
    const planned = Number(/all(\d+) planned evaluations/.exec(RECEIPTS.plan.quote)?.[1]);
    expect(RESULTS.planned).toBe(planned);
    expect(RESULTS.plan_receipt.href).toBe(RECEIPTS.plan.href);
    expect(RESULTS.planned % (STUDY?.cases.length ?? 0)).toBe(0);
  });

  it("the count is the latest post's: as many results as it says are recorded, out of the same plan", () => {
    const m = /(\d+)\/(\d+) (?:real reviews )?recorded/.exec(RECEIPTS.count.quote);
    expect(m).not.toBeNull();
    expect(RESULTS.results.length).toBe(Number(m?.[1]));
    expect(RESULTS.planned).toBe(Number(m?.[2]));
    expect(RESULTS.receipt.href).toBe(RECEIPTS.count.href);
    expect(RESULTS.as_of).toBe(RECEIPTS.count.posted_at);
  });

  it("each result is the one its post names: case, try and verdict, at the post's time", () => {
    // The review's own verdict, by what was planted: a planted mistake is caught
    // when changes are requested and missed when approved; a harmless change is
    // let through when approved and a false alarm when changes are requested. A
    // new kind of outcome needs its words added here, on purpose.
    const VERDICT: Record<string, string> = {
      caught: "CHANGES_REQUESTED",
      missed: "APPROVED",
      passed: "APPROVED",
      flagged: "CHANGES_REQUESTED",
    };
    const WORD: Record<string, string> = { caught: "CAUGHT", missed: "MISSED" };
    expect(RESULTS.results.length).toBe(RECEIPTS.results.length);
    RESULTS.results.forEach((r, i) => {
      const receipt = RECEIPTS.results[i] as { href: string; posted_at: string; quote: string; builder_case?: string };
      expect(r.receipt.href).toBe(receipt.href);
      expect(r.at).toBe(receipt.posted_at);
      expect(VERDICT[r.outcome]).toBeDefined();
      const id = receipt.builder_case ?? r.case;
      const named = [`${id}/pass${r.pass}: ${WORD[r.outcome]}`, `${id}/P${r.pass} | ${VERDICT[r.outcome]}`];
      expect(named.some((n) => receipt.quote.includes(n))).toBe(true);
      expect(receipt.quote).toContain(VERDICT[r.outcome]);
    });
  });

  it("a result posted under another id maps to our case through the study record's own words for it", () => {
    const ids = RECEIPTS.study_ids as unknown as Record<string, { maps_to: string; study_quote: string }>;
    const cases = STUDY_RECEIPTS.cases as Record<string, { quote: string }>;
    const remapped = RESULTS.results.filter((_, i) => (RECEIPTS.results[i] as { builder_case?: string }).builder_case);
    expect(remapped.length).toBeGreaterThan(0);
    RESULTS.results.forEach((r, i) => {
      const builderCase = (RECEIPTS.results[i] as { builder_case?: string }).builder_case;
      if (!builderCase) return;
      expect(ids[builderCase].maps_to).toBe(r.case);
      expect(cases[r.case].quote).toBe(ids[builderCase].study_quote);
    });
    // Two of Builder B's ids never map to one case.
    const targets = Object.entries(ids).filter(([k]) => !k.startsWith("_")).map(([, v]) => v.maps_to);
    expect(new Set(targets).size).toBe(targets.length);
  });

  it("the tally is the latest post's own: mistakes caught of those reviewed, and false alarms among the harmless changes", () => {
    const defects = /Observed defects: \*\*(\d+)\/(\d+) caught\*\*/.exec(RECEIPTS.count.defects_quote);
    const controls = /Observed controls: \*\*(\d+)\/(\d+) false alarms\*\*/.exec(RECEIPTS.count.controls_quote);
    expect(defects && controls).toBeTruthy();
    const tally = reviewerTally(loadReviewerResults(STUDY)!, STUDY!);
    expect([tally.mistakes.right, tally.mistakes.reviewed]).toEqual([Number(defects?.[1]), Number(defects?.[2])]);
    expect([tally.harmless.wrong, tally.harmless.reviewed]).toEqual([Number(controls?.[1]), Number(controls?.[2])]);
  });
});

describe("the tally and the blocks", () => {
  it("plans every planted mistake and every harmless change for each try, and counts the results", () => {
    const results = loadReviewerResults(STUDY)!;
    const tally = reviewerTally(results, STUDY!);
    const passes = results.planned / STUDY!.cases.length;
    const defects = STUDY!.cases.filter((c) => c.kind === "defect").length;
    const controls = STUDY!.cases.filter((c) => c.kind === "control").length;
    expect(tally.mistakes.planned).toBe(defects * passes);
    expect(tally.harmless.planned).toBe(controls * passes);
    expect(tally.mistakes.planned + tally.harmless.planned).toBe(results.planned);
    expect(tally.mistakes.reviewed + tally.harmless.reviewed).toBe(results.results.length);
    expect(tally.mistakes.right + tally.mistakes.wrong).toBe(tally.mistakes.reviewed);
  });

  it("marks one bug per planted mistake and one decoy per harmless change, by the tries recorded so far", () => {
    const results = loadReviewerResults(STUDY)!;
    const bugs = caseMarks(results, STUDY!, "defect");
    const decoys = caseMarks(results, STUDY!, "control");
    expect(bugs.length).toBe(STUDY!.cases.filter((c) => c.kind === "defect").length);
    expect(decoys.length).toBe(STUDY!.cases.filter((c) => c.kind === "control").length);
    const tried = new Set(results.results.map((r) => r.case));
    STUDY!.cases
      .filter((c) => c.kind === "defect")
      .forEach((c, i) => expect(bugs[i] === "not_yet").toBe(!tried.has(c.id)));
    STUDY!.cases
      .filter((c) => c.kind === "control")
      .forEach((c, i) => expect(decoys[i] === "not_yet").toBe(!tried.has(c.id)));
  });

  it("a mistake caught on one try and missed on another is marked wrong, never right", () => {
    const raw = clone();
    raw.results = [
      { case: "r01", pass: 1, outcome: "caught", at: "2026-11-06T08:00:00Z", receipt: { label: "x", href: "https://example.test/a" } },
      { case: "r01", pass: 2, outcome: "missed", at: "2026-11-06T09:00:00Z", receipt: { label: "y", href: "https://example.test/b" } },
    ];
    const marks = caseMarks(loadReviewerResults(STUDY, raw)!, STUDY!, "defect");
    expect(marks[STUDY!.cases.findIndex((c) => c.id === "r01")]).toBe("wrong");
  });

  it("a missed mistake and a false alarm count as wrong calls", () => {
    const raw = clone();
    raw.results = [
      { case: "r01", pass: 1, outcome: "missed", at: "2026-11-06T08:00:00Z", receipt: { label: "x", href: "https://example.test/a" } },
      { case: "c01", pass: 1, outcome: "flagged", at: "2026-11-06T09:00:00Z", receipt: { label: "y", href: "https://example.test/b" } },
    ];
    const tally = reviewerTally(loadReviewerResults(STUDY, raw)!, STUDY!);
    expect(tally.mistakes).toMatchObject({ reviewed: 1, right: 0, wrong: 1 });
    expect(tally.harmless).toMatchObject({ reviewed: 1, right: 0, wrong: 1 });
  });
});

describe("an unreadable list is refused, never repaired", () => {
  const refuse = (mutate: (raw: ReturnType<typeof clone>) => void) => {
    const raw = clone();
    mutate(raw);
    expect(resultsProblem(raw, STUDY!)).not.toBeNull();
    expect(loadReviewerResults(STUDY, raw)).toBeNull();
  };

  it("a harmless change cannot be caught, and a planted mistake cannot be passed", () => {
    refuse((raw) => (raw.results[0].case = "c01"));
    refuse((raw) => (raw.results[0].outcome = "passed"));
  });

  it("a case the study does not have, a try the plan does not have, or the same try twice", () => {
    refuse((raw) => (raw.results[0].case = "r99"));
    refuse((raw) => (raw.results[0].pass = 4));
    refuse((raw) => raw.results.push({ ...raw.results[raw.results.length - 1] }));
  });

  it("a plan that does not split evenly across the cases, or no plan", () => {
    refuse((raw) => (raw.planned = 44));
    refuse((raw) => delete raw.planned);
  });

  it("a result recorded after the count it belongs to, or out of time order", () => {
    refuse((raw) => (raw.results[raw.results.length - 1].at = "2026-11-07T00:00:00Z"));
    refuse((raw) =>
      raw.results.unshift({ ...raw.results[0], case: "r05", at: "2026-11-06T08:00:00Z" })
    );
  });

  it("a missing receipt or a date with no time", () => {
    refuse((raw) => delete raw.results[0].receipt);
    refuse((raw) => (raw.as_of = "2026-11-06"));
  });

  it("no study record, no picture", () => {
    expect(loadReviewerResults(null)).toBeNull();
  });
});
