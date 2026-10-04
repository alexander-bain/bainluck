/**
 * #10239 — each team's projected final points, kept apart from the points it
 * has actually scored.
 *
 * A sportsbook that quotes a full-game spread and a full-game total for the
 * same game, in the same capture, implies a final score for each side:
 * `home = (total - spread) / 2`, `away = (total + spread) / 2`
 * (`backend/app/utils/odds_math.py::project_scores`). This module turns a
 * series of those pairs into something a chart can draw honestly. It does NOT
 * produce forecasts: every value it returns is a pair the source returned,
 * unchanged, or nothing at all.
 *
 * ── WHAT THE INPUT HAS TO PROVE, AND WHERE THAT PROOF LIVES ─────────────────
 *
 * `projected_home_score` / `projected_away_score` are generic fields. On their
 * own they do not say which period they describe, or whether the two halves
 * came from one book at one moment. The aggregate `history` line, for one,
 * is NOT a pair in that sense: each minute bucket averages only the books
 * that wrote a row that minute (write-time dedup), and the route adds
 * carried-forward points at the window cutoff and at "now". So nothing here
 * reads `history`.
 *
 * What is admitted is one sportsbook's own series (`bookmaker_history[book]`).
 * Each of its pairs is written by `tasks/odds_polling.py::_parse_snapshot_values`
 * from that book's `spreads` and `totals` markets in one poll. A baseball run
 * line projects nothing (#8617), and a pair whose leader contradicts the same
 * book's moneyline is nulled on the way out (#8231). The wire carries no
 * marker saying any of that. The caller states it as `basis`, and the only
 * value that type allows names the producer rule above. If that rule ever
 * changes, the basis stops being true and the mount must be withdrawn.
 *
 * Times are OUR capture minute, not the venue's publication time (the venue's
 * `last_update` is not kept), so the reader is told "recorded", nothing more.
 *
 * ── WHAT THE CHART MAY NEVER DO ─────────────────────────────────────────────
 *
 * - Draw a sport whose spread is not an expected margin in points. Only the
 *   sports in `PROJECTED_FINAL_POINTS_SPORTS` are admitted. Baseball's fixed
 *   ±1.5 run line, soccer goals, tennis sets and golf positions are refused by
 *   name, not by a unit lookup that would let soccer through.
 * - Bridge a gap. A missing half, a non-finite value, a value already beaten
 *   by the recorded score, or a pair whose leader contradicts its own
 *   moneyline all break the line. A single valid reading between two gaps is
 *   still drawn, as a dot.
 * - Append the final result to the forecast line. Readings at or after the
 *   final whistle are dropped, and actual scores are a separate series.
 * - Show anything after `asOf`. Inspection rebuilds the series at the cursor,
 *   so a scrubbed reading cannot reveal a later projection or a later score.
 * - Invent a 0–0 start. Actual steps begin at the first recorded score at or
 *   after the observed kickoff. Before kickoff there are none.
 */

import { sourceLabel } from "@/lib/sourceLabels";
import type { EventHistoryResponse } from "@/lib/types";

/**
 * Sports whose sportsbook spread is an expected margin in points. Admission
 * is by name on purpose (see module doc). Add a sport here only with its own
 * fixture proving both units and orientation.
 */
export const PROJECTED_FINAL_POINTS_SPORTS: ReadonlySet<string> = new Set([
  "americanfootball_nfl",
]);

/** Y-axis gridline step per admitted sport: one touchdown with the extra point. */
const TICK_STEP: Record<string, number> = { americanfootball_nfl: 7 };

/**
 * The only basis this module accepts: one sportsbook, one capture, full-game
 * spread and total. See the module doc for the producer it cites.
 */
export type ProjectedFinalPointsBasis = "same_book_same_capture_full_game_spread_and_total";

export interface ProjectedPairObservation {
  timestamp: string;
  home: number | null | undefined;
  away: number | null | undefined;
  /** The same book's home win probability at this capture, when served. */
  homeProbability?: number | null;
  /** When the source last confirmed this exact pair (`valid_until`). */
  heldUntil?: string | null;
  /**
   * `recorded` = a row we actually captured, stamped with our capture minute.
   * `synthetic` = a row the history route RE-STAMPED at its window cutoff
   * (an older capture still valid then). That timestamp is not an
   * observation, so the row is never admitted. Absent means `recorded`.
   */
  kind?: "recorded" | "synthetic";
}

export interface ActualScoreObservation {
  timestamp: string;
  home_score: number;
  away_score: number;
}

