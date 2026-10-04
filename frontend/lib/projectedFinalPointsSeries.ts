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
 * Times are OUR capture, not the venue's publication time (the venue's
 * `last_update` is not kept), so the reader is told "recorded", nothing more.
 *
 * ── WHICH ROWS COUNT AS RECORDED (#10461) ───────────────────────────────────
 *
 * A windowed request re-stamps an older capture at the cutoff minute, in the
 * same shape as a real one. The route now says which is which: `kind` and
 * `observed_at` (our original capture instant). A row is admitted as recorded
 * only when it carries `kind: "recorded"` AND an `observed_at` inside its own
 * displayed minute, and it is then placed at `observed_at`, so `asOf` and a
 * scrub cursor compare against the capture itself. `synthetic`, an unknown
 * kind, a missing or malformed `observed_at` are refused, never promoted.
 * `observed_at` must be a valid calendar instant written with its offset
 * (`parseCaptureInstant`): a local time, a bare date or an impossible day
 * (`2026-02-30`) is not a capture, even when a lenient parser would round it
 * onto the displayed minute.
 *
 * A row with no provenance at all (a payload from before the contract) is
 * admitted ONLY on a finished page whose history was served whole: a finished
 * page AND a history whose own `status` is finished, a completion boundary,
 * and no request cutoff, so no row can be a re-stamp. A completion stamp
 * alone does not say the history behind it is the finished game's. Anywhere
 * else the row is refused, so a live or pregame chart draws nothing until the
 * server says what each row is.
 *
 * ── WHAT A ROW'S `valid_until` IS NOT ───────────────────────────────────────
 *
 * The capture minute is the only evidence a pair was quoted. `valid_until` is
 * NOT read, on purpose. `odds_polling.py::_create_or_update_snapshot` sets the
 * old row's `valid_until = now` when the values CHANGE, just before it writes
 * the new row, as well as on an unchanged re-read. So on any row with a
 * successor it is the first capture of a DIFFERENT pair, and on the newest row
 * it is a re-read that may sit across hours with no poll. Read as "confirmed
 * through", a pair recorded at 00:00 and replaced at 03:00 would vouch for a
 * three-hour hole. So the line holds a reading only up to the next recorded
 * capture, and only when that capture follows within `MAX_CAPTURE_GAP_MS`.
 *
 * ── WHAT THE CHART MAY NEVER DO ─────────────────────────────────────────────
 *
 * - Draw a sport whose spread is not an expected margin in points. Only the
 *   sports in `PROJECTED_FINAL_POINTS_SPORTS` are admitted. Baseball's fixed
 *   ±1.5 run line, soccer goals, tennis sets and golf positions are refused by
 *   name, not by a unit lookup that would let soccer through.
 * - Bridge a gap. A missing half, a non-finite value, a value already beaten
 *   by the recorded score, a pair whose leader contradicts its own moneyline,
 *   or a next capture recorded more than `MAX_CAPTURE_GAP_MS` later all break
 *   the line. A single valid reading between two gaps is still drawn, as a dot.
 * - Append the final result to the forecast line. Readings at or after the
 *   server-recorded completion boundary (`completed_at`) are dropped, and
 *   actual scores are a separate series. That boundary is when our server
 *   recorded the game finished, not an observed final whistle, so it does not
 *   prove every dropped reading came after the whistle, or every kept one before.
 * - Show anything after `asOf`. Inspection rebuilds the series at the cursor,
 *   so a scrubbed reading cannot reveal a later projection or a later score.
 * - Invent a 0–0 start. Actual steps begin at the first recorded score at or
 *   after the score floor. Before it there are none.
 *
 * ── THE SCORE FLOOR IS NOT A KICKOFF ────────────────────────────────────────
 *
 * Actual scores need a floor: the instant from which a recorded score is a
 * game-state observation rather than a pregame placeholder. An observed
 * kickoff is one, but nothing serves an observed kickoff today
 * (`commence_time` is the schedule, and `commence_time_is_kickoff` only says
 * it is not a Kalshi expiration, #7878). So the floor may instead be the FIRST
 * RECORDED GAME STATE: the `not_before` bound of the first-period marker an
 * instrument saw (`firstRecordedGameStateAt`). That bound is the last poll
 * that showed no first period. It is not proof the kick happened or play
 * began, so a 0–0 recorded there is a real recorded score, never a kickoff
 * 0–0, and `kickoffAt` stays null. An `estimated` marker is arithmetic on the
 * schedule and is refused.
 */

import { normalizePeriodLabel, PERIOD_SOURCE_ESTIMATED, type ServedPeriodMarker } from "@/lib/periodMarkers";
import { sourceLabel } from "@/lib/sourceLabels";
import type { BookmakerHistoryPoint, EventHistoryResponse } from "@/lib/types";

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
  /**
   * `recorded` = a row we actually captured, stamped with our capture.
   * `synthetic` = a row the history route RE-STAMPED at its window cutoff
   * (an older capture still valid then). That timestamp is not an
   * observation, so the row is never admitted. `unproven` = the row's
   * provenance was missing, unknown or malformed where it is required
   * (module doc), so it is never admitted either. Absent means `recorded`;
   * `projectedFinalPointsInputFromHistory` always sets it.
   */
  kind?: "recorded" | "synthetic" | "unproven";
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
  /**
   * The first recorded game state (`firstRecordedGameStateAt`), the score
   * floor when `kickoffAt` is unknown. NOT a kickoff (module doc).
   */
  scoreObservationStartAt?: string | null;
  /**
   * The server-recorded completion boundary (`completed_at`), or null while
   * the game is unfinished. A processing time, not an observed final whistle.
   */
  finalAt: string | null;
  /** Nothing after this instant is read. The page's now, or the cursor. */
  asOf: string;
  /**
   * Start of the drawn window. Defaults to the earliest reading in the hour
   * before the score floor, else the floor itself; six hours before `asOf`
   * before the floor.
   */
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
  /** The recorded capture minute. Where the point is drawn, and the time a reader is told. */
  at: number;
  home: number;
  away: number;
  /** Where the drawn hold ends: the next recorded capture, or this one before a break. */
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
  /** Empty before the score floor. Right-continuous: each holds until the next. */
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
 * Once the game has started, the window reaches back at most this long before
 * kickoff, and only as far as the earliest reading in it, so the game gets
 * most of the width. Six pregame hours left it a sliver at the
 * right edge (phone-width render, 2026-10-03).
 */
export const PREGAME_CONTEXT_MS = HOUR_MS;
/**
 * The longest stretch between two recorded captures the line may hold a
 * reading across. Past this the stretch is unobserved and the line breaks. A
 * rendering choice, not a measured poll cadence.
 */
export const MAX_CAPTURE_GAP_MS = HOUR_MS;

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const t = Date.parse(value);
  return Number.isFinite(t) ? t : null;
}

const CAPTURE_INSTANT = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/;

/**
 * A served capture instant (`observed_at`), or null. Stricter than
 * `parseTime` on purpose, and used only for provenance: the string must be an
 * ISO-8601 date-time with seconds and an explicit offset, on a real calendar
 * day. `Date.parse` reads an offset-less string as the reader's local time and
 * rolls `2026-02-30` over to March 2, so either could land on a displayed
 * minute by accident and be promoted to a recorded capture.
 */
export function parseCaptureInstant(value: unknown): number | null {
  if (typeof value !== "string") return null;
  const m = CAPTURE_INSTANT.exec(value);
  if (!m) return null;
  const [, y, mo, d, h, mi, sec, frac, zone] = m;
  const [year, month, day, hour, minute, second] = [y, mo, d, h, mi, sec].map(Number);
  if (month < 1 || month > 12 || hour > 23 || minute > 59 || second > 59) return null;
  const wall = Date.UTC(year, month - 1, day, hour, minute, second);
  // A day the month does not have rolls into the next one; that is not this instant.
  if (new Date(wall).getUTCDate() !== day) return null;
  let offsetMs = 0;
  if (zone !== "Z") {
    const oh = Number(zone.slice(1, 3));
    const om = Number(zone.slice(4, 6));
    if (oh > 23 || om > 59) return null;
    offsetMs = (zone[0] === "-" ? -1 : 1) * (oh * 60 + om) * 60 * 1000;
  }
  const ms = frac ? Math.floor(Number(`0.${frac}`) * 1000) : 0;
  return wall + ms - offsetMs;
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

/** The admitted actual steps, oldest first. Empty without a score floor. */
function admitActuals(input: ProjectedFinalPointsInput, floor: number | null, asOf: number): ActualStep[] {
  if (floor === null || floor > asOf) return [];
  const steps: ActualStep[] = [];
  for (const row of input.actuals) {
    const at = parseTime(row.timestamp);
    if (at === null || at < floor || at > asOf) continue;
    if (!isPoints(row.home_score) || !isPoints(row.away_score)) continue;
    steps.push({ at, home: row.home_score, away: row.away_score });
  }
  return steps.sort((a, b) => a.at - b.at);
}

/**
 * The window opens at the book's earliest recorded reading in the pregame
 * hour, or at the floor when it has none. Opening the full hour drew blank
 * axis up to the first reading: 14780549's book starts 50 s before the floor,
 * which left the first hour of the plot empty (2026-10-04).
 */
function startedWindowStart(pairs: ProjectedPairObservation[], floor: number): number {
  const context = floor - PREGAME_CONTEXT_MS;
  let start = floor;
  for (const pair of pairs) {
    if (!isAdmittedKind(pair)) continue;
    const at = parseTime(pair.timestamp);
    if (at !== null && at >= context && at < start) start = at;
  }
  return start;
}

function isAdmittedKind(pair: ProjectedPairObservation): boolean {
  return pair.kind === undefined || pair.kind === "recorded";
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
  // An observed kickoff when there is one, otherwise the first recorded game state (module doc).
  const scoreFloor = parseTime(input.kickoffAt) ?? parseTime(input.scoreObservationStartAt);
  const final = parseTime(input.finalAt);
  // Readings stop at the recorded completion boundary, and never run past the reader's now.
  const end = final !== null && final <= asOfRaw ? final : asOfRaw;
  const phase: ProjectedFinalPointsPhase =
    final !== null && final <= asOfRaw ? "after" : scoreFloor !== null && scoreFloor <= asOfRaw ? "during" : "before";
  const started = scoreFloor !== null && scoreFloor <= end;
  const start =
    parseTime(input.windowStartAt) ??
    (started ? startedWindowStart(input.pairs, scoreFloor) : end - DEFAULT_WINDOW_MS);

  const actualSteps = phase === "before" ? [] : admitActuals(input, scoreFloor, end);

  type Row =
    | { at: number; kind: "valid"; home: number; away: number }
    | { at: number; kind: "withheld"; reason: WithheldReason };
  const rows: Row[] = [];
  for (const pair of input.pairs) {
    if (!isAdmittedKind(pair)) continue;
    const at = parseTime(pair.timestamp);
    // Strictly before the completion boundary: a reading stamped at it is not a forecast.
    if (at === null || at > end || (final !== null && at >= final)) continue;
    // Only captures inside the window. Nothing older is carried in (module doc).
    if (at < start) continue;
    const { home, away } = pair;
    if (home == null || away == null) {
      rows.push({ at, kind: "withheld", reason: "pair_incomplete" });
      continue;
    }
    if (!isPoints(home) || !isPoints(away)) {
      rows.push({ at, kind: "withheld", reason: "not_a_number" });
      continue;
    }
    if (contradictsMoneyline(home, away, pair.homeProbability)) {
      rows.push({ at, kind: "withheld", reason: "contradicts_moneyline" });
      continue;
    }
    const scored = actualAt(actualSteps, at);
    if (scored && (home < scored.home || away < scored.away)) {
      rows.push({ at, kind: "withheld", reason: "below_recorded_score" });
      continue;
    }
    rows.push({ at, kind: "valid", home, away });
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
    // The line only runs on to the next VALID capture. If the next reading is
    // unusable, or was recorded long after this one, nothing recorded the
    // stretch in between, so the line stops at this capture.
    const broken = !next || next.kind === "withheld" || next.at - row.at > MAX_CAPTURE_GAP_MS;
    const holdEnd = broken ? row.at : next.at;
    run.push({ at: row.at, home: row.home, away: row.away, holdEnd });
    if (next && broken) close();
  }
  close();

  if (!segments.length) return { supported: false, reason: "no_valid_pair" };
  const lastRun = segments[segments.length - 1];
  const latest = lastRun[lastRun.length - 1];
  const lastRow = rows[rows.length - 1];
  const latestIntervalUnavailable =
    lastRow.kind === "withheld" || end - latest.at > MAX_CAPTURE_GAP_MS;

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
 * How a served row may be admitted as recorded evidence (module doc). The
 * picker and the input builder share it, so a book cannot be picked on rows
 * the chart would then refuse.
 */
export interface ProjectionAdmission {
  /** The page shows a finished game (completed/closed status). */
  finishedPage: boolean;
  /** The request's window cutoff, or null when the route served the whole series. */
  cutoffAt: string | null;
  /** Nothing captured after this instant counts. */
  asOf: string;
}

type HistoryForAdmission = Pick<EventHistoryResponse, "bookmaker_history" | "completed_at" | "status">;

/** History statuses that say the served history is a finished game's. */
export const FINISHED_HISTORY_STATUSES: ReadonlySet<string> = new Set(["completed", "closed"]);

/**
 * True when a row without provenance may still be read as a recorded capture:
 * a finished page AND a finished history (its own `status`), served whole with
 * a completion boundary. A live, scheduled or missing history status refuses,
 * whatever `completed_at` says.
 */
function legacyRowsAdmitted(history: HistoryForAdmission, admission: ProjectionAdmission): boolean {
  return (
    admission.finishedPage &&
    admission.cutoffAt === null &&
    FINISHED_HISTORY_STATUSES.has(history.status ?? "") &&
    parseTime(history.completed_at) !== null
  );
}

const MINUTE_MS = 60 * 1000;

/**
 * One served row's admission: the kind it is read as and the instant it is
 * placed at. Explicit provenance decides whenever any of it is present; a
 * row with none is recorded only when `legacy` allows it.
 */
function admitRow(row: BookmakerHistoryPoint, legacy: boolean): { kind: "recorded" | "synthetic" | "unproven"; timestamp: string } {
  const hasProvenance = row.kind !== undefined || row.observed_at !== undefined;
  if (!hasProvenance) return { kind: legacy ? "recorded" : "unproven", timestamp: row.timestamp };
  if (row.kind === "synthetic") return { kind: "synthetic", timestamp: row.timestamp };
  if (row.kind !== "recorded") return { kind: "unproven", timestamp: row.timestamp };
  const observed = parseCaptureInstant(row.observed_at);
  const minute = parseTime(row.timestamp);
  // The displayed minute is the capture truncated to the minute. Anything else is not this row's capture.
  if (observed === null || minute === null || Math.floor(observed / MINUTE_MS) * MINUTE_MS !== minute) {
    return { kind: "unproven", timestamp: row.timestamp };
  }
  // Placed at the instant the strict parse read, so nothing downstream re-reads the string leniently.
  return { kind: "recorded", timestamp: new Date(observed).toISOString() };
}

/**
 * The named sportsbook with the most ADMITTED complete pairs captured by
 * `asOf`. Counting raw rows would let a book whose rows are all re-stamps or
 * unproven hide another book with real readings. Only named sources are
 * eligible, so the chart can always say whose numbers it draws. Ties go to
 * the alphabetically first key, so the choice does not change from one
 * payload ordering to the next.
 */
export function pickProjectionSportsbook(history: HistoryForAdmission, admission: ProjectionAdmission): string | null {
  const legacy = legacyRowsAdmitted(history, admission);
  const asOf = parseTime(admission.asOf);
  if (asOf === null) return null;
  let best: string | null = null;
  let bestCount = 0;
  const books = Object.keys(history.bookmaker_history ?? {}).sort();
  for (const book of books) {
    if (!sourceLabel(book)) continue;
    let count = 0;
    for (const row of history.bookmaker_history?.[book] ?? []) {
      if (!isPoints(row.projected_home_score) || !isPoints(row.projected_away_score)) continue;
      const admitted = admitRow(row, legacy);
      const at = parseTime(admitted.timestamp);
      if (admitted.kind === "recorded" && at !== null && at <= asOf) count++;
    }
    if (count > bestCount) {
      best = book;
      bestCount = count;
    }
  }
  return best;
}

/** Instruments whose period markers record what they saw (`ServedPeriodMarker`). */
const OBSERVING_MARKER_SOURCES: ReadonlySet<string> = new Set(["espn_state", "espn_box", "statpal", "win_prob"]);
/** Precisions that place a period start, not merely its first score. */
const PERIOD_START_PRECISIONS: ReadonlySet<string> = new Set(["first_seen", "boundary_observed"]);

/**
 * The first recorded game state: the earliest `not_before` among the served
 * first-period markers an instrument observed, or null when there is none.
 * An `estimated` marker, a marker with no source or no lower bound, and a
 * `first_score` marker are all refused. NOT a kickoff (module doc), so it is
 * only ever passed as `scoreObservationStartAt`.
 */
export function firstRecordedGameStateAt(
  markers: ServedPeriodMarker[] | null | undefined,
  sportKey: string | null | undefined,
): string | null {
  let best: { at: number; iso: string } | null = null;
  for (const m of markers ?? []) {
    if (!m.source || m.source === PERIOD_SOURCE_ESTIMATED || !OBSERVING_MARKER_SOURCES.has(m.source)) continue;
    if (!m.precision || !PERIOD_START_PRECISIONS.has(m.precision)) continue;
    if (normalizePeriodLabel(m.period, sportKey) !== "Q1") continue;
    const at = parseTime(m.not_before);
    if (at === null || (best && best.at <= at)) continue;
    best = { at, iso: m.not_before as string };
  }
  return best?.iso ?? null;
}

/**
 * Builds the input from a served history payload. The caller chooses the
 * book and supplies the observed kickoff, because neither is in the payload,
 * and may supply the first recorded game state as the score floor.
 *
 * Each row is admitted by its served provenance (module doc): `kind:
 * "recorded"` with an `observed_at` inside its own minute is placed at that
 * capture; anything else is marked and refused. `cutoffAt` is the window
 * cutoff the request asked for (`now - hours`), or null when the route
 * serves the whole series; with `finishedPage` it decides only whether a row
 * WITHOUT provenance may be read the pre-contract way.
 */
export function projectedFinalPointsInputFromHistory(
  history: Pick<EventHistoryResponse, "bookmaker_history" | "score_history" | "completed_at" | "status">,
  opts: {
    sportKey: string | null | undefined;
    sourceKey: string;
    kickoffAt: string | null;
    scoreObservationStartAt?: string | null;
    asOf: string;
    cutoffAt: string | null;
    finishedPage: boolean;
  },
): ProjectedFinalPointsInput {
  const rows = history.bookmaker_history?.[opts.sourceKey] ?? [];
  const legacy = legacyRowsAdmitted(history, opts);
  return {
    sportKey: opts.sportKey,
    sourceKey: opts.sourceKey,
    basis: "same_book_same_capture_full_game_spread_and_total",
    pairs: rows.map((p) => {
      const { kind, timestamp } = admitRow(p, legacy);
      return {
        timestamp,
        home: p.projected_home_score,
        away: p.projected_away_score,
        homeProbability: p.home_probability,
        // `valid_until` deliberately not carried: continuity, not confirmation (module doc).
        kind,
      };
    }),
    actuals: history.score_history ?? [],
    kickoffAt: opts.kickoffAt,
    scoreObservationStartAt: opts.scoreObservationStartAt ?? null,
    finalAt: history.completed_at ?? null,
    asOf: opts.asOf,
  };
}
