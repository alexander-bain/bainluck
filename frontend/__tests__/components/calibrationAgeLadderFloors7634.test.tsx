/**
 * #7634 — the accuracy page's staleness banner stops printing an age that
 * disagrees with the date beside it.
 *
 * Shopped on production, 1280px, default view, 2026-09-20 23:40Z:
 *
 *     Showing the last complete snapshot. These numbers were built Sep 15,
 *     4:16 AM (6 days ago) and are not being refreshed right now. 132 hourly
 *     rebuilds have come and gone without a new snapshot.
 *
 * Today was Sep 20. A reader who counts from the date the same sentence prints
 * gets 5. The artifact is 479,048 s = 5.54 d and `Math.round(5.54)` is 6.
 *
 * #7612's header, taken 1h55m earlier at `age_s: 469_772`, recorded the same
 * banner reading "(5 days ago)". Nothing republished in between — the page
 * flipped to "6 days" as the artifact crossed 5½ days old, while the date it
 * annotates stayed Sep 15. That is the tell: the parenthetical and the
 * timestamp were derived from the same instant and disagreed anyway.
 *
 * ═══ WHY NO EXISTING GUARD COULD SEE IT ═══
 *
 * `formatAge` was module-private inside `app/calibration/page.tsx`, a
 * `"use client"` component, so nothing could import it — the identical hole
 * CAL-P1024 (#1865) closed in the same file after `datagolf` spent weeks
 * rendering its raw payload key. `calibrationStaleness.test.ts` covers the
 * functions that build the banner's SENTENCES; the number inside the
 * parentheses was not one of them.
 *
 * ═══ THE TWO MISTAKES, BECAUSE ONE FIX DOES NOT COVER BOTH ═══
 *
 *   1. It ROUNDED. Five sibling modules floor and four carry the comment
 *      verbatim — "Human age, rounded DOWN — '8 days ago' must never flatter
 *      to '7'."
 *   2. Each rung's threshold was tested against the ROUNDED value
 *      (`const hours = Math.round(s / 3600); if (hours < 48)`), so the days
 *      rung opened at 47.5 h and a 47 h 59 m artifact read "2 days".
 *
 * Fixing (1) alone leaves every boundary half a rung early, which is why the
 * boundary table below is asserted separately from the floor property.
 *
 * ═══ WHAT THIS FILE ASSERTS, AND WHY THAT SHAPE ═══
 *
 * The floor property is written as "parse the label back and check it against
 * the input", NOT as "compare to a second copy of the ladder". A reference
 * implementation would pass by construction and keep passing if both copies
 * drifted together; parsing states the reader's own check — does the count I
 * am shown match the whole units that have actually elapsed.
 *
 * A property that scans nothing reads clean, so the sweep is proved to bite
 * before it is trusted: the same property is re-run over the ladder as it
 * shipped and MUST report violations, and the label parser is checked against
 * a specimen it should reject.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";
import { stalenessAgeLabel } from "@/lib/calibrationStaleness";

// Mock the hook, not the fetcher: `renderToStaticMarkup` runs no effect, so a
// real SWR hands the page `undefined` and the suite photographs the loading
// state instead (#6265).
jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: (global as unknown as { __calPayload: CalibrationData }).__calPayload,
  }),
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

jest.mock("@/components/CalibrationChart", () => ({ __esModule: true, default: () => null }));

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

import CalibrationPage from "@/app/calibration/page";

/* ═════════════════════ the ladder as it shipped ═════════════════════ */

/**
 * `page.tsx`'s `formatAge`, transcribed from `b0c279ffc` before this repair.
 *
 * Kept so the sweep can be shown to FAIL on it. Without that, a green sweep
 * over the new ladder is equally consistent with a property that never fires.
 * Frozen deliberately: it is a record of a defect, and refreshing it from the
 * repaired source would empty the control of the thing it exists to hold
 * (standing notice 50).
 */
