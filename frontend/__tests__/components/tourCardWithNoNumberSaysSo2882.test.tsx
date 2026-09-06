/**
 * #2882 — a tour/league card with NO probability says so, instead of printing
 * two dashes, an empty bar, and a favourite it never measured.
 *
 * WHAT A READER SAW. `https://bainluck.com/sport/tennis/wta`, 390px,
 * 2026-09-06 11:20Z, during the US Open. `GET /api/leagues/tennis_wta` returned
 * FOUR upcoming games and every one of them had `home_win_probability: null`
 * AND `away_win_probability: null`:
 *
 *   15305552  Bondar / Kalinina      v Routliffe / Sutjiadi   null / null
 *   15305555  Siniakova / Townsend   v Hunter / Krawczyk      null / null
 *   15305768  Osaka                  v Rybakina               null / null
 *   15305770  Perez / Schuurs        v Mertens / Shnaider     null / null
 *
 * The rail rendered four full-width cards in the ordinary chrome, each printing
 * `-` where the number goes, an empty grey bar between the two names, and the
 * HOME side in `text-text-primary` against the away side in
 * `text-text-secondary` — the card naming a favourite off a coin it never
 * flipped. The issue was filed at 1 card of 6; it is now the whole rail.
 *
 * THE RULE IS NOT NEW. #3459 settled it this morning for the event hero and the
 * play card: when NEITHER side has a number, say it in words. This is that rule
 * reaching the third surface, in the same words, so the three cannot drift.
 * `AnimatedProbability` renders `-` per side and has no notion of both sides
 * being absent — correct for ONE absent side, which is the ordinary shape (the
 * envelope derives away from home, so a lone null is normal) and which arm 6
 * pins unchanged.
 *
 * WHY THE ARMS ARE ON THE RAIL AND NOT ONLY THE CARD. #2882 asked for the class
 * to be asserted "on the rail, not on the one event that exposed it, because
 * the next such row will be a different sport". Arms 1-3 render
 * `LeagueGameRail` end-to-end through `leagueGameToEvent`, so a future rail that
 * forks the card, or an envelope mapping that starts stamping a 0, fails here.
 *
 * BOTH DIRECTIONS, PER GOTCHA #43. Every "says so" arm has a control that a
 * PRICED card is untouched — otherwise a card that printed no chips at all, or
 * a rail that dropped unpriced games entirely, would pass the headline
 * assertion. Arm 3 is the mixed rail, which is the one a blanket suppression
 * cannot fake.
 *
 * ARMS 9-11 are the crest, found on the same LOOK and fixed in the same card:
 * the inline initialism counted the pair separator as a word, so a doubles
 * crest read "S/" — one initial and a dangling slash.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));
jest.mock("../../hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import EventCard from "@/components/EventCard";
import LeagueGameRail from "@/components/LeagueGameRail";
import { teamCrestInitials } from "@/lib/teamShortName";
import type { LeagueGameBrief } from "@/lib/api";
import type { Event } from "@/lib/types";

const IN_THE_FUTURE = new Date(Date.now() + 3 * 3600_000).toISOString();
const IN_THE_PAST = new Date(Date.now() - 3 * 3600_000).toISOString();

/** The production specimen: an unpriced US Open doubles fixture on the WTA rail. */
function unpricedGame(over: Partial<LeagueGameBrief> = {}): LeagueGameBrief {
  return {
    id: 15305555,
    home_team: "Siniakova / Townsend",
    away_team: "Hunter / Krawczyk",
    commence_time: IN_THE_FUTURE,
    status: "scheduled",
    home_score: null,
    away_score: null,
    home_win_probability: null,
    away_win_probability: null,
    sport: "tennis_wta",
    ...over,
  } as unknown as LeagueGameBrief;
}

/** Its priced neighbour, so every absence assertion has a presence beside it. */
function pricedGame(over: Partial<LeagueGameBrief> = {}): LeagueGameBrief {
  return unpricedGame({ id: 15301130, home_win_probability: 0.62, ...over });
}

function rail(games: LeagueGameBrief[]): string {
  return renderToStaticMarkup(
    <LeagueGameRail title="Upcoming Games" games={games} />,
  );
}

function card(over: Partial<Event> = {}): string {
  const event = {
    id: 15305555,
    external_id: null,
    sport: "tennis_wta",
    sport_name: "WTA Tour",
    home_team: "Siniakova / Townsend",
    away_team: "Hunter / Krawczyk",
    commence_time: IN_THE_FUTURE,
    status: "scheduled",
    home_score: null,
    away_score: null,
    home_team_data: { primary_color: "#2563eb" },
    away_team_data: { primary_color: "#64748b" },
    ...over,
  } as unknown as Event;
  return renderToStaticMarkup(<EventCard event={event} />);
}

/** Priced `current_odds`, the shape `leagueGameToEvent` builds. */
const PRICED_ODDS = {
  captured_at: IN_THE_PAST,
  home_probability: 0.62,
  away_probability: 0.38,
  spread: null,
  over_under: null,
  projected_home_score: null,
  projected_away_score: null,
};

/** Every whole percent the markup actually prints, in document order. */
function printedPercents(html: string): number[] {
  return Array.from(html.replace(/<[^>]*>/g, " ").matchAll(/(\d+)%/g)).map(m =>
    Number(m[1]),
  );
}

