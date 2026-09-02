/**
 * UX-P267 (#2549) — the tournament card says when the tournament starts.
 *
 * THE DEFECT, still live when this was written. Discover is the default landing
 * page, and its only tournament card read:
 *
 *     Omega European Masters
 *     Crans-sur-Sierre GC
 *     Started Mon, Aug 31          <- the tournament starts Sep 3
 *
 * while the SAME card payload carried `start_date: "2026-09-03T00:00:00+00:00"`,
 * `schedule_status: "upcoming"`, and a backend-computed `headline: "Tomorrow"`.
 * Nothing was missing from the wire. `commence_time` — a per-market Kalshi open
 * time, seven different values across this tournament's seven markets — was
 * being read as a schedule, and the module's two trust windows cannot catch that
 * because an open time is always RECENT, which is the region both windows admit.
 *
 * PROVENANCE OF THE FIXTURE. `OMEGA` is the card the production feed served at
 * 2026-09-02 03:1x PT (`GET /api/feed?limit=60`, the single `type: "tournament"`
 * item). The other three are the remaining rows of `GET /api/golf` at the same
 * minute, carried into the same shape — which is not an assumption: the feed
 * builder constructs the card by copying these exact keys off that exact dict
 * (`routes/feed.py`, `"start_date": t.get("start_date")` and its neighbours), so
 * these values ARE what the feed emits for those tournaments. They are the whole
 * live slate, not a sample.
 *
 * WHAT EACH ROW IS FOR — every branch of the fix has a live specimen:
 *
 *   omega      start_date Sep 3 vs commence Aug 31   THE DEFECT (the only row that moves)
 *   biltmore   start_date == commence, same day      agree-control: schedule wins, string identical
 *   major_2027 no start_date, commence +499d         the +365d fallback window must still fire
 *   major_2030 no start_date, commence -45d          the -7d fallback window must still fire
 *
 * THE CLOCK IS FROZEN, never seeded from `Date.now()` (gotcha #44) — the card
 * reads the ambient clock, so a run straddling a date boundary would otherwise
 * flip "Starts Thu, Sep 3" to "Starts tomorrow".
 *
 * ⚠️ WHAT THIS SUITE CANNOT PROVE, STATED RATHER THAN IMPLIED. `jest.config.js`
 * pins `process.env.TZ = 'UTC'` for the whole suite, so local IS UTC in here and
 * an assertion of the form "a UTC-midnight start_date must not render as the
 * previous day" is green on the fix AND green on a naive local-render bug alike
 * — a string common to both arms. Rather than ship that decoration, the
 * zone-independence is made TRUE BY CONSTRUCTION (the declared day is lifted out
 * of the ISO string as integers and never round-tripped through a local `Date`)
 * and the guard pins the construction: see `describe("the construction")`.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedTournamentData } from "@/lib/types";
import {
  formatDeclaredStartLabel,
  formatTournamentTimingLabel,
} from "@/lib/gameTimeLabel";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import { TournamentCard } from "../../components/discover/TournamentCard";

/** 2026-09-02 10:15:00Z — the instant the slate below was captured. */
const NOW_T = Date.parse("2026-09-02T10:15:00Z");

beforeAll(() => {
  jest.useFakeTimers();
  jest.setSystemTime(NOW_T);
});
afterAll(() => {
  jest.useRealTimers();
});

function tournament(over: Partial<FeedTournamentData>): FeedTournamentData {
  return {
    key: "k",
    name: "A Tournament",
    is_major: false,
    golfers: [{ name: "A Golfer", probability: 0.1, rank: 1, movement_24h: null }],
    market_ids: [1],
    source_count: 1,
    ...over,
  } as FeedTournamentData;
}

