/**
 * #9378 — a golf tournament that has not started calls its rank-1 row the
 * "Favorite", not the "Leader".
 *
 * WHAT THE READER SAW: `/sports` at 390px, 2026-09-28 13:15Z — the Alfred
 * Dunhill Links Championship card read `DP World Tour Oct 1–4` and then
 * **11.8% Ludvig Aberg · Leader**, three days before the first tee shot. In golf
 * "Leader" is the top of the leaderboard; before the start the rank-1 row is the
 * price favourite. The payload below is the served item (`/api/feed?mode=sports`,
 * same read): `schedule_status: "upcoming"`, `start_date` Oct 1, `champion: null`.
 *
 * Every block pairs the pre-start frame with a frame the fix must NOT touch:
 * in progress (Leader), decided (Champion), no `start_date` (Leader, as before).
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
import { isTournamentBeforeStart } from "@/lib/tournamentLive";
import type { GolfTournament } from "@/lib/types";

/** The shop frame: Monday before a Thursday start. */
const BEFORE = "2026-09-28T13:15:00Z";
/** Round 1 under way at St Andrews. */
const DURING = "2026-10-01T11:00:00Z";

function at<T>(now: string, fn: () => T): T {
  jest.useFakeTimers({ now: new Date(now) });
  try {
    return fn();
  } finally {
    jest.useRealTimers();
  }
}

const golfer = (name: string, probability: number, movement_24h: number | null = null) => ({
  name,
  probability,
  rank: 0,
  movement_24h,
  american_odds: null,
  opening_probability: null,
  sources: {},
});

function dunhill(over: Partial<GolfTournament> = {}): GolfTournament {
  return {
    key: "alfred_dunhill_links_championship",
    name: "Alfred Dunhill Links Championship",
    is_major: false,
    tour: "dp_world",
    tour_label: "DP World Tour",
    commence_time: "2026-10-01T00:00:00+00:00",
    resolution_date: "2026-10-04T00:00:00+00:00",
    start_date: "2026-10-01T00:00:00+00:00",
    end_date: "2026-10-04T00:00:00+00:00",
    schedule_status: "upcoming",
    market_ids: [1],
    champion: null,
    golfers: [
      golfer("Ludvig Aberg", 0.118),
      golfer("Tommy Fleetwood", 0.101, 0.0355),
      golfer("Matt Fitzpatrick", 0.086),
      golfer("Ryan Gerard", 0.072),
      golfer("Viktor Hovland", 0.071),
    ],
    ...over,
  };
}

/** The hero caption is the word opening the caption div — read it from markup, not stripped text. */
function caption(t: GolfTournament, now: string): string | null {
  const html = at(now, () => renderToStaticMarkup(<TournamentCard tournament={t} />));
  const m = html.match(/<div class="text-xs text-text-secondary">(Favorite|Leader|Champion)/);
  return m ? m[1] : null;
}

describe("#9378 — the hero caption before, during and after a tournament", () => {
  it("the specimen: three days before the start the rank-1 row is the Favorite", () => {
    expect(caption(dunhill(), BEFORE)).toBe("Favorite");
  });

  it("control: once round 1 is under way the same card says Leader", () => {
    expect(caption(dunhill(), DURING)).toBe("Leader");
  });

  it("control: a champion is still the Champion, even with a future start_date", () => {
    expect(caption(dunhill({ champion: "Ludvig Aberg" }), BEFORE)).toBe("Champion");
  });

  it("control: no start_date keeps the old caption (not known to be before the start)", () => {
    expect(caption(dunhill({ start_date: null, commence_time: null, end_date: null }), BEFORE)).toBe("Leader");
  });
});

describe("#9378 — isTournamentBeforeStart", () => {
  it("true strictly before the first day's midnight-UTC stamp, false from it on", () => {
    const t = { start_date: "2026-10-01T00:00:00+00:00" };
    expect(at("2026-09-30T23:59:59Z", () => isTournamentBeforeStart(t))).toBe(true);
    expect(at("2026-10-01T00:00:00Z", () => isTournamentBeforeStart(t))).toBe(false);
  });

  it("absent or unparseable start_date is false", () => {
    expect(at(BEFORE, () => isTournamentBeforeStart({ start_date: null }))).toBe(false);
    expect(at(BEFORE, () => isTournamentBeforeStart({}))).toBe(false);
    expect(at(BEFORE, () => isTournamentBeforeStart({ start_date: "not a date" }))).toBe(false);
  });
});
