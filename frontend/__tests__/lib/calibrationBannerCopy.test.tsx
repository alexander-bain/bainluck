// CAL-P080 (#2007) — THE STALENESS BANNER MAY DESCRIBE, IT MAY NOT PREDICT.
//
// This suite exists because the same defect shipped twice, in consecutive
// queues, in the same three sentences.
//
//   1. #2007 item 1b replaced "not being refreshed right now" — false, because
//      the curve IS rebuilt hourly and on time; what is dated is the market
//      census under it.
//   2. CAL-P079 rendered the replacement and caught the NEW closing clause
//      being false in the same way one clause later: "It catches up as the
//      backlog re-stages." The banner renders in exactly one state — a bank
//      frozen over drift — and pre-`program/calibration-75` a frozen bank never
//      re-staged, so the promise was false for the entire 24 hours it was on
//      screen. It was captured off the pixels, filed, and fixed here.
//
// Both were forward-looking claims, and that is the pattern this file guards
// rather than the two strings. A prediction in a staleness banner is uniquely
// bad: the reader is being told the thing they are looking at is out of date,
// and the very next clause tells them not to worry about it. If the promise
// does not hold — and this renderer has NO EVIDENCE that it will, because
// "the bank advanced" needs two samples over two beats and this is one render
// of one payload (see `backend/scripts/verify_rolling_restage.py`) — then the
// banner has talked the reader out of the only correct reaction to it.
//
// So: the copy may state what was measured, and what that MEANS. It may not
// say what happens next.
//
// Asserted at the SOURCE level, following the precedent set (and reasoned out)
// in `calibrationAuditHooks.test.tsx`: the page is a large client component
// behind SWR, and rendering it here would prove less and break more.

import * as fs from "fs";
import * as path from "path";

import {
  decideCalibrationStaleness,
  stalenessScheduleClause,
  type CalibrationProducerDisclosure,
} from "@/lib/calibrationStaleness";

const PAGE = path.join(__dirname, "..", "..", "app", "calibration", "page.tsx");
const SOURCE: string = fs.readFileSync(PAGE, "utf8");

/** The banner's JSX, from its test hook to the start of the hero below it. */
function bannerRegion(source: string): string {
  const start = source.indexOf('data-testid="calibration-stale-banner"');
  const end = source.indexOf("{/* Hero */}", start);
  if (start < 0 || end < 0) {
    throw new Error(
      "could not locate the staleness banner region — if the hook or the hero " +
        "marker was renamed, re-anchor this test rather than deleting it",
    );
  }
  return source.slice(start, end);
}

/**
 * Strip `{/* ... *\/}` JSX comments.
 *
 * Load-bearing, not hygiene: the comment above the frozen-inputs branch QUOTES
 * both retired sentences verbatim, so that a future reader learns why they went
 * instead of reinventing them. Scanning the raw region would therefore fail on
 * the very documentation that prevents the regression, and the cheapest way to
 * make this suite green would be to delete that explanation. Comments are
 * prose about the copy; only the copy is the copy.
 */
function withoutComments(region: string): string {
  return region.replace(/\{\/\*[\s\S]*?\*\/\}/g, " ");
}

/**
 * Forward-looking constructions, each with the reason it is banned HERE.
 *
 * Deliberately narrow. This is not a general future-tense linter — "The curve
 * rebuilds hourly" is present tense about a SCHEDULE that is externally true
 * (the beat fires at :15 every hour) and is a fact the reader can check, not a
 * promise about the payload in front of them. What is banned is a claim about
 * what will happen to THIS staleness.
 */
const BANNED: Array<{ pattern: RegExp; why: string }> = [
  {
    pattern: /catches up/i,
    why: "CAL-P079's filed defect verbatim — the frozen bank does not catch up",
  },
  {
    pattern: /\bwill\b/i,
    why: "a promise about this payload's future, which one render cannot support",
  },
  {
    pattern: /\bsoon\b|\bshortly\b|\bany (?:minute|moment)\b/i,
    why: "an unbounded timing claim; the banner has no deadline to offer",
  },
  {
    pattern: /\bautomatically\b/i,
    why: "tells the reader to disregard the staleness they were just shown",
  },
  {
    pattern: /next (?:beat|run|rebuild|cycle)/i,
    why: "#2007's original shape — 'it resolves itself on the next beat', which it did not",
  },
  {
    pattern: /resolves? itself|sorts? itself|fixes? itself/i,
    why: "the same claim in the active voice",
  },
  {
    pattern: /as the backlog|once the backlog|when the backlog/i,
    why: "conditions the reader's trust on a drain this render cannot observe",
  },
];

