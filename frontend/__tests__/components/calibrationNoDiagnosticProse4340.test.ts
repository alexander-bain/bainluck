// #4340 — notice 34 on /calibration: the charts stop being buried under grey
// method prose.
//
// Alex, Tue 2026-09-08 4:00pm PT, on a 390px shop of a sibling page: *"all the
// grey text is madness, and shouldn't be user-facing at all"*. Coverage counts,
// limitations, method notes and any sentence written to satisfy a reviewer go
// in the PR, the artifact, or a tooltip — never in the page body. A reader sees
// the number, the small source mark, and at most one short caption.
//
// He then inventoried this page himself (#4340, Wed 09:34 PT) and found three
// always-visible instances. Two of them are here because a GUARD wanted them:
// the By Source announcement and the population-arithmetic note were both held
// outside their folds on the stated grounds that `innerText` does not return a
// closed `<details>`, so folding them would blind the browser rail. That is the
// failing-self-audit shape, and notice 34's clause of Wed 4:15am PT settles it:
// the numbers move to data-attributes so probes still read them, and the prose
// stops being a reader's problem.
//
// So this suite grades the trade in both directions. It is not enough that the
// prose is gone — the facts it carried must still be measurable, and the reader
// must still be able to reach the affordances the prose used to announce.
//
// WHY A SOURCE SCAN. `page.tsx` is a ~2,000-line SWR client component and this
// suite runs under `testEnvironment: 'node'` with no jsdom, the same call
// `calibrationAuditHooks.test.tsx` makes and for the same reason ("rendering it
// would prove less and break more"). The lib-level halves below are graded by
// CALLING the real functions on the frozen production payload.

import * as fs from "fs";
import * as path from "path";

import { compareMatchedBuckets, MatchedBucketInput } from "@/lib/calibrationMath";
import { PROD_BUCKETS } from "../lib/calibrationProdFixture";

const PAGE_PATH = path.join(__dirname, "..", "..", "app", "calibration", "page.tsx");
const RAW: string = fs.readFileSync(PAGE_PATH, "utf8");

/**
 * The source with COMMENTS REMOVED.
 *
 * Load-bearing, and the reason is this file: the change that removed the banned
 * clauses quotes several of them verbatim in the comments that explain the
 * removal. A banned-substring scan over the raw source would red on the
 * explanation for the fix — the trap where a source-scan guard flags its own
 * subject's name. Only what a reader can be handed is in scope, so comments go.
 *
 * Line comments are stripped only when they START a line (after whitespace), so
 * a `//` inside a URL or a string literal survives. Getting this wrong in the
 * generous direction is the other classic failure — a stripper that also eats
 * strings would delete the very prose this suite is looking for and pass every
 * assertion. `the stripper does not eat rendered prose` below is the control.
 */