const OMEGA = tournament({
  key: "omega_european_masters",
  name: "Omega European Masters",
  slug: "omega-european-masters",
  tour: "dp_world",
  tour_label: "DP World Tour",
  venue: "Crans-sur-Sierre GC",
  location: "Crans-Montana, Switzerland",
  start_date: "2026-09-03T00:00:00+00:00",
  end_date: "2026-09-06T00:00:00+00:00",
  schedule_status: "upcoming",
  commence_time: "2026-08-31T15:11:13+00:00",
  resolution_date: "2026-09-06T00:00:00+00:00",
  golfers: [{ name: "Ryan Gerard", probability: 0.085, rank: 1, movement_24h: 0.005 }],
});

const BILTMORE = tournament({
  key: "biltmore_championship_asheville",
  name: "Biltmore Championship Asheville",
  slug: "biltmore-championship-asheville",
  tour: "pga",
  tour_label: "PGA Tour",
  venue: "The Cliffs at Walnut Cove",
  location: "Arden, NC",
  start_date: "2026-09-17T00:00:00+00:00",
  end_date: "2026-09-20T00:00:00+00:00",
  schedule_status: "upcoming",
  commence_time: "2026-09-17T00:00:00+00:00",
  resolution_date: "2026-09-20T00:00:00+00:00",
  golfers: [
    { name: "Scottie Scheffler", probability: 0.182, rank: 1, movement_24h: null },
  ],
});

const MAJOR_2027 = tournament({
  key: "golfers_to_win_a_pga_tour_major_in_2027",
  name: "Golfers To Win A Pga Tour Major In 2027",
  slug: "golfers-to-win-a-pga-tour-major-in-2027",
  tour: "pga",
  tour_label: "PGA Tour",
  venue: null,
  start_date: null,
  end_date: null,
  schedule_status: null,
  commence_time: "2028-01-14T15:00:00+00:00",
  resolution_date: "2028-01-14T15:00:00+00:00",
  golfers: [
    { name: "Scottie Scheffler", probability: 0.059, rank: 1, movement_24h: null },
  ],
});

const MAJOR_2030 = tournament({
  key: "golfers_to_win_a_pga_tour_major_before_2030",
  name: "Golfers To Win A Pga Tour Major Before 2030",
  slug: "golfers-to-win-a-pga-tour-major-before-2030",
  tour: "pga",
  tour_label: "PGA Tour",
  venue: null,
  start_date: null,
  end_date: null,
  schedule_status: null,
  commence_time: "2026-07-19T18:17:17+00:00",
  resolution_date: "2030-07-07T14:00:00+00:00",
  golfers: [{ name: "Miles Russell", probability: 0.032, rank: 1, movement_24h: null }],
});

const LIVE_SLATE = [OMEGA, BILTMORE, MAJOR_2027, MAJOR_2030];

function render(data: FeedTournamentData): string {
  return renderToStaticMarkup(
    <TournamentCard data={data} liked={false} setLiked={() => {}} />,
  );
}

/**
 * The timing line as the READER sees it, cut out of the rendered card.
 *
 * Read off the rendered markup and not off the helper, because the helper is one
 * transform upstream of the user: the card decides in its own `whatHit` branch
 * whether to print the line at all, and a guard that stops short of the markup
 * is green on a card that renders nothing (ux/1006's finding, twice).
 */
function timingLine(html: string): string {
  const m = /<p class="text-xs text-text-muted mt-0\.5">([^<]*)<\/p>/.exec(html);
  return m ? m[1] : "";
}