describe("the calibration staleness banner", () => {
  const copy = withoutComments(bannerRegion(SOURCE));

  it("still renders prose for all three staleness kinds", () => {
    // Non-vacuity. Every assertion below is satisfied by an empty banner, and
    // deleting the copy is not a fix for the copy being wrong.
    for (const kind of ["last-good", "frozen-inputs", "undisclosed"]) {
      expect(copy).toContain(`staleness.kind === "${kind}"`);
    }
    expect(copy.length).toBeGreaterThan(800);
  });

  it.each(BANNED.map((b) => [b.pattern.source, b] as const))(
    "makes no forward-looking promise: /%s/",
    (_src, banned) => {
      const hit = copy.match(banned.pattern);
      expect(
        hit
          ? `banner copy contains ${JSON.stringify(hit[0])} — ${banned.why}`
          : null,
      ).toBeNull();
    },
  );

  it("keeps saying WHEN the census was staged, which is the measured half", () => {
    // The ban above removes a claim; it must not be satisfiable by removing the
    // disclosure too. The frozen-inputs branch's whole job is to date the
    // inputs, so the date and the drift both have to survive it.
    expect(copy).toContain("staleness.stagedAt");
    expect(copy).toContain("staleness.stagedAgeS");
    expect(copy).toContain("driftClause");
  });

  // #2649: the schedule sentence MOVED OUT of this region.
  //
  // It used to be a string literal in the JSX, so scanning `copy` covered it.
  // It now comes from `stalenessScheduleClause`, because the sentence had to
  // become conditional on `producer.stalled` — the page was promising "The
  // curve rebuilds hourly" over a payload reporting 51 missed beats. That fix
  // is right, and it silently took the clause out of this suite's reach: a
  // future "we'll be back shortly" added to that function would sail past every
  // assertion above.
  //
  // So the ban follows the copy. And it follows it as OUTPUT rather than as
  // source text, which is strictly stronger: source-scanning a function whose
  // whole job is to return different strings in different states can only see
  // the literals, never which one actually renders.
  describe("the schedule clause is held to the same ban", () => {
    /** Every state the clause can render in, so no branch escapes the scan. */
    const STATES: Array<[string, CalibrationProducerDisclosure | null]> = [
      ["stalled with a count", { stalled: true, beats_missed: 51 }],
      ["stalled, one beat", { stalled: true, beats_missed: 1 }],
      ["stalled, count unreadable", { stalled: true, beats_missed: null }],
      ["stalled, zero beats", { stalled: true, beats_missed: 0 }],
      ["beat is landing", { stalled: false, beats_missed: 0 }],
      ["producer block absent", null],
    ];

    function clauseIn(producer: CalibrationProducerDisclosure | null): string {
      const notice = decideCalibrationStaleness({
        availability: "stale",
        cache: { status: "stale", generated_at: "2026-08-31T04:37:36Z", age_s: 184401 },
        ...(producer === null ? {} : { producer }),
      });
      if (notice === null) throw new Error("fixture produced no notice");
      return stalenessScheduleClause(notice) ?? "";
    }

    it("renders a real sentence in the states that have one", () => {
      // Non-vacuity, same reason as above: an always-empty clause would satisfy
      // every ban below, and emptying it is not a fix.
      expect(clauseIn({ stalled: true, beats_missed: 51 }).length).toBeGreaterThan(20);
      expect(clauseIn({ stalled: false, beats_missed: 0 }).length).toBeGreaterThan(10);
    });

    it.each(STATES)("makes no forward-looking promise when %s", (_label, producer) => {
      const clause = clauseIn(producer);
      for (const banned of BANNED) {
        const hit = clause.match(banned.pattern);
        expect(
          hit ? `schedule clause contains ${JSON.stringify(hit[0])} — ${banned.why}` : null,
        ).toBeNull();
      }
    });
  });

  it("documents the retired sentences instead of quietly dropping them", () => {
    // The comment block is the reason this defect did not ship a third time.
    // It lives OUTSIDE `copy` by construction (see `withoutComments`), so it is
    // asserted against the raw region.
    const raw = bannerRegion(SOURCE);
    expect(raw).toContain("catches up as the backlog");
    expect(raw).toContain("not being refreshed right now");
  });
});
