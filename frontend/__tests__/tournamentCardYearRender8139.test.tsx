/**
 * #8139 — a tournament card states the YEAR when its date is not this season's.
 *
 * Two things sit behind this, one already on production and one arriving.
 *
 * ALREADY ON PRODUCTION. The archived `GET /api/golf` body of 2026-08-29
 * (`fixtures/uxp179_golf_before.json`) carries
 * `golfers_to_win_a_pga_tour_major_in_2027` with no `start_date` and a
 * `commence_time` of **2028-01-14**, and the card printed a bare **"Jan 14"**
 * for it — sixteen months away, rendered between two tournaments that had
 * started that Thursday, under a title reading "…Major In 2027". Nothing on the
 * card told the reader which January it meant. That row is pinned as a split
 * control in `capture/golfTournamentCardLiveWindowCapture.test.tsx`.
 *
 * ARRIVING. #8139's producer half makes `/api/golf` serve the Ryder Cup's real
 * `2027-09-17 → 2027-09-19` out of `majors_calendar.yaml`, in place of today's
 * `start_date: null`. The instant that payload changes — no frontend deploy
 * involved — a yearless `Sep 17–19` would render inside a list of 2026
 * tournaments and read as this season. That is worse than the honest blank
 * #8123 prints today, so the renderer has to be able to say the year FIRST.
 * This file is that precondition, shipped alone: it is safe on its own because
 * every row `/api/golf` serves today is in-season, and the in-season cases below
 * assert byte-for-byte that they did not move.
 *
 * The rule is the calendar year, compared in UTC: it says the year when the
 * date is not in the reader's own year, at either end of the window.
 *
 *   cd frontend && npx jest --testPathPatterns=tournamentCardYearRender8139
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

/** A 2026 reader. Every expectation below is stated against this clock. */
const NOW = "2026-09-22T23:55:00Z";

function at<T>(now: string, fn: () => T): T {
  jest.useFakeTimers({ now: new Date(now) });
  try {
    return fn();
  } finally {
    jest.useRealTimers();
  }
}

const EYEBROW_DATE_SPAN = /<span class="text-text-tertiary">([^<]*)<\/span>/;

function eyebrowDate(t: GolfTournament, now: string = NOW): string | null {
  const m = at(now, () =>
    renderToStaticMarkup(<TournamentCard tournament={t} />),
  );
  return m.match(EYEBROW_DATE_SPAN)?.[1] ?? null;
}

/**
 * The Ryder Cup as `/api/golf` serves it TODAY (verbatim, read 2026-09-22),
 * plus the `start_date`/`end_date` #8139's producer half will fill in from
 * `majors_calendar.yaml:146`. Two sides, so this renders through `CupCard` —
 * the branch the Ryder Cup actually takes on the page.
 */
const RYDER_CUP_2027: GolfTournament = {
  key: "ryder_cup",
  name: "Ryder Cup",
  slug: "ryder-cup",
  is_major: false,
  tour: null,
  tour_label: null,
  commence_time: "2026-08-28T20:16:51+00:00",
  resolution_date: "2027-09-30T14:00:00+00:00",
  start_date: "2027-09-17T00:00:00+00:00",
  end_date: "2027-09-19T00:00:00+00:00",
  schedule_status: null,
  market_ids: [],
  golfers: [
    { name: "Team Europe", probability: 0.535 },
    { name: "Team USA", probability: 0.4 },
  ],
} as unknown as GolfTournament;

/**
 * The Presidents Cup, verbatim from the same payload and the same minute: this
 * season's dates, on the same branch. The non-widening control.
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

/** The same shapes on the leader/chasers branch, to prove both are wired. */
function asStrokePlay(t: GolfTournament, overrides: Partial<GolfTournament> = {}): GolfTournament {
  return {
    ...t,
    key: "fedex_open_de_france",
    name: "Fedex Open De France",
    slug: "fedex-open-de-france",
    tour_label: "European Tour",
    golfers: [
      { name: "Rory McIlroy", probability: 0.12 },
      { name: "Jon Rahm", probability: 0.09 },
      { name: "Tommy Fleetwood", probability: 0.07 },
    ],
    ...overrides,
  } as unknown as GolfTournament;
}

describe("#8139 · a date outside the reader's season carries its year", () => {
  it("the Ryder Cup's real calendar dates render as 'Sep 17–19, 2027'", () => {
    // The payload #8139's producer half will serve. Without this change the
    // same row reads "Sep 17–19" in a list of 2026 tournaments.
    expect(eyebrowDate(RYDER_CUP_2027)).toBe("Sep 17–19, 2027");
  });

  it("the year is on the leader/chasers branch too, not just the cup card", () => {
    // Both branches call the same helper; wiring one and missing the other
    // would pass every cup-shaped assertion in this file.
    expect(eyebrowDate(asStrokePlay(RYDER_CUP_2027))).toBe("Sep 17–19, 2027");
  });

  it("a single out-of-season date carries its year — the archived 'Jan 14'", () => {
    // `golfers_to_win_a_pga_tour_major_in_2027`, read from production
    // 2026-08-29: no window, a 2028-01-14 stamp, and a card that said "Jan 14".
    const future = asStrokePlay(RYDER_CUP_2027, {
      start_date: null,
      end_date: null,
      commence_time: "2028-01-14T15:00:00+00:00",
      resolution_date: null,
    });
    expect(eyebrowDate(future)).toBe("Jan 14, 2028");
  });

  it("a window that crosses New Year's states BOTH years", () => {
    // One year on a two-year window is a lie whichever end it is put on.
    const crossing = asStrokePlay(RYDER_CUP_2027, {
      start_date: "2026-12-30T00:00:00+00:00",
      end_date: "2027-01-02T00:00:00+00:00",
    });
    expect(eyebrowDate(crossing)).toBe("Dec 30, 2026–Jan 2, 2027");
  });

  it("a same-month window a year apart does not collapse to a day range", () => {
    // The old end-day collapse tested the MONTH only, so Sep 2026 → Sep 2027
    // would have printed "Sep 17–19" and hidden twelve months inside a dash.
    // Wholly in the future, so the schedule window cannot make this card LIVE
    // and swap the eyebrow date for a pulse — a window containing `now` has no
    // date span to read at all.
    const yearApart = asStrokePlay(RYDER_CUP_2027, {
      start_date: "2027-05-10T00:00:00+00:00",
      end_date: "2028-05-12T00:00:00+00:00",
    });
    expect(eyebrowDate(yearApart)).toBe("May 10, 2027–May 12, 2028");
  });
});