describe("#2549 — the card stops saying a tournament started before it starts", () => {
  test("THE DEFECT: Omega European Masters starts Sep 3, and the card says so", () => {
    const line = timingLine(render(OMEGA));
    // The backend computed `headline: "Tomorrow"` off the same `start_date`; the
    // card now agrees with it instead of contradicting it.
    expect(line).toBe("Starts tomorrow");
    // Both directions, in the reader's words rather than by implication: the
    // false claim is gone and the true one is present.
    expect(line).not.toContain("Started");
    expect(line).not.toContain("Aug 31");
  });

  test("the whole live slate, card by card", () => {
    expect(LIVE_SLATE.map((t) => timingLine(render(t)))).toEqual([
      "Starts tomorrow", // omega     — WAS "Started Mon, Aug 31"
      "Starts Thu, Sep 17", // biltmore  — unchanged
      "Resolves Jan 14, 2028", // major_2027 — unchanged (+365d window)
      "Resolves Jul 7, 2030", // major_2030 — unchanged (-7d window)
    ]);
  });

  test("exactly ONE card on the live slate moves", () => {
    // The fix's blast radius, asserted as a number rather than described. Every
    // row whose `start_date` is absent or agrees with `commence_time` must render
    // byte-identically to what the fallback alone would produce.
    const moved = LIVE_SLATE.filter(
      (t) =>
        formatTournamentTimingLabel(
          t.start_date,
          t.commence_time,
          t.resolution_date,
          NOW_T,
        ) !==
        formatTournamentTimingLabel(null, t.commence_time, t.resolution_date, NOW_T),
    );
    expect(moved.map((t) => t.key)).toEqual(["omega_european_masters"]);
  });
});

describe("controls — green on main too", () => {
  test("biltmore: start_date agrees with commence_time, so the string cannot move", () => {
    // The agree-control. It proves the schedule taking priority is not a restyle:
    // when the two sources say the same day, the reader sees the same words.
    expect(timingLine(render(BILTMORE))).toBe("Starts Thu, Sep 17");
  });

  test("major_2027: no start_date, so the +365d fallback window still fires", () => {
    expect(timingLine(render(MAJOR_2027))).toBe("Resolves Jan 14, 2028");
  });

  test("major_2030: no start_date, so the -7d fallback window still fires", () => {
    expect(timingLine(render(MAJOR_2030))).toBe("Resolves Jul 7, 2030");
  });

  test("a settled marquee still leads with its champion and prints no date", () => {
    const html = render({ ...OMEGA, marquee_whathit: true } as FeedTournamentData);
    expect(timingLine(html)).toBe("");
    expect(html).toContain("Champion");
  });

  test("the venue and leader are untouched", () => {
    const html = render(OMEGA);
    expect(html).toContain("Crans-sur-Sierre GC");
    expect(html).toContain("Ryan Gerard");
  });
});

