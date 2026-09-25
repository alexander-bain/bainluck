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
  stalenessInputSentence,
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
 *
 * #7696: it strips BARE `/* ... *\/` blocks too, not only brace-wrapped ones.
 * Inside a JSX opening tag an attribute-position comment needs no braces, and
 * the comment explaining a retired attribute reading necessarily QUOTES it —
 * so a scan that skipped those would read the documentation of a fix as the
 * defect itself, and the cheapest green would again be deleting the
 * explanation. Same rule, one more syntax: comments are prose about the copy.
 */
function withoutComments(region: string): string {
  return region.replace(/\{\/\*[\s\S]*?\*\/\}/g, " ").replace(/\/\*[\s\S]*?\*\//g, " ");
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
    // inputs, so the date has to survive it.
    expect(copy).toContain("staleness.stagedAt");
    expect(copy).toContain("staleness.stagedAgeS");
  });

  // #4118 / STANDING NOTICE 34 — this assertion used to also require
  // `driftClause`, on the reasoning above: the date and the drift both had to
  // survive the ban. The drift no longer survives it AS A SENTENCE, and the
  // reasoning is not being abandoned so much as re-satisfied one layer down.
  //
  // Alex, 2026-09-08: coverage counts do not go in the page body; they go in
  // "the PR, the artifact, or a tooltip". ", and 128 of 128 units have drifted
  // since" is a coverage count, and "units" is a word for a staged census
  // partition that no reader can define (notice 19). It was also the only
  // clause of that banner in the banned shape — the age, the staged date and
  // the consequence are all warnings, and all three are untouched.
  //
  // What made this safe rather than a quiet loss: the drift was ALREADY
  // published on the same element as `data-units-drifted` / `data-units-banked`
  // (#2007 item 1b put it there so a rail would not have to parse the
  // sentence). So the count moved from the prose to the data, which is where
  // the notice sends it, and every rail that read it still reads it. Pinned
  // here so the pairing is asserted in the same suite that used to demand the
  // sentence, and again in `calibrationNotice34.test.ts`.
  it("publishes the drift as DATA now that the sentence does not carry it", () => {
    expect(copy).not.toContain("driftClause");
    expect(copy).toContain("data-units-drifted");
    expect(copy).toContain("data-units-banked");
  });

  // #4113: the frozen-inputs body repeats the headline's currency claim one
  // line down — "The curve was rebuilt on schedule, but …" — and unlike the
  // schedule clause it is a string literal in this region, so the ban is a
  // source assertion here rather than an output one. Both halves are pinned:
  // the sentence still exists (it is true and worth saying when the beat is
  // landing), and it cannot be reached without the producer's proof.
  it("does not claim the curve was rebuilt on schedule without the proof", () => {
    expect(copy).toContain("rebuilt on schedule");
    expect(copy).toMatch(/producerProvenCurrent[\s\S]{0,120}?rebuilt on schedule/);
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

  // #5185: the undisclosed banner's input sentence moved out of this region
  // into `stalenessInputSentence`, so — exactly like the schedule clause — the
  // region scan above can no longer see it. Scanned as OUTPUT, every branch.
  describe("the input sentence is held to the same ban", () => {
    const REASONS: Array<string | null> = ["served_bank_empty", "served_at_absent", "phase_ledger_unreadable", null];

    function sentenceFor(reason: string | null): string {
      const notice = decideCalibrationStaleness({
        availability: "stale",
        staged: reason === null ? null : { measured: false, reason },
        producer: { stalled: true, beats_missed: 138 },
      });
      if (notice === null || notice.kind !== "undisclosed") throw new Error("fixture missed `undisclosed`");
      return stalenessInputSentence(notice);
    }

    it("renders two different sentences across the reasons", () => {
      // Non-vacuity: a scan over one repeated string would prove nothing about
      // the branch #5185 added.
      expect(new Set(REASONS.map(sentenceFor)).size).toBe(2);
    });

    it.each(REASONS)("makes no forward-looking promise when staged.reason is %s", reason => {
      const line = sentenceFor(reason);
      for (const banned of BANNED) {
        const hit = line.match(banned.pattern);
        expect(hit ? `input sentence contains ${JSON.stringify(hit[0])} — ${banned.why}` : null).toBeNull();
      }
      // And the #5185-specific one: under a stalled producer, "a rebuild is
      // underway" is a progress claim this render cannot support.
      expect(line).not.toMatch(/underway|in progress|\byet\b/i);
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

/**
 * #7696 — the banner's temporal facts must not be read off `cache`.
 *
 * `cache` is attached by `_dated()` alone, so reading the artifact's date or age
 * from it makes both invisible on the main tier — which still banners, because
 * `_serve` clamps `availability` down for an unreadable staged bank without
 * attaching one. `decideCalibrationStaleness` resolves the tier-independent
 * fallback (`generated_at`, `producer.age_s`); the page's job is to use it.
 *
 * Source assertions, like the rest of this file, and for the same reason: the
 * page is a `"use client"` SWR component and mounting it proves less.
 */
describe("#7696 the banner dates the artifact on every tier", () => {
  const copy = withoutComments(bannerRegion(SOURCE));

  it("reads no temporal fact off `cache` — the fallback-tier-only block", () => {
    // The literal defect: `data-generated-at={data.cache?.generated_at ?? ""}`
    // published an empty attribute on exactly the tier the sentence went blind
    // on, so the rail could not catch it either.
    expect(copy).not.toMatch(/data\.cache\?\.(generated_at|age_s)/);
    expect(copy).toContain("data-generated-at={staleness.generatedAt");
  });

  it("the undisclosed branch renders the date it now has", () => {
    // Non-vacuity: this string is absent from the pre-fix page, and the two
    // assertions above are all satisfiable while the branch stays wordless.
    const undisclosed = copy.slice(copy.indexOf('staleness.kind === "undisclosed"'));
    expect(undisclosed).toContain("staleness.generatedAt &&");
    expect(undisclosed).toContain("These numbers were built");
    expect(undisclosed).toContain("stalenessAgeLabel(staleness.ageS)");
  });

  it("and only when it has one — no `earlier` furniture in this branch", () => {
    // The `last-good` branch prints the literal "earlier" for an undated
    // artifact. Copying that here would put a word where a fact belongs in the
    // one state whose subject is that we could not read the inputs.
    const undisclosed = copy.slice(copy.indexOf('staleness.kind === "undisclosed"'));
    expect(undisclosed).not.toContain('"earlier"');
  });
});