function roundedLadderAsShipped(seconds: number): string {
  if (seconds < 90) return "moments";
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes} min`;
  const hours = Math.round(seconds / 3600);
  if (hours < 48) return `${hours} hr`;
  return `${Math.round(seconds / 86400)} days`;
}

/* ═════════════════════ the reader's own check ═════════════════════ */

const UNIT_SECONDS: Record<string, number> = { min: 60, hr: 3600, days: 86400 };

/**
 * The rung an age belongs to. These four thresholds are the SPEC — the words
 * and the cutovers were never the defect and did not move — so restating them
 * here is not re-implementing the ladder. The arithmetic, which is what was
 * wrong, is not restated anywhere: it is recovered from the label and checked
 * against the input.
 */
function rungFor(seconds: number): string {
  if (seconds < 90) return "moments";
  if (seconds < 90 * 60) return "min";
  if (seconds < 48 * 3600) return "hr";
  return "days";
}

/**
 * Does this label state the whole units that have actually elapsed?
 *
 * Returns the reason it does not, or `null` when it is honest. Two independent
 * ways to lie, matching the two mistakes, because a fix for one is not a fix
 * for the other:
 *
 *   * WRONG COUNT — the number is not the floor of the elapsed units in the
 *     unit it names ("6 days" over 5.54 days).
 *   * WRONG RUNG — the label names a coarser or finer unit than the age is in
 *     ("1 hr" over 89½ minutes, where the minutes rung runs to 90). This one
 *     is not a count error: one whole hour really has elapsed at 5,370 s, so a
 *     floor check alone reads it as honest. It still shows the reader 3,600
 *     where the page's own rungs say 5,340, and it is the tell for a threshold
 *     tested against a rounded value.
 *
 * Plus the shape check, so a label this page never emits cannot pass by being
 * unparseable.
 */
function dishonest(label: string, seconds: number): string | null {
  const rung = rungFor(seconds);
  if (label === "moments") {
    return rung === "moments" ? null : `"moments" at ${seconds}s — that is the ${rung} rung`;
  }
  const match = /^(\d+) (min|hr|days)$/.exec(label);
  if (!match) return `unparseable label ${JSON.stringify(label)} at ${seconds}s`;
  const [, digits, unit] = match;
  if (unit !== rung) {
    return `"${label}" at ${seconds}s — names ${unit}, but ${seconds}s is in the ${rung} rung`;
  }
  const count = Number(digits);
  const expected = Math.floor(seconds / UNIT_SECONDS[unit]);
  if (count !== expected) {
    return `"${label}" at ${seconds}s — ${expected} ${unit} have elapsed, not ${count}`;
  }
  return null;
}

/** Ten days of ages, every second. The banner's whole working range and past it. */
const SWEEP_SECONDS = 10 * 86400;

function sweep(ladder: (s: number) => string): string[] {
  const violations: string[] = [];
  for (let s = 0; s < SWEEP_SECONDS; s += 1) {
    const why = dishonest(ladder(s), s);
    if (why !== null) violations.push(why);
  }
  return violations;
}

/* ═════════════════ the property proves itself first ═════════════════ */

describe("the honesty check can fail", () => {
  test("the parser rejects a label that overstates, understates and mis-units", () => {
    // Severing each half of the check in turn: if `dishonest` returned null
    // unconditionally every assertion below it would pass.
    expect(dishonest("6 days", 479_048)).toContain("5 days have elapsed, not 6");
    expect(dishonest("4 days", 479_048)).toContain("5 days have elapsed, not 4");
    expect(dishonest("moments", 479_048)).toContain("that is the days rung");
    expect(dishonest("2 weeks", 479_048)).toContain("unparseable");
    expect(dishonest("1 hour", 3_600)).toContain("unparseable");

    // The rung half, which no count check can reach: one whole hour HAS
    // elapsed at 5,370 s, so this is honest arithmetic in the wrong unit.
    expect(dishonest("1 hr", 5_370)).toContain("names hr, but 5370s is in the min rung");
    expect(dishonest("89 min", 5_370)).toBeNull();

    // …and it accepts the honest readings, so it is not simply rejecting everything.
    expect(dishonest("5 days", 479_048)).toBeNull();
    expect(dishonest("moments", 89)).toBeNull();
    expect(dishonest("1 min", 90)).toBeNull();
  });

  test("positive control: the shipped ladder fails this sweep, in both directions", () => {
    const violations = sweep(roundedLadderAsShipped);

    // Measured: 432,870 of 864,000 — 50.1% of every age in the first ten days.
    expect(violations.length).toBeGreaterThan(400_000);

    // Overstating is the common case and it is what a reader saw on Sep 20.
    expect(violations).toContain(
      '"6 days" at 479048s — 5 days have elapsed, not 6',
    );
    // The rung threshold read off the rounded value: 47h59m59s promoted to days.
    expect(violations).toContain(
      '"2 days" at 172799s — names days, but 172799s is in the hr rung',
    );
    // And the 30-second window where it reads YOUNGER — "1 hr" over 89½
    // minutes. Caught by the rung half of the check, not the count half: the
    // count is a correct floor and the unit is wrong, which is the signature
    // of a threshold tested against a rounded value.
    expect(violations).toContain('"1 hr" at 5370s — names hr, but 5370s is in the min rung');
  });
});

/* ═════════════════════════ the repaired ladder ═════════════════════════ */

describe("#7634 — stalenessAgeLabel states elapsed whole units", () => {
  test("every age across ten days reads as the floor of its own unit", () => {
    const violations = sweep(stalenessAgeLabel);
    expect(violations.slice(0, 5)).toEqual([]);
    expect(violations).toHaveLength(0);
  });

  test("the rung boundaries are read off the RAW value, not a rounded one", () => {
    // Each pair straddles a threshold. The right-hand column is what the
    // shipped ladder printed; every one of them was early.
    const table: Array<[number, string, string]> = [
      [89, "moments", "moments"],
      [90, "1 min", "2 min"], //    the `moments` guard releases; round skips "1 min"
      [5_369, "89 min", "89 min"], // the last second both ladders agree
      [5_370, "89 min", "1 hr"], //   round(s/60) hits 90 half a minute early
      [5_399, "89 min", "1 hr"], //   89m59s — still the minutes rung
      [5_400, "1 hr", "2 hr"], //     exactly 90 min — the hours rung opens here
      [7_199, "1 hr", "2 hr"], //   1h59m59s
      [7_200, "2 hr", "2 hr"],
      [172_799, "47 hr", "2 days"], // 47h59m59s
      [172_800, "2 days", "2 days"], // exactly 48 h — the days rung opens here
      [479_048, "5 days", "6 days"], // the artifact on screen 2026-09-20 23:40Z
    ];
    for (const [seconds, expected, asShipped] of table) {
      expect([seconds, stalenessAgeLabel(seconds)]).toEqual([seconds, expected]);
      expect([seconds, roundedLadderAsShipped(seconds)]).toEqual([seconds, asShipped]);
    }
  });

  test('"1 min" and "1 hr" become reachable, for the whole span each is true', () => {
    // Asserted as a SPAN, not as set membership, because "1 hr" WAS reachable
    // on the old ladder — for 30 of the 1,800 seconds it is the honest reading,
    // the sliver where the minutes rung had rounded up to 90 and the hours rung
    // had not yet rounded up to 2. A membership check passes on 30 seconds and
    // would have called the defect fixed.
    const span = (ladder: (s: number) => string, label: string, from: number, to: number) => {
      let hits = 0;
      for (let s = from; s < to; s += 1) if (ladder(s) === label) hits += 1;
      return hits;
    };
    // 30 s, not 60: the `moments` guard owns [0, 89], so "1 min" is true only
    // across [90, 119]. The rounded ladder printed "2 min" for all of it.
    expect(span(stalenessAgeLabel, "1 min", 0, 3_600)).toBe(30);
    expect(span(roundedLadderAsShipped, "1 min", 0, 3_600)).toBe(0);

    expect(span(stalenessAgeLabel, "1 hr", 0, 86_400)).toBe(1_800);
    expect(span(roundedLadderAsShipped, "1 hr", 0, 86_400)).toBe(30);
  });

  test('"1 days" is unreachable because the days rung opens at 48 h', () => {
    // There is no singular branch, and adding one for a string nothing can
    // produce would be dead code. Asserted as a property so that MOVING a rung
    // fails this test rather than quietly shipping "1 days" to a reader.
    for (let s = 0; s < SWEEP_SECONDS; s += 1) {
      if (stalenessAgeLabel(s) === "1 days") throw new Error(`"1 days" at ${s}s`);
    }
    expect(stalenessAgeLabel(48 * 3_600)).toBe("2 days");
    expect(stalenessAgeLabel(48 * 3_600 - 1)).toBe("47 hr");
  });

  test("total on every input a render path can hand it", () => {
    // The caller is JSX. A throw here is a blank accuracy page, so there is no
    // input for which refusing to answer is acceptable.
    for (const bad of [NaN, Infinity, -Infinity, -1, -86_400, 0, 0.5, 89.999]) {
      expect(typeof stalenessAgeLabel(bad)).toBe("string");
    }
    // A negative age is clock skew, not an age. It must not print a count.
    expect(stalenessAgeLabel(-86_400)).toBe("moments");
    expect(stalenessAgeLabel(NaN)).toBe("moments");
    // Non-integer seconds floor like any other value rather than rounding up.
    expect(stalenessAgeLabel(5_399.99)).toBe("89 min");
  });
});

/* ══════════════ and the reader is shown the repaired number ══════════════ */

const STALE_ENVELOPE = (ageS: number) => ({
  availability: "stale",
  staged: { measured: false, reason: "served_bank_empty" },
  producer: {
    task: "precompute_calibration_main",
    interval_s: 3600,
    stall_after_s: 14400,
    age_s: ageS,
    beats_missed: 132,
    stalled: true,
  },
  cache: {
    status: "stale",
    reason: "main_key_absent_durable",
    age_s: ageS,
    generated_at: "2026-09-15T11:16:10.215051+00:00",
  },
});

function bucket(category: string, idx: number, priceMoved: boolean, n: number) {
  return {
    bucket_idx: idx,
    source: "kalshi",
    category,
    price_moved: priceMoved,
    n,
    winners: Math.round(n * (0.05 + idx * 0.1)),
    avg_prob: 0.05 + idx * 0.1,
    sum_prob: n * (0.05 + idx * 0.1),
    sum_sq_err: n * 0.1,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

const CATEGORIES = [
  { category: "baseball", traded: 80_000, untraded: 60_000 },
  { category: "basketball", traded: 58_000, untraded: 11_000 },
];

function makePayload(envelope: Record<string, unknown>): CalibrationData {
  const buckets = CATEGORIES.flatMap(c =>
    [0, 1, 2, 3, 4].flatMap(i => [
      bucket(c.category, i, true, c.traded / 5),
      bucket(c.category, i, false, c.untraded / 5),
    ]),
  );
  return {
    buckets,
    total_markets: 12_000,
    total_outcomes: CATEGORIES.reduce((t, c) => t + c.traded + c.untraded, 0),
    total_winners: 100_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-15T11:16:10.215051+00:00",
    date_range: { start: "2021-09-01", end: "2026-09-15" },
    min_category_outcomes: 1000,
    by_source: [{ source: "kalshi", ece: 0.02, mce: 0.05, n: 2_000 }],
    by_category: CATEGORIES.map(c => ({
      category: c.category,
      ece: 0.02,
      n: c.traded + c.untraded,
    })),
    small_sample_categories: [],
    ...envelope,
  } as unknown as CalibrationData;
}

/** The banner element, from its own attribute to the end of its div. */
function banner(html: string): string {
  const at = html.indexOf('data-testid="calibration-stale-banner"');
  expect(at).toBeGreaterThan(-1);
  const open = html.lastIndexOf("<div", at);
  return html.slice(open, html.indexOf("</div>", at));
}

function render(ageS: number): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload(
    STALE_ENVELOPE(ageS),
  );
  return renderToStaticMarkup(<CalibrationPage />);
}

describe("the banner a reader sees carries the repaired age", () => {
  test("positive control: the harness renders the real banner, dated", () => {
    // Every assertion below is about text INSIDE this element. A loading shell
    // or a crashed render would satisfy a bare `not.toContain("6 days")`.
    const text = banner(render(479_048));
    expect(text).toContain("Showing the last complete snapshot.");
    expect(text).toContain("These numbers were built");
    expect(text).toContain("Sep 15");
    expect(text).toContain("132 hourly rebuilds have come and gone");
  });

  test("the artifact on screen 2026-09-20 23:40Z is dated 5 days, beside its Sep 15", () => {
    const text = banner(render(479_048));
    expect(text).toContain("(5 days ago)");
    expect(text).not.toContain("6 days ago");
  });

  test("a 47h59m artifact is dated in hours, not promoted to 2 days", () => {
    const text = banner(render(172_799));
    expect(text).toContain("(47 hr ago)");
    expect(text).not.toContain("days ago");
  });
});