/** The visible text, tags stripped, whitespace collapsed. */
function text(html: string): string {
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

describe("#2882 — the rail's unpriced card says so", () => {
  test("ARM 1: an unpriced game renders the sentence and prints no number", () => {
    // THE BUG. Before the fix this rail printed two `-` chips and an empty bar.
    const html = rail([unpricedGame()]);
    expect(html).toContain("No price yet");
    expect(printedPercents(html)).toEqual([]);
  });

  test("ARM 1b: the card is still ON the rail, with both competitors named", () => {
    // "Fixed" must not mean the reader loses the fixture. #2882 offered dropping
    // the card as one option; the product rule #3459 settled is to keep it and
    // say the absence, so the reader still learns the match exists and when.
    const t = text(rail([unpricedGame()]));
    expect(t).toContain("Siniakova / Townsend");
    expect(t).toContain("Hunter / Krawczyk");
  });

  test("ARM 2 (CONTROL): a PRICED game on the same rail is untouched", () => {
    // Without this, a change that suppressed every chip would pass ARM 1.
    const html = rail([pricedGame()]);
    expect(html).not.toContain("No price yet");
    expect(printedPercents(html)).toEqual([62, 38]);
  });

  test("ARM 3 (CONTROL): a MIXED rail keeps the priced numbers and says it once", () => {
    // The arm a blanket suppression cannot fake, and the arm a "drop the
    // unpriced card" fix cannot fake either: two cards, one pair of numbers,
    // one sentence.
    const html = rail([pricedGame(), unpricedGame()]);
    expect(printedPercents(html)).toEqual([62, 38]);
    expect(text(html).match(/No price yet/g)).toHaveLength(1);
  });
});

describe("#2882 — with no reading there is no favourite", () => {
  test("ARM 4: neither side is emphasised over the other", () => {
    // `(homeProb ?? 0) >= (awayProb ?? 0)` is `0 >= 0` when both are absent, so
    // the home side was drawn as the favourite on every unpriced card.
    const html = card();
    expect(html).not.toContain("text-text-secondary");
    expect(html.match(/text-text-primary/g)?.length).toBeGreaterThanOrEqual(2);
  });

  test("ARM 5 (CONTROL): a priced card still emphasises its favourite", () => {
    // Proves ARM 4 removed the claim only where there is nothing behind it,
    // rather than deleting the emphasis rule.
    const html = card({ current_odds: PRICED_ODDS } as Partial<Event>);
    expect(html).toContain("text-text-secondary");
    expect(html).toContain("text-text-primary");
  });
});

describe("#2882 — the scope bounds", () => {
  test("ARM 6 (CONTROL): ONE absent side still prints the pair, no sentence", () => {
    // A lone null is the ordinary shape on this envelope, and `-` beside a real
    // number reads as the comparison it is. Only the both-null case changes.
    const html = card({
      current_odds: { ...PRICED_ODDS, away_probability: null },
    } as unknown as Partial<Event>);
    expect(html).not.toContain("No price yet");
    expect(printedPercents(html)).toContain(62);
  });

  test("ARM 7 (CONTROL): a FINISHED card with no price says nothing extra", () => {
    // The settled score block is that card's whole statement; adding this line
    // under it would be the card saying two things about one absence.
    const html = card({
      status: "completed",
      commence_time: IN_THE_PAST,
      home_score: 2,
      away_score: 1,
    } as unknown as Partial<Event>);
    expect(html).not.toContain("No price yet");
  });

  test("ARM 8 (CONTROL): an unreported card with no price says nothing extra", () => {
    // `hasNoReportedResult` — a scheduled row hours past its own start (#3211).
    // Its "no result reported" summary is likewise the whole statement.
    const html = card({ commence_time: IN_THE_PAST } as unknown as Partial<Event>);
    expect(html).not.toContain("No price yet");
  });
});

describe("#2882's neighbour — a pair crest names both players", () => {
  test("ARM 9: a doubles pair keeps both initials", () => {
    // THE BUG: "Siniakova / Townsend" made the initials S, /, T and the
    // two-character cap cut it to "S/".
    expect(teamCrestInitials("Siniakova / Townsend")).toBe("S/T");
    expect(teamCrestInitials("Bondar / Kalinina")).toBe("B/K");
    expect(teamCrestInitials("Maria Buculei / Nemcsek")).toBe("M/N");
  });

  test("ARM 10 (CONTROL): every non-pair name shortens exactly as before", () => {
    expect(teamCrestInitials("Osaka")).toBe("O");
    expect(teamCrestInitials("Boston Celtics")).toBe("BC");
    expect(teamCrestInitials("Scranton/Wilkes-Barre RailRiders")).toBe("SR");
    expect(teamCrestInitials("Bodo/Glimt")).toBe("B");
    expect(teamCrestInitials("")).toBe("");
    expect(teamCrestInitials(null)).toBe("");
  });

  test("ARM 11: the rendered crest square carries the pair, not half of it", () => {
    // Rendered, not grepped: the card has to actually reach the fallback (no
    // logo, no flag) for the reader to see this at all.
    const t = text(card());
    expect(t).toContain("S/T");
    expect(t).toContain("H/K");
  });
});
