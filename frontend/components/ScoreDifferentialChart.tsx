"use client";

import { useState, useMemo, useEffect } from "react";
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { format, parseISO } from "date-fns";
import { makeEnsurePoint, fillMinuteGaps } from "@/lib/chartTimeline";
import { sourceLabel } from "@/lib/sourceColors";
import { sportVocab, playedCountAbsence, playedUnits, withUnit } from "@/lib/marketMapUtils";
import type { PlayedLinescore } from "@/lib/marketMapUtils";
import type {
  OddsHistoryPoint,
  BookmakerHistoryPoint,
  ScoreHistoryPoint,
  ESPNHistoryPoint,
} from "@/lib/types";
import type { PeriodBoundary } from "@/lib/periodMarkers";

interface ScoreDifferentialChartProps {
  history: OddsHistoryPoint[];
  homeTeam: string;
  awayTeam: string;
  commenceTime?: string;
  isLive?: boolean;
  bookmakerHistory?: Record<string, BookmakerHistoryPoint[]>;
  scoreHistory?: ScoreHistoryPoint[];
  /** ESPN history — dense score updates every 60s (supplements sparse ScoreSnapshot data) */
  espnHistory?: ESPNHistoryPoint[];
  currentHomeScore?: number | null;
  currentAwayScore?: number | null;
  eventStatus?: string;
  /** When true, chart fills its parent container height instead of using fixed h-40 */
  fillContainer?: boolean;
  /** Period boundaries for vertical divider annotations */
  periodBoundaries?: PeriodBoundary[];
  /** Home team primary color (hex) for team label styling */
  homeTeamColor?: string;
  /** Away team primary color (hex) for team label styling */
  awayTeamColor?: string;
  /** Home team logo URL (small) */
  homeTeamLogo?: string;
  /** Away team logo URL (small) */
  awayTeamLogo?: string;
  /** Home team abbreviation (e.g. "BOS") from ESPN */
  homeTeamAbbrev?: string;
  /** Away team abbreviation (e.g. "OKC") from ESPN */
  awayTeamAbbrev?: string;
  /** Start timestamp (ISO) from the Win Probability chart — constrains domain to match OddsChart */
  chartStartTime?: string;
  chartEndTime?: string;
  sharedTicks?: string[];
  /** External time range from parent — syncs both charts' All/Since Start toggle */
  externalTimeRange?: "all" | "live";
  onTimeRangeChange?: (range: "all" | "live") => void;
  /**
   * The event's sport key (ux/1034 B5). Decides whether `home_score` counts the
   * thing the projection is quoted in — see `hasActualScoreData`. Omitted, the
   * chart behaves exactly as it always has (`sportVocab` answers `true` for a
   * sport it has not been told about; the field's own note says why that
   * default runs the opposite way from `hasDerivedSpread`'s).
   */
  sportKey?: string;
  /**
   * The event's per-set games line (live/073). The chart does not draw it — a
   * final line has no clock — but a page that HOLDS the games may not tell the
   * reader it did not record them, so the note reads off this.
   */
  linescore?: PlayedLinescore | null;
  /**
   * Whether a totals map is actually rendered further down this page (#3240).
   *
   * The note used to send the reader to "the games map below" on the strength
   * of HOLDING the games, which is a different fact from DRAWING them: the map
   * needs a game-total market to build a rail from, and a tennis page can hold
   * a fresh ESPN games line while its only linked markets are a duel and an
   * exact-score field. Three live US Open pages read that way on 2026-09-05.
   *
   * The caller answers this with `totalsMapRenders(gameMarkets)` — the same
   * selectors `MarketMapSection` builds the card from. It defaults to `false`
   * because the failure is one-directional: a note that states the count where
   * a map does exist is merely redundant, while a note pointing at a card that
   * does not is the bug.
   */
  totalsMapPresent?: boolean;
  /** Prediction market spread/total data from binary contracts */
  pmSpreadData?: {
    implied_spreads?: Record<string, { spread: number; confidence: number; contracts: { threshold: number; probability: number }[] }>;
    implied_totals?: Record<string, { total: number; confidence: number; contracts: { threshold: number; probability: number }[] }>;
    projected_final?: { home_score: number; away_score: number; spread_source: string; total_source: string } | null;
  } | null;
}

type TimeRange = "all" | "live";

const TIME_RANGE_OPTIONS: { value: TimeRange; label: string }[] = [
  { value: "all", label: "All" },
  { value: "live", label: "Since Start" },
];

interface ChartDataPoint {
  timestamp: string;
  time: string;
  projectedDiff: number | null;
  actualDiff: number | null;
  [key: string]: string | number | null | undefined;
}

/**
 * Combined chart showing projected score differential (spread) and actual score difference.
 * Y-axis centered at 0. Positive = home team leading, negative = away team leading.
 */
