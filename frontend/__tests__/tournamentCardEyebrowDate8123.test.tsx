/**
 * #8123 — a tournament card never dates an event with a capture timestamp.
 *
 * On production `/categories/golf` the Ryder Cup card read
 *
 *     ⛳ Cup  Aug 28
 *     Ryder Cup
 *     Team Europe 53.5%   vs   Team USA 40.0%
 *
 * — a date almost a month in the PAST, sitting directly above the "Upcoming
 * Tournaments" heading, on an event whose own prop markets ("U.S. Team Captain
 * at 2027 Ryder Cup") and `resolution_date` both say 2027.
 *
 * `GET /api/golf` serves that row with `start_date: null`, `end_date: null` and
 * `commence_time: 2026-08-28T20:16:51+00:00`. The `20:16:51` is the tell: a
 * Ryder Cup session does not start at 20:16:51. That is when we captured the
 * market, not a time of play — the class Alex's 2026-09-14 directive names,
 * "scheduled kickoff/capture timestamps are not automatically actual start or
 * finish". The card's `start_date || commence_time` ran the two fields together
 * as if they were interchangeable, and that `||` is what turned a backend gap
 * into a false statement on the page.
 *
 * The rule under test is deliberately NARROW — suppress only where the date is
 * PROVABLY not a date of play: no `start_date`, a `commence_time` already gone,
 * and a `resolution_date` still ahead. An unresolved event cannot have been
 * played on a date that has already passed. Everything else renders as before,
 * which is why most of this file is the cases that must NOT change.
 *
 * Every payload below is verbatim from `GET /api/golf`, read 2026-09-22.
 *
 *   cd frontend && npx jest --testPathPatterns=tournamentCardEyebrowDate8123
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import TournamentCard from "@/components/TournamentCard";
import type { GolfTournament } from "@/lib/types";

/** Between the Ryder Cup's capture stamp and its 2027 resolution. */
const NOW = "2026-09-22T23:55:00Z";

function at<T>(now: string, fn: () => T): T {
  jest.useFakeTimers({ now: new Date(now) });
  try {
    return fn();
  } finally {
    jest.useRealTimers();
  }
}

function markup(t: GolfTournament, now: string = NOW): string {
  return at(now, () =>
    renderToStaticMarkup(<TournamentCard tournament={t} />),
  );
}

/** The eyebrow date — the line above the name, the only span in that slot. */
const EYEBROW_DATE_SPAN = /<span class="text-text-tertiary">([^<]*)<\/span>/;
const eyebrowDate = (m: string): string | null =>
  m.match(EYEBROW_DATE_SPAN)?.[1] ?? null;

/**
 * Ryder Cup, verbatim from `GET /api/golf` 2026-09-22. Two sides, so it renders
 * through the CupCard branch — the branch the defect was REPORTED on, and the
 * one the UX-P180 control population cannot reach (all four of those rows take
 * the leader/chasers branch).
 */
const RYDER_CUP: GolfTournament = {
  key: "ryder_cup",
  name: "Ryder Cup",
  slug: "ryder-cup",
  is_major: false,
  tour: null,
  tour_label: null,
  commence_time: "2026-08-28T20:16:51+00:00",
  resolution_date: "2027-09-30T14:00:00+00:00",
  start_date: null,
  end_date: null,
  schedule_status: null,
  market_ids: [],
  golfers: [
    { name: "Team Europe", probability: 0.535 },
    { name: "Team USA", probability: 0.4 },
  ],
} as unknown as GolfTournament;

/**
 * Presidents Cup, verbatim from the same payload and the same minute. The card
 * two rows up on the same page, through the same branch, WITH real scheduled
 * dates — the non-widening control. If this one ever loses its date, the fix
 * has stopped being narrow.
 */
const PRESIDENTS_CUP: GolfTournament = {
  key: "presidents_cup",
  name: "Presidents Cup",
  slug: "presidents-cup",
  is_major: false,
  tour: "pga",
  tour_label: "PGA Tour",
  commence_time: "2026-09-24T00:00:00+00:00",
  resolution_date: "2026-09-27T00:00:00+00:00",
  start_date: "2026-09-24T00:00:00+00:00",
  end_date: "2026-09-27T00:00:00+00:00",
  schedule_status: "upcoming",
  market_ids: [],
  golfers: [
    { name: "Team USA", probability: 0.815 },
    { name: "Team World", probability: 0.145 },
  ],
} as unknown as GolfTournament;