export interface ProjectedFinalPointsInput {
  sportKey: string | null | undefined;
  /** A sportsbook key, as served in `bookmaker_history`. */
  sourceKey: string;
  basis: ProjectedFinalPointsBasis;
  pairs: ProjectedPairObservation[];
  actuals: ActualScoreObservation[];
  /** OBSERVED kickoff. A scheduled start is not one; pass null if unknown. */
  kickoffAt: string | null;
  /** The final whistle (`completed_at`), or null while the game is unfinished. */
  finalAt: string | null;
  /** Nothing after this instant is read. The page's now, or the cursor. */
  asOf: string;
  /** Start of the drawn window. Defaults to an hour before kickoff, or six hours before `asOf` pregame. */
  windowStartAt?: string | null;
}

export type ProjectedFinalPointsUnsupportedReason =
  | "sport_not_supported"
  | "source_not_named"
  | "no_valid_pair";

export interface ProjectedFinalPointsUnsupported {
  supported: false;
  reason: ProjectedFinalPointsUnsupportedReason;
}

export type WithheldReason =
  | "pair_incomplete"
  | "not_a_number"
  | "below_recorded_score"
  | "contradicts_moneyline";

export interface ForecastPoint {
  /** Where the point is drawn: its capture, or the window start if it was held into the window. */
  at: number;
  /** When the source first returned this pair. This is the time a reader is told. */
  observedAt: number;
  /** When the source last confirmed this exact pair, clipped to the window end. */
  confirmedThrough: number;
  home: number;
  away: number;
  /** Where the drawn hold ends: the next reading, or the last confirmation before a break. */
  holdEnd: number;
}

export interface WithheldReading {
  at: number;
  reason: WithheldReason;
}

export interface ActualStep {
  at: number;
  home: number;
  away: number;
}

export type ProjectedFinalPointsPhase = "before" | "during" | "after";

export interface ProjectedFinalPointsSeries {
  supported: true;
  sourceKey: string;
  sourceName: string;
  phase: ProjectedFinalPointsPhase;
  /** Runs of consecutive valid readings. A run of one is drawn as a dot. */
  segments: ForecastPoint[][];
  withheld: WithheldReading[];
  /** Empty before kickoff. Right-continuous: each holds until the next. */
  actualSteps: ActualStep[];
  start: number;
  end: number;
  /** The newest valid reading in the window. */
  latest: ForecastPoint;
  /** The recorded score at `end`, or null when none is admitted. */
  latestActual: ActualStep | null;
  /** True when the newest stretch of the window has no usable reading. */
  latestIntervalUnavailable: boolean;
  yMax: number;
  yTicks: number[];
}

const HOUR_MS = 60 * 60 * 1000;
/** Pregame lookback when the caller names no window start. */
export const DEFAULT_WINDOW_MS = 6 * HOUR_MS;
/**
 * Once the game has started, the window opens this long before kickoff, so
 * the game gets most of the width. Six pregame hours left it a sliver at the
 * right edge (phone-width render, 2026-10-03).
 */
export const PREGAME_CONTEXT_MS = HOUR_MS;
/**
 * How long past a pair's last confirmation the line may run before the next
 * reading. Past this the stretch is unobserved and the line breaks. A
 * rendering choice, not a measured poll cadence.
 */
export const MAX_UNCONFIRMED_MS = HOUR_MS;

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const t = Date.parse(value);
  return Number.isFinite(t) ? t : null;
}

