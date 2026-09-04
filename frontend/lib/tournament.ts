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
  if (rowIsPresentedAsLive(row)) return null;
  const when = stalenessLabel(row.age_hours);
  if (row.mixed_freshness && row.stale_sources.length > 0) {
    return `${readingCountLabel(row.stale_sources.length)} ${when}`;
  }
  return when;
}

export interface BoardNotice {
  tone: "stale" | "dark";
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

export function formatBoardProbability(probability: number | null): string {
  if (probability === null || !Number.isFinite(probability)) return "—";
  return `${(probability * 100).toFixed(1)}%`;
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
