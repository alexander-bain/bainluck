/**
 * #10298 — POLYMARKET'S GAME LISTING, BESIDE ITS OWN GAME, PRINTS NO FAVOURITE.
 *
 * Production, `/search?q=lions`, 2026-10-03 06:4xZ: GAMES served Lions v Packers
 * (Oct 25) at Lions 56%, and ANSWERS led with "Packers vs. Lions — Packers 53%":
 * market 61040985, Polymarket's listing for that same game (event 14780566), whose
 * legs are a stale team-win leg beside spreads and a second-half total. The
 * dropdown served the same row under the game for `q=lions packers`.
 *
 * Producer half (PR #10299) adds `related_game_listing: {event_id, question_count}`
 * ONLY when the game is in the same response and leaves `top_outcomes` as it was.
 * This is the web consumer half: #10089's link, "N questions on this game ›", with
 * no percentages. Every arm has its control: the same row WITHOUT the key prints
 * exactly what it printed before.
 */

import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "../../components/FuturesCard";
import SearchFamilyCard from "../../components/SearchFamilyCard";
import type { FuturesFamily, FuturesMarket, FuturesOutcome } from "../../lib/types";
import type { TypeaheadSuggestion } from "../../lib/api";
import { countAnswersShown, futuresAnswer, suggestionSubtitle } from "../../lib/searchSuggestionDisplay";
import { relatedGameListingText } from "../../lib/relatedGameListing";

const GAME_ID = 14780566;
const LISTING_ID = 61040985;
// The specimen's legs, as served (name, probability).
const LEGS: [string, number][] = [["Packers", 0.53], ["Spread -5.5", 0.29], ["Packers 2H O/U 20.5", 0.5], ["1H Spread -6.5", 0.5]];
const KEY = { event_id: GAME_ID, question_count: 4 };

function outcome(id: number, name: string, probability: number): FuturesOutcome {
  return {
    id, name, probability,
    american_odds: null, rank: null, rank_change_24h: null, probability_change_24h: null,
    movement: null, opening_probability: null, opening_american_odds: null,
    is_winner: false, last_updated: null,
  } as FuturesOutcome;
}

function listing(over: Partial<FuturesMarket> = {}): FuturesMarket {
  return {
    id: LISTING_ID, name: "Packers vs. Lions", description: null, source: "polymarket", category: "championship",
    sport: "americanfootball_nfl", sport_name: "NFL", llm_sport_category: "football", market_type: "field",
    market_tier: 5, external_id: null, mutually_exclusive: false, commence_time: null,
    resolution_date: "2026-10-25T17:00:00+00:00", outcome_count: LEGS.length, created_at: null, updated_at: null,
    status: "open", event_commence_time: "2026-10-25T17:00:00+00:00", prices_updated_at: "2026-10-03T06:40:00Z",
    top_outcomes: LEGS.map(([n, p], i) => outcome(LISTING_ID * 10 + i, n, p)),
    ...over,
  } as unknown as FuturesMarket;
}

const family = (headline: FuturesMarket): FuturesFamily =>
  ({ family_key: "lions", label: "Detroit Lions", headline, members: [], more_count: 0 } as unknown as FuturesFamily);

describe("Answers family row", () => {
  test("beside its game: the link, and no percentage anywhere on the row", () => {
    const html = renderToStaticMarkup(<SearchFamilyCard family={family(listing({ related_game_listing: KEY }))} />);
    expect(html).toContain("4 questions on this game");
    expect(html).toContain("data-related-listing-link");
    expect(html).toContain(`href="/futures/${LISTING_ID}"`);
    expect(html).not.toMatch(/\d%/);
  });
  test("control: the same row without the key prints its leader as before", () => {
    const html = renderToStaticMarkup(<SearchFamilyCard family={family(listing())} />);
    expect(html).toContain("53%");
    expect(html).not.toContain("on this game");
  });
});

describe("flat Futures & Markets card", () => {
  // The price-age pip reads the clock; pin it an hour after the specimen's prices.
  beforeEach(() => { jest.useFakeTimers({ now: new Date("2026-10-03T07:40:00Z") }); });
  afterEach(() => { jest.useRealTimers(); });
  test("beside its game: the link replaces the rows, the price age and the corner count", () => {
    const html = renderToStaticMarkup(<FuturesCard market={listing({ related_game_listing: KEY })} />);
    expect(html).toContain("4 questions on this game");
    expect(html).not.toMatch(/\d%/);
    expect(html).not.toContain("Spread -5.5");
    expect(html).not.toMatch(/>4<\/span>/);
    expect(html).not.toContain("1h ago");
  });
  test("control: the same card without the key draws its rows and count as before", () => {
    const html = renderToStaticMarkup(<FuturesCard market={listing()} />);
    expect(html).toContain("53%");
    expect(html).toContain("Spread -5.5");
    expect(html).toMatch(/>4<\/span>/);
    expect(html).toContain("1h ago");
    expect(html).not.toContain("on this game");
  });
});

describe("typeahead row", () => {
  const row = (over: Partial<TypeaheadSuggestion> = {}): TypeaheadSuggestion => ({
    type: "futures", text: "Packers vs. Lions", market_id: LISTING_ID, market_type_label: "Game",
    top_outcomes: LEGS.slice(0, 3).map(([name, probability]) => ({ name, probability })),
    ...over,
  } as TypeaheadSuggestion);
  test("beside its game row: the link text, no answer, not counted as an answer", () => {
    const keyed = row({ related_game_listing: KEY });
    expect(suggestionSubtitle(keyed)).toEqual({ kind: "futures-label", text: "4 questions on this game" });
    expect(futuresAnswer(keyed)).toBeNull();
    expect(countAnswersShown([keyed])).toBe(0);
  });
  test("control: the same row without the key leads with its answer", () => {
    const plain = row();
    expect(suggestionSubtitle(plain)?.kind).toBe("futures-answer");
    expect(futuresAnswer(plain)?.leader.name).toBe("Packers");
    expect(countAnswersShown([plain])).toBe(1);
  });
});

test("wording: singular, and an unusable count still says where the link goes", () => {
  expect(relatedGameListingText({ event_id: GAME_ID, question_count: 1 })).toBe("1 question on this game");
  expect(relatedGameListingText({ event_id: GAME_ID, question_count: 0 })).toBe("More questions on this game");
  expect(relatedGameListingText({ event_id: GAME_ID, question_count: 2.5 })).toBe("More questions on this game");
  expect(relatedGameListingText(null)).toBeNull();
  expect(relatedGameListingText(undefined)).toBeNull();
});