function isPoints(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

/** Same rule as `odds_math.projection_contradicts_moneyline`, re-checked client-side. */
function contradictsMoneyline(home: number, away: number, homeProbability: number | null | undefined): boolean {
  if (typeof homeProbability !== "number" || !Number.isFinite(homeProbability)) return false;
  const lean = homeProbability - 0.5;
  const margin = home - away;
  return (lean > 0 && margin < 0) || (lean < 0 && margin > 0);
}

function actualAt(steps: ActualStep[], t: number): ActualStep | null {
  let found: ActualStep | null = null;
  for (const step of steps) {
    if (step.at > t) break;
    found = step;
  }
  return found;
}

/** The admitted actual steps, oldest first. Empty without an observed kickoff. */
function admitActuals(input: ProjectedFinalPointsInput, kickoff: number | null, asOf: number): ActualStep[] {
  if (kickoff === null || kickoff > asOf) return [];
  const steps: ActualStep[] = [];
  for (const row of input.actuals) {
    const at = parseTime(row.timestamp);
    if (at === null || at < kickoff || at > asOf) continue;
    if (!isPoints(row.home_score) || !isPoints(row.away_score)) continue;
    steps.push({ at, home: row.home_score, away: row.away_score });
  }
  return steps.sort((a, b) => a.at - b.at);
}

function niceMax(value: number, step: number): number {
  return Math.max(step, Math.ceil(value / step) * step);
}

export function buildProjectedFinalPointsSeries(
  input: ProjectedFinalPointsInput,
): ProjectedFinalPointsSeries | ProjectedFinalPointsUnsupported {
  const sportKey = input.sportKey ?? "";
  if (!PROJECTED_FINAL_POINTS_SPORTS.has(sportKey)) {
    return { supported: false, reason: "sport_not_supported" };
  }
  const sourceName = sourceLabel(input.sourceKey);
  if (!sourceName) return { supported: false, reason: "source_not_named" };

  const asOfRaw = parseTime(input.asOf);
  if (asOfRaw === null) return { supported: false, reason: "no_valid_pair" };
  const kickoff = parseTime(input.kickoffAt);
  const final = parseTime(input.finalAt);
  // Readings stop at the final whistle, and never run past the reader's now.
  const end = final !== null && final <= asOfRaw ? final : asOfRaw;
  const phase: ProjectedFinalPointsPhase =
    final !== null && final <= asOfRaw ? "after" : kickoff !== null && kickoff <= asOfRaw ? "during" : "before";
  const started = kickoff !== null && kickoff <= end;
  const start =
    parseTime(input.windowStartAt) ?? (started ? kickoff - PREGAME_CONTEXT_MS : end - DEFAULT_WINDOW_MS);

  const actualSteps = phase === "before" ? [] : admitActuals(input, kickoff, end);

  type Row =
    | { at: number; kind: "valid"; home: number; away: number; heldUntil: number }
    | { at: number; kind: "withheld"; reason: WithheldReason };
  const rows: Row[] = [];
  for (const pair of input.pairs) {
    if (pair.kind === "synthetic") continue;
    const at = parseTime(pair.timestamp);
    // Strictly before the final: a reading stamped at the whistle is not a forecast.
    if (at === null || at > end || (final !== null && at >= final)) continue;
    const heldUntil = Math.max(at, parseTime(pair.heldUntil) ?? at);
    // A pair stamped before the window still counts if it was held into it.
    if (heldUntil < start) continue;
    const { home, away } = pair;
    if (home == null || away == null) {
      if (at >= start) rows.push({ at, kind: "withheld", reason: "pair_incomplete" });
      continue;
    }
    if (!isPoints(home) || !isPoints(away)) {
      if (at >= start) rows.push({ at, kind: "withheld", reason: "not_a_number" });
      continue;
    }
    if (contradictsMoneyline(home, away, pair.homeProbability)) {
      if (at >= start) rows.push({ at, kind: "withheld", reason: "contradicts_moneyline" });
      continue;
    }
    const scored = actualAt(actualSteps, at);
    if (scored && (home < scored.home || away < scored.away)) {
      rows.push({ at, kind: "withheld", reason: "below_recorded_score" });
      continue;
    }
    rows.push({ at, kind: "valid", home, away, heldUntil });
  }
  rows.sort((a, b) => a.at - b.at);

  const segments: ForecastPoint[][] = [];
  const withheld: WithheldReading[] = [];
  let run: ForecastPoint[] = [];
  const close = () => {
    if (run.length) segments.push(run);
    run = [];
  };
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    if (row.kind === "withheld") {
      withheld.push({ at: row.at, reason: row.reason });
      close();
      continue;
    }
    const next = rows[i + 1];
    const at = Math.max(row.at, start);
    const confirmedThrough = Math.max(at, Math.min(row.heldUntil, end));
    // The line only runs on to the next VALID reading. If the next reading is
    // unusable, or arrived long after the last confirmation, the stretch in
    // between was never vouched for, so the line stops at the last confirmation.
    const broken = !next || next.kind === "withheld" || next.at - confirmedThrough > MAX_UNCONFIRMED_MS;
    const holdEnd = broken ? confirmedThrough : next.at;
    run.push({ at, observedAt: row.at, confirmedThrough, home: row.home, away: row.away, holdEnd });
    if (next && broken) close();
  }
  close();

  if (!segments.length) return { supported: false, reason: "no_valid_pair" };
  const lastRun = segments[segments.length - 1];
  const latest = lastRun[lastRun.length - 1];
  const lastRow = rows[rows.length - 1];
  const latestIntervalUnavailable =
    lastRow.kind === "withheld" || end - latest.confirmedThrough > MAX_UNCONFIRMED_MS;

  let high = 0;
  for (const seg of segments) for (const p of seg) high = Math.max(high, p.home, p.away);
  for (const s of actualSteps) high = Math.max(high, s.home, s.away);
  const step = TICK_STEP[sportKey] ?? 7;
  const yMax = niceMax(high + step / 4, step);
  const yTicks: number[] = [];
  for (let v = 0; v <= yMax; v += step) yTicks.push(v);

  return {
    supported: true,
    sourceKey: input.sourceKey,
    sourceName,
    phase,
    segments,
    withheld,
    actualSteps,
    start,
    end,
    latest,
    latestActual: actualAt(actualSteps, end),
    latestIntervalUnavailable,
    yMax,
    yTicks,
  };
}

