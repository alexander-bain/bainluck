/**
 * League page → shared card system (UX-P074 / #1860, ruling 047).
 *
 * Ruling 047: "Every surface that shows an event or a market renders it through
 * the shared card components. League pages get no bespoke variants." It settles
 * three retrofits on the league page, and the three functions here are what each
 * one needs that is a DECISION rather than a render:
 *
 *   1. events        → `leagueGameToEvent`  (rail brief → the shared card's Event)
 *   2. date ladders  → `dateLadder`        (which markets are ladders, in order)
 *   3. yes/no        → `binaryAnswer`       (which markets are binaries, and the
 *                                            ONE answer each of them has)
 *
 * They live in lib/ and are pure so the classification can be pinned by tests
 * against the real production payload — the classification is the part that can
 * be wrong in a way a screenshot does not show.
 */

import type { LeagueGameBrief, LeagueMarket, LeagueMarketOutcome } from "./api";
import type { QuantityRung } from "@/components/QuantityGroup";
import type { Event } from "./types";

// ---------------------------------------------------------------------------
// 1. Events → the standard event card
// ---------------------------------------------------------------------------

/**
 * Map one league-rail game onto the shape the SHARED event card reads.
 *
 * This is a rename, not a computation: every field either comes straight off the
 * envelope (which UX-P074 extended to carry the card's contract) or is absent.
 * Nothing is invented — in particular a missing probability stays missing rather
 * than becoming 0 or 50 (register E2 / #1776's other half), and a missing
 * `current_odds` is left undefined rather than stamped with nulls, because the
 * card's own withholding logic keys off it.
 */
export function leagueGameToEvent(game: LeagueGameBrief): Event {
  const home = game.current_odds?.home_probability ?? game.home_win_probability;
  const away =
    game.current_odds?.away_probability ??
    (game.home_win_probability != null
      ? Number((1 - game.home_win_probability).toFixed(6))
      : null);

  const event: Event = {
    id: game.id,
    external_id: game.external_id ?? `league-game-${game.id}`,
    sport: game.sport ?? null,
    home_team: game.home_team,
    away_team: game.away_team,
    // The card guards an unparseable time itself (it must, since this field is
    // typed nullable here and non-null there); passing "" is how "we have no
    // time for this game" travels, and it renders as no time rather than as
    // "Invalid Date".
    commence_time: game.commence_time ?? "",
    completed_at: game.completed_at ?? null,
    status: (game.status as Event["status"]) ?? "scheduled",
    home_score: game.home_score,
    away_score: game.away_score,
  };

  if (home != null || away != null) {
    // The absent fields are stated as EXPLICIT nulls rather than left off. The
    // shared card asks `projected_home_score !== null` before printing a
    // projection, and an omitted key answers that test with `undefined !== null`
    // → true → `Math.round(undefined)` → the card prints "Proj NaN-NaN". (The
    // card's guard is fixed too — a shared card must not depend on its callers
    // spelling absence one particular way — but a payload that says "we have no
    // projection" out loud is the honest half of that pair.)
    //
    // `captured_at` is the one field genuinely not in this envelope: the league
    // rail carries a blend, not a snapshot, and inventing a capture time would
    // be worse than the cast.
    event.current_odds = {
      home_probability: home,
      away_probability: away,
      spread: null,
      over_under: null,
      projected_home_score: null,
      projected_away_score: null,
    } as Event["current_odds"];
  }
  if (game.opening_odds) {
    event.opening_odds = game.opening_odds as Event["opening_odds"];
  }
  if (game.home_team_data) event.home_team_data = game.home_team_data;
  if (game.away_team_data) event.away_team_data = game.away_team_data;
  if (game.espn) event.espn = game.espn as Event["espn"];

  return event;
}

// ---------------------------------------------------------------------------
// 2. Date-ladder props → the existing heatmap card
// ---------------------------------------------------------------------------

export interface DateLadder {
  /** Rungs for the SHARED Quantity kernel (`components/QuantityGroup`). */
  rungs: QuantityRung[];
  /**
   * The direction word, stated ONCE for the whole ladder instead of on every
   * rung — unless the rungs disagree, in which case each keeps its own word and
   * this is null. A ladder whose rungs mix "before" and "after" is not one
   * question asked at eight thresholds, and flattening it into one would be the
   * heatmap asserting a shape the data does not have.
   */
  hint: string | null;
}

/** "Before Nov 1, 2029" / "By Aug 1, 2030" / "After May 1, 2028". */
const LADDER_PREFIX = /^(before|by|on or before|after|on or after)\s+(.{4,})$/i;

/** A ladder needs rungs. Two dates are a pair of props, not a ladder. */
const MIN_LADDER_OUTCOMES = 3;

function parseLadderOutcome(
  o: LeagueMarketOutcome,
): { at: number; direction: string; label: string } | null {
  const m = LADDER_PREFIX.exec((o.name || "").trim());
  if (!m) return null;
  const at = Date.parse(m[2].trim());
  if (!Number.isFinite(at)) return null;
  const word = m[1].toLowerCase();
  return {
    at,
    direction: word.includes("after") ? "after" : "before",
    label: m[2].trim(),
  };
}

