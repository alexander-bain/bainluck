/**
 * ux/1096 / #3028 — WHAT THE LEAGUE PAGE ACTUALLY RENDERS WHEN ITS LEAGUE IS DORMANT.
 *
 * `/sports/basketball_nba`, 2026-09-06, whole page above the fold:
 *
 *     No games
 *     This page lists games for this league.
 *
 * with 8 upcoming games and 94 markets sitting behind `/api/leagues`. The page
 * asked for 14 days; NBA's first game is 44 days out.
 *
 * ═══ HOW EACH ARM IS READ, AND WHY NOT OFF THE NEW ATTRIBUTE ═══
 *
 * 🔴 THE LOAD-BEARING PARAGRAPH. The obvious extractor counts
 * `[data-league-horizon="widened"]` — an attribute THIS DIFF ADDS — so on the
 * parent it matches nothing and any `[].every(...)` over it is vacuously true.
 * Every arm that claims GAMES ARE ON THE PAGE therefore reads `href="/events/{id}"`
 * instead: `EventCard` has rendered that since long before this diff, so the
 * ordered list of ids in the markup is an arm-independent reading of exactly
 * what a reader scrolls past. Only `the widened page says so` reads the new
 * attribute, and it is labelled as part of the ship.
 *
 * ═══ THE CONTROLS PASS ON BOTH SIDES OF THE CHANGE ═══
 *
 * ⚠️ ux/1093 shipped a dead control — it asserted the new field, so it failed on
 * the parent like every real arm and proved nothing. The two controls here
 * (`the in-season league is untouched` and `a failed widen still renders what
 * the near-term window found`) assert only behaviour the parent already has,
 * and were run against the parent to confirm they pass there.
 *
 * ═══ THE REQUEST LEDGER IS THE POINT OF THE MIRROR ARM ═══
 *
 * The damaging regression is an in-season league widening to 90 days (NFL:
 * 17 games at `days=14`, **120** at `days=60`). "The page still looks right"
 * cannot catch that — the page would be full of football either way. So the
 * SWR mock records every key it is asked for, and the mirror arm asserts the
 * second key was never requested at all.
 *
 * ═══ THE CLOCK ═══
 *
 * Fixtures are offsets from one pinned anchor, and the anchor is set at MODULE
 * SCOPE rather than in `beforeAll` — `leaguePageSections2948.test.tsx` records
 * that renders in a describe body run during collection, before any hook, and
 * a hook-pinned clock left exactly those on the real time.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const NOW = new Date("2026-09-06T12:00:00Z").getTime();
const DAY = 24 * 60 * 60 * 1000;

jest.useFakeTimers({ now: NOW, doNotFake: ["nextTick"] });
afterAll(() => {
  jest.useRealTimers();
});

type Row = {
  id: number;
  sport: string;
  home_team: string;
  away_team: string;
  commence_time: string;
  status: string;
};

function game(id: number, offsetMs: number, status = "scheduled"): Row {
  return {
    id,
    sport: "basketball_nba",
    home_team: `Home ${id}`,
    away_team: `Away ${id}`,
    commence_time: new Date(NOW + offsetMs).toISOString(),
    status,
  };
}

/** Games `dayOffsets` days out, ids 100, 101, … in order. */
function schedule(dayOffsets: number[]): Row[] {
  return dayOffsets.map((d, i) => game(100 + i, d * DAY));
}

// ── The SWR seam ──────────────────────────────────────────────────────────
//
// The page issues two distinct keys: `["events", sportKey]` for the fixed
// window and `["events", sportKey, 90]` for the widened one. The mock answers
// them separately and RECORDS them, because "the widened request was never
// made" is an assertion no rendered markup can carry.

type Response = { data?: unknown; error?: unknown; isLoading?: boolean };

let nearTerm: Response;
let widened: Response;
let requestedKeys: unknown[][];

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    // A null key is SWR's "do not fetch". It must not be recorded, or the
    // mirror arm would see the widened key on every page.
    if (key === null || key === undefined) {
      return { data: undefined, error: undefined, isLoading: false, mutate: () => {} };
    }
    const parts = Array.isArray(key) ? key : [key];
    requestedKeys.push(parts as unknown[]);
    if (parts[0] === "sports") {
      return {
        data: { sports: [{ key: "basketball_nba", name: "NBA", group: "Basketball" }] },
      };
    }
    const source = parts.length > 2 ? widened : nearTerm;
    return {
      data: source.data,
      error: source.error,
      isLoading: source.isLoading ?? false,
      mutate: () => {},
    };
  },
}));

jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  useAnalytics: () => ({ trackEventCardClick: () => undefined }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const SportPage = require("@/app/sports/[key]/page").default;

/** No defaults — both windows are always stated by the arm that renders. */
function render(near: Response, wide: Response): string {
  nearTerm = near;
  widened = wide;
  requestedKeys = [];
  return renderToStaticMarkup(
    React.createElement(SportPage, { params: { key: "basketball_nba" } }),
  );
}

/** The ids a reader can actually click, in markup order. */
function renderedEventIds(html: string): number[] {
  return [...html.matchAll(/href="\/events\/(\d+)"/g)].map((m) => Number(m[1]));
}

/**
 * The empty state, read off the anchor UX-P221 gave it — NOT off the string
 * "No games". `data-empty-state-name` predates this diff, so the reading is
 * arm-independent, and it cannot be fooled by prose elsewhere on the page that
 * happens to contain the same words.
 */
function rendersEmptyState(html: string): boolean {
  return html.includes('data-empty-state-name="league-no-upcoming-events"');
}

function widenedWasRequested(): boolean {
  return requestedKeys.some((k) => k[0] === "events" && k.length > 2);
}

describe("#3028 — the dormant league stops saying 'No games'", () => {
  test("the NBA page as filed: 0 in the window, 36 held, and the reader sees the 36", () => {
    const html = render({ data: { events: [] } }, { data: { events: schedule([44, 45, 46]) } });

    expect(rendersEmptyState(html)).toBe(false);
    expect(renderedEventIds(html)).toEqual([100, 101, 102]);
  });

  test("the NHL page as re-measured: 1 game at day 13 does not count as fixed", () => {
    // 🔴 THE ARM THAT SEPARATES THIS FIX FROM "ADD A FEW DAYS". The page is not
    // empty here — the parent renders one card and reads as working — but we
    // hold 32 games and the reader can reach one.
    const html = render(
      { data: { events: schedule([13]) } },
      { data: { events: schedule([13, 23, 34]) } },
    );

    expect(renderedEventIds(html)).toEqual([100, 101, 102]);
  });

  test("the widened page says so, in a line that states only what was measured", () => {
    // Part of the ship: this reads the attribute the diff adds. Its value is
    // that the copy is pinned, not that it exists.
    const html = render({ data: { events: [] } }, { data: { events: schedule([44]) } });

    expect(html).toContain('data-league-horizon="widened"');
    expect(html.replace(/\s+/g, " ")).toContain(
      "Nothing scheduled in the next week — showing every upcoming game we hold.",
    );
    // It must not open with the dead page's own first line — see the comment
    // at the notice in `app/sports/[key]/page.tsx`.
    expect(html).not.toContain("No games in the next week");
  });

  test("'No games' never flashes underneath a widened request that is still in flight", () => {
    const html = render(
      { data: { events: [] } },
      { data: undefined, isLoading: true },
    );

    expect(rendersEmptyState(html)).toBe(false);
    expect(html).toContain("Loading events...");
  });

  test("a league we genuinely hold nothing for still says so", () => {
    // The empty state is not being deleted — a league with no schedule at any
    // horizon must still tell the reader that, and must not claim a widened
    // window found something.
    const html = render({ data: { events: [] } }, { data: { events: [] } });

    expect(rendersEmptyState(html)).toBe(true);
    expect(html).not.toContain('data-league-horizon="widened"');
  });
});

describe("#3028 — the mirror: an in-season league is untouched", () => {
  test("CONTROL (passes on both arms) — this Sunday's slate renders, in order", () => {
    const html = render({ data: { events: schedule([0.25, 1, 3]) } }, { data: undefined });

    expect(renderedEventIds(html)).toEqual([100, 101, 102]);
    expect(rendersEmptyState(html)).toBe(false);
  });

  test("the widened request is never issued, so the season cannot bury the week", () => {
    // 🔴 THE REGRESSION ARM. NFL measured 17 games at `days=14` and 120 at
    // `days=60`; nothing in the markup would distinguish those two pages at a
    // glance, so the claim is made against the request ledger.
    render({ data: { events: schedule([0.25, 1, 3]) } }, { data: { events: schedule([0.25, 60]) } });

    expect(widenedWasRequested()).toBe(false);
  });

  test("a live game holds the fixed window open even with nothing else soon", () => {
    const html = render(
      { data: { events: [game(100, -30 * 60 * 1000, "live"), game(101, 30 * DAY)] } },
      { data: { events: schedule([30, 40, 50]) } },
    );

    expect(widenedWasRequested()).toBe(false);
    expect(renderedEventIds(html)).toEqual([100, 101]);
  });

  test("the widened request is not issued before the first window has answered", () => {
    // An undefined payload reads as an empty array. Without the `Boolean(eventsData)`
    // gate, every in-season page would fire the 90-day request during its own
    // first paint and then throw the result away.
    render({ data: undefined, isLoading: true }, { data: { events: schedule([44]) } });

    expect(widenedWasRequested()).toBe(false);
  });
});

describe("#3028 — the widened request failing is not the page failing", () => {
  test("CONTROL (passes on both arms) — the near-term window's games still render", () => {
    const html = render(
      { data: { events: schedule([13]) } },
      { data: undefined, error: new Error("boom") },
    );

    expect(renderedEventIds(html)).toEqual([100]);
    expect(rendersEmptyState(html)).toBe(false);
    expect(html).not.toContain('data-league-horizon="widened"');
  });
});