/** Every instant a reader can step to: each valid or withheld reading, oldest first. */
export function inspectionInstants(series: ProjectedFinalPointsSeries): number[] {
  const set = new Set<number>();
  for (const seg of series.segments) for (const p of seg) set.add(p.at);
  for (const w of series.withheld) set.add(w.at);
  return Array.from(set).sort((a, b) => a - b);
}

/** The series as it stood at `t`. Nothing after `t` survives. */
export function seriesAt(
  input: ProjectedFinalPointsInput,
  t: number,
): ProjectedFinalPointsSeries | ProjectedFinalPointsUnsupported {
  const asOf = parseTime(input.asOf);
  const clipped = asOf === null ? t : Math.min(asOf, t);
  // Keep the full view's window: a pregame cursor would otherwise re-anchor
  // the default lookback on itself and pull in readings the chart never drew.
  const full = buildProjectedFinalPointsSeries(input);
  const windowStartAt = input.windowStartAt ?? (full.supported ? new Date(full.start).toISOString() : null);
  return buildProjectedFinalPointsSeries({ ...input, asOf: new Date(clipped).toISOString(), windowStartAt });
}

/**
 * The sportsbook whose own series carries the most complete pairs in the
 * payload. Only named sources are eligible, so the chart can always say whose
 * numbers it draws. Ties go to the alphabetically first key, so the choice
 * does not change from one payload ordering to the next.
 */
export function pickProjectionSportsbook(history: Pick<EventHistoryResponse, "bookmaker_history">): string | null {
  let best: string | null = null;
  let bestCount = 0;
  const books = Object.keys(history.bookmaker_history ?? {}).sort();
  for (const book of books) {
    if (!sourceLabel(book)) continue;
    const count = (history.bookmaker_history?.[book] ?? []).filter(
      (p) => isPoints(p.projected_home_score) && isPoints(p.projected_away_score),
    ).length;
    if (count > bestCount) {
      best = book;
      bestCount = count;
    }
  }
  return best;
}

/**
 * Slack past the request cutoff inside which a row may be a re-stamp. The
 * route truncates to the minute and its clock is not the reader's.
 */
export const CUTOFF_RESTAMP_SLACK_MS = 2 * 60 * 1000;

/**
 * Builds the input from a served history payload. The caller chooses the
 * book and supplies the observed kickoff, because neither is in the payload.
 *
 * `cutoffAt` is the window cutoff the request asked for (`now - hours`), or
 * null when the route serves the whole series (a finished game). The route
 * re-stamps an older row that was still valid at the cutoff with the cutoff
 * minute and gives it no marker (`routes/events.py`, per-book history), so
 * every row at or near the cutoff is marked `synthetic` and refused. A
 * served observation-kind field would make this exact; until then this
 * errs toward refusing.
 */
export function projectedFinalPointsInputFromHistory(
  history: Pick<EventHistoryResponse, "bookmaker_history" | "score_history" | "completed_at">,
  opts: {
    sportKey: string | null | undefined;
    sourceKey: string;
    kickoffAt: string | null;
    asOf: string;
    cutoffAt: string | null;
  },
): ProjectedFinalPointsInput {
  const rows = history.bookmaker_history?.[opts.sourceKey] ?? [];
  const cutoff = parseTime(opts.cutoffAt);
  const restampedThrough = cutoff === null ? null : cutoff + CUTOFF_RESTAMP_SLACK_MS;
  return {
    sportKey: opts.sportKey,
    sourceKey: opts.sourceKey,
    basis: "same_book_same_capture_full_game_spread_and_total",
    pairs: rows.map((p) => ({
      timestamp: p.timestamp,
      home: p.projected_home_score,
      away: p.projected_away_score,
      homeProbability: p.home_probability,
      heldUntil: p.valid_until ?? null,
      kind: restampedThrough !== null && (parseTime(p.timestamp) ?? -Infinity) <= restampedThrough ? "synthetic" : "recorded",
    })),
    actuals: history.score_history ?? [],
    kickoffAt: opts.kickoffAt,
    finalAt: history.completed_at ?? null,
    asOf: opts.asOf,
  };
}
