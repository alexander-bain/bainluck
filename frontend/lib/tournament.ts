/**
 * Tournament championship-board types and pure presentation logic (UX-P131).
 *
 * Everything here is a pure function so the jest gate can assert it directly —
 * this suite runs in the node environment with no jsdom, so logic that only
 * exists inside a component body is logic no guard can reach (ruling 005).
 *
 * The rules that are load-bearing rather than cosmetic:
 *
 * - `sparklinePoints` plots on a FIXED 0-100 axis and draws straight segments
 *   between real observations. No smoothing, no auto-scaled y-axis. An
 *   auto-scaled axis makes a 2pp wiggle look like a collapse, which is the
 *   opposite of informative on a page whose subject is movement.
 *
 * - `boardNotice` and `rowIsPresentedAsLive` exist because of #2199. The US
 *   Open outright fields have been price-dark for 8-32 days. The failure this
 *   guards is not an empty board — it is a board that prints July's number in
 *   the same confident type it would print a live one. The server decides
 *   liveness (`probability_is_live`); this file only decides how loudly to say
 *   so, and it is never permitted to upgrade a non-live row.
 */

import { formatProbabilityPercent } from "./probabilityDisplay";
import { renderedDuelPercents, renderedPercent } from "./renderedPercent";
import type { BracketSlot } from "./bracket";
import type { PlayoffGridPayload } from "./playoffGrid";
import type { Broadcast, PlayerImage, SlateData } from "./slate";
import type { PropMarket } from "./tournamentProps";
import type { TournamentResults } from "./tournamentResults";

export type PriceState = "live" | "stale" | "dark";

export interface TournamentTrendPoint {
  date: string;
  probability: number;
}

/**
 * A point in the FINE series — one per hour observed, not one per day (#4173).
 *
 * ⚠️ **THE KEY IS `at`, AND THE NAME IS THE GUARD.** A day point is parsed as
 * ``new Date(`${point.date}T00:00:00Z`)``; reusing `date` for an instant would
 * build `2026-09-09T08:00:00ZT00:00:00Z`, which is an `Invalid Date`, which is
 * `NaN`, which is a blank plot with nothing in the console. With a second name
 * the same mistake is a `npm run typecheck` error instead of an empty chart.
 *
 * `at` is always a full ISO-8601 instant with an explicit `Z`.
 */
export interface TournamentFinePoint {
  at: string;
  probability: number;
}

export interface TournamentSourceView {
  source: string;
  probability: number;
  observed_at: string | null;
  /** THIS contributor's own freshness (UX-P135). The row's verdict is the AND. */
  age_hours: number | null;
  price_state: PriceState;
}

export interface TournamentRow {
  entity_key: string;
  display_name: string;
  seed: number | null;
  country: string | null;
  /** Register-pinned face + flag (Alex's ruling 8). Never resolved client-side. */
  image?: PlayerImage | null;
  rank: number;
  state: string;
  probability: number | null;
  probability_is_live: boolean;
  /**
   * The GOVERNING (oldest) contributor's reading — "as of when is this whole
   * number true". Not the newest: a blend containing a 20-day-old leg is a
   * 20-day-old number however recently its other leg moved (UX-P135).
   */
  observed_at: string | null;
  age_hours: number | null;
  price_state: PriceState;
  /** The newest contributor's reading — an extra fact beside the verdict. */
  freshest_observed_at: string | null;
  freshest_age_hours: number | null;
  /** Names of the contributors that are not live, so the UI can say which. */
  stale_sources: string[];
  /** Some contributors live, some not. A wholly stale row is NOT mixed. */
  mixed_freshness: boolean;
  source_count: number;
  sources: TournamentSourceView[];
  blend_rule: string | null;
  divergent: boolean;
  trend: TournamentTrendPoint[];
  /**
   * The same history at hourly resolution, last 14 days (#4173).
   *
   * ⚠️ **BOTH SERIES ARE PERMANENT AND THEY ARE READ BY DIFFERENT PICTURES.**
   * `trend` is what `TrendSparkline` draws and what `trend_delta` measures — 250
   * vertices in a 52px sparkline is mush, and a delta over 14 days printed beside
   * a 30-day line would be two spans on one row. `trend_hourly` is what
   * `ContenderChart` draws, where 15 vertices across an 817px plot is the
   * staircase ux reported. One blend rule, two resolutions.
   *
   * Optional because a payload served by a backend older than #4173 does not
   * carry it, and the chart falls back to `trend` rather than going blank.
   */
  trend_hourly?: TournamentFinePoint[];
  trend_delta: number | null;
  /** UX-P157. The AND over this row's contributors — see `lib/liquidity`. */
  liquidity?: string | null;
  liquidity_reasons?: string[] | null;
}