describe("#8139 · the rule is keyed on the reader's year, not on a pinned one", () => {
  it("the very same Ryder Cup row prints NO year to a 2027 reader", () => {
    // Non-vacuity in the direction that matters: the year is not simply always
    // appended to 2027 dates, nor is 2026 hard-coded anywhere. Read from inside
    // the 2027 season, the identical row renders the bare in-season form.
    expect(eyebrowDate(RYDER_CUP_2027, "2027-09-01T12:00:00Z")).toBe("Sep 17–19");
  });

  it("and the Presidents Cup's 2026 dates DO carry a year to that same reader", () => {
    // The mirror image, same clock: last season's window seen from 2027.
    expect(eyebrowDate(PRESIDENTS_CUP, "2027-09-01T12:00:00Z")).toBe("Sep 24–27, 2026");
  });

  it.each([
    // 30 minutes either side of midnight UTC on New Year's. Both expectations
    // are the UTC answer and hold in EVERY zone, so this is an assertion of
    // zone-independence rather than a zone gate (UX-P180's pattern, not
    // UX-P179's) — but off a UTC box they also each kill the mutant that reads
    // the reader's year with `getFullYear()`: at 23:30Z a zone east of UTC has
    // already turned 2027 locally, at 00:30Z a zone west of it has not.
    ["the last half-hour of 2026, UTC", "2026-12-31T23:30:00Z", "Jan 5, 2027"],
    ["the first half-hour of 2027, UTC", "2027-01-01T00:30:00Z", "Jan 5"],
  ])("a Jan 5 2027 card across the turn of the year: %s", (_label, now, expected) => {
    const jan = asStrokePlay(RYDER_CUP_2027, {
      start_date: "2027-01-05T00:00:00+00:00",
      end_date: null,
    });
    expect(eyebrowDate(jan, now)).toBe(expected);
  });
});

describe("#8139 · the population this must NOT touch", () => {
  it("the Presidents Cup keeps exactly the bytes it had: 'Sep 24–27'", () => {
    // Every row `/api/golf` serves today is in-season, which is what makes this
    // renderer change safe to ship ahead of its producer half.
    expect(eyebrowDate(PRESIDENTS_CUP)).toBe("Sep 24–27");
  });

  it("an in-season single date keeps its bare form", () => {
    const single = asStrokePlay(PRESIDENTS_CUP, { end_date: null });
    expect(eyebrowDate(single)).toBe("Sep 24");
  });

  it("an in-season window spanning two months keeps its bare form", () => {
    const spanning = asStrokePlay(PRESIDENTS_CUP, {
      start_date: "2026-09-28T00:00:00+00:00",
      end_date: "2026-10-01T00:00:00+00:00",
    });
    expect(eyebrowDate(spanning)).toBe("Sep 28–Oct 1");
  });

  it("a date EARLIER in the reader's own year is still this season — no year", () => {
    // The rule is the year, not the future: a March card read in September is
    // one of the rows on screen, and stamping "2026" on it would be noise.
    const march = asStrokePlay(PRESIDENTS_CUP, {
      start_date: "2026-03-05T00:00:00+00:00",
      end_date: "2026-03-08T00:00:00+00:00",
    });
    expect(eyebrowDate(march)).toBe("Mar 5–8");
  });

  it("#8123's suppression is untouched — no start_date, stale stamp, still blank", () => {
    // The Ryder Cup as served TODAY. The year rule must not resurrect a date
    // that #8123 refuses to state at all.
    const asServed = {
      ...RYDER_CUP_2027,
      start_date: null,
      end_date: null,
    } as GolfTournament;
    expect(eyebrowDate(asServed)).toBeNull();
  });
});

describe("#8139 · an unreadable stamp states nothing at all", () => {
  it("junk in the date field prints no date, not 'undefined NaN'", () => {
    // Reachable before this change (a row with no `resolution_date` to trigger
    // #8123's suppression falls straight through to the formatter) and it
    // printed the literal string "undefined NaN"; with a year appended it would
    // have become "undefined NaN, NaN".
    const junk = asStrokePlay(RYDER_CUP_2027, {
      start_date: "not-a-date",
      end_date: null,
      resolution_date: null,
    });
    const m = at(NOW, () =>
      renderToStaticMarkup(<TournamentCard tournament={junk} />),
    );
    expect(m).not.toContain("undefined");
    expect(m).not.toContain("NaN");
    expect(m.match(EYEBROW_DATE_SPAN)).toBeNull();
    // and the rest of the card still renders
    expect(m).toContain("Fedex Open De France");
    expect(m).toContain("Rory McIlroy");
  });

  it("an unreadable END keeps the start it can read", () => {
    const junkEnd = asStrokePlay(RYDER_CUP_2027, { end_date: "not-a-date" });
    expect(eyebrowDate(junkEnd)).toBe("Sep 17, 2027");
  });
});
