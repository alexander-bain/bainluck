/**
 * #10868 — THE HOCKEY JOURNEY SCREEN (web), PART TWO: THE TWO-TEAM
 * WIN-PROBABILITY HISTORY.
 *
 * PILLARS: TRUTH / FORMATTING. SHIP: on `nhl-journey` the history under the
 * matrix draws only what was recorded — the last pregame reading, then the
 * game — and leaves every unrecorded stretch blank, never a settlement or a
 * line run on to now; the away side of a two-outcome blend is said to be its
 * other side, and is withheld where the sport prices a draw.
 *
 * The web port of native `HockeyJourneyHistoryAdapter10868` (read its header for
 * the full reasoning). It reads the `/api/events/{id}/history` body the page
 * already holds and decides nothing an authority already decides:
 *
 *   - which line      the backend blend (`aggregate_line`) when the body also
 *                     serves venue series (`win_prob_history` non-empty), else
 *                     the sportsbook consensus (`history`). Native
 *                     `OddsChartView.primarySource`/`servedPoints`
 *                     (OddsChartView.swift:2803, :3146), the same shape as web
 *                     `OddsChart`'s `showBlendLine` (OddsChart.tsx:1583: a
 *                     multi-source body with a backend blend). Never a client mean.
 *   - the away trace  the row's served away value, else on the blend the
 *                     documented two-outcome complement `1 − home` OF THE SAME
 *                     ROW through `printableAway` (drawPricedWinner.ts:117), which
 *                     withholds it on a sport that prices a draw. Same rows,
 *                     times, breaks and removals as home — never an extra point.
 *   - breaks          `classifySeriesSupport` (chartObservationSupport.ts:206),
 *                     web's #7878 rule with native's thresholds (600 s floor, 15×
 *                     the series' own in-game cadence; pre-match never judged),
 *                     applied inside each stretch between unreadable rows. An
 *                     unreadable row (no value, outside 0…1, a consensus row
 *                     priced by 0 books, an unreadable or non-advancing time)
 *                     breaks the run. The rule's game-start window is the
 *                     listed commence (`event.commence_time`) in EVERY case,
 *                     confirmed kick-off or not — what web's chart passes
 *                     (OddsChart.tsx:1676, :1754) and native's `gameStartDate`
 *                     — so a real in-play hole is never joined; it only breaks
 *                     lines, never splits pregame from game. NOTE: web's
 *                     existing `OddsChart` keeps `connectNulls` on the blend
 *                     and never judges it (OddsChart.tsx:3695-3704) — this
 *                     screen breaks it, as native does, because "Gaps remain
 *                     blank" is its claim.
 *   - not readings    removed outright (no point, no gap): a finished game's
 *                     settlement row (the LAST served row, at the value the
 *                     served verdict names or a served `final` witness states),
 *                     the blend's pinned edge (`blend_edge_pinned`), and blend
 *                     minutes holding only the backend's live-edge carry-forward
 *                     (native `BlendPreview.carriedForwardMinutes`,
 *                     BlendPreview.swift:985; web's twin in blendPreview.ts:382
 *                     is private and omits sportsbook-row minutes — mirrored
 *                     from native so both platforms remove the same minutes).
 *   - game end        a finished game is clipped at the web chart's own end,
 *                     `computeSharedChartDomain(...).end` (eventKeyStats.ts:1401)
 *                     — the instant web's win-probability chart ends on the same
 *                     page. Native clips at `gameEndDate` (last game-end row +
 *                     120 s), so the two can end one row apart (see report).
 *   - pregame / game  split at the listed start only when the body says it is a
 *                     kick-off (`commence_time_is_kickoff !== false`) and the row
 *                     says it is not a placeholder (`start_is_tbd !== true`). No
 *                     confirmed start ⇒ no split, never one at a guessed time:
 *                     the recorded rows still draw, as ONE unsplit history with
 *                     no last pregame reading, hollow mark or guide, and the
 *                     readout says the start is not confirmed.
 *   - guides          `derivePeriodBoundaries` (periodMarkers.ts:1358), the
 *                     page's own period markers, kept only for period STARTS
 *                     (native keeps labels `PeriodLabel.columnLabel` admits: no
 *                     "Final", no ends, no intermission); scoring plays at their
 *                     served time. Only inside the frame.
 *   - axis words      `axisTimeFormat` + `formatAxisTime` (chartAxisTimeLabel.ts),
 *                     the web twin of native `xAxisPlan` (#8135).
 *   - every percent   `formatProbabilityPercent`; a complement row's two figures
 *                     through `renderedComplementPercents` (renderedPercent.ts:478)
 *                     so one instant never reads 51% beside 50%.
 *
 * Phase scopes (the accepted screen's own): before — readable pregame rows from
 * the listed start less one day up to the last pregame row, no guides; live —
 * the last pregame row, then the game's rows up to now; final — the last
 * pregame row, then the game's rows up to the game's end, without the
 * settlement row. No confirmed start, any phase — every readable dated row up
 * to now (a finished game's end), unsplit; no one-day floor (it is measured
 * from a confirmed start).
 *
 * No `/history` response at all (not arrived, or failed — the page does not
 * say which, so neither is claimed): "History unavailable", no source note,
 * no runs, no working chart control. Native
 * `HockeyJourneyHistoryAdapter10868.unavailable`. A response with no readable
 * row is still "No recorded history".
 *
 * PURE: no fetch, no subscription, no timer. `nowMs` is a parameter.
 */