export interface TournamentBoardData {
  draw: string;
  label: string;
  rows: TournamentRow[];
  contenders: number;
  unpriced: number;
  /** How many priced rows are not live, and how many blend legs of unequal age. */
  rows_not_live: number;
  mixed_freshness_rows: number;
  price_state: PriceState;
  newest_observed_at: string | null;
  age_hours: number | null;
  /**
   * #5917 — THE DRAW IS OVER AND WE KNOW WHO WON.
   *
   * Present (not null) only on a board whose final is complete with a winner;
   * absent on every undecided board and on every payload served before live's
   * half of this ship, which is why it is optional. It carries the winner's key
   * ALONE, resolved into this board's key space: the score and the completion
   * time live on the result row in `results`, a different fragment, and copying
   * them here would duplicate a fact across two readers.
   */
  decided?: { winner_entity_key: string } | null;
}

export interface TournamentPayload {
  slug: string;
  title: string;
  subtitle: string;
  tournament: string;
  season: string;
  register_version: number;
  register_generated_at: string;
  draw_released: boolean;
  boards: TournamentBoardData[];
  /**
   * The daily slate (UX-P132). Optional so a client built against this type
   * still compiles against a server that predates it — and so the Today tab
   * degrades to its empty state rather than throwing if the key is absent.
   */
  slate?: SlateData;
  /** Curated props & futures (UX-P132). Optional for the same reason as `slate`. */
  props?: PropMarket[];
  /** Where to watch — static per-tournament mapping (UX-P132, Alex's item 4). */
  broadcasts?: Broadcast[];
  /**
   * Positional bracket slots per draw (UX-P134). Empty arrays until the draw
   * ceremony latches `draw_released`; `null` entries are slots the register
   * holds no player for and render as undetermined, never as an invented name.
   */
  bracket?: Record<string, (BracketSlot | null)[]>;
  /**
   * THE PLAYOFF GRID, per draw (UX-P139). Built server-side from the
   * register's `reaches` and nothing else, because Alex's amendment makes cell
   * provenance a correctness property: "the grid reads only the register", and
   * a client stitching cells out of three payload sections cannot be held to
   * that. Optional so an older server degrades to the pre-draw boards.
   */
  grids?: Record<string, PlayoffGridPayload>;
  /**
   * Decided matches with their scores (UX-P139, Alex's item 9), from ESPN.
   * A separate section rather than a field on the slate — a slate structurally
   * cannot hold a finished match; see `build_results`.
   */
  results?: TournamentResults;
  /**
   * WHICH `events` ROW EACH FIXTURE IS — the server's own id-anchored
   * resolution, published so every list on this page can route from the SAME
   * map instead of each one growing its own idea of where a match lives
   * (#2568).
   *
   * `by_matchup` is the one this page reads: `matchup_key -> events.id`,
   * resolved in `backend/app/utils/tournament_event_link.py` by dereferencing
   * the register's pinned match-winner `market_id` through
   * `futures_markets.event_id`. It is NEVER a name match — a matchup the
   * server could not resolve is simply absent from the map, and the row that
   * carries it renders as text rather than as a link to a guess.
   *
   * The slate already had this baked onto each row as `event_id`; the FINISHED
   * list never did, which is the whole of #2568: 89 of the 100 rows on the
   * Men's tab are results rows, and every one of them was inert while the
   * server already knew the event id for 28 of them.
   *
   * ux/1002: and then the MATCH list read only the per-row stamp, so the page
   * held two answers to one question and the live half was the one that could
   * go dead. Both lists resolve through `lib/tournamentEventLink.ts` now —
   * "every list on this page routes from the SAME map" is finally true of
   * every list, which is what this field was published for.
   *
   * `unresolved` is the reason census (`MARKET_UNLINKED`, `NO_PINNED_MARKET`,
   * …) — kept on the type because a row with no link has to be a NAMED gap and
   * not a row that quietly stopped being clickable.
   *
   * `by_espn` is the SECOND channel (#2693 step 2): `ESPN competition id ->
   * events.id`, dereferenced through `events.espn_id`. It exists because
   * `by_matchup` structurally cannot serve the FINISHED list — `build_slate`
   * retires a matchup the moment its match starts, so most finished rows have
   * no register key left and 118 of 235 were inert. Kept as its own field and
   * its own counts rather than merged in: a reader asking which channel routed
   * a row must be able to tell, and `espn_unresolved.ESPN_ID_AMBIGUOUS` above
   * zero is a step-2 regression that would be invisible inside a total.
   */
  event_links?: {
    by_matchup?: Record<string, number>;
    by_event?: Record<string, string>;
    linked?: number;
    unresolved?: Record<string, number> | null;
    by_espn?: Record<string, number>;
    espn_linked?: number;
    espn_unresolved?: Record<string, number> | null;
  };
  /** "Thursday 27 August, 12:00 ET" — Alex's item 1. */
  draw_release_at?: string;
  draw_release_label?: string;
  main_draw_starts_at?: string;
  main_draw_label?: string;
  render_findings: string[];
  generated_at: string;
}

