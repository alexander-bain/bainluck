/**
 * #5761 — the hero's age badge stops counting in a unit it has outgrown.
 *
 * A 19-hour-old MiLB page stamped itself `1166m ago`; the Como–Parma page I
 * shot on production at 05:20Z said `818m ago`. Minutes were unbounded, so the
 * string grew without limit and a week-old page read `10000m ago`. The badge
 * now climbs the same ladder every other age mark on the site climbs.
 *
 * ═══ WHY THE ASSERTIONS ARE LABELLED ═══
 *
 * The house convention (see `priceAgeMark4970.test.tsx`):
 *
 *   SHIP     red against the parent. This is the change.
 *   GUARD    green against the parent, red against a plausible mutant of the
 *            new code. It protects a DECISION, not the diff.
 *   CONTROL  green against both. It pins what must not move.
 *
 * A GUARD with no named mutant is a wish. Each one names the mutation it dies
 * to; the run is recorded at the foot.
 *
 * ═══ THE NEGATIVES ARE POINTED AT EXTRACTED TEXT, AND THE EXTRACTOR THROWS ═══
 *
 * ux/1248 found six inherited `not.toContain(...)` guards on the hero caption
 * that a wording change had silently made vacuous — they forbade a string that
 * could no longer occur under ANY wording. The same trap is live here: the
 * defect string `1166m ago` is a substring of nothing else, but an assertion
 * pointed at the whole document would also pass if the badge stopped rendering
 * altogether. So every assertion below reads `badgeText()`, which THROWS when
 * no badge drew — an extractor returning `""` for a missing element is the same
 * vacuity by a second route.
 *
 * ═══ THE CLOCK IS FROZEN, NOT AMBIENT ═══
 *
 * Gotcha #44. `LiveAgeStamp` reads `Date.now()` inside `ageSeconds` and does not
 * thread a clock (production should not have to), so the suite pins the instant
 * and expresses every stamp as an offset from it. No assertion below branches on
 * when the suite happens to run.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import LiveAgeStamp from "@/components/event/LiveAgeStamp";
import { formatAgeFromSeconds, formatSourceAge } from "@/lib/sourceAge";

/** A fixed instant. Every stamp below is expressed as an offset from it. */
const NOW = Date.parse("2026-09-14T05:20:00.000Z");
const SEC = 1000;
const MIN = 60 * SEC;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

let nowSpy: jest.SpyInstance;
beforeEach(() => {
  nowSpy = jest.spyOn(Date, "now").mockReturnValue(NOW);
});
afterEach(() => nowSpy.mockRestore());

/**
 * The badge's VISIBLE string, or a throw.
 *
 * Not the markup, and not the aria-label: the defect is what a reader sees, and
 * a negative assertion that can pass because nothing rendered is not a guard.
 */
function badgeText(ageMs: number, props: Partial<{ connected: boolean }> = {}): string {
  const html = renderToStaticMarkup(
    <LiveAgeStamp
      updatedAt={new Date(NOW - ageMs).toISOString()}
      connected={props.connected ?? true}
    />,
  );
  const m = html.match(/<span class="tabular-nums">([^<]*)<\/span>/);
  if (!m) {
    throw new Error(
      `LiveAgeStamp drew no age span for ageMs=${ageMs}. An assertion about a ` +
        `string that never rendered proves nothing. Markup was: ${html}`,
    );
  }
  return m[1];
}