import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import { printableAway } from "@/lib/drawPricedWinner";
import { classifySeriesSupport, evidenceResolutionS } from "@/lib/chartObservationSupport";
import { computeSharedChartDomain } from "@/lib/eventKeyStats";
import { derivePeriodBoundaries } from "@/lib/periodMarkers";
import { axisTimeFormat, formatAxisTime } from "@/lib/chartAxisTimeLabel";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { renderedComplementPercents } from "@/lib/renderedPercent";
import { isFinishedStatus } from "@/lib/eventState";
import { clockWords, parseMs, servedOutcome, type HockeyJourneyPhase } from "./hockeyJourneyCore";
import type {
  HockeyJourneyLine,
  HockeyJourneySide,
  HockeyJourneyHistoryPoint,
  HockeyJourneyReading,
  HockeyJourneyHistorySeries,
  HockeyJourneyGuide,
  HockeyJourneyHistory,
} from "./hockeyJourneyTypes";

export type {
  HockeyJourneyLine,
  HockeyJourneySide,
  HockeyJourneyHistoryPoint,
  HockeyJourneyReading,
  HockeyJourneyHistorySeries,
  HockeyJourneyGuide,
  HockeyJourneyHistory,
} from "./hockeyJourneyTypes";

export const HISTORY_WORDS = {
  title: "Win probability",
  beforeCaption: "Before game",
  gameCaption: "Game history",
  pregame: "Pregame",
  recorded: "Recorded",
  lastPregame: "Last pregame",
  notRecorded: "Not recorded",
  noHistory: "No recorded history",
  /** No history response at all: says nothing about whether rows exist or why. */
  historyUnavailable: "History unavailable",
  hollowKey: "Hollow · last pregame",
  gapsNote: "Gaps remain blank.",
  blendSource: "Source: Bain Luck",
  consensusSource: "Source: Sportsbook Consensus (market)",
  unconfirmedStart: "Start time not confirmed",
  unconfirmedStartWords: "Pregame and game readings are split at a confirmed start, and this game has none yet.",
  details: "History & source details",
} as const;

/** The before frame reaches back one day from the listed start. */
export const BEFORE_WINDOW_MS = 24 * 60 * 60 * 1000;
/** A single drawn instant still needs a frame to sit in. */
const SINGLE_INSTANT_PAD_MS = 30 * 60 * 1000;
/** Phone tick budget (native `xAxisTicks` on the phone count). */
const MAX_X_TICKS = 4;