/**
 * A row may be presented as a live number only when the SERVER says so.
 *
 * Written as a named predicate rather than inlined at each call site so there
 * is exactly one place that can ever be wrong, and so the guard suite can
 * assert it directly. It deliberately cannot look at `probability` or
 * `price_state` to talk itself into a yes.
 */
export function rowIsPresentedAsLive(row: TournamentRow): boolean {
  return row.probability_is_live === true;
}

/** Human age, rounded DOWN — "8 days ago" must never flatter to "7". */
export function stalenessLabel(ageHours: number | null): string {
  if (ageHours === null || !Number.isFinite(ageHours)) return "never";
  if (ageHours < 1) {
    const minutes = Math.max(1, Math.floor(ageHours * 60));
    return `${minutes} min ago`;
  }
  if (ageHours < 48) {
    const hours = Math.floor(ageHours);
    return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  }
  const days = Math.floor(ageHours / 24);
  return `${days} days ago`;
}

/**
 * How MANY readings behind this number are old — never WHICH venue they are.
 *
 * Ruling 141 (Alex, 2026-08-28) bans venue names in reader copy: a reader gets
 * our probability, not our sourcing. This function is what replaced the
 * `SOURCE_LABELS` map that turned `polymarket` into "Polymarket" for the line
 * under a muted row.
 *
 * The name was never the load-bearing part. What that line has to say is *some
 * of this is old, not all of it* — see `rowFreshnessLabel` for why. A count
 * says exactly that, in the page's own honesty vocabulary ("no reading yet"),
 * and it says it without handing the reader a venue they never asked about.
 */
const COUNT_WORDS = ["no", "one", "two", "three", "four", "five"];

export function readingCountLabel(count: number): string {
  const word = COUNT_WORDS[count] ?? String(count);
  return `${word} reading${count === 1 ? "" : "s"}`;
}

/**
 * The line under a muted row, explaining WHICH reading is old.
 *
 * `null` for a live row — a healthy row says nothing, or the admission stops
 * being an admission.
 *
 * The mixed case is the one this function exists for (UX-P135). A row built
 * from a one-hour reading and a twenty-day one is muted, and "20 days ago"
 * alone would be read as "we have not looked at this in three weeks" — which
 * is false and would make the whole board look more abandoned than it is.
 * Saying that only PART of it is old is both more honest and less alarming.
 * It deliberately reports the GOVERNING age, never the freshest, because the
 * age has to be true of the number printed beside it.
 *
 * UX-P150, ruling 141: this used to name the stale leg — "Polymarket 20 days
 * ago". The count carries the same fact ("one reading 20 days ago") and the
 * venue name is not ours to put in front of a reader. `stale_sources` is
 * still the payload field it reads; only the rendering changed.
 */