const RENDERED: string = RAW
  .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, " ") // {/* JSX comments */}
  .replace(/\/\*[\s\S]*?\*\//g, " ") // /* block comments */
  .replace(/^[ \t]*\/\/.*$/gm, " "); // // whole-line comments

/**
 * Newlines collapsed to single spaces.
 *
 * Not cosmetic — without it every assertion in this file is VACUOUS. JSX prose
 * is hard-wrapped at ~100 columns, so "because the providers differ by more
 * than 28x in how much of the curve they carry" is four source lines and no
 * banned clause is ever a contiguous substring of the file. A guard that can
 * never match passes forever. `the predicate fires on the prose it bans` below
 * is the control that would have caught it, and did.
 */
const collapse = (s: string): string => s.replace(/\s+/g, " ");

/** The slice of a region that a reader sees without opening anything. */
function unfoldedHead(region: string): string {
  const fold = region.indexOf("<details");
  return fold === -1 ? region : region.slice(0, fold);
}

function regionBetween(start: string, end: string): string {
  const i = RENDERED.indexOf(start);
  expect(i).toBeGreaterThan(-1);
  const j = RENDERED.indexOf(end, i);
  expect(j).toBeGreaterThan(i);
  return RENDERED.slice(i, j);
}

/**
 * The clauses Alex quoted from the render, verbatim, with the JSX entities the
 * page writes them with. Each is a notice-34 category: a method note, a
 * limitation, or a coverage count.
 *
 * Pinned as EXACT strings rather than as a regex over a category, deliberately.
 * Alex's own caution on #4118: a guard that bans a sentence must pin the exact
 * set, because `not.toMatch(/the curve is current/)` red-lit the #4113 FIX —
 * the honest way to withhold a claim in English is to negate it in front of the
 * reader, so the honest replacement contains the banned phrase.
 */
const BANNED_FROM_THE_BODY: ReadonlyArray<readonly [string, string]> = [
  [
    "the 28x justification",
    "because the providers differ by more than 28x in how much of",
  ],
  [
    "the reviewer-answering clause",
    "so you can see exactly how much data stands behind each point rather than having any",
  ],
  ["the hollow-dot key", "are faded hollow dots with wide error"],
  ["the CI key", "Error bars are the 95% CI"],
];

/**
 * The head of By Source EXACTLY as it shipped, from `git show HEAD~:page.tsx`
 * before this change — the bytes behind Alex's 390px shot.
 *
 * A frozen specimen, not a paraphrase. An absence claim is only worth what its
 * positive control is worth, and the control has to run the SAME predicate over
 * text that should fail it (a control that merely proves the function was
 * called proves nothing about the predicate).
 */
const PRE_FIX_HEAD = `
          One panel per data provider &mdash; the same three rows as Source Comparison above &mdash;
          all on the same 0&ndash;100% axis so the curves are directly comparable, and each panel
          states its own sample size, because the providers differ by more than 28x in how much of
          the curve they carry. Error bars are the 95% CI (wider = less certain). Every bucket is
          shown &mdash; well-sampled buckets are solid dots, small-sample ones
          (&lt;{MIN_CHART_BUCKET_N.toLocaleString()} outcomes) are faded hollow dots with wide error
          bars, so you can see exactly how much data stands behind each point rather than having any
          hidden. Click any point for example outcomes, or select a provider tab for the full-width
          view.
`;

describe("the predicate fires on the prose it bans", () => {
  test.each(BANNED_FROM_THE_BODY)(
    "%s is found in the head as it shipped",
    (_label, clause) => {
      // If this goes red, the clause was reworded and the ban below is a
      // no-op — the guard would then be green on a page that reprinted it.
      expect(collapse(PRE_FIX_HEAD)).toContain(clause);
    }
  );

  test("the shipped head really was three paragraphs' worth of them", () => {
    expect(BANNED_FROM_THE_BODY.length).toBe(4);
  });
});

describe("the stripper does not eat rendered prose", () => {
  // The other way this suite could be vacuous: a comment stripper that also
  // swallowed JSX text would make every assertion below trivially true — the
  // page could print all four banned clauses and this would still be green.
  test("a caption the page still shows is present after stripping", () => {
    expect(collapse(RENDERED)).toContain("One panel per data provider, all on the same");
    expect(collapse(RENDERED)).toContain("Tap any point for example");
  });

  test("and a banned clause quoted in a comment does NOT survive it", () => {
    // The raw file contains this clause — inside the comment that explains why
    // it was removed. Without the strip, this suite would red on its own
    // documentation: the source-scan guard that flags its own subject.
    const clause = BANNED_FROM_THE_BODY[1][1];
    expect(collapse(RAW)).toContain(clause);
    expect(collapse(RENDERED)).not.toContain(clause);
  });
});

describe("By Source: one short caption, then the charts", () => {
  // From the section's own hook to the provider tab row — the head, i.e.
  // everything between the heading and the first thing a reader came for.
  const head = () =>
    unfoldedHead(
      regionBetween(
        'data-testid="calibration-by-source-section"',
        'data-testid="calibration-provider-panel"'
      )
    );

  test.each(BANNED_FROM_THE_BODY)(
    "%s is not in the always-visible head",
    (_label, clause) => {
      expect(collapse(head())).not.toContain(clause);
    }
  );

  test("the head renders exactly one paragraph", () => {
    // The count is the assertion. Three paragraphs was the defect Alex
    // photographed (~30 lines at 390px before a single curve); "no banned
    // clause" alone would pass a fourth paragraph of freshly written prose.
    const paragraphs = head().match(/<p[\s>]/g) ?? [];
    expect(paragraphs).toHaveLength(1);
  });

  test("that paragraph is the caption, and it is short", () => {
    const h = head();
    expect(h).toContain('data-testid="calibration-by-source-caption"');
    // The rendered sentence, entities resolved, well inside "short caption".
    const text = h
      .slice(h.indexOf('data-testid="calibration-by-source-caption"'))
      .replace(/<[^>]*>/g, " ")
      .replace(/&[a-z]+;/g, "-")
      .replace(/\s+/g, " ")
      .trim();
    expect(text.length).toBeLessThan(200);
  });

  test("the drawing key and the two derived notes are behind the fold", () => {
    const region = regionBetween(
      'data-testid="calibration-by-source-section"',
      'data-testid="calibration-provider-panel"'
    );
    const key = region.indexOf('data-testid="calibration-panels-key"');
    const keyEnd = region.indexOf("</details>", key);
    expect(key).toBeGreaterThan(-1);
    expect(keyEnd).toBeGreaterThan(key);
    for (const hook of [
      "calibration-panels-key-note",
      "calibration-shape-annex-note",
      "calibration-withheld-sources-note",
    ]) {
      const at = region.indexOf(`data-testid="${hook}"`);
      expect(at).toBeGreaterThan(key);
      expect(at).toBeLessThan(keyEnd);
    }
  });

  test("the facts the head stopped stating travel as data instead", () => {
    // Notice 34's remedy, and the reason folding is not the same as deleting.
    const head5 = RENDERED.slice(
      RENDERED.indexOf('data-testid="calibration-by-source-section"') - 500,
      RENDERED.indexOf('data-testid="calibration-by-source-section"') + 500
    );
    expect(head5).toContain("data-thin-floor=");
    expect(head5).toContain("data-shape-breakdown-providers=");
    expect(head5).toContain("data-withheld-sources=");
  });
});

describe("the population arithmetic is folded, and still measurable", () => {
  test("the partition note is INSIDE the overall-split disclosure", () => {
    // It was outside, on purpose, so `innerText` could reach it. That reason is
    // what notice 34's clause overrides.
    const open = RENDERED.indexOf('data-testid="calibration-overall-split"');
    const note = RENDERED.indexOf('data-testid="calibration-activity-partition"');
    const close = RENDERED.indexOf("</details>", note);
    expect(open).toBeGreaterThan(-1);
    expect(note).toBeGreaterThan(open);
    expect(close).toBeGreaterThan(note);
    // Nothing may close the disclosure between the summary and the note, or the
    // note is back outside it while this test still passes.
    expect(RENDERED.slice(open, note)).not.toContain("</details>");
  });

  test("every term of the sentence is on an element the rail already reads", () => {
    // No attribute was added for this: a second copy of a count is a drift
    // risk, and all five terms already travel. If one of these is ever dropped,
    // folding the sentence WOULD have made the arithmetic unmeasurable.
    for (const attr of [
      "data-moved-n=",
      "data-unchanged-n=",
      "data-not-applicable-n=",
    ]) {
      expect(RENDERED).toContain(attr);
    }
    const pop = RENDERED.indexOf('data-testid="calibration-population-count"');
    expect(pop).toBeGreaterThan(-1);
    const popBlock = RENDERED.slice(pop - 300, pop + 300);
    expect(popBlock).toContain("data-cohort-n=");
    expect(popBlock).toContain("data-full-n=");
  });
});

describe("the matched-bucket sentence states the finding and stops", () => {
  const cmp = compareMatchedBuckets(PROD_BUCKETS as MatchedBucketInput[]);

  test("it still says what it found, on the frozen production payload", () => {
    // Graded by calling the real function, not by scanning for a string: the
    // removal must not have taken the finding with it.
    const s = cmp.sentence as string;
    expect(s).toContain("9 of 10");
    expect(s).toContain("40-50%");
    expect(s).toContain("4.3pp");
    expect(s.trim().endsWith("outcomes.")).toBe(true);
  });

  test("and it no longer defends its own method to the reader", () => {
    const s = cmp.sentence as string;
    expect(s).not.toContain("predicted-probability mix fixed");
    expect(s).not.toContain("the two headline figures above cannot do");
  });

  test("the defence survives where a reviewer looks", () => {
    // Deleting the clause must not delete the ARGUMENT. It is the reason this
    // comparison leads the section at all, and `calibrationMatchedBuckets`
    // grades it on real bytes under the name below.
    const suite = fs.readFileSync(
      path.join(__dirname, "..", "lib", "calibrationMatchedBuckets.test.ts"),
      "utf8"
    );
    expect(suite).toContain(
      "it disagrees with the aggregate reading, which is the reason it exists"
    );
  });
});