/** One served row of the line, values as served. */
export interface HockeyJourneyServedRow {
  index: number;
  timestamp: string;
  t: number | null;
  home: number | null;
  /** Served, or on the blend the printable complement of this row's home. */
  away: number | null;
  awayIsComplement: boolean;
  /** False for a consensus row priced by 0 books: not a sportsbook reading. */
  priced: boolean;
}

interface Entry {
  row: HockeyJourneyServedRow;
  /** Null where the time is unreadable or does not advance past the row before. */
  t: number | null;
}

interface Vertex {
  entry: Entry;
  t: number;
  p: number;
}

interface Drawn {
  runs: Vertex[][];
  lastPregame: Vertex | null;
  pregameDrawn: boolean;
}

/** The chart's own primary line on this body. */
export function historyLine(history: EventHistoryResponse): HockeyJourneyLine {
  const multiSource = Object.keys(history.win_prob_history ?? {}).length > 0;
  const blendServed = (history.aggregate_line ?? []).some((p) => parseMs(p?.timestamp) !== null);
  return multiSource && blendServed ? "blend" : "consensus";
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Every served row of the line, in served order. */
export function servedRows(
  history: EventHistoryResponse,
  line: HockeyJourneyLine,
  sport: string | null | undefined,
): HockeyJourneyServedRow[] {
  if (line === "blend") {
    return (history.aggregate_line ?? []).map((point, index) => {
      const home = finiteNumber(point.home_probability);
      // `aggregate_line` serves `timestamp` + `home_probability` today; a served
      // away value is read if a later producer adds one.
      const servedAway = finiteNumber((point as unknown as { away_probability?: unknown }).away_probability);
      const away = home === null ? null : printableAway(servedAway ?? 1 - home, sport);
      return {
        index,
        timestamp: point.timestamp,
        t: parseMs(point.timestamp),
        home,
        away,
        awayIsComplement: servedAway === null && away !== null,
        priced: true,
      };
    });
  }
  return (history.history ?? []).map((point, index) => ({
    index,
    timestamp: point.timestamp,
    t: parseMs(point.timestamp),
    home: finiteNumber(point.home_probability),
    away: finiteNumber(point.away_probability),
    awayIsComplement: false,
    priced: point.bookmaker_count !== 0,
  }));
}

/** A team's own served value on a row, or null when the row is a gap for it. */
function sideValue(row: HockeyJourneyServedRow, side: HockeyJourneySide): number | null {
  if (!row.priced) return null;
  const v = side === "home" ? row.home : row.away;
  return v !== null && v >= 0 && v <= 1 ? v : null;
}

/** Blend minutes that hold only the backend's live-edge carry-forward. */
function carriedForwardMinutes(history: EventHistoryResponse): Set<number> {
  const minute = (stamp: string): number | null => {
    const t = parseMs(stamp);
    return t === null ? null : Math.floor(t / 60_000) * 60_000;
  };
  const carried = new Set<number>();
  const real = new Set<number>();
  for (const series of Object.values(history.win_prob_history ?? {})) {
    for (const point of series ?? []) {
      const at = minute(point.timestamp);
      if (at === null) continue;
      if (point.live_edge === true || point.evidence?.kind === "live_edge") carried.add(at);
      else real.add(at);
    }
  }
  const sportsbooks = [
    ...(history.history ?? []).map((p) => p.timestamp),
    ...Object.values(history.bookmaker_history ?? {}).flatMap((points) => (points ?? []).map((p) => p.timestamp)),
  ];
  for (const stamp of sportsbooks) {
    const at = minute(stamp);
    if (at !== null) real.add(at);
  }
  for (const at of real) carried.delete(at);
  return carried;
}

/**
 * The finished game's settlement row: the LAST served row, when its value is
 * the result the served verdict names, or a served witness — a venue point of
 * kind `final` under a readable evidence contract, or ESPN's `Final` row —
 * states it at the same instant and value.
 */
export function settlementIndex(
  rows: HockeyJourneyServedRow[],
  history: EventHistoryResponse,
  event: EventDetailResponse,
): number | null {
  if (!isFinishedStatus(event.status) && !isFinishedStatus(history.status)) return null;
  const last = rows[rows.length - 1];
  if (!last || last.home === null) return null;
  const outcome = servedOutcome(event.status, event.home_score, event.away_score, event.hero_settled_result);
  const settled = outcome === "home" ? 1 : outcome === "away" ? 0 : outcome === "draw" ? 0.5 : null;
  if (settled !== null && last.home === settled) return last.index;
  return witnessesSettlement(last, history) ? last.index : null;
}

function witnessesSettlement(row: HockeyJourneyServedRow, history: EventHistoryResponse): boolean {
  if (row.t === null || row.home === null) return false;
  if (evidenceResolutionS(history.evidence_contract) !== null) {
    for (const points of Object.values(history.win_prob_history ?? {})) {
      for (const p of points ?? []) {
        if (p.evidence?.kind === "final" && parseMs(p.timestamp) === row.t && p.home_probability === row.home) {
          return true;
        }
      }
    }
  }
  return (history.espn_history ?? []).some(
    (p) => p.period === "Final" && parseMs(p.timestamp) === row.t && p.home_probability === row.home,
  );
}

/** The rows that are not readings at all. */
export function removedRows(
  history: EventHistoryResponse,
  event: EventDetailResponse,
  line: HockeyJourneyLine,
  rows: HockeyJourneyServedRow[],
): Set<number> {
  const removed = new Set<number>();
  const terminal = settlementIndex(rows, history, event);
  if (terminal !== null) removed.add(terminal);
  if (line !== "blend") return removed;
  const last = rows[rows.length - 1];
  if (history.blend_edge_pinned === true && last) removed.add(last.index);
  const carried = carriedForwardMinutes(history);
  if (carried.size > 0) {
    for (const row of rows) {
      if (row.t === null) continue;
      if (carried.has(Math.floor(row.t / 60_000) * 60_000)) removed.add(row.index);
    }
  }
  return removed;
}

function entriesOf(rows: HockeyJourneyServedRow[], removed: Set<number>): Entry[] {
  let previous: number | null = null;
  const out: Entry[] = [];
  for (const row of rows) {
    if (removed.has(row.index)) continue;
    let t = row.t;
    if (t !== null && previous !== null && t <= previous) t = null;
    if (t !== null) previous = t;
    out.push({ row, t });
  }
  return out;
}

/** The listed start, only when it is a kick-off and not a placeholder. */
export function historyKickoff(history: EventHistoryResponse, event: EventDetailResponse): number | null {
  if (event.start_is_tbd === true) return null;
  if (history.commence_time_is_kickoff === false) return null;
  return parseMs(event.commence_time);
}

/**
 * Split one stretch of readable vertices where the chart's own rule breaks it.
 * `gapStart` is the rule's game-start window: the listed commence, always.
 */
function segments(stretch: Vertex[], gapStart: number | null): Vertex[][] {
  if (stretch.length < 2) return stretch.length === 1 ? [stretch] : [];
  const support = classifySeriesSupport(
    stretch.map((v) => ({ atMs: v.t })),
    { gameStartMs: gapStart, domainEndMs: null },
  );
  const holes = new Set(
    support.unsupported.filter((iv) => iv.kind === "interior").map((iv) => `${iv.fromMs}>${iv.toMs}`),
  );
  const out: Vertex[][] = [];
  let run: Vertex[] = [stretch[0]];
  for (let i = 1; i < stretch.length; i += 1) {
    if (holes.has(`${stretch[i - 1].t}>${stretch[i].t}`)) {
      out.push(run);
      run = [stretch[i]];
    } else {
      run.push(stretch[i]);
    }
  }
  out.push(run);
  return out;
}

/**
 * `kickoff` is the confirmed start that splits pregame from game (null when
 * unconfirmed: then no row is pregame); `gapStart` is the gap rule's window,
 * the listed commence.
 */
function drawnSeries(
  entries: Entry[],
  side: HockeyJourneySide,
  phase: HockeyJourneyPhase,
  kickoff: number | null,
  gapStart: number | null,
  end: number,
  nowMs: number,
): Drawn {
  let lastPregamePosition = -1;
  if (kickoff !== null) {
    entries.forEach((entry, i) => {
      if (entry.t !== null && entry.t < kickoff && entry.t <= nowMs && sideValue(entry.row, side) !== null) {
        lastPregamePosition = i;
      }
    });
  }
  const pregameEntry = lastPregamePosition >= 0 ? entries[lastPregamePosition] : null;
  const pregameValue = pregameEntry ? sideValue(pregameEntry.row, side) : null;
  const lastPregame: Vertex | null =
    pregameEntry && pregameEntry.t !== null && pregameValue !== null
      ? { entry: pregameEntry, t: pregameEntry.t, p: pregameValue }
      : null;

  let start = -1;
  let stop = -1;
  const limit = Math.min(end, nowMs);
  if (kickoff === null) {
    // No split to make: every readable dated row up to the frame's end, as one history.
    start = entries.findIndex((e) => e.t !== null);
    entries.forEach((e, i) => {
      if (e.t !== null && e.t <= limit) stop = i;
    });
  } else if (phase === "before") {
    const floor = kickoff - BEFORE_WINDOW_MS;
    start = entries.findIndex((e) => e.t !== null && e.t >= floor);
    stop = lastPregamePosition;
  } else {
    start = lastPregamePosition >= 0 ? lastPregamePosition : entries.findIndex((e) => e.t !== null && e.t >= kickoff);
    entries.forEach((e, i) => {
      if (e.t !== null && e.t <= limit) stop = i;
    });
  }
  if (start < 0 || stop < 0 || start > stop) return { runs: [], lastPregame, pregameDrawn: false };

  const stretches: Vertex[][] = [[]];
  for (const entry of entries.slice(start, stop + 1)) {
    const value = sideValue(entry.row, side);
    if (entry.t !== null && value !== null) {
      stretches[stretches.length - 1].push({ entry, t: entry.t, p: value });
    } else if (stretches[stretches.length - 1].length > 0) {
      stretches.push([]);
    }
  }
  const runs: Vertex[][] = [];
  for (const stretch of stretches) {
    for (const run of segments(stretch, gapStart)) if (run.length > 0) runs.push(run);
  }
  const pregameDrawn =
    lastPregame !== null && runs.some((run) => run.some((v) => v.entry.row.index === lastPregame.entry.row.index));
  return { runs, lastPregame, pregameDrawn };
}

/**
 * A reading's figure. On a blend row whose away side is the complement, both
 * teams' figures are ONE two-sided decision (`renderedComplementPercents`).
 */
function readingFigure(vertex: Vertex, side: HockeyJourneySide): string {
  const row = vertex.entry.row;
  if (row.awayIsComplement && row.home !== null && row.away !== null) {
    const [awayPct, homePct] = renderedComplementPercents(row.home);
    return side === "home"
      ? formatProbabilityPercent(row.home, { rendered: homePct })
      : formatProbabilityPercent(row.away, { rendered: awayPct });
  }
  return formatProbabilityPercent(vertex.p);
}

export function historySeriesId(line: HockeyJourneyLine, eventId: number, side: HockeyJourneySide): string {
  return `${line}:${eventId}:${side}`;
}

export function historyPointId(seriesId: string, timestamp: string): string {
  return `${seriesId}#${timestamp}`;
}

function seriesOf(
  id: string,
  side: HockeyJourneySide,
  name: string,
  drawn: Drawn,
  phase: HockeyJourneyPhase,
  kickoff: number | null,
): HockeyJourneyHistorySeries {
  const hollow = drawn.pregameDrawn && drawn.lastPregame ? drawn.lastPregame.entry.row.index : null;
  const runs = drawn.runs.map((run) =>
    run.map((v) => ({
      id: historyPointId(id, v.entry.row.timestamp),
      t: v.t,
      p: v.p,
      hollow: v.entry.row.index === hollow,
      row: v.entry.row.index,
      figure: readingFigure(v, side),
    })),
  );
  // With no confirmed start the baseline slot says why it holds no reading.
  let before: HockeyJourneyReading = {
    kind: "absent",
    words: kickoff === null ? HISTORY_WORDS.unconfirmedStartWords : HISTORY_WORDS.notRecorded,
  };
  if (drawn.lastPregame) {
    const v = drawn.lastPregame;
    before = {
      kind: "reading",
      figure: readingFigure(v, side),
      provenance: `${HISTORY_WORDS.lastPregame} · ${clockWords(v.t) ?? ""}`,
      pointId: drawn.pregameDrawn ? historyPointId(id, v.entry.row.timestamp) : null,
    };
  }
  let recorded: HockeyJourneyReading = { kind: "absent", words: HISTORY_WORDS.notRecorded };
  const lastRun = drawn.runs[drawn.runs.length - 1];
  const latest = lastRun ? lastRun[lastRun.length - 1] : undefined;
  if (phase === "live" && kickoff !== null && latest && latest.t >= kickoff) {
    recorded = {
      kind: "reading",
      figure: readingFigure(latest, side),
      provenance: `${HISTORY_WORDS.recorded} ${clockWords(latest.t) ?? ""}`,
      pointId: historyPointId(id, latest.entry.row.timestamp),
    };
  }
  return { id, side, name, runs, before, recorded };
}

/** A period START, as native's column label admits it: not an end, "Final", or a break. */
const PERIOD_START_LABEL = /^(?:P\d+|Q\d+|\d+H|OT\d*|SO)$/;

function guidesFor(
  history: EventHistoryResponse,
  event: EventDetailResponse,
  lower: number,
  upper: number,
): HockeyJourneyGuide[] {
  const guides: Array<{ guide: HockeyJourneyGuide; order: number }> = [];
  const boundaries = derivePeriodBoundaries(
    history.espn_history,
    history.win_prob_history,
    history.scoring_plays,
    history.period_markers,
    event.sport,
  );
  for (const b of boundaries) {
    const t = parseMs(b.timestamp);
    if (t === null || t < lower || t > upper || !PERIOD_START_LABEL.test(b.label)) continue;
    guides.push({ guide: { id: `period:${b.label}`, t, label: b.label, kind: "period" }, order: guides.length });
  }
  (history.scoring_plays ?? []).forEach((play, index) => {
    const t = parseMs(play.timestamp);
    if (t === null || t < lower || t > upper) return;
    const text = (play.short_text || play.description || "").trim();
    const label = [play.type, text].filter((part) => !!part).join(" · ");
    if (!label) return;
    guides.push({ guide: { id: `play:${play.timestamp}#${index}`, t, label, kind: "play" }, order: guides.length });
  });
  return guides.sort((a, b) => a.guide.t - b.guide.t || a.order - b.order).map((g) => g.guide);
}

/** Whole-hour ticks inside the frame, thinned to the phone budget; else the two ends. */
function xTicksFor(lower: number, upper: number, nowMs: number): Array<{ t: number; label: string }> {
  const format = axisTimeFormat(lower, upper, nowMs);
  const hour = 60 * 60 * 1000;
  const first = new Date(lower);
  first.setMinutes(0, 0, 0);
  if (first.getTime() < lower) first.setTime(first.getTime() + hour);
  const hours: number[] = [];
  for (let t = first.getTime(); t <= upper; t += hour) hours.push(t);
  let picked: number[];
  if (hours.length === 0) {
    picked = upper > lower ? [lower, upper] : [lower];
  } else {
    const step = Math.max(1, Math.ceil(hours.length / MAX_X_TICKS));
    picked = hours.filter((_, i) => i % step === 0);
  }
  return picked.map((t) => ({ t, label: formatAxisTime(t, format) }));
}

const Y_TICKS = [
  { p: 0, label: "0%" },
  { p: 0.5, label: "50%" },
  { p: 1, label: "100%" },
];

function summaryOf(teams: Array<[string, boolean]>): string {
  const shown = teams.filter(([, drawn]) => drawn).map(([name]) => name);
  const missing = teams.filter(([, drawn]) => !drawn).map(([name]) => name);
  if (shown.length === 0) return HISTORY_WORDS.noHistory;
  const lead = `${shown.join(" and ")} win probability, recorded observations only.`;
  return missing.length === 0 ? lead : `${lead} No recorded history for ${missing.join(" or ")}.`;
}

/** "Boston Bruins is the other side of the same line: 100% − Minnesota Wild." */
export function complementNote(away: string, home: string): string {
  return `${away} is the other side of the same line: 100% − ${home}.`;
}

function sourceNote(line: HockeyJourneyLine): string {
  return line === "blend" ? HISTORY_WORDS.blendSource : HISTORY_WORDS.consensusSource;
}

/** A response with nothing readable to draw: "No recorded history". */
function absence(
  history: EventHistoryResponse,
  event: EventDetailResponse,
  line: HockeyJourneyLine,
  phase: HockeyJourneyPhase,
  plot: { title: string; words: string | null },
): HockeyJourneyHistory {
  const empty = (side: HockeyJourneySide, name: string): HockeyJourneyHistorySeries => ({
    id: historySeriesId(line, history.event_id ?? event.id, side),
    side,
    name,
    runs: [],
    before: { kind: "absent", words: HISTORY_WORDS.notRecorded },
    recorded: { kind: "absent", words: HISTORY_WORDS.notRecorded },
  });
  return {
    title: HISTORY_WORDS.title,
    caption: phase === "before" ? HISTORY_WORDS.beforeCaption : HISTORY_WORDS.gameCaption,
    line,
    series: [empty("home", event.home_team), empty("away", event.away_team)],
    domain: null,
    guides: [],
    xTicks: [],
    yTicks: [],
    readout: "single",
    beforeLabel: HISTORY_WORDS.pregame,
    recordedLabel: HISTORY_WORDS.recorded,
    markKey: null,
    notes: [sourceNote(line)],
    summary: HISTORY_WORDS.noHistory,
    absence: plot,
    detailsLabel: HISTORY_WORDS.details,
  };
}

/**
 * No history response at all — not arrived yet, or failed; the page does not
 * say which, so neither is claimed. The chart slot says "History unavailable",
 * names no source, draws nothing and offers no working control (the screen
 * renders no Details disclosure over an empty notes list, and there is no
 * retry). The rest of the page composes from its own inputs. Native
 * `HockeyJourneyHistoryAdapter10868.unavailable`.
 */
export function unavailableHistory(event: EventDetailResponse, phase: HockeyJourneyPhase): HockeyJourneyHistory {
  const W = HISTORY_WORDS.historyUnavailable;
  const empty = (side: HockeyJourneySide, name: string): HockeyJourneyHistorySeries => ({
    // Native names the slot's series on the blend; no line is claimed here.
    id: `history:${event.id}:${side}`,
    side,
    name,
    runs: [],
    before: { kind: "absent", words: W },
    recorded: { kind: "absent", words: W },
  });
  return {
    title: HISTORY_WORDS.title,
    caption: phase === "before" ? HISTORY_WORDS.beforeCaption : HISTORY_WORDS.gameCaption,
    line: null,
    series: [empty("home", event.home_team), empty("away", event.away_team)],
    domain: null,
    guides: [],
    xTicks: [],
    yTicks: [],
    readout: "single",
    beforeLabel: W,
    recordedLabel: HISTORY_WORDS.recorded,
    markKey: null,
    notes: [],
    summary: W,
    absence: { title: W, words: null },
    detailsLabel: HISTORY_WORDS.details,
  };
}

/** The finished game's end, as web's own win-probability chart ends it. */
export function historyGameEnd(history: EventHistoryResponse, event: EventDetailResponse): number | null {
  const domain = computeSharedChartDomain(
    history,
    "all",
    event.status,
    event.commence_time,
    event.sport ?? undefined,
  );
  return parseMs(domain?.end);
}

export function hockeyJourneyHistory(
  history: EventHistoryResponse | null | undefined,
  event: EventDetailResponse,
  phase: HockeyJourneyPhase,
  nowMs: number,
): HockeyJourneyHistory {
  if (!history) return unavailableHistory(event, phase);
  const line = historyLine(history);
  // Null when the start is not a confirmed kick-off: the readings still draw, unsplit.
  const kickoff = historyKickoff(history, event);
  // The gap rule's window: the listed commence, whether or not it is a confirmed kick-off.
  const gapStart = parseMs(event.commence_time);
  const rows = servedRows(history, line, event.sport);
  const entries = entriesOf(rows, removedRows(history, event, line, rows));
  const end = phase === "final" ? Math.min(historyGameEnd(history, event) ?? nowMs, nowMs) : nowMs;

  const homeId = historySeriesId(line, history.event_id, "home");
  const awayId = historySeriesId(line, history.event_id, "away");
  const home = drawnSeries(entries, "home", phase, kickoff, gapStart, end, nowMs);
  const away = drawnSeries(entries, "away", phase, kickoff, gapStart, end, nowMs);

  const times = [...home.runs, ...away.runs].flatMap((run) => run.map((v) => v.t));
  if (times.length === 0) return absence(history, event, line, phase, { title: HISTORY_WORDS.noHistory, words: null });
  const first = Math.min(...times);
  const last = Math.max(...times);
  const domain =
    last > first ? { lower: first, upper: last } : { lower: first - SINGLE_INSTANT_PAD_MS, upper: last + SINGLE_INSTANT_PAD_MS };

  const shownAway = [...away.runs.flat(), ...(away.lastPregame ? [away.lastPregame] : [])];
  const complement = shownAway.some((v) => v.entry.row.awayIsComplement)
    ? complementNote(event.away_team, event.home_team)
    : null;

  return {
    title: HISTORY_WORDS.title,
    caption: phase === "before" ? HISTORY_WORDS.beforeCaption : HISTORY_WORDS.gameCaption,
    line,
    series: [
      seriesOf(homeId, "home", event.home_team, home, phase, kickoff),
      seriesOf(awayId, "away", event.away_team, away, phase, kickoff),
    ],
    domain,
    guides: phase === "before" || kickoff === null ? [] : guidesFor(history, event, domain.lower, last),
    xTicks: xTicksFor(domain.lower, domain.upper, nowMs),
    yTicks: Y_TICKS,
    readout: kickoff !== null && phase === "live" ? "beforeAndRecorded" : "single",
    beforeLabel: kickoff === null ? HISTORY_WORDS.unconfirmedStart : HISTORY_WORDS.pregame,
    recordedLabel: HISTORY_WORDS.recorded,
    markKey: kickoff === null ? null : HISTORY_WORDS.hollowKey,
    notes: [sourceNote(line), ...(complement ? [complement] : []), HISTORY_WORDS.gapsNote],
    summary:
      summaryOf([
        [event.home_team, home.runs.length > 0],
        [event.away_team, away.runs.length > 0],
      ]) + (complement ? ` ${complement}` : ""),
    absence: null,
    detailsLabel: HISTORY_WORDS.details,
  };
}