export function rowFreshnessLabel(row: TournamentRow): string | null {
  return rowFreshness(row)?.label ?? null;
}

/**
 * The board's half of #4283 — the same admission plus what a renderer needs.
 * Mirrors `slateRowFreshness` deliberately, for the reason UX-P135 gives: a
 * reader should not have to learn two vocabularies for one idea, and neither
 * should the two components that draw it.
 *
 *     kind: "age"     an age-bearing method note  → draw a `FreshnessDot`
 *     kind: "answer"  "no reading yet", an answer → keep it in the body
 */
export function rowFreshness(
  row: TournamentRow
): { label: string; kind: "age" | "answer"; ageHours: number | null } | null {
  if (rowIsPresentedAsLive(row)) return null;
  const when = stalenessLabel(row.age_hours);
  const label =
    row.mixed_freshness && row.stale_sources.length > 0
      ? `${readingCountLabel(row.stale_sources.length)} ${when}`
      : when;
  const ageHours =
    row.age_hours !== null && Number.isFinite(row.age_hours) ? row.age_hours : null;
  return { label, kind: ageHours === null ? "answer" : "age", ageHours };
}

/**
 * #5924 — IS THE DRAW ON SCREEN FINISHED? Over EVERY board the pill is showing.
 *
 * `drawsShown` is one draw for a singles pill and three for Doubles (#4124), so
 * "the first matching board" is the wrong reading of the question: a graded
 * men's doubles final would then speak for the mixed draw still being played.
 *
 * Empty set is FALSE, deliberately. `[].every(...)` is true in logic and wrong
 * on a page — a payload with no board for this pill knows nothing about whether
 * the draw is over, and the hedged empty states downstream are the right answer
 * to that, not "the final has been played".
 *
 * #8005 — A PILL WITH NO BOARD. The doubles have no board at all (boards are
 * built from championship futures and no venue lists a doubles title market),
 * so on boards alone the Doubles pill could never be decided and fell through
 * to "a match that is on right now would be missing" ten days after all three
 * finals. `decidedDraws` is the server's per-draw answer (`slate.decided_draws`,
 * graded from the same scoreboard), and a draw counts as decided when its OWN
 * board says so OR the server lists it. Still never inferred from rendered results.
 */
export function shownBoardsAreDecided(
  boards: TournamentBoardData[] | null | undefined,
  drawsShown: readonly string[],
  decidedDraws?: readonly string[] | null,
): boolean {
  // PER DRAW, which also closes #5924's own over-claim: "every board shown is
  // decided" let one graded doubles board speak for a boardless draw beside it.
  const decided = new Set(decidedDraws ?? []);
  for (const board of boards ?? []) {
    if (board.decided) decided.add(board.draw);
  }
  return drawsShown.length > 0 && drawsShown.every((draw) => decided.has(draw));
}

export interface BoardNotice {
  tone: "stale" | "dark" | "decided";
  headline: string;
  detail: string;
}

/**
 * The visible admission. `null` only when the board is genuinely live.
 *
 * The wording says what we are showing and what we are not: the last confirmed
 * reading, not a live one. A banner that only says "some data may be delayed"
 * lets the reader keep believing the number.
 *
 * UX-P146: said *price* four times and now says none. Alex's product-wide
 * ruling — "'price' as a noun is banned in user-facing copy; the word is
 * PROBABILITY". The admission is unchanged in force and in specificity; only
 * the vocabulary moved. See `tournamentPlainLanguage.test.tsx`, which pins both
 * halves: the banned word absent AND the staleness still stated.
 */
