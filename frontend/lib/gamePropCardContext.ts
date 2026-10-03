/**
 * #10263 — A GAME-PROP CARD SAYS WHICH GAME IT IS ABOUT.
 *
 * Production, `/search?q=dodgers` at 390px, 2026-10-02: three Dodgers–Braves
 * games upcoming (Tomorrow, Oct 4, Oct 6), and the Markets grid printed cards
 * titled only `Spread: Los Angeles Dodgers (-2.5)`, `1st 5 Innings Spread: …`
 * and `Los Angeles Dodgers Team Total: O/U 4.5` — no opponent, no date. The
 * spread card's rows read `Atlanta Braves 63%` under a "Dodgers -2.5" title,
 * which looks like a contradiction until you know it means Braves +2.5 covers.
 *
 * The data was already served: every linked game prop carries the game's
 * kickoff as `event_commence_time`. What the row does NOT carry is the
 * opponent, so the matchup comes from, in order:
 *
 *  1. the title itself — `Atlanta Braves vs. Los Angeles Dodgers: O/U 8.5`
 *     already names both sides, so nothing is added (saying it twice is noise);
 *  2. a game the same page already holds (Search's Games list) with the SAME
 *     kickoff instant that names one of the prop's teams — exact instant, so
 *     a doubleheader's two games stay apart and Oct 4 can never borrow Oct 3;
 *  3. a two-way market whose two outcomes are the two sides (a spread or a
 *     moneyline leg) — the outcomes ARE the matchup.
 *
 * Anything else (a team total with no game on the page) gets the date alone.
 * The date is `formatScheduledGameLabel`, the wording the Games list and the
 * Discover card already print for the same kickoff, and like them it says
 * nothing once the game has started.
 *
 * PURE: no clock unless `now` is defaulted, no I/O.
 */

import type { FuturesMarket } from "@/lib/types";
import { formatScheduledGameLabel } from "@/lib/gameTimeLabel";
import { teamShortName, teamShortNames } from "@/lib/teamShortName";

/** The fields of a served game this module reads. `Event` satisfies it. */
export interface GamePropGameRef {
  home_team: string | null;
  away_team: string | null;
  commence_time: string | null;
  sport?: string | null;
}

type MarketInput = Pick<FuturesMarket, "name" | "event_commence_time" | "sport"> & {
  outcomes?: { name: string }[] | null;
  top_outcomes?: { name: string }[] | null;
};

/** Outcome words that name an answer, never a side. */
const NON_SIDE = /^(yes|no|over|under|draw|tie)$/i;

/** A title that already names both sides: `X vs. Y: …`, `X vs Y - …`, `X @ Y`. */
const NAMES_BOTH_SIDES = /\s(vs\.?|v\.?|@)\s/i;

function sameInstant(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false;
  const ta = Date.parse(a);
  const tb = Date.parse(b);
  return !Number.isNaN(ta) && ta === tb;
}

function mentions(haystack: string, name: string | null | undefined): boolean {
  const n = (name ?? "").trim().toLowerCase();
  return n.length > 0 && haystack.toLowerCase().includes(n);
}

function shippedOutcomeNames(market: MarketInput): string[] {
  return (market.top_outcomes ?? market.outcomes ?? []).map((o) => o.name);
}

/** "Braves @ Dodgers", or null when the card must not (or need not) say one. */
export function gamePropMatchup(
  market: MarketInput,
  games: readonly GamePropGameRef[] = [],
): string | null {
  if (!market.event_commence_time) return null;
  if (NAMES_BOTH_SIDES.test(market.name)) return null;

  const names = shippedOutcomeNames(market);
  const text = [market.name, ...names].join(" | ");
  const candidates = games.filter(
    (g) =>
      sameInstant(g.commence_time, market.event_commence_time) &&
      (mentions(text, g.home_team) || mentions(text, g.away_team)),
  );
  // Two games at one instant both naming the prop's text would be a guess.
  if (candidates.length === 1) {
    const g = candidates[0];
    const pair = teamShortNames({ name: g.home_team }, { name: g.away_team }, g.sport ?? market.sport);
    if (pair.home && pair.away) return `${pair.away} @ ${pair.home}`;
  }

  if (names.length === 2 && names.every((n) => n.trim() && !NON_SIDE.test(n.trim()))) {
    const [a, b] = names.map((n) => teamShortName(n, null, market.sport));
    if (a && b && a !== b) return `${a} vs ${b}`;
  }
  return null;
}

/** "Braves @ Dodgers · Tomorrow 1:00 PM" — or the half that exists, or null. */
export function gamePropContextLine(
  market: MarketInput,
  games: readonly GamePropGameRef[] = [],
  now: number = Date.now(),
): string | null {
  if (!market.event_commence_time) return null;
  const parts = [
    gamePropMatchup(market, games),
    formatScheduledGameLabel(market.event_commence_time, now) || null,
  ].filter((p): p is string => !!p);
  return parts.length ? parts.join(" · ") : null;
}

/** `Spread: Los Angeles Dodgers (-2.5)`, `1st 5 Innings Spread: Lakers (+3.5)`. */
const SPREAD_TITLE = /\bSpread:\s*(.+?)\s*\(([+-])(\d+(?:\.\d+)?)\)\s*$/i;

/**
 * Row labels for a two-sided spread: the named side keeps the title's line,
 * the other side carries its mirror — `Atlanta Braves +2.5` /
 * `Los Angeles Dodgers -2.5`. Null when the market is not exactly that shape
 * (the caller keeps its own labels), so a spread whose outcomes are not the
 * two sides — or do not include the side the title names — is left alone.
 */
export function spreadSideLabels(marketName: string, outcomeNames: readonly string[]): string[] | null {
  const m = SPREAD_TITLE.exec(marketName);
  if (!m || outcomeNames.length !== 2) return null;
  const [, team, sign, line] = m;
  const key = team.trim().toLowerCase();
  const named = outcomeNames.findIndex((n) => n.trim().toLowerCase() === key);
  if (named < 0) return null;
  const other = 1 - named;
  if (!outcomeNames[other].trim() || NON_SIDE.test(outcomeNames[other].trim())) return null;
  const mirror = sign === "-" ? "+" : "-";
  return outcomeNames.map((n, i) => `${n.trim()} ${i === named ? sign : mirror}${line}`);
}
