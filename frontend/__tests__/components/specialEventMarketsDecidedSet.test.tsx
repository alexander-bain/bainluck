/**
 * ux/1103 (#3629) — A SET THAT IS OVER SAYS WHO WON IT.
 *
 * Production, 2026-09-06 18:05Z, the only live tennis match on the site holding
 * `Set N Winner` markets — Kostyuk vs Noskova on Arthur Ashe, Noskova a set up.
 * The "Additional Markets" card read:
 *
 *     Kostyuk wins Set 2      ████████░░░░  64%
 *     Kostyuk wins Set 1                    last quote 0%
 *
 * Row two is not wrong. It is a result written as a price. Set 1 finished, the
 * scoreboard banked it `0` / `1`, and the page had every fact it needed to say
 * `Noskova won Set 1` — Alex's standing *settled means settled* ruling asks
 * cards for RESULTS, and "last quote 0%" makes a reader do the inference.
 *
 * ── WHY THIS SUITE IS DIFFERENTIAL, AGAIN ────────────────────────────────────
 *
 * `decidedSetsWinner` is the THIRD optional prop threaded page → component →
 * pure module on this surface, and the first two both shipped broken exactly
 * once: #2086's `eventStatus` was declared, passed, and destructured by nobody,
 * and `specialEventMarketsLiveSet` exists because `completedSets` could have
 * gone the same way. An optional prop dropped mid-thread is invisible to tsc
 * and to a grep, so the load-bearing test renders the SAME payload with and
 * without it and requires the two markups to differ.
 *
 * ── AND WHY MOST OF IT IS ABOUT REFUSING ─────────────────────────────────────
 *
 * A frozen quote is weak. A settled row naming the WRONG player is a lie on a
 * marquee page, so `decidedSetResult` fails closed at every door it can, and
 * five of the tests below are about the doors rather than the ship.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { SETTLED_QUOTE_PREFIX } from "@/lib/settledQuote";
import {
  completedSetsForTennis,
  decidedSetsWinnerFor,
  type DecidedSetsWinner,
} from "@/lib/otherMarketGroups";
import type { GameMarketsResponse } from "@/lib/api";

/** Verbatim wire, `GET /api/events/15304906/game-markets`, 2026-09-06 18:05Z. */
const WIRE = [
  { market_name: "Set 1 Winner: Kostyuk vs Noskova", outcome_name: "No", probability: 0.999, source: "polymarket" },
  { market_name: "Set 1 Winner: Kostyuk vs Noskova", outcome_name: "Yes", probability: 0.0005, source: "polymarket" },
  { market_name: "US Open WTA: Marta Kostyuk vs Linda Noskova", outcome_name: "No", probability: 0.575, source: "polymarket" },
  { market_name: "US Open WTA: Marta Kostyuk vs Linda Noskova", outcome_name: "Yes", probability: 0.42, source: "polymarket" },
  { market_name: "Set 2 Winner: Kostyuk vs Noskova", outcome_name: "Yes", probability: 0.555, source: "polymarket" },
  { market_name: "Set 2 Winner: Kostyuk vs Noskova", outcome_name: "No", probability: 0.445, source: "polymarket" },
];

function payload(overrides: Partial<GameMarketsResponse> = {}): GameMarketsResponse {
  return {
    event_id: 15304906,
    home_team: "Marta Kostyuk",
    away_team: "Linda Noskova",
    home_score: 0,
    away_score: 1,
    status: "live",
    totals: [],
    player_props: [],
    team_totals: [],
    spreads: [],
    period_markets: [],
    matchups: [],
    other: WIRE,
    pace: null,
    ...overrides,
  } as unknown as GameMarketsResponse;
}

/** The page's own wiring, run end to end rather than hand-fed a winner. */
const renderAsPage = (data: GameMarketsResponse, sport = "tennis_wta_us_open") =>
  renderToStaticMarkup(
    <SpecialEventMarkets
      data={data}
      eventStatus={data.status}
      completedSets={completedSetsForTennis(sport, data)}
      decidedSetsWinner={decidedSetsWinnerFor(sport, data)}
    />,
  );

const renderWith = (winner: DecidedSetsWinner | null | undefined) =>
  renderToStaticMarkup(
    <SpecialEventMarkets
      data={payload()}
      eventStatus="live"
      completedSets={1}
      decidedSetsWinner={winner}
    />,
  );

/** The bar is a `<div>` whose inline width encodes the probability. */
const BAR = /style="width:\s*\d/g;

const visible = (html: string) =>
  html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&#x2F;/g, "/")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");

/**
 * The text of each result row, read off the ROW ELEMENT rather than off a
 * window of characters following its label.
 *
 * It was the window before, and the window silently depended on the decided row
 * rendering LAST on its card: once sets were ordered 1, 2, 3 instead of by
 * price (#3861), `Noskova won Set 1` was followed by the live `Kostyuk wins
 * Set 2 56%` and the scrape captured a SIBLING's percentage. `OutcomeBar`'s
 * result branch renders `outcome.result` and nothing else, so the element is
 * the honest boundary and the row's whole text can be asserted exactly.
 */
const resultRows = (html: string): string[] =>
  [...html.matchAll(/<div[^>]*data-testid="special-markets-result"[\s\S]*?<\/div><\/div>/g)].map(
    (m) => visible(m[0]).trim(),
  );