export function boardNotice(board: TournamentBoardData): BoardNotice | null {
  // #5917 — STALENESS IS THE WRONG APOLOGY FOR A QUESTION THAT IS OVER.
  //
  // The women's board said "Updates paused. Last confirmed reading 7 hours ago.
  // These are the last probabilities we saw, not live ones" above "Elena
  // Rybakina 99%", sixteen hours after Rybakina won the title — while two inches
  // below, on the same screen, a settled prop read "Yes · Settled · last reading
  // 100%". The prices are not paused because a feed went quiet; they are paused
  // because the answer exists and it is a name. "Not live ones" invites the
  // reader to believe a fresher number is coming. None is.
  //
  // FIRST, before every freshness branch, because a decided board is ALSO stale
  // by construction — the staleness is true and it is not the point (Alex's
  // standing ruling: settled means settled).
  //
  // The name comes from the board's own rows, never from the key: an unresolved
  // key is a board we cannot narrate, and inventing "elena-rybakina" as prose is
  // worse than the general sentence.
  if (board.decided) {
    const champion = board.rows.find(
      (row) => row.entity_key === board.decided!.winner_entity_key,
    );
    return {
      tone: "decided",
      headline: "Settled",
      detail: champion
        ? `${champion.display_name} won the title.`
        : "This draw is decided.",
    };
  }
  if (board.price_state === "live") return null;
  const when = stalenessLabel(board.age_hours);
  if (board.price_state === "dark" && board.newest_observed_at === null) {
    return {
      tone: "dark",
      headline: "No numbers yet",
      detail:
        "No market has put a probability on this draw yet. Nothing below is a live number.",
    };
  }
  return {
    tone: board.price_state,
    headline: "Updates paused",
    detail: `Last confirmed reading ${when}. These are the last probabilities we saw, not live ones.`,
  };
}

/**
 * Straight segments between real observations on a FIXED 0-100 axis.
 *
 * Returns an empty string for fewer than two points: one observation is not a
 * trend, and joining it to an assumed origin would draw a movement that never
 * happened.
 */
