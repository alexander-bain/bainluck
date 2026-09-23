// #925 — PERIOD AND CLOCK ARE OBSERVED SEPARATELY, SO THEY AGE SEPARATELY.
//
// ── PROVENANCE ───────────────────────────────────────────────────────────────
//
// This file is codex's independent reproducer
// (`artifacts/other-model-chart-clients-finish/codex-regressions/
// codexIndependentStateClocks925.test.tsx`), pinned here as the acceptance for
// the correction its review required before the #925 dating layer could be
// adopted. Its three scenarios and its three assertions on rendered output are
// reproduced unchanged.
//
// ONE THING IS DIFFERENT, and it is the whole correction. The reproducer's rows
// stamp `_periodObservedAt` on a CLOCK-only observation, because the candidate
// it was written against had a single shared stamp for both fields — that
// sharing IS the defect. Rows here stamp `_clockObservedAt` on a clock
// observation and `_periodObservedAt` on a period observation, which is what
// `OddsChart`'s enrich step now emits. Adapting the input to the corrected
// field shape is required; adapting the ASSERTIONS would have been answering
// the test instead of the reader, so the expected output is byte-identical to
// codex's.
//
// ── WHAT THE READER SEES ─────────────────────────────────────────────────────
//
// A scrub point at 8:03 PM whose game clock was last seen at 8:00 PM must not
// print that clock as if it had been read at 8:03. The `~` said "approximate"
// and never said how old; a period-only observation at 8:03 silently made the
// card stop saying even that.
//
// ── CONTROLS ─────────────────────────────────────────────────────────────────
//
// The third test is codex's control and is the strawman guard for the other
// two: when BOTH fields are observed at 8:03 nothing is carried, so the badge
// is exact and the card must print no age line at all. A change that simply
// always printed "as of" would pass the first two and fail this one.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import GamePlayCard from "@/components/GamePlayCard";
import { carryGameStateForward, type CarriedGameStateRow } from "@/lib/chartGameState";

const t0 = "2026-09-22T20:00:00Z";
const t3 = "2026-09-22T20:03:00Z";

/** The real path: carry the rows, hand the last one to the real card. */
function card(rows: CarriedGameStateRow[]): string {
  const p = carryGameStateForward(rows).at(-1)!;
  return renderToStaticMarkup(
    <GamePlayCard
      homeTeam="Boston Celtics"
      awayTeam="Oklahoma City Thunder"
      sportKey="basketball_nba"
      activePoint={{
        timestamp: p.timestamp,
        homeProb: 0.6,
        awayProb: 0.4,
        period: p._period,
        clock: p._clock,
        clockApprox: p._clockApprox,
        periodApprox: p._periodApprox,
        periodObservedAt: p._periodObservedAt,
        clockObservedAt: p._clockObservedAt,
        scoreObservedAt: p._scoreObservedAt,
        scoreApprox: p._scoreApprox,
      }}
    />,
  );
}

test("period-only observation must not erase the carried clock's age", () => {
  const html = card([
    { timestamp: t0, _period: "1", _clock: "7:41", _periodObservedAt: t0, _clockObservedAt: t0 },
    { timestamp: t3, _period: "1", _periodObservedAt: t3 },
  ]);
  expect(html).toContain("~7:41");
  expect(html).toContain("as of 8:00 PM");
});

test("clock-only observation must not present a carried period as freshly observed", () => {
  const html = card([
    { timestamp: t0, _period: "1", _clock: "7:41", _periodObservedAt: t0, _clockObservedAt: t0 },
    { timestamp: t3, _clock: "4:41", _clockObservedAt: t3 },
  ]);
  expect(html).toContain("Q1");
  expect(html).toContain("as of 8:00 PM");
});

test("a complete new observation has no carried-state age (control)", () => {
  const html = card([
    { timestamp: t0, _period: "1", _clock: "7:41", _periodObservedAt: t0, _clockObservedAt: t0 },
    { timestamp: t3, _period: "1", _clock: "4:41", _periodObservedAt: t3, _clockObservedAt: t3 },
  ]);
  expect(html).toContain("Q1 4:41");
  expect(html).not.toContain("as of");
});

// ── The marks the two scenarios above leave on the badge ─────────────────────
//
// Codex's three tests fix the AGE LINE. These pin which half of the badge wears
// the `~`, because "as of 8:00 PM" is only readable if the reader can see which
// half it is about. The rule: the `~` marks the odd one out, and never appears
// twice.