describe("a decided set states its result", () => {
  test("THE SHIP: the row names the winner, on the page's own wiring", () => {
    const text = visible(renderAsPage(payload()));
    expect(text).toContain("Noskova won Set 1");
    // The loser's name is not left standing beside it as a live-sounding claim.
    expect(text).not.toContain("Kostyuk wins Set 1");
  });

  test("no number survives on the row — not a percentage, not a last quote", () => {
    const html = renderAsPage(payload());
    // Set 2 is still being played and keeps its 56%, so the assertion has to be
    // about the decided ROW rather than about the card.
    const row = resultRows(html).find((r) => r.includes("Noskova won Set 1")) ?? "";
    expect(row).not.toMatch(/\d+%/);
    expect(row).not.toContain(SETTLED_QUOTE_PREFIX);
    // The row is the result and NOTHING else — stronger than "no number
    // nearby", and it cannot be satisfied by a row that happens to be last.
    expect(row).toBe("Noskova won Set 1");
  });

  test("the decided set LEADS the card, because sets read in order (#3861)", () => {
    // Set 1 is over and Set 2 is being played, so the card is the story of the
    // match in sequence: the result, then the live question. Under the old
    // price order the finished set sank to the bottom at 0.05% — the reader met
    // set 2 first and the completed one last, which is neither chronological
    // nor ranked by anything the page shows.
    const text = visible(renderAsPage(payload()));
    expect(text.indexOf("Noskova won Set 1")).toBeGreaterThan(-1);
    expect(text.indexOf("Kostyuk wins Set 2")).toBeGreaterThan(-1);
    expect(text.indexOf("Noskova won Set 1")).toBeLessThan(text.indexOf("Kostyuk wins Set 2"));
  });

  test("THE REGRESSION GUARD: with and without the winner must differ", () => {
    // Drop the prop anywhere page → component → module and these collapse into
    // one string. No pixel has to be named for that to red.
    expect(renderWith({ side: "away", homeTeam: "Marta Kostyuk", awayTeam: "Linda Noskova" }))
      .not.toEqual(renderWith(undefined));
  });

  test("THE OTHER DIRECTION: the set being played keeps its live bar", () => {
    // Gotcha #43. Over-suppression here strips a live match of its prices.
    const html = renderAsPage(payload());
    expect(html.match(BAR) ?? []).toHaveLength(1);
    expect(visible(html)).toContain("Kostyuk wins Set 2");
    expect(visible(html)).toContain("56%");
  });

  test("the market may name its sides in either order", () => {
    const swapped = payload({
      other: WIRE.map((r) => ({
        ...r,
        market_name: r.market_name.replace("Kostyuk vs Noskova", "Noskova vs Kostyuk"),
      })),
    } as Partial<GameMarketsResponse>);
    expect(visible(renderAsPage(swapped))).toContain("Noskova won Set 1");
  });
});

describe("it refuses rather than guesses", () => {
  test("a set apiece names nobody — the score cannot say who took set 1", () => {
    // 1–1 is the whole reason `min === 0` is the test. Either player could have
    // won set 1 and the event carries no per-set line to break the tie.
    const level = payload({ home_score: 1, away_score: 1 });
    const text = visible(renderAsPage(level));
    expect(text).not.toContain("won Set 1");
    expect(text).toContain(`${SETTLED_QUOTE_PREFIX} 0%`);
  });

  test("sides that do not pair with the two teams name nobody", () => {
    // A mislinked market, or a name this view cannot resolve. Weak beats wrong.
    const text = visible(
      renderWith({ side: "away", homeTeam: "Coco Gauff", awayTeam: "Naomi Osaka" }),
    );
    expect(text).not.toContain("won Set 1");
    expect(text).toContain(`${SETTLED_QUOTE_PREFIX} 0%`);
  });

  test("two competitors sharing a surname name nobody", () => {
    // `Set 1 Winner: Bryan vs Bryan` — each side matches both teams, so there
    // is no pairing, and picking one would be a coin flip presented as a fact.
    const brothers = payload({
      home_team: "Bob Bryan",
      away_team: "Mike Bryan",
      other: WIRE.map((r) => ({
        ...r,
        market_name: r.market_name.replace("Kostyuk vs Noskova", "Bryan vs Bryan"),
      })),
    } as Partial<GameMarketsResponse>);
    expect(visible(renderAsPage(brothers))).not.toContain("won Set 1");
  });

  test("no set is over yet, so nothing is stated and nothing is frozen", () => {
    const fresh = payload({ home_score: 0, away_score: 0 });
    const html = renderAsPage(fresh);
    expect(visible(html)).not.toContain("won Set 1");
    expect(visible(html)).not.toContain(SETTLED_QUOTE_PREFIX);
    expect(html.match(BAR) ?? []).toHaveLength(2);
  });

  test("a non-tennis payload is untouched, scores and all", () => {
    // Every other sport reaches this module with the same two score columns
    // meaning something else entirely. `decidedSetsWinnerFor` refuses at the
    // sport door before any of the rest of it runs.
    const html = renderAsPage(payload(), "baseball_mlb");
    expect(visible(html)).not.toContain("won Set 1");
    expect(html.match(BAR) ?? []).toHaveLength(2);
  });
});