/** The same shape on the leader/chasers branch, to prove both are wired. */
const LONG_HORIZON_FUTURE: GolfTournament = {
  ...RYDER_CUP,
  key: "golfers_to_win_a_major_before_2030",
  name: "Golfers To Win A Major Before 2030",
  slug: "golfers-to-win-a-major-before-2030",
  tour_label: "PGA Tour",
  commence_time: "2026-07-19T18:17:17+00:00",
  resolution_date: "2030-07-07T14:00:00+00:00",
  golfers: [
    { name: "Miles Russell", probability: 0.032 },
    { name: "Koivun", probability: 0.032 },
    { name: "Novak", probability: 0.02 },
  ],
} as unknown as GolfTournament;

describe("#8123 · the reported specimen", () => {
  it("the Ryder Cup card prints no date instead of a 2026 capture stamp", () => {
    expect(eyebrowDate(markup(RYDER_CUP))).toBeNull();
  });

  it("specifically, it no longer prints 'Aug 28'", () => {
    // Pinned as the literal string a reader saw, so this fails loudly if the
    // suppression is ever reverted or routed around.
    expect(markup(RYDER_CUP)).not.toContain("Aug 28");
  });

  it("suppresses ONLY the date — the rest of the card is intact", () => {
    const m = markup(RYDER_CUP);
    expect(m).toContain("Ryder Cup");
    expect(m).toContain("Team Europe");
    expect(m).toContain("Team USA");
    expect(m).toContain("53.5");
    expect(m).toContain("40.0");
  });

  it("the same shape is suppressed on the leader/chasers branch too", () => {
    // Both branches read the same helper; without this, wiring one and missing
    // the other would pass every other test here.
    const m = markup(LONG_HORIZON_FUTURE);
    expect(eyebrowDate(m)).toBeNull();
    expect(m).not.toContain("Jul 19");
    expect(m).toContain("Miles Russell");
  });
});

describe("#8123 · the population the fix must NOT touch", () => {
  it("the Presidents Cup keeps its real scheduled dates", () => {
    // Same page, same minute, same branch, real `start_date`/`end_date`.
    expect(eyebrowDate(markup(PRESIDENTS_CUP))).toBe("Sep 24–27");
  });

  it("a real start_date wins even when the capture stamp looks suspect", () => {
    // start_date present, commence_time past, resolution_date future — the
    // suppression triggers on the ABSENCE of start_date, never on its presence.
    const scheduled = {
      ...RYDER_CUP,
      start_date: "2027-09-28T00:00:00+00:00",
      end_date: "2027-09-30T00:00:00+00:00",
    } as GolfTournament;
    expect(eyebrowDate(markup(scheduled))).toBe("Sep 28–30");
  });

  it("a FUTURE commence_time still shows — it is not provably wrong", () => {
    const upcoming = {
      ...RYDER_CUP,
      commence_time: "2027-09-28T00:00:00+00:00",
    } as GolfTournament;
    expect(eyebrowDate(markup(upcoming))).toBe("Sep 28");
  });

  it("a row with no resolution_date is not second-guessed", () => {
    // Two of the four served windowless rows are exactly this (the mis-filed
    // darts and snooker markets). With nothing to contradict the stamp we
    // cannot prove it wrong, so we do not suppress it.
    const noResolution = {
      ...RYDER_CUP,
      resolution_date: null,
    } as GolfTournament;
    expect(eyebrowDate(markup(noResolution))).toBe("Aug 28");
  });

  it("an already-resolved event keeps its date", () => {
    // Past commence, PAST resolution: nothing contradictory about a finished
    // event carrying a past date, so settled cards are untouched.
    const resolved = {
      ...RYDER_CUP,
      resolution_date: "2026-08-30T00:00:00+00:00",
    } as GolfTournament;
    expect(eyebrowDate(markup(resolved))).toBe("Aug 28");
  });

  it("an unparseable commence_time does not crash the card", () => {
    const junk = { ...RYDER_CUP, commence_time: "not-a-date" } as GolfTournament;
    expect(() => markup(junk)).not.toThrow();
  });
});

describe("#8123 · the suppression is keyed on the clock, not on the row", () => {
  it("the very same Ryder Cup row DID print a date before its stamp passed", () => {
    // Non-vacuity: read at a moment before 2026-08-28T20:16:51 the identical
    // row renders "Aug 28", so these tests are exercising the rule and not a
    // row that simply never had a date to show.
    expect(eyebrowDate(markup(RYDER_CUP, "2026-08-01T12:00:00Z"))).toBe("Aug 28");
  });

  it("and stops printing it the moment the stamp goes past", () => {
    expect(eyebrowDate(markup(RYDER_CUP, "2026-08-28T20:16:52Z"))).toBeNull();
  });
});