describe("the construction — why this cannot be wrong in another timezone", () => {
  /**
   * These are the claims that stand IN PLACE OF a zone-sensitivity test, which
   * this harness cannot run (TZ is pinned to UTC suite-wide). They assert the
   * property that makes the zone bug unrepresentable, not an instance of it.
   */
  test("a UTC-midnight start_date renders its OWN declared day", () => {
    // The C270 P1 shape: `2026-09-10T00:00:00+00:00` is a calendar date wearing a
    // timestamp. A local render of it lands on Sep 9 west of UTC. Deliberately
    // more than a day out, so the ABSOLUTE format path is the one under test —
    // inside +/-1d the relative words would answer without formatting anything.
    expect(formatDeclaredStartLabel("2026-09-10T00:00:00+00:00", NOW_T)).toBe(
      "Starts Thu, Sep 10",
    );
  });

  test("the declared day is read from the STRING, not from an instant", () => {
    // Same calendar day declared under three different offsets. A `Date`-based
    // reading would place these on three different UTC instants and could render
    // three different days; a string reading cannot. This is the property, and
    // it holds regardless of the zone the suite runs in.
    const labels = [
      "2026-09-10T00:00:00+00:00",
      "2026-09-10T00:00:00-07:00",
      "2026-09-10T23:59:59+14:00",
    ].map((s) => formatDeclaredStartLabel(s, NOW_T));
    expect(new Set(labels).size).toBe(1);
    expect(labels[0]).toBe("Starts Thu, Sep 10");
  });

  test("a date-only start_date works too, and agrees with the timestamp form", () => {
    expect(formatDeclaredStartLabel("2026-09-10", NOW_T)).toBe(
      formatDeclaredStartLabel("2026-09-10T00:00:00+00:00", NOW_T),
    );
    expect(formatDeclaredStartLabel("2026-09-10", NOW_T)).toBe("Starts Thu, Sep 10");
  });

  test("relative words are measured against the READER's calendar day", () => {
    expect(formatDeclaredStartLabel("2026-09-02T00:00:00+00:00", NOW_T)).toBe(
      "Starts today",
    );
    expect(formatDeclaredStartLabel("2026-09-03T00:00:00+00:00", NOW_T)).toBe(
      "Starts tomorrow",
    );
    expect(formatDeclaredStartLabel("2026-09-01T00:00:00+00:00", NOW_T)).toBe(
      "Started yesterday",
    );
  });

  test("a start in another year carries the year", () => {
    expect(formatDeclaredStartLabel("2027-04-08T00:00:00+00:00", NOW_T)).toBe(
      "Starts Thu, Apr 8, 2027",
    );
  });

  test("an in-progress tournament honestly says it started, with no staleness window", () => {
    // The fallback suppresses anything older than 7 days because a market
    // timestamp that stale is not a start date. A SCHEDULE that old is still a
    // schedule, and silence here would re-open the gap #1700 set out to close.
    expect(formatDeclaredStartLabel("2026-08-23T00:00:00+00:00", NOW_T)).toBe(
      "Started Sun, Aug 23",
    );
  });

  test("garbage and impossible dates say nothing and let the fallback run", () => {
    expect(formatDeclaredStartLabel(null, NOW_T)).toBe("");
    expect(formatDeclaredStartLabel("", NOW_T)).toBe("");
    expect(formatDeclaredStartLabel("not a date", NOW_T)).toBe("");
    // `Date.UTC` rolls this over to Mar 3; printing a day the wire never declared
    // is the exact defect this function exists to remove.
    expect(formatDeclaredStartLabel("2026-02-31T00:00:00+00:00", NOW_T)).toBe("");
    // …and the card falls through to the fallback rather than going silent.
    expect(
      formatTournamentTimingLabel(
        "2026-02-31T00:00:00+00:00",
        "2026-09-17T00:00:00+00:00",
        null,
        NOW_T,
      ),
    ).toBe("Starts Thu, Sep 17");
  });
});

describe("the parameter stays required", () => {
  /**
   * ux/1010's lesson, encoded: a `startDate = null` default would keep every call
   * site compiling while letting the next one silently re-acquire #2549 with the
   * suite still green. There is one production call site, so required is free.
   */
  test("formatTournamentTimingLabel declares four parameters, startDate first", () => {
    // `Function.length` counts parameters BEFORE the first defaulted one, so this
    // is 3 while `now` has its default — and it drops to 2 the moment anyone
    // gives `startDate` a default, which is the regression being pinned.
    expect(formatTournamentTimingLabel.length).toBe(3);
    expect(/^function[^(]*\(\s*startDate\b/.test(formatTournamentTimingLabel.toString()))
      .toBe(true);
  });

  test("the counter-case: a function that ignores startDate fails this suite", () => {
    // Without this arm, deleting the new branch entirely would leave the
    // controls green and only the defect arms red — which reads as "one test is
    // broken" rather than "the ship is gone".
    const ignoresIt = (
      _s: string | null,
      c: string | null,
      r: string | null,
      n: number,
    ) => formatTournamentTimingLabel(null, c, r, n);
    expect(
      ignoresIt(OMEGA.start_date!, OMEGA.commence_time!, OMEGA.resolution_date!, NOW_T),
    ).toBe("Started Mon, Aug 31");
    expect(
      formatTournamentTimingLabel(
        OMEGA.start_date,
        OMEGA.commence_time,
        OMEGA.resolution_date,
        NOW_T,
      ),
    ).not.toBe("Started Mon, Aug 31");
  });
});
