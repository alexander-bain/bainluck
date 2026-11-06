/**
 * #12102 S4 — the AI code reviewer's study says what its receipts say.
 *
 * `data/reviewer-study-2026-11-05.json` describes each planted bug and healthy
 * change in our own words. `data/reviewer-study-2026-11-05.receipts.json`
 * keeps the receipts' words beside each row; only this suite reads it. Every
 * row is held to its quote: our tests caught each bug, passed each healthy
 * change, and at the receipt's time (4:36 PM PT Nov 5) the reviewer had
 * reviewed none of them, so every square reads NOT RUN as of that time. The
 * reviews started that night, and the page points at the full study's first
 * result rather than implying the squares are newer than their receipt.
 */

import RAW from "@/lib/evals/data/reviewer-study-2026-11-05.json";
import RECEIPTS from "@/lib/evals/data/reviewer-study-2026-11-05.receipts.json";
import { caseProblem, loadReviewerStudy } from "@/lib/evals/reviewerStudy";
import { EVALS_SOURCES } from "@/lib/evals/sources";
import { pacificClockLabel, pacificDayLabel } from "@/lib/evals/truth";

type Quote = { quote: string; from: string };
const CASE_QUOTES = RECEIPTS.cases as Record<string, Quote>;
const STUDY_QUOTES = RECEIPTS.study as Record<string, Quote>;

describe("the study record", () => {
  const study = loadReviewerStudy();

  it("loads every row", () => {
    expect(study).not.toBeNull();
    expect(study?.cases).toHaveLength(RAW.cases.length);
    expect(RAW.cases.map(caseProblem)).toEqual(RAW.cases.map(() => null));
  });

  it("has as many bugs and healthy changes as the ruling that set the study says", () => {
    const m = /(\d+) defects \+ (\d+) controls/.exec(STUDY_QUOTES.dropped.quote);
    expect(m).not.toBeNull();
    expect(study?.cases.filter((c) => c.kind === "defect")).toHaveLength(Number(m?.[1]));
    expect(study?.cases.filter((c) => c.kind === "control")).toHaveLength(Number(m?.[2]));
  });

  it("every planted bug is its receipt's row: our tests caught it, the reviewer has not run", () => {
    for (const c of study?.cases.filter((x) => x.kind === "defect") ?? []) {
      const q = CASE_QUOTES[c.id];
      expect({ id: c.id, quoted: !!q }).toEqual({ id: c.id, quoted: true });
      expect(q.quote.startsWith(`| ${c.id} |`)).toBe(true);
      expect(q.quote).toMatch(/\| yes \(\d+ failing case\(s\)\) \|/);
      expect(q.quote.endsWith("| NOT RUN |")).toBe(true);
      expect(c.ourTests).toBe("caught");
      expect(c.reviewer).toBe("not_run");
    }
  });

  it("every healthy change is named in the receipt, passed our tests, and has not been reviewed", () => {
    expect(STUDY_QUOTES.controls_pass.quote).toMatch(/control gates pass/);
    expect(STUDY_QUOTES.controls_behavior.quote).toMatch(/behavior-preserving/);
    for (const c of study?.cases.filter((x) => x.kind === "control") ?? []) {
      expect({ id: c.id, quoted: !!CASE_QUOTES[c.id] }).toEqual({ id: c.id, quoted: true });
      expect(c.ourTests).toBe("pass");
      expect(c.reviewer).toBe("not_run");
    }
  });

  it("NOT RUN is the record's word at the squares' time: no paid review at the study's receipt, nor yet at the pilot's", () => {
    expect(STUDY_QUOTES.no_reviews.quote).toMatch(/paid reviews 0/);
    expect(STUDY_QUOTES.pilot_no_reviews.quote).toMatch(/0\/3 real reviews/);
    expect(study?.cases.every((c) => c.reviewer === "not_run")).toBe(true);
  });

  it("the squares are as of their receipt's own time, to the minute", () => {
    const q = STUDY_QUOTES.snapshot_time;
    expect(q.from).toBe(study?.receipt.href);
    const clock = (pacificClockLabel(study!.asOf) as string).replace(/ PT$/, "");
    expect(q.quote).toContain(`${pacificDayLabel(study!.asOf)}, ${clock} PST`);
    expect(q.quote).toMatch(/paid reviews 0/);
  });

  it("the full study's first result came after the squares, and the page links its receipt", () => {
    const q = STUDY_QUOTES.full_study_first;
    const full = study?.fullStudy;
    expect(full).not.toBeNull();
    expect(full?.receipt.href).toBe(q.from);
    const clock = (pacificClockLabel(full!.firstResultAt) as string).replace(/ PT$/, "");
    expect(q.quote).toContain(`${pacificDayLabel(full!.firstResultAt)} ${clock} PST`);
    expect(q.quote).toMatch(/Full-set/);
    expect(Date.parse(full!.firstResultAt)).toBeGreaterThan(Date.parse(study!.asOf));
  });

  it("the dropped bug is the issue Fable filed, on the bug that was never fixed", () => {
    expect(STUDY_QUOTES.dropped_issue.quote).toContain(`#${study?.dropped?.issue}`);
    expect(STUDY_QUOTES.dropped_live.quote).toMatch(/already-present escape on master/);
    expect(study?.dropped?.decided).toBe(STUDY_QUOTES.dropped.from);
  });

  it("every quote comes from a post the page lists as a source", () => {
    const listed = EVALS_SOURCES.map((s) => s.href);
    for (const q of [...Object.values(CASE_QUOTES), ...Object.values(STUDY_QUOTES)]) {
      expect(listed).toContain(q.from);
    }
    expect(listed).toContain(study?.receipt.href);
  });
});

describe("a malformed row drops the grid, never one square", () => {
  const good = RAW.cases[0] as Record<string, unknown>;

  it.each([
    ["an unknown kind", { ...good, kind: "maybe" }, /kind/],
    ["no label", { ...good, label: " " }, /label/],
    ["a planted bug our tests merely passed", { ...good, our_tests: "pass" }, /our_tests/],
    ["a healthy change our tests caught", { ...good, kind: "control", our_tests: "caught" }, /our_tests/],
    ["an unknown reviewer result", { ...good, reviewer: "zero" }, /reviewer/],
  ])("%s", (_label, row, why) => {
    expect(caseProblem(row)).toMatch(why);
    expect(loadReviewerStudy({ ...RAW, cases: [...RAW.cases, row] })).toBeNull();
  });

  it("a study without a receipt link is not shown", () => {
    expect(loadReviewerStudy({ ...RAW, receipt: { label: "x", href: "" } })).toBeNull();
  });

  it("a study dated by day alone is not shown: the squares need their receipt's time", () => {
    expect(loadReviewerStudy({ ...RAW, as_of: "2026-11-05" })).toBeNull();
  });

  it("a full-study result dated before the squares is not shown", () => {
    const full = { ...RAW.full_study, first_result_at: "2026-11-05T20:00:00Z" };
    expect(loadReviewerStudy({ ...RAW, full_study: full })).toBeNull();
  });
});
