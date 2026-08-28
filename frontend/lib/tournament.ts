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

/** How a source id reads in a sentence. Unknown ids pass through unchanged. */
const SOURCE_LABELS: Record<string, string> = {
  kalshi: "Kalshi",
  polymarket: "Polymarket",
  odds_api: "sportsbooks",
  espn: "ESPN",
};

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

/**
 * The line under a muted row, explaining WHICH reading is old.
 *
 * `null` for a live row — a healthy row says nothing, or the admission stops
 * being an admission.
 *
 * The mixed case is the one this function exists for (UX-P135). A row blended
 * from a one-hour Kalshi price and a twenty-day Polymarket price is muted, and
 * "20 days ago" alone would be read as "we have not looked at this in three
 * weeks" — which is false and would make the whole board look more abandoned
 * than it is. Naming the stale leg is both more honest and less alarming:
 * "Polymarket 20 days ago" says exactly what is wrong and implies the rest is
 * not. It deliberately reports the GOVERNING age, never the freshest, because
 * the age has to be true of the number printed beside it.
 */
export function rowFreshnessLabel(row: TournamentRow): string | null {
  if (rowIsPresentedAsLive(row)) return null;
  const when = stalenessLabel(row.age_hours);
  if (row.mixed_freshness && row.stale_sources.length > 0) {
    return `${row.stale_sources.map(sourceLabel).join(" + ")} ${when}`;
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
 * The wording says what we are showing and what we are not: "the last
 * confirmed reading, not a live price". A banner that only says "some data may
 * be delayed" lets the reader keep believing the number.
 */
export function boardNotice(board: TournamentBoardData): BoardNotice | null {
  if (board.price_state === "live") return null;
  const when = stalenessLabel(board.age_hours);
  if (board.price_state === "dark" && board.newest_observed_at === null) {
    return {
      tone: "dark",
      headline: "No prices yet",
      detail:
        "We have not recorded a price for this draw. Nothing below is a live number.",
    };
  }
  return {
    tone: board.price_state,
    headline: "Prices paused",
    detail: `Last confirmed reading ${when}. These are the last prices we saw, not live prices.`,
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
