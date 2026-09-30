/**
 * #9212 — a finished golf tournament says who won.
 *
 * WHAT THE READER SAW: `/sports` at 390px, 2026-09-27 21:27Z — under **Live Now**
 * the FedEx Open de France read **● LIVE · 100.0% Matthew Fitzpatrick · Leader
 * +17.9 pts today**, hours after the final round ended (11:27 PM in France). The
 * Presidents Cup read **● LIVE · Team USA 99.5%** with ESPN already calling it
 * final. The calendar window was the only test, so the card could not be over
 * before midnight UTC — and once the window closed, the section's `else` would
 * have filed the champion under Upcoming.
 *
 * The decided signal is served (live's PR #9235): `champion`, ESPN's winner once
 * ESPN says STATUS_FINAL, spelled as the card's own golfer row. The payload
 * shapes below are that contract (`backend/tests/test_golf_champion_9212.py`).
 * Every block pairs the specimen with `champion: null`, which must decide exactly
 * as before.
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
import { groupFeedIntoSections } from "@/lib/feedSections";
import { championRowIndex, isTournamentDecided, isTournamentLive } from "@/lib/tournamentLive";
import type { FeedItem, FeedTournamentData, GolfTournament } from "@/lib/types";

/** 21:27Z on the final day — inside the calendar window, which runs to 00:00Z. */
const NOW = "2026-09-27T21:27:00Z";