test("the carried half is the marked half, and only one half is ever marked", () => {
  const periodFresh = card([
    { timestamp: t0, _period: "1", _clock: "7:41", _periodObservedAt: t0, _clockObservedAt: t0 },
    { timestamp: t3, _period: "1", _periodObservedAt: t3 },
  ]);
  // Clock carried, period fresh → the clock wears it (as it has since 8bf2bf8d).
  expect(badge(periodFresh)).toBe("Q1 ~7:41");

  const clockFresh = card([
    { timestamp: t0, _period: "1", _clock: "7:41", _periodObservedAt: t0, _clockObservedAt: t0 },
    { timestamp: t3, _clock: "4:41", _clockObservedAt: t3 },
  ]);
  // Period carried, clock fresh → the period wears it. Without this the reader
  // sees a completely unmarked "Q1 4:41" over an "as of 8:00 PM" and cannot
  // tell which of the two the line is talking about.
  expect(badge(clockFresh)).toBe("~Q1 4:41");

  const bothCarried = card([
    { timestamp: t0, _period: "1", _clock: "7:41", _periodObservedAt: t0, _clockObservedAt: t0 },
    { timestamp: t3 },
  ]);
  // Both carried → ONE tilde, not two; the age line covers the whole badge.
  expect(badge(bothCarried)).toBe("Q1 ~7:41");
  expect(bothCarried).toContain("as of 8:00 PM");
});

test("a carry inside one displayed minute prints no age line (nothing to say)", () => {
  // The rows are minute-keyed but their timestamps are raw, so a carried state
  // can be seconds old and format to the same wall-clock minute as the price.
  // "8:03 PM / as of 8:03 PM" is two lines saying one thing — noise under a
  // badge that has three lines already, and exactly the diagnostic clutter D102
  // forbids. The `~` still does its job.
  const html = card([
    { timestamp: "2026-09-22T20:03:10Z", _period: "1", _clock: "7:41",
      _periodObservedAt: "2026-09-22T20:03:10Z", _clockObservedAt: "2026-09-22T20:03:10Z" },
    { timestamp: "2026-09-22T20:03:50Z" },
  ]);
  expect(badge(html)).toBe("Q1 ~7:41"); // carried, and marked as carried
  expect(html).not.toContain("as of"); // but there is no age worth printing
});

test("when both halves are carried from DIFFERENT minutes, the age names the older", () => {
  // Without this arm "oldest" and "newest" agree on every other case in this
  // file — both halves are carried from the same row everywhere else — so the
  // rule would have no specimen that can tell the two apart and a reversal
  // would be invisible. Period last seen 7:58, clock last seen 8:00, scrubbing
  // at 8:03: the badge is at least five minutes old, and saying "8:00" would
  // make it look three.
  const html = card([
    { timestamp: "2026-09-22T19:58:00Z", _period: "1", _periodObservedAt: "2026-09-22T19:58:00Z" },
    { timestamp: t0, _clock: "7:41", _clockObservedAt: t0 },
    { timestamp: t3 },
  ]);
  expect(html).toContain("as of 7:58 PM");
  expect(html).not.toContain("as of 8:00 PM");
});

test("a clock the badge does not show cannot date the badge (#7860 interaction)", () => {
  // ESPN's period detail already spells the clock — `period: "9:44 - 2nd
  // Quarter"` arrives beside `game_clock: "9:44"` — and `trustedLiveClock`
  // suppresses the duplicate standalone clock (#7860). So the age line must be
  // decided over what is DISPLAYED, not over what the point carries: here the
  // only clock on screen lives inside the period string and must age with the
  // period. Keying this on `point.clockApprox` alone would date a badge by an
  // observation the reader cannot see.
  const html = card([
    {
      timestamp: t0,
      _period: "9:44 - 2nd Quarter",
      _clock: "9:44",
      _periodObservedAt: t0,
      _clockObservedAt: t0,
    },
    { timestamp: t3, _period: "9:44 - 2nd Quarter", _periodObservedAt: t3 },
  ]);
  // The suppressed clock is stale (last seen 8:00) but is not on screen, and
  // the period IS this minute's — so there is nothing to date.
  expect(badge(html)).toBe("9:44 - 2nd Quarter");
  expect(html).not.toContain("as of");
  // And the deduplication itself still holds: the clock is printed once.
  expect((badge(html)!.match(/9:44/g) ?? []).length).toBe(1);
});

/** Text inside the game-state badge (the bg-surface-secondary span). */
function badge(html: string): string | null {
  const m = html.match(/bg-surface-secondary[^>]*>([^<]*)</);
  return m ? m[1] : null;
}