export function sparklinePoints(
  trend: TournamentTrendPoint[],
  width: number,
  height: number
): string {
  if (!Array.isArray(trend) || trend.length < 2) return "";
  const n = trend.length;
  return trend
    .map((point, index) => {
      const clamped = Math.max(0, Math.min(1, point.probability));
      const x = (index * width) / (n - 1);
      const y = height - clamped * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

/** Direction of travel, with a dead band so noise does not read as a move. */
export function trendDirection(delta: number | null): "up" | "down" | "flat" {
  if (delta === null || !Number.isFinite(delta)) return "flat";
  if (delta > 0.003) return "up";
  if (delta < -0.003) return "down";
  return "flat";
}

/**
 * ═══ THE BOARD PRINTS THE SAME PERCENT THE MATCH CARD DOES (#5893) ═══
 *
 * Alex, on the hub on men's final day: NEXT UP said Zverev **58%**, and the
 * board three rows below said **57.2%**. With two players left, "who wins the
 * final" and "who wins the title" are one question, and the page answered it
 * twice.
 *
 * The served halves of that were live/199's (PR #5902 — the board now carries
 * the final's blend, 0.575). What survived the payload fix was the RENDERING,
 * and it was two separate departures from the product's standing rule:
 *
 * 1. **A decimal.** `(p * 100).toFixed(1)` was a private copy of the rounding
 *    rule that UX-P046 made one module's job. The comment in `tournamentResults`
 *    defended it as precision on a live figure a reader watches move — measured
 *    against the real payload on 2026-09-13 that defence is empty: the men's
 *    board's 36 rows print just FOUR distinct strings (`57.2%`, `42.5%`, and
 *    then `0.1%` eighteen times and `0.0%` sixteen times), so the decimal
 *    separates nothing and prints `0.1%` over a probability of 0.0005. Going
 *    through `formatProbabilityPercent` also buys the boundary rule the board
 *    never had — a live-but-tiny contender reads `<1%`, never `0%`.
 *
 * 2. **Per-row rounding on a two-horse field.** Whole percents alone do not
 *    close it: 0.575 and 0.425 are a complement pair on a half-cent grid, so
 *    half-up sends BOTH up and the board prints 58/43 under a card printing
 *    58/42. That is #2452 / #2060 / UX-P114, for the fourth time, and the
 *    answer is the same one the match card above it already calls —
 *    `renderedDuelPercents`: round the favourite once, derive the other side.
 *
 * So the board decides its integers ONCE, over the whole field, and the row
 * formatter is handed the answer. A row cannot compute this alone for exactly
 * the reason `SideLine` cannot: a side does not know its opponent.
 *
 * WHEN THE PAIR RULE FIRES: exactly two rows print 1% or more. That is "the
 * draw is down to its final" stated in terms of what the reader can see — a
 * semi-final field of four still has four numbers to print and is left alone.
 *
 * Whether those two are a COMPLEMENT pair is deliberately not re-asked here.
 * `renderedDuelPercents` already declines a pair outside [0.99, 1.01] and hands
 * back the per-row rounding, and a second copy of that test is a second place
 * for the band to drift. The draft did ask it, and a mutation run is what said
 * so: removing the duplicate check killed no test, because it could not.
 */
export function boardRenderedPercents(
  rows: readonly TournamentRow[] | null | undefined,
): Record<string, number | null> {
  const percents: Record<string, number | null> = {};
  if (!rows) return percents;
  for (const row of rows) percents[row.entity_key] = renderedPercent(row.probability);

  const contenders = rows.filter((row) => (percents[row.entity_key] ?? 0) >= 1);
  if (contenders.length !== 2) return percents;

  const [first, second] = renderedDuelPercents(
    contenders[0].probability,
    contenders[1].probability,
  );
  percents[contenders[0].entity_key] = first;
  percents[contenders[1].entity_key] = second;
  return percents;
}

/**
 * One row's number. `rendered` is the field-level integer from
 * `boardRenderedPercents`; without it the row rounds alone, which is correct for
 * a caller that genuinely has one probability and no field.
 */
export function formatBoardProbability(
  probability: number | null,
  rendered?: number | null,
): string {
  if (probability === null || !Number.isFinite(probability)) return "—";
  return formatProbabilityPercent(probability, { rendered });
}

export function formatTrendDelta(delta: number | null): string {
  if (delta === null || !Number.isFinite(delta)) return "—";
  const points = delta * 100;
  const sign = points > 0 ? "+" : "";
  return `${sign}${points.toFixed(1)}`;
}

/**
 * ═══ THE TWO HALVES, JOINED (latency/135) ═══════════════════════════════════
 *
 * The hub asks for its first screen and its second half as two requests —
 * `?sections=first` (20 KB gzipped) then `?sections=rest` (67 KB) — because 77%
 * of this payload renders nothing until a reader scrolls or taps the Bracket
 * tab. This is where the second one lands.
 *
 * IT TAKES ONLY WHAT `rest` OWNS, and that is the whole design. A spread
 * (`{...first, ...rest}`) would look identical in every test written against a
 * fresh pair and be wrong on the case that actually happens: the two fragments
 * are built from two requests, seconds apart, each with its own `generated_at`,
 * and the second one describes sections BELOW the fold. Letting it overwrite
 * the page's stamp would date the reader's live numbers by a section they
 * cannot see. So the named keys are copied and nothing else is.
 *
 * `event_links` is merged rather than replaced for the mirror-image reason: its
 * `by_matchup` channel addresses the day's card and arrives with `first`, its
 * `by_espn` channel addresses the finished list and arrives with `rest`, and
 * whichever one a plain assignment kept, the other list would go inert. That is
 * #2568 and #2693 step 2 both re-broken by a spread operator, so it is asserted
 * in `__tests__/lib/tournamentSections.test.ts` rather than trusted.
 */
export function mergeTournamentSections(
  first: TournamentPayload,
  rest: Partial<TournamentPayload> | null | undefined
): TournamentPayload {
  if (!rest) return first;
  return {
    ...first,
    ...(rest.grids !== undefined ? { grids: rest.grids } : {}),
    ...(rest.results !== undefined ? { results: rest.results } : {}),
    event_links: { ...(first.event_links ?? {}), ...(rest.event_links ?? {}) },
  };
}