function at<T>(fn: () => T): T {
  jest.useFakeTimers({ now: new Date(NOW) });
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

function frenchOpen(champion: string | null): GolfTournament {
  return {
    key: "fedex_open_de_france",
    name: "FedEx Open de France",
    is_major: false,
    tour: "euro",
    tour_label: "DP World Tour",
    commence_time: null,
    resolution_date: null,
    start_date: "2026-09-24T00:00:00+00:00",
    end_date: "2026-09-27T00:00:00+00:00",
    schedule_status: "upcoming",
    market_ids: [1],
    champion,
    golfers: [
      golfer("Matthew Fitzpatrick", 1.0, 0.179),
      golfer("Adrien Dumont de Chassart", 0.006),
      golfer("Jayden Schaper", 0.004),
      golfer("Kristoffer Reitan", 0.003),
      golfer("Kiradech Aphibarnrat", 0.001),
    ],
  };
}

function presidentsCup(champion: string | null): GolfTournament {
  return {
    key: "presidents_cup",
    name: "Presidents Cup",
    is_major: false,
    commence_time: null,
    resolution_date: null,
    start_date: "2026-09-24T00:00:00+00:00",
    end_date: "2026-09-27T00:00:00+00:00",
    schedule_status: "in-progress",
    market_ids: [2],
    champion,
    golfers: [golfer("Team USA", 0.995), golfer("Team International", 0.01)],
  };
}

const card = (t: GolfTournament) => at(() => renderToStaticMarkup(<TournamentCard tournament={t} />));
const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();

describe("#9212 — the card leads with the champion", () => {
  it("the specimen: Final + Fitzpatrick Won/Champion; no LIVE, no Leader, no move", () => {
    const t = text(card(frenchOpen("Matthew Fitzpatrick")));
    expect(t).toContain("Final");
    expect(t).toMatch(/Matthew Fitzpatrick Won/);
    expect(t).toContain("Champion");
    expect(t).not.toContain("LIVE");
    expect(t).not.toContain("Leader");
    expect(t).not.toContain("pts today");
  });

  it("control: champion null keeps today's card — LIVE, Leader, the move", () => {
    const t = text(card(frenchOpen(null)));
    expect(t).toContain("LIVE");
    expect(t).toContain("Leader");
    expect(t).toContain("+17.9 pts today");
    expect(t).not.toContain("Champion");
  });

  it("the hero is the CHAMPION's row, not the price leader's", () => {
    const t = text(card(frenchOpen("Jayden Schaper")));
    expect(t).toMatch(/0\.4 % Jayden Schaper Won/);
    // …and the price leader drops to the chasers strip (last name only).
    expect(t).toContain("Fitzpatrick 100.0%");
    expect(t).not.toMatch(/Schaper 0\.4%/);
  });

  it("a champion with no row of its own is named without a borrowed number", () => {
    const t = text(card(frenchOpen("Somebody Else")));
    expect(t).toMatch(/Somebody Else Won/);
    expect(t).not.toMatch(/100\.0 % Somebody Else/);
    expect(t).not.toContain("Leader");
  });
});

describe("#9212 — the cup card", () => {
  it("ESPN's 'USA' crowns 'Team USA': Final, Won, no LIVE", () => {
    const t = text(card(presidentsCup("USA")));
    expect(t).toContain("Final");
    expect(t).toMatch(/Team USA Won/);
    expect(t).not.toMatch(/Won Team International/);
    expect(t).not.toContain("LIVE");
  });

  it("control: champion null keeps the LIVE cup card, nobody crowned", () => {
    const t = text(card(presidentsCup(null)));
    expect(t).toContain("LIVE");
    expect(t).not.toContain("Won");
    expect(t).not.toContain("Final");
  });

  it("a champion matching neither side is Final with no side crowned", () => {
    const t = text(card(presidentsCup("Europe")));
    expect(t).toContain("Final");
    expect(t).not.toContain("Won");
  });
});

function feedItem(t: GolfTournament, extra: Partial<FeedTournamentData> = {}): FeedItem {
  const { golfers, ...rest } = t;
  const data: FeedTournamentData = {
    ...rest,
    golfers: golfers.map((g) => ({ name: g.name, probability: g.probability, rank: g.rank, movement_24h: g.movement_24h })),
    source_count: 1,
    ...extra,
  } as FeedTournamentData;
  return { type: "tournament", data } as unknown as FeedItem;
}

const sectionOf = (item: FeedItem) =>
  at(() => groupFeedIntoSections([item]).map((s) => s.key));

describe("#9212 — the section files a decided tournament with the results", () => {
  it("champion ⇒ Just Happened, not Live Now", () => {
    expect(sectionOf(feedItem(frenchOpen("Matthew Fitzpatrick")))).toEqual(["finished"]);
  });

  it("control: champion null inside the window ⇒ Live Now, as before", () => {
    expect(sectionOf(feedItem(frenchOpen(null)))).toEqual(["live"]);
  });

  it("a marquee in its WHAT-HIT window is a result too, not Live Now or Upcoming", () => {
    expect(sectionOf(feedItem(frenchOpen(null), { marquee_whathit: true }))).toEqual(["finished"]);
  });

  it("a payload with no champion key at all decides exactly as null", () => {
    const item = feedItem(frenchOpen(null));
    delete (item.data as Partial<FeedTournamentData>).champion;
    expect(sectionOf(item)).toEqual(["live"]);
  });
});

describe("#9212 — the deciders", () => {
  it("isTournamentLive: a champion vetoes the window; null does not", () => {
    at(() => {
      expect(isTournamentLive(frenchOpen("Matthew Fitzpatrick"))).toBe(false);
      expect(isTournamentLive(frenchOpen(null))).toBe(true);
    });
  });

  it("isTournamentDecided reads the served signals only — never a 100% price", () => {
    expect(isTournamentDecided({ champion: "X" })).toBe(true);
    expect(isTournamentDecided({ marquee_whathit: true })).toBe(true);
    expect(isTournamentDecided({ champion: null, marquee_whathit: false })).toBe(false);
    expect(isTournamentDecided(frenchOpen(null) as never)).toBe(false);
  });

  it("championRowIndex folds accents and case, and misses loudly", () => {
    const rows = [{ name: "Ludvig Åberg" }, { name: "Matthew Fitzpatrick" }];
    expect(championRowIndex(rows, "ludvig aberg")).toBe(0);
    expect(championRowIndex(rows, "Matthew  Fitzpatrick")).toBe(1);
    expect(championRowIndex(rows, "Matt Fitzpatrick")).toBe(-1);
    expect(championRowIndex(rows, null)).toBe(-1);
    expect(championRowIndex(rows, "")).toBe(-1);
  });
});