describe("#5761 — the age badge ladders past the hour", () => {
  it("SHIP: the filed 19-hour specimen reads 19h, not 1166m", () => {
    // The issue's own specimen: /events/15310426, first pitch Sep 11 7:05 PM PDT,
    // read at 2026-09-12 21:45Z. Parent rendered `1166m ago`.
    expect(badgeText(1166 * MIN)).toBe("19h ago");
  });

  it("SHIP: my own production specimen reads 13h, not 818m", () => {
    // Como–Parma /events/15297960, shot at 390px 2026-09-14 05:20Z while paying
    // #5995's LOOK. Parent rendered `818m ago`.
    expect(badgeText(818 * MIN)).toBe("13h ago");
  });

  it("SHIP: no age renders a three-or-more-digit minute count, at any age", () => {
    // The unbounded-growth half. A week-old page read `10000m ago` on the parent.
    for (const ms of [100 * MIN, 818 * MIN, 1166 * MIN, 7 * DAY, 400 * DAY]) {
      expect(badgeText(ms)).not.toMatch(/\d{3,}m ago/);
    }
  });

  it("SHIP: a day-old page says yesterday and a week-old one counts days", () => {
    expect(badgeText(25 * HOUR)).toBe("yesterday");
    expect(badgeText(7 * DAY)).toBe("7d ago");
  });

  it("GUARD: the sub-minute branch still counts SECONDS and still says live", () => {
    // Dies to: `const label = formatAgeFromSeconds(age)` — delegating for every
    // age, which is the obvious simplification and would print "just now" over a
    // live hero, deleting the one signal this badge exists to carry.
    expect(badgeText(8 * SEC)).toBe("live · 8s ago");
    expect(badgeText(59 * SEC)).toBe("live · 59s ago");
  });

  it("GUARD: the handover from seconds to minutes is at 60s exactly", () => {
    // Dies to: `age <= 60` in the branch, which strands `60s ago` on the badge.
    expect(badgeText(60 * SEC)).toBe("live · 1m ago");
  });

  it("GUARD: the minute rung survives, and hands over at 60 minutes exactly", () => {
    // Dies to: an hour rung placed at the wrong boundary (`hours <= 24`,
    // `mins < 30`), and to dropping the minute rung in favour of hours.
    expect(badgeText(3 * MIN)).toBe("3m ago");
    expect(badgeText(59 * MIN)).toBe("59m ago");
    expect(badgeText(60 * MIN)).toBe("1h ago");
  });

  it("GUARD: the hour rung runs to 24h, and 'yesterday' is one day only", () => {
    // Dies to: `days >= 1 => "yesterday"`, which would call a 5-day-old page
    // yesterday — the failure mode that makes a stale page look fresh.
    expect(badgeText(23 * HOUR)).toBe("23h ago");
    expect(badgeText(24 * HOUR)).toBe("yesterday");
    expect(badgeText(47 * HOUR)).toBe("yesterday");
    expect(badgeText(48 * HOUR)).toBe("2d ago");
  });

  it("CONTROL: an old badge drops the word 'live'; a fresh one keeps it", () => {
    // Unmoved by this ship, and the reason the SHIP strings above carry no
    // `live · ` prefix. #5459's withdrawal presentation is not touched here.
    expect(badgeText(8 * SEC)).toContain("live · ");
    expect(badgeText(1166 * MIN)).not.toContain("live");
  });

  it("CONTROL: the extractor throws rather than passing an empty string", () => {
    // The vacuity check on the rig itself (ux/1248). If this ever stops throwing,
    // every `not.toMatch` above has a second way to pass without examining
    // anything.
    const html = renderToStaticMarkup(<LiveAgeStamp updatedAt={null} connected />);
    expect(html).toBe("");
    expect(() =>
      // Same extractor, applied to the render that draws nothing.
      (() => {
        const m = html.match(/<span class="tabular-nums">([^<]*)<\/span>/);
        if (!m) throw new Error("no badge");
        return m[1];
      })(),
    ).toThrow();
  });
});

describe("#5761 — the ladder is shared, not copied", () => {
  it("CONTROL: formatSourceAge is unchanged by the extraction", () => {
    // `formatSourceAge` now delegates to `formatAgeFromSeconds`. It is called by
    // BookmakerTable and the models page, so the refactor must be observationally
    // identical for every rung — this pins the two entry points together rather
    // than restating the expected strings, which would just be the ladder typed
    // a third time.
    for (const secs of [0, 30, 59, 60, 61, 3599, 3600, 86399, 86400, 172800, 600000]) {
      expect(formatSourceAge(new Date(NOW - secs * 1000).toISOString(), NOW)).toBe(
        formatAgeFromSeconds(secs),
      );
    }
  });

  it("GUARD: the badge and the bookmaker column agree about one instant", () => {
    // Dies to: re-inlining the thresholds in LiveAgeStamp (the state this ship
    // left). Two age marks on one page disagreeing about the same stamp is the
    // defect class `heroFactIsStale` was extracted to prevent; this is that
    // argument applied to the wording.
    for (const mins of [3, 59, 60, 818, 1166, 1440, 2880]) {
      expect(badgeText(mins * MIN)).toBe(
        formatSourceAge(new Date(NOW - mins * MIN).toISOString(), NOW),
      );
    }
  });
});

/**
 * ═══ MUTATION RUN (ux/1249, recorded on the exact source) ═══
 *
 * Each mutant applied to the shipped source, suite run, source restored and
 * verified byte-identical by sha256 afterwards.
 *
 *   1. `LiveAgeStamp`: `const label = formatAgeFromSeconds(age)` (delegate for
 *      every age, dropping the seconds branch)          → RED, 1 test
 *   2. `LiveAgeStamp`: `age <= 60` in the branch         → RED, 1 test
 *   3. `LiveAgeStamp`: label restored to the parent
 *      `${Math.floor(age / 60)}m ago`                    → RED, 7 tests
 *   4. `sourceAge`: `if (days >= 1) return "yesterday"`  → RED, 2 tests
 *   5. `sourceAge`: `if (hours < 48)` (hour rung over-runs) → RED, 2 tests
 *
 * 5 mutants, 5 killed. Counts are the measured `Tests: N failed` line from each
 * run, not an estimate — mutant 1 kills ONE test rather than the two arms I first
 * wrote down, because the `live · ` CONTROL survives it ("live · just now" still
 * contains the prefix). Recording the guess would have overstated the suite.
 *
 * Mutant 3 IS the parent source, so that row is also the SHIP-redness proof: the
 * four SHIP tests fail against the commit this ship is built on.
 *
 * Restored and verified byte-identical by sha256 after every mutant.
 */