export default function ScoreDifferentialChart({
  history,
  homeTeam,
  awayTeam,
  commenceTime,
  isLive = false,
  bookmakerHistory,
  scoreHistory,
  espnHistory,
  currentHomeScore,
  currentAwayScore,
  eventStatus,
  fillContainer = false,
  periodBoundaries,
  homeTeamColor,
  awayTeamColor,
  homeTeamLogo,
  awayTeamLogo,
  homeTeamAbbrev,
  awayTeamAbbrev,
  chartStartTime,
  chartEndTime,
  sharedTicks,
  externalTimeRange,
  onTimeRangeChange,
  sportKey,
  linescore,
  totalsMapPresent = false,
  pmSpreadData,
}: ScoreDifferentialChartProps) {
  const isClosed = eventStatus === "closed" || eventStatus === "completed";

  const hasPostStartData = useMemo(() => {
    if (!commenceTime) return false;
    const cutoffTime = parseISO(commenceTime);
    // Check any data source for post-start data
    if (history?.some((point) => parseISO(point.timestamp) >= cutoffTime)) return true;
    if (scoreHistory?.some((point) => parseISO(point.timestamp) >= cutoffTime)) return true;
    if (espnHistory?.some((point) => parseISO(point.timestamp) >= cutoffTime)) return true;
    return false;
  }, [history, scoreHistory, espnHistory, commenceTime]);

  const defaultTimeRange: TimeRange =
    (isClosed || isLive) && hasPostStartData ? "live" : "all";
  const [internalTimeRange, setInternalTimeRange] = useState<TimeRange>(defaultTimeRange);

  const timeRange = externalTimeRange ?? internalTimeRange;
  const handleTimeRangeChange = (range: TimeRange) => {
    if (onTimeRangeChange) onTimeRangeChange(range);
    else setInternalTimeRange(range);
  };

  // Sync timeRange when data loads asynchronously
  const [hasUserOverridden, setHasUserOverridden] = useState(false);
  useEffect(() => {
    if (!hasUserOverridden && !externalTimeRange && defaultTimeRange === "live") {
      setInternalTimeRange("live");
    }
  }, [defaultTimeRange, hasUserOverridden]);

  // Filter projected history based on time range
  // Use commenceTime directly — no "smart" start skipping (see OddsChart for rationale)
  const filteredHistory = useMemo(() => {
    if (!history || history.length === 0) return [];
    if (timeRange === "all") return history;
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    return history.filter((point) => parseISO(point.timestamp) >= cutoffTime);
  }, [history, timeRange, commenceTime]);

  // Filter bookmaker history based on time range
  const filteredBookmakerHistory = useMemo(() => {
    if (!bookmakerHistory || Object.keys(bookmakerHistory).length === 0)
      return {};
    const entries = Object.entries(bookmakerHistory);
    if (timeRange === "all") {
      const filtered: Record<string, BookmakerHistoryPoint[]> = {};
      for (const [bookmaker, points] of entries) {
        const withScores = points.filter(
          (point) =>
            point.projected_home_score !== null &&
            point.projected_home_score !== undefined
        );
        if (withScores.length > 0) filtered[bookmaker] = withScores;
      }
      return filtered;
    }
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    const filtered: Record<string, BookmakerHistoryPoint[]> = {};
    for (const [bookmaker, points] of entries) {
      const withScores = points.filter((point) => {
        const hasScores =
          point.projected_home_score !== null &&
          point.projected_home_score !== undefined;
        if (!hasScores) return false;
        return parseISO(point.timestamp) >= cutoffTime;
      });
      if (withScores.length > 0) filtered[bookmaker] = withScores;
    }
    return filtered;
  }, [bookmakerHistory, timeRange, commenceTime]);

  // Filter score history based on time range
  const filteredScoreHistory = useMemo(() => {
    if (!scoreHistory || scoreHistory.length === 0) return [];
    if (timeRange === "all") return scoreHistory;
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    return scoreHistory.filter(
      (point) => parseISO(point.timestamp) >= cutoffTime
    );
  }, [scoreHistory, timeRange, commenceTime]);

  // Filter ESPN history based on time range (dense score updates every 60s)
  const filteredEspnHistory = useMemo(() => {
    if (!espnHistory || espnHistory.length === 0) return [];
    if (timeRange === "all") return espnHistory;
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    return espnHistory.filter(
      (point) => parseISO(point.timestamp) >= cutoffTime
    );
  }, [espnHistory, timeRange, commenceTime]);

  const bookmakers = useMemo(
    () => Object.keys(filteredBookmakerHistory),
    [filteredBookmakerHistory]
  );

  const hasProjectedScoreData = useMemo(() => {
    if (!history || history.length === 0) return false;
    return history.some(
      (point) =>
        point.projected_home_score !== null &&
        point.projected_away_score !== null
    );
  }, [history]);

  /**
   * ═══ ux/1034 B5: THE FLAT LINE WAS A UNIT ERROR ═══
   *
   * Alex, on `/events/15293830` (Marozsan–Zheng): *"Score Differential is in
   * GAMES (the green projection is the books' game spread); the bug is 'Actual
   * Score Diff' is fed the SET score so it sits flat."*
   *
   * Exactly right. `score_history` for that match is four points — `0-0`,
   * `0-1`, `0-2`, `0-3` — and those are SETS, while `projected_home_score`
   * 15.1 / `projected_away_score` 19.7 are GAMES. The orange line was a
   * three-unit step function drawn under a ±5 game axis, and next to a
   * fluid win-probability chart it reads as a broken widget rather than as
   * the category error it is.
   *
   * **The fix Alex asked for needs data we do not hold.** "Actual = cumulative
   * games differential from ESPN's linescore" is the right answer and the
   * linescore is not in any payload this page fetches: `/api/events/{id}`
   * carries `home_score`/`away_score` as sets and nothing per-set, and
   * `espn_history` is EMPTY for tennis (0 of 798 snapshots on this event).
   * Capturing it is a backend change and is on the bus.
   *
   * ⚠️ **THAT BACKEND CHANGE SHIPPED (live/073) AND THE PARAGRAPH ABOVE IS NOW
   * HISTORY.** `/api/events/{id}` carries `linescore` — the per-set games in
   * our home/away order — for every anchored tennis row. What it does NOT
   * carry is those games AGAINST A CLOCK: the line is a final (or
   * as-of-now) state, and `score_history`'s four stamps are set boundaries,
   * so an actual line drawn here would have one point per set and not one per
   * game. That is a chart-shape decision with its own design, deliberately not
   * taken by the ship that made it possible. What live/073 changes here is only
   * the SENTENCE — a page holding the games may not tell a reader it does not
   * hold them.
   *
   * What ships here is the half that does not need it: the widget keeps its
   * projection, and STOPS DRAWING A LINE IN THE WRONG UNIT. A number in the
   * wrong unit is worse than an absent one — it looks sourced.
   *
   * `sportVocab` decides, not a `startsWith("tennis")` here: the same question
   * is asked by the two market maps on this page, and two answers to it is how
   * one of them comes to disagree with the other.
   */
  const scoreboardCountsTheUnit = sportVocab(sportKey).scoreboardCountsTheUnit;

  const hasActualScoreData =
    scoreboardCountsTheUnit &&
    (filteredScoreHistory.length > 0 ||
      filteredEspnHistory.some((p) => p.home_score != null && p.away_score != null));

  /**
   * The sentence the chart owes a reader whose actual line is missing.
   *
   * #3136: the claim itself comes from `playedCountAbsence` — shared with the
   * Games map's subtitle a few hundred pixels down the same page, because the
   * two are missing the same number for the same reason and a reader who is
   * told "not captured YET" here and "did not record" there learns to trust
   * neither. Only the wrapping sentence is this widget's own.
   */
  // Short team names, for the axis labels and for the unit note below.
  const homeShort = homeTeamAbbrev || homeTeam.split(" ").pop() || homeTeam;
  const awayShort = awayTeamAbbrev || awayTeam.split(" ").pop() || awayTeam;

  const unitMismatchNote = (() => {
    if (scoreboardCountsTheUnit) return null;
    const vocab = sportVocab(sportKey);
    if (!vocab.scoreboardUnit) return null;
    // live/073: the page holds the games now. It may still not draw them here —
    // a final line has no clock — but the claim has to change with the fact, and
    // the reader is told where the number IS rather than that there is none.
    const played = playedUnits(vocab, { home: null, away: null }, linescore);
    if (played) {
      const lead = `The scoreboard reports ${vocab.scoreboardUnit}, so the line below is the books' projected ${vocab.unitSingular} margin.`;
      // #3240: holding the number and drawing the map are two facts, and the
      // pointer may only be printed on the second. Where there is no card to
      // point at, the note carries the count itself — that page knew the games
      // and printed them nowhere.
      //
      // NAMED, not `17-15`. The settled hero prints the line WINNER-FIRST
      // (`eventOutcome.ts`, reversed when the winner is away) while a games
      // count is held in home/away order, so a bare pair sits under a line
      // running the other way and half the readers will take it backwards —
      // the hazard `formatLinescore`'s own note is about. Naming the sides
      // makes the order unreadable-wrong instead of silently-wrong.
      //
      // Tense tracks the match, like the absence clause below it (#3136): a
      // finished match did not go on winning games after it ended.
      const won = isClosed ? "won" : "has won";
      return totalsMapPresent
        ? `${lead} The ${vocab.unit} played are on the ${vocab.totalTitle.toLowerCase()} below.`
        : `${lead} ${homeShort} ${won} ${withUnit(played.home, vocab)} to ${awayShort}'s ${played.away}.`;
    }
    return `The scoreboard reports ${vocab.scoreboardUnit}, so ${playedCountAbsence(vocab.unit, isClosed)}. The line below is the books' projected ${vocab.unitSingular} margin.`;
  })();

  // Build chart data by merging projected and actual score data on timeline.
  // Bucket by minute so each "h:mm a" label is unique — required for
  // ReferenceLine period markers to match categorical XAxis values.
  const chartBuild = useMemo(() => {
    const dataMap = new Map<string, ChartDataPoint>();

    const ensurePoint = makeEnsurePoint<ChartDataPoint>(dataMap, () => ({
      projectedDiff: null,
      actualDiff: null,
    }));

    // Seed ALL filtered history timestamps so x-axis matches the Win Probability chart.
    // Without this, points lacking projected_home_score would be skipped and the
    // chart would start later than the Win Probability chart.
    for (const point of filteredHistory) {
      ensurePoint(point.timestamp);
    }

    // Add projected score differentials where available
    for (const point of filteredHistory) {
      if (
        point.projected_home_score === null ||
        point.projected_away_score === null
      )
        continue;

      const diff = point.projected_home_score - point.projected_away_score;
      const dp = ensurePoint(point.timestamp);
      dp.projectedDiff = Math.round(diff * 10) / 10;

      // Expand valid_until for flat-line rendering
      if (point.valid_until) {
        const endTime = parseISO(point.valid_until);
        const startTime = parseISO(point.timestamp);
        if (endTime.getTime() - startTime.getTime() > 60000) {
          const endDp = ensurePoint(point.valid_until);
          if (endDp.projectedDiff === null) endDp.projectedDiff = Math.round(diff * 10) / 10;
        }
      }
    }

    // Add bookmaker differential lines
    for (const [bookmaker, points] of Object.entries(
      filteredBookmakerHistory
    )) {
      for (const point of points) {
        if (
          point.projected_home_score === null ||
          point.projected_home_score === undefined
        )
          continue;
        const awayScore = point.projected_away_score ?? 0;
        const diff =
          Math.round((point.projected_home_score - awayScore) * 10) / 10;

        const dp = ensurePoint(point.timestamp);
        dp[`${bookmaker}_diff`] = diff;

        // Expand valid_until
        if (point.valid_until) {
          const endTime = parseISO(point.valid_until);
          const startTime = parseISO(point.timestamp);
          if (endTime.getTime() - startTime.getTime() > 60000) {
            const endDp = ensurePoint(point.valid_until);
            if (endDp[`${bookmaker}_diff`] === undefined) {
              endDp[`${bookmaker}_diff`] = diff;
            }
          }
        }
      }
    }

    // Ensure all bookmaker keys exist on all data points
    const allBookmakers = Object.keys(filteredBookmakerHistory);
    const allPoints = Array.from(dataMap.values());
    for (const point of allPoints) {
      for (const bookmaker of allBookmakers) {
        if (point[`${bookmaker}_diff`] === undefined) {
          point[`${bookmaker}_diff`] = null;
        }
      }
    }

    // Add actual score differences from ScoreSnapshot (authoritative when available)
    for (const point of filteredScoreHistory) {
      const diff = point.home_score - point.away_score;
      const dp = ensurePoint(point.timestamp);
      dp.actualDiff = diff;
    }

    // Supplement with ESPN history scores (dense 60s updates, fills gaps between sparse ScoreSnapshots)
    for (const point of filteredEspnHistory) {
      if (point.home_score == null || point.away_score == null) continue;
      const dp = ensurePoint(point.timestamp);
      // Only set if ScoreSnapshot hasn't already set this minute's value
      if (dp.actualDiff === null) {
        dp.actualDiff = point.home_score - point.away_score;
      }
    }

    // Fill missing minutes for uniform x-axis spacing.
    // Both charts use categorical XAxis where each category gets equal pixel width.
    // Without filling gaps, this chart has fewer categories than OddsChart,
    // causing different pixel-per-minute spacing and visible x-axis misalignment.
    // Determine chart domain from authoritative game timeline, not from
    // whatever data happens to exist. commenceTime is the game start;
    // the last ESPN/score/odds timestamp is the game end (or current time if live).
    const allTimestamps = Array.from(dataMap.keys()).sort();
    if (allTimestamps.length >= 2 || commenceTime) {
      let first = allTimestamps.length >= 2
        ? parseISO(allTimestamps[0])
        : parseISO(commenceTime!);
      let last = allTimestamps.length >= 2
        ? parseISO(allTimestamps[allTimestamps.length - 1])
        : first;

      // Sync domain with OddsChart so both charts have identical x-axis
      if (chartStartTime) {
        const startFromParent = parseISO(chartStartTime);
        startFromParent.setSeconds(0, 0);
        first = startFromParent;
      } else if (timeRange === "live" && commenceTime) {
        // Fallback: "Since Start" mode starts at commenceTime
        const gameStart = parseISO(commenceTime);
        gameStart.setSeconds(0, 0);
        if (gameStart < first) first = gameStart;
      }

      if (chartEndTime) {
        const endFromParent = parseISO(chartEndTime);
        endFromParent.setSeconds(0, 0);
        last = endFromParent;  // Match exactly, don't just extend
      }

      fillMinuteGaps(first, last, ensurePoint);
    }

    // Ensure period boundary timestamps have matching chart categories
    if (periodBoundaries && periodBoundaries.length > 0) {
      for (const b of periodBoundaries) {
        ensurePoint(b.timestamp);
      }
    }

    // Add prediction market implied spread as a constant line at current value
    // (This is a snapshot, not a time series — we only have the current implied spread)
    if (pmSpreadData?.implied_spreads) {
      const allPts = Array.from(dataMap.values());
      for (const [source, data] of Object.entries(pmSpreadData.implied_spreads)) {
        if (source === "sportsbook") continue; // Already shown as projected spread
        const key = `pm_${source}_spread`;
        for (const pt of allPts) {
          // Show the implied spread as a flat line across all timestamps
          pt[key] = data.spread;
        }
      }
    }

    // Prune points outside the shared domain so category count matches OddsChart exactly
    const domainStart = chartStartTime ? parseISO(chartStartTime).getTime() : -Infinity;
    const domainEnd = chartEndTime ? parseISO(chartEndTime).getTime() : Infinity;
    for (const [key, pt] of dataMap) {
      const t = parseISO(pt.timestamp).getTime();
      if (t < domainStart || t > domainEnd) dataMap.delete(key);
    }

    const points = Array.from(dataMap.values()).sort(
      (a, b) =>
        parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime()
    );

    // ── WHERE THIS CHART ACTUALLY HAS INK (CERT-1989, corrected by CERT-1995) ──
    //
    // Computed HERE — last, after the shared-domain prune above — because a
    // point outside the domain is deleted and never drawn, so a span taken
    // earlier could be bounded by a category that does not exist by the time
    // anything renders. That was CERT-1995's second finding.
    //
    // And only over the series THIS RENDER ENABLES, which was its first and
    // sharper one. `actualDiff` is written for tennis and then deliberately not
    // drawn: `home_score` counts SETS while the projection is quoted in GAMES,
    // so ux/1034 B5 suppresses the line rather than plot a wrong-unit series.
    // Counting those values put a chip over blank visible space on exactly the
    // sport this whole queue is about. A value in the data is not a line on the
    // screen — the same mistake as bounding by timestamps, one level in.
    //
    // The remaining keys are safe against the synthesis above without needing to
    // run before it: `fillMinuteGaps` and the marker categories both insert
    // points whose score values stay null (this chart has no forward-fill), and
    // `pm_*_spread` — painted onto every point, "a snapshot, not a time series"
    // by its own comment — is excluded by name. Bookmaker lines are always
    // rendered, so they always count.
    const drawnScoreKeys = [
      ...(hasProjectedScoreData ? ["projectedDiff"] : []),
      ...(hasActualScoreData ? ["actualDiff"] : []),
      ...allBookmakers.map((b) => `${b}_diff`),
    ];
    let scoreFrom: number | null = null;
    let scoreTo: number | null = null;
    for (const pt of points) {
      if (!drawnScoreKeys.some((k) => typeof pt[k] === "number")) continue;
      const t = parseISO(pt.timestamp).getTime();
      if (scoreFrom === null || t < scoreFrom) scoreFrom = t;
      if (scoreTo === null || t > scoreTo) scoreTo = t;
    }
    const scoreSpan =
      scoreFrom === null ? null : { from: scoreFrom, to: scoreTo as number };

    return { points, scoreSpan };
  }, [filteredHistory, filteredBookmakerHistory, filteredScoreHistory, filteredEspnHistory, chartStartTime, chartEndTime, pmSpreadData, periodBoundaries, hasProjectedScoreData, hasActualScoreData]);

  const chartData = chartBuild.points;
  /** Where this chart's score lines actually start and end — see the build. */
  const scoreSpan = chartBuild.scoreSpan;

  // Filter period boundaries, deduplicate close markers, alternate label positions
  const filteredPeriodBoundaries = useMemo(() => {
    if (!periodBoundaries || periodBoundaries.length === 0 || chartData.length === 0) return [];

    // A MARKER NEEDS A SCORE LINE UNDER IT, NOT A CATEGORY (CERT-1989).
    // `scoreSpan` is the extent of the drawn score series, measured before this
    // component inserted the marker timestamps themselves. No score line means
    // no marker: a chip cannot mark a period on a chart with nothing plotted.
    if (!scoreSpan) return [];
    const chartStart = scoreSpan.from;
    const chartEnd = scoreSpan.to;

    // Label spacing is a PIXEL problem, so it is measured on the x-axis — the
    // full category extent — and not on the drawn subset above.
    const chartDuration =
      parseISO(chartData[chartData.length - 1].timestamp).getTime() -
      parseISO(chartData[0].timestamp).getTime();
    const minSpacing = Math.max(chartDuration * 0.05, 180_000);

    const filtered = periodBoundaries
      .filter((b) => {
        const t = parseISO(b.timestamp).getTime();
        return t >= chartStart && t <= chartEnd;
      })
      .sort((a, b) => parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime());

    const deduped: typeof filtered = [];
    for (const b of filtered) {
      const t = parseISO(b.timestamp).getTime();
      if (deduped.length > 0) {
        const prevT = parseISO(deduped[deduped.length - 1].timestamp).getTime();
        if (t - prevT < minSpacing) {
          deduped[deduped.length - 1] = b;
          continue;
        }
      }
      deduped.push(b);
    }

    // Cap at 12 labels max to prevent overlap on dense games (baseball)
    const capped = deduped.length > 12
      ? deduped.filter((_, i) => i % Math.ceil(deduped.length / 12) === 0)
      : deduped;

    return capped.map((b, i) => ({
      ...b,
      time: format(parseISO(b.timestamp), "h:mm a"),
      labelPosition: i % 2 === 0 ? "insideTopLeft" : "insideTopRight",
    }));
  }, [periodBoundaries, chartData, scoreSpan]);

  // Early returns — show chart if we have ANY data (projected or actual scores)
  if ((!history || history.length === 0) && !hasActualScoreData) return null;
  if (!hasProjectedScoreData && !hasActualScoreData) {
    return (
      <div className="text-center py-4 text-sm text-text-muted">
        Score data is not available for this event.
      </div>
    );
  }
  if (chartData.length === 0) return null;

  // Calculate Y-axis domain symmetrically around 0
  const allDiffValues = chartData
    .flatMap((d) => {
      const values: number[] = [];
      if (d.projectedDiff !== null) values.push(d.projectedDiff);
      if (d.actualDiff !== null) values.push(d.actualDiff);
      return values;
    })
    .filter((v): v is number => v !== null);

  const maxAbs =
    allDiffValues.length > 0
      ? Math.max(...allDiffValues.map(Math.abs)) + 1
      : 5;
  // Make symmetric around 0, rounding up to nearest 2 for a tighter fit
  const domainMax = Math.max(2, Math.ceil(maxAbs / 2) * 2);

  // #3240: `homeShort`/`awayShort` are derived above the unit note, which also
  // names the two sides. One definition, so the axis and the sentence under it
  // cannot end up calling the same player two different things.

  // Custom tooltip
  const CustomTooltip = ({
    active,
    payload,
    label,
  }: {
    active?: boolean;
    payload?: Array<{
      value: number;
      name: string;
      color: string;
      dataKey: string;
    }>;
    label?: string;
  }) => {
    if (active && payload && payload.length) {
      const projectedEntry = payload.find(
        (e) => e.dataKey === "projectedDiff" && e.value !== null
      );
      const actualEntry = payload.find(
        (e) => e.dataKey === "actualDiff" && e.value !== null
      );
      const bookmakerEntries = payload.filter(
        (e) =>
          e.dataKey !== "projectedDiff" &&
          e.dataKey !== "actualDiff" &&
          e.value !== null
      );

      const formatDiff = (val: number) => {
        if (val === 0) return "Even";
        const leader = val > 0 ? homeShort : awayShort;
        return `${leader} +${Math.abs(val).toFixed(1)}`;
      };

      return (
        <div className="bg-surface-card p-3 rounded-lg shadow-lg border border-white/10 max-w-xs">
          <p className="text-xs text-text-muted mb-2">{label}</p>
          {projectedEntry && (
            <p className="text-sm font-semibold text-emerald-600">
              Projected: {formatDiff(projectedEntry.value)}
            </p>
          )}
          {actualEntry && (
            <p className="text-sm font-semibold text-orange-600">
              Actual: {formatDiff(actualEntry.value)}
            </p>
          )}
          {payload?.find(e => e.dataKey === "pm_kalshi_spread" && e.value !== null) && (
            <p className="text-sm font-semibold" style={{ color: "#7c3aed" }}>
              Kalshi: {formatDiff(payload!.find(e => e.dataKey === "pm_kalshi_spread")!.value)}
            </p>
          )}
          {payload?.find(e => e.dataKey === "pm_polymarket_spread" && e.value !== null) && (
            <p className="text-sm font-semibold" style={{ color: "#db2777" }}>
              Polymarket: {formatDiff(payload!.find(e => e.dataKey === "pm_polymarket_spread")!.value)}
            </p>
          )}
          {bookmakerEntries.length > 0 && (
            <div className="mt-2 pt-2 border-t border-white/10">
              <p className="text-xs text-text-muted mb-1">By sportsbook:</p>
              {bookmakerEntries.map((entry) => {
                const bookmaker = entry.dataKey.replace("_diff", "");
                return (
                  <p key={bookmaker} className="text-xs text-text-muted">
                    {bookmaker}: {formatDiff(entry.value)}
                  </p>
                );
              })}
            </div>
          )}
        </div>
      );
    }
    return null;
  };

  return (
    <div
      className={fillContainer ? "flex flex-col h-full gap-1" : "space-y-3"}
      /* ux/1034 B5: WHICH SERIES THIS CHART WILL DRAW, on the wrapper.
         recharts renders nothing inside `ResponsiveContainer` without a
         viewport, so a server render — which is all a guard or the capture rig
         can see — cannot observe a `<Line>` or a legend entry. Without this the
         suppression would be untestable except through the sentence beside it,
         and a sentence is not the claim: the claim is that no set count is
         plotted on a games axis. It is also true in a browser, which is where
         somebody debugging this will look first. */
      data-actual-series={hasActualScoreData ? "true" : "false"}
      data-projected-series={hasProjectedScoreData ? "true" : "false"}
      /* How many period chips this chart will draw, for the same reason as the
         two attributes above and as OddsChart's (CERT-1989): recharts renders
         no `<ReferenceLine>` inside `ResponsiveContainer` without a viewport,
         so a guard hunting the label in server markup passes on both arms. */
      data-period-boundaries={filteredPeriodBoundaries.length}
    >
      {/* Time range selector */}
      <div className="flex flex-wrap items-center gap-1 shrink-0">
        {TIME_RANGE_OPTIONS.map((option) => (
          <button
            key={option.value}
            onClick={() => { handleTimeRangeChange(option.value); setHasUserOverridden(true); }}
            className={`font-medium rounded-full transition-colors ${
              fillContainer
                ? `px-[0.4vw] py-[0.1vh] text-[0.9vh] ${
                    timeRange === option.value
                      ? "bg-surface-card/10 text-white/40"
                      : "text-white/15 hover:text-white/25"
                  }`
                : `px-3 py-1.5 text-xs ${
                    timeRange === option.value
                      ? "bg-text-primary text-surface-deep"
                      : "bg-surface-elevated text-text-secondary hover:bg-surface-border"
                  }`
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {/* ux/1034 B5: WHY THERE IS NO ACTUAL LINE. A widget that quietly drops
          half of itself reads as a widget that failed to load, and the reader
          has no way to tell that from "we are refusing to draw a set count on a
          games axis". Suppressed in `fillContainer` (the fullscreen modal),
          which has no room for a sentence and no chrome to hang it on. */}
      {unitMismatchNote && !fillContainer && (
        <p
          className="shrink-0 text-[11.5px] leading-snug text-text-muted"
          data-testid="score-diff-unit-note"
        >
          {unitMismatchNote}
        </p>
      )}

      {/* Chart with vertical team labels */}
      <div className={`flex ${fillContainer ? "flex-1 min-h-0" : "h-48"}`}>
        {/* Vertical team labels on left side — matches OddsChart layout */}
        <div className="flex flex-col items-center justify-between py-3 shrink-0" style={{ width: 28 }}>
          <div className="flex items-center gap-1" style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}>
            {homeTeamLogo && (
              <img src={homeTeamLogo} alt="" width={12} height={12} className="object-contain" style={{ transform: "rotate(90deg)" }} />
            )}
            <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color: homeTeamColor || "#16a34a" }}>
              {homeShort}
            </span>
          </div>
          <div className="flex items-center gap-1" style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}>
            {awayTeamLogo && (
              <img src={awayTeamLogo} alt="" width={12} height={12} className="object-contain" style={{ transform: "rotate(90deg)" }} />
            )}
            <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color: awayTeamColor || "#2563eb" }}>
              {awayShort}
            </span>
          </div>
        </div>

        {/* Chart area */}
        <div className="flex-1 min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 5, right: 10, left: fillContainer ? 5 : 0, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 12, fill: "#6B7280" }}
              tickLine={false}
              axisLine={{ stroke: "rgba(0,0,0,0.1)" }}
              {...(sharedTicks
                ? { ticks: sharedTicks }
                : { interval: chartData.length <= 10 ? 0 : "preserveStartEnd", minTickGap: 50 }
              )}
            />
            <YAxis
              domain={[Math.min(0, -domainMax), Math.max(0, domainMax)]}
              ticks={(() => {
                const step = Math.max(2, Math.ceil(domainMax / 3));
                const ticks: number[] = [];
                for (let v = -domainMax; v <= domainMax; v += step) {
                  ticks.push(v);
                }
                if (!ticks.includes(0)) ticks.push(0);
                return ticks.sort((a, b) => a - b);
              })()}
              width={44}
              tick={{ fontSize: 10, fill: "#9ca3af" }}
              tickLine={false}
              axisLine={{ stroke: "rgba(0,0,0,0.1)" }}
              tickFormatter={(value: number) => {
                if (value === 0) return "0";
                return value > 0 ? `+${value}` : `${value}`;
              }}
            />
            <ReferenceLine
              y={0}
              stroke="rgba(0,0,0,0.2)"
              strokeWidth={2}
              label={{
                value: "0",
                position: "right",
                style: { fontSize: 10, fill: "rgba(0,0,0,0.4)" },
              }}
            />
            {/* Period boundary markers — rendered in front of data area */}
            {filteredPeriodBoundaries.map((b) => (
              <ReferenceLine
                key={`period-${b.label}-${b.timestamp}`}
                x={b.time}
                stroke="rgba(0,0,0,0.25)"
                strokeWidth={1.5}
                strokeDasharray="6 4"
                isFront
                label={{
                  value: b.label,
                  position: ((b as { labelPosition?: string }).labelPosition || "insideTopLeft") as "insideTopLeft" | "insideTopRight",
                  style: { fontSize: 10, fill: "rgba(0,0,0,0.5)", fontWeight: 600 },
                }}
              />
            ))}
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: "12px" }}
              iconType="circle"
              payload={[
                ...(hasProjectedScoreData
                  ? [
                      {
                        value: "Projected margin" as string,
                        type: "circle" as const,
                        color: "#10b981",
                      },
                    ]
                  : []),
                ...(hasActualScoreData
                  ? [
                      {
                        value: "Actual Score Diff" as string,
                        type: "circle" as const,
                        color: "#f97316",
                      },
                    ]
                  : []),
                ...(pmSpreadData?.implied_spreads?.kalshi
                  ? [{ value: "Kalshi Implied" as string, type: "circle" as const, color: "#7c3aed" }]
                  : []),
                ...(pmSpreadData?.implied_spreads?.polymarket
                  ? [{ value: "Polymarket Implied" as string, type: "circle" as const, color: "#db2777" }]
                  : []),
              ]}
            />

            {/* Individual bookmaker spread lines (subtle gray) */}
            {bookmakers.map((bookmaker) => (
              <Line
                key={`${bookmaker}_diff`}
                type="linear"
                dataKey={`${bookmaker}_diff`}
                stroke="rgba(0,0,0,0.12)"
                strokeWidth={1}
                dot={false}
                activeDot={false}
                connectNulls
                legendType="none"
              />
            ))}

            {/* Projected score differential (spread) */}
            {hasProjectedScoreData && (
              <Line
                type="linear"
                dataKey="projectedDiff"
                name="Projected margin"
                stroke="#10b981"
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 5 }}
                connectNulls
              />
            )}

            {/* Actual score difference */}
            {hasActualScoreData && (
              <Line
                type="stepAfter"
                dataKey="actualDiff"
                name="Actual Score Diff"
                stroke="#f97316"
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 5 }}
                connectNulls
              />
            )}

            {/* Prediction market implied spread lines */}
            {pmSpreadData?.implied_spreads?.kalshi && (
              <Line
                type="linear"
                dataKey="pm_kalshi_spread"
                name="Kalshi Implied"
                stroke="#7c3aed"
                strokeWidth={2}
                strokeDasharray="8 4"
                dot={false}
                activeDot={{ r: 4, fill: "#7c3aed" }}
                connectNulls
              />
            )}
            {pmSpreadData?.implied_spreads?.polymarket && (
              <Line
                type="linear"
                dataKey="pm_polymarket_spread"
                name="Polymarket Implied"
                stroke="#db2777"
                strokeWidth={2}
                strokeDasharray="6 4"
                dot={false}
                activeDot={{ r: 4, fill: "#db2777" }}
                connectNulls
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
        </div>
      </div>

      {bookmakers.length > 0 && (
        <p className="text-xs text-text-muted text-center shrink-0">
          {/* #2442, CERT-642's first finding: this was the THIRD spelling of
              one supplier on the same screen and my sweep never reached it,
              because the guard rendered `MarketMapSection` and `OddsChart` and
              never this component. Through the registry like the other two. */}
          Gray lines show each {sourceLabel("betting").toLowerCase()}
        </p>
      )}
    </div>
  );
}