/**
 * This market as a date ladder for the SHARED Quantity kernel — or null when it
 * is not one.
 *
 * `components/QuantityGroup` IS the existing heatmap card ruling 047 points at:
 * "the same primitive covers MLB hit props, RT scores, CPI ladders, and
 * temperature buckets", and L2-119 already gave it a `wideLabels` mode built for
 * date/time buckets. So this function produces rungs and produces NOTHING else —
 * no second ladder component. (`components/ThresholdGrid` was the one L2-118
 * replaced. It had no live importer and this queue nearly reused it anyway,
 * believing the name; UX-P075 DELETED it — gotcha #133, Alex ruling 2.)
 *
 * Measured 2026-08-14 on `/api/leagues/baseball_mlb`: six "X: Debut Date"
 * markets, 6–8 outcomes each, shaped "Before Nov 1, 2029". They were rendering
 * as a probability-sorted list truncated to six of eight — a ladder with two
 * rungs missing and the rest in an order a ladder does not have.
 *
 * ALL outcomes must parse. A market where three of five rungs are dates and the
 * rest are something else is not a ladder we understand, and rendering it as one
 * would assert an order over rows we could not read.
 */
export function dateLadder(market: LeagueMarket): DateLadder | null {
  const outcomes = market.top_outcomes || [];
  if (outcomes.length < MIN_LADDER_OUTCOMES) return null;

  const parsed: { o: LeagueMarketOutcome; at: number; direction: string; label: string }[] = [];
  for (const o of outcomes) {
    const p = parseLadderOutcome(o);
    if (!p) return null;
    parsed.push({ o, ...p });
  }

  const directions = new Set(parsed.map((p) => p.direction));
  const uniform = directions.size === 1 ? [...directions][0] : null;

  const rungs: QuantityRung[] = parsed.map((p) => ({
    key: p.o.id,
    // The date alone when the whole ladder shares a direction (the word is
    // printed once in the hint); the full phrase when they differ.
    label: uniform ? p.label : `${p.direction === "after" ? "After" : "Before"} ${p.label}`,
    probability: p.o.probability,
    // Epoch ms. The reader never sees it — QuantityGroup sorts on it, which is
    // what turns eight probability-sorted rows back into a ladder.
    value: p.at,
  }));

  return {
    rungs,
    hint: uniform === "before" ? "on or before" : uniform === "after" ? "after" : null,
  };
}

// ---------------------------------------------------------------------------
// 3. Yes/no markets → single-row binary presentation
// ---------------------------------------------------------------------------

export interface BinaryAnswer {
  /** The YES probability — the answer to the question the market's name asks. */
  probability: number | null;
  /** 24h movement of the YES side, sign-corrected when only "No" was priced. */
  movement: number | null;
}

const YES = /^yes$/i;
const NO = /^no$/i;

/**
 * The single answer a yes/no market has — or null when the market is not one.
 *
 * Ruling 047: "Two rows per binary is ruled out. A yes/no market is one question
 * with one answer; rendering it as two rows makes the reader do the arithmetic of
 * noticing that the rows are complements."
 *
 * There is a sharper reason than redundancy, measured on production 2026-08-14:
 * `top_outcomes` is sorted by probability, and 15 of the 21 MLB binaries
 * therefore led with **No**. "Will the Athletics clinch a spot in the 2026 MLB
 * Postseason?" put `No 94.9%` on its first line — so the row a reader takes as
 * the answer was stating the complement of the question. Reading the Yes side by
 * NAME rather than by rank is what fixes that, and it is why this is a function
 * with a test rather than a `top_outcomes[0]`.
 *
 * One-sided binaries count: the same payload carries "Shohei Ohtani: Cy Young and
 * MVP Winner" with a single outcome, `Yes 1%`. One row is already the right
 * number of rows for it, and it must not fall through to a list card.
 */
export function binaryAnswer(market: LeagueMarket): BinaryAnswer | null {
  const outcomes = market.top_outcomes || [];
  if (outcomes.length === 0 || outcomes.length > 2) return null;

  const yes = outcomes.find((o) => YES.test((o.name || "").trim()));
  const no = outcomes.find((o) => NO.test((o.name || "").trim()));

  // Two outcomes that are not a Yes/No pair are two real answers (a playoff
  // series is "Dodgers or Padres", not "yes or no") — those keep both rows.
  if (outcomes.length === 2 && !(yes && no)) return null;
  if (outcomes.length === 1 && !yes && !no) return null;

  if (yes) {
    return { probability: yes.probability, movement: yes.movement_24h };
  }
  // Only the No side is priced: state the Yes side as its complement rather than
  // printing the No number under a Yes-shaped question.
  const p = no?.probability;
  return {
    probability: p == null ? null : Number((1 - p).toFixed(6)),
    movement: no?.movement_24h == null ? null : -no.movement_24h,
  };
}

/** Strip the league prefix and trailing season from a market name. */
export function cleanMarketName(name: string): string {
  return (name || "")
    .replace(/^(NBA|NHL|MLB|NFL|WNBA|MLS)[:\s]+/i, "")
    .replace(/\s*(2024|2025|2026)(-\d+)?\s*$/i, "")
    .trim();
}
