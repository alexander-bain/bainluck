"use client";

import { useState, useMemo, useEffect } from "react";
import {
  ComposedChart,
  Line,
  Area,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import Link from "next/link";
import { format, parseISO } from "date-fns";
import { useAnalyticsContext } from "@/components/Analytics";
import type {
  OddsHistoryPoint,
  BookmakerHistoryPoint,
  ESPNHistoryPoint,
  WinProbHistoryPoint,
  WinProbSourceMeta,
  ScoringPlay,
  ActiveChartPoint,
} from "@/lib/types";
import type { PeriodBoundary } from "@/lib/periodMarkers";

/** Fallback source configs when win_prob_sources metadata isn't available */
const FALLBACK_SOURCE_CONFIG: Record<string, { display_name: string; color: string; dash_pattern: string | null; type: "model" | "market" }> = {
  betting: { display_name: "Betting Odds", color: "#e5e7eb", dash_pattern: null, type: "market" },
  espn: { display_name: "ESPN", color: "#f97316", dash_pattern: "6 3", type: "model" },
  stat_model: { display_name: "Bain Luck Model", color: "#8b5cf6", dash_pattern: "4 4", type: "model" },
  kalshi: { display_name: "Kalshi", color: "#22c55e", dash_pattern: "8 4", type: "market" },
  polymarket: { display_name: "Polymarket", color: "#3b82f6", dash_pattern: "8 4", type: "market" },
  fangraphs: { display_name: "MLB Model", color: "#06b6d4", dash_pattern: "4 4", type: "model" },
};

/** Bain Luck aggregated line config */
const BAIN_LUCK_CONFIG = {
  color: "#059669", // emerald-600 — distinctive green
  displayName: "Bain Luck",
  dataKey: "bainLuckDelta",
};

interface OddsChartProps {
  history: OddsHistoryPoint[];
  homeTeam: string;
  awayTeam: string;
  commenceTime?: string;
  isLive?: boolean;
  bookmakerHistory?: Record<string, BookmakerHistoryPoint[]>;
  /** ESPN win probability history (legacy, used as fallback) */
  espnHistory?: ESPNHistoryPoint[];
  /** Multi-source win probability history */
  winProbHistory?: Record<string, WinProbHistoryPoint[]>;
  /** Source metadata (display names, colors, types) */
  winProbSources?: Record<string, WinProbSourceMeta>;
  /** Scoring plays from StatPal play-by-play for chart annotations */
  scoringPlays?: ScoringPlay[];
  /** Backend-computed aggregate line (weighted median with staleness decay) */
  aggregateLine?: Array<{ timestamp: string; home_probability: number }>;
  /** Event ID for analytics tracking */
  eventId?: number;
  /** Event status - determines default filter: closed/completed defaults to "Since Start", open defaults to "All" */
  eventStatus?: string;
  /** When true, chart fills its parent container height instead of using fixed h-80 */
  fillContainer?: boolean;
  /** Period boundaries for vertical divider annotations (Q1/Q2/Q3/Q4 etc.) */
  periodBoundaries?: PeriodBoundary[];
  /** Home team primary color (hex) for team label styling */
  homeTeamColor?: string;
  /** Away team primary color (hex) for team label styling */
  awayTeamColor?: string;
  /** Home team logo URL (small) */
  homeTeamLogo?: string;
  /** Away team logo URL (small) */
  awayTeamLogo?: string;
  /** Callback when user hovers/scrubs chart — null when mouse leaves */
  onActivePointChange?: (point: ActiveChartPoint | null) => void;
  /** Callback reporting the chart's actual rendered time domain (first & last timestamps).
   *  Used by ScoreDifferentialChart to match its x-axis exactly. */
  onRenderedDomain?: (startISO: string, endISO: string) => void;
}

type TimeRange = "all" | "live";

const TIME_RANGE_OPTIONS: { value: TimeRange; label: string }[] = [
  { value: "all", label: "All" },
  { value: "live", label: "Since Start" },
];

interface ChartDataPoint {
  timestamp: string;
  time: string;
  /** Home probability delta from 50% (range: -50 to +50) */
  homeDelta: number | null;
  /** ESPN home probability delta from 50% (legacy) */
  espnDelta: number | null;
  /** Bain Luck aggregated probability delta (multi-source mode) */
  bainLuckDelta: number | null;
  /** Game state carried through for interactive play-by-play card */
  _homeScore?: number | null;
  _awayScore?: number | null;
  _period?: string | null;
  _clock?: string | null;
  _scoringPlay?: ScoringPlay | null;
  [key: string]: string | number | null | undefined | ScoringPlay;
}

/** Resolved source info used for rendering */
interface ResolvedSource {
  key: string;
  dataKey: string;
  displayName: string;
  color: string;
  dashPattern: string | null;
  type: "model" | "market";
  snapshotCount: number;
}

/**
 * Win probability chart with two display modes:
 *
 * **Mode A (Multi-source):** When multiple probability sources exist
 * (sportsbooks + ESPN/Kalshi/Polymarket/models), shows:
 *   - An aggregated "Bain Luck" line prominently (solid, with area fill)
 *   - Each individual SOURCE as a thin, semi-transparent line with its color
 *   - Individual bookmakers are HIDDEN
 *
 * **Mode B (Sportsbooks-only):** When only sportsbook data exists:
 *   - Sportsbook consensus line shown prominently (solid, with area fill)
 *   - Individual bookmaker lines shown faintly in grey
 */
export default function OddsChart({
  history,
  homeTeam,
  awayTeam,
  commenceTime,
  isLive = false,
  bookmakerHistory,
  espnHistory,
  winProbHistory,
  winProbSources,
  scoringPlays,
  aggregateLine,
  eventId,
  eventStatus,
  fillContainer = false,
  periodBoundaries,
  homeTeamColor,
  awayTeamColor,
  homeTeamLogo,
  awayTeamLogo,
  onActivePointChange,
  onRenderedDomain,
}: OddsChartProps) {
  const isClosed = eventStatus === "closed" || eventStatus === "completed";
  const { track } = useAnalyticsContext();

  const hasPostStartData = useMemo(() => {
    if (!history || history.length === 0 || !commenceTime) return false;
    const cutoffTime = parseISO(commenceTime);
    return history.some((point) => parseISO(point.timestamp) >= cutoffTime);
  }, [history, commenceTime]);

  const defaultTimeRange: TimeRange =
    (isClosed || isLive) && hasPostStartData ? "live" : "all";
  const [timeRange, setTimeRange] = useState<TimeRange>(defaultTimeRange);

  // Sync timeRange when data loads asynchronously — useState only uses
  // its initial value on mount, so if history arrives after first render
  // the default stays "all" even when it should be "live"
  const [hasUserOverridden, setHasUserOverridden] = useState(false);
  useEffect(() => {
    if (!hasUserOverridden && defaultTimeRange === "live") {
      setTimeRange("live");
    }
  }, [defaultTimeRange, hasUserOverridden]);

  // For "Since Start" mode, use commenceTime directly as the start cutoff.
  // Previously used a "smartStartTime" that scanned for the first 2% odds
  // change — but with sparse betting data (one point every ~30 min), this
  // often skipped 1-2 hours past the actual game start, showing 6:20 PM
  // instead of 4:30 PM for a game that started at 4:30 PM.
  // commenceTime is the actual game start from ESPN/StatPal/Odds API —
  // use it directly.

  // Compute smart end time for completed/closed games:
  // Bookmakers keep reporting stale data 15-20 min after a game ends,
  // stretching the chart far beyond the actual game duration.
  // Use the latest game-state signal (ESPN, win prob models, score snapshots)
  // as the true end, plus a small buffer.
  const smartEndTime = useMemo(() => {
    if (!isClosed) return null; // Only clip completed games

    const candidates: Date[] = [];

    // Signal 1: last ESPN history point (most reliable game-end signal)
    if (espnHistory && espnHistory.length > 0) {
      candidates.push(parseISO(espnHistory[espnHistory.length - 1].timestamp));
    }

    // Signal 2: last win probability model point (stat_model, ESPN source, etc.)
    if (winProbHistory) {
      for (const points of Object.values(winProbHistory)) {
        if (points.length > 0) {
          candidates.push(parseISO(points[points.length - 1].timestamp));
        }
      }
    }

    // Signal 3: last aggregate line point
    if (aggregateLine && aggregateLine.length > 0) {
      candidates.push(parseISO(aggregateLine[aggregateLine.length - 1].timestamp));
    }

    const latestGameSignal = candidates.length > 0
      ? candidates.reduce((a, b) => (a > b ? a : b))
      : null;

    if (!latestGameSignal) return null;

    // Add 2-minute buffer to avoid clipping the last data point
    return new Date(latestGameSignal.getTime() + 2 * 60 * 1000);
  }, [isClosed, espnHistory, winProbHistory, aggregateLine]);

  // Filter history based on time range
  const filteredHistory = useMemo(() => {
    if (!history || history.length === 0) return [];
    if (timeRange === "all") return history;
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    let filtered = history.filter((point) => parseISO(point.timestamp) >= cutoffTime);
    if (smartEndTime) {
      filtered = filtered.filter((point) => parseISO(point.timestamp) <= smartEndTime);
    }
    return filtered;
  }, [history, timeRange, commenceTime, smartEndTime]);

  // Filter bookmaker history
  const filteredBookmakerHistory = useMemo(() => {
    if (!bookmakerHistory || Object.keys(bookmakerHistory).length === 0)
      return {};
    if (timeRange === "all") return bookmakerHistory;
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    const filtered: Record<string, BookmakerHistoryPoint[]> = {};
    for (const [bookmaker, points] of Object.entries(bookmakerHistory)) {
      let pts = points.filter(
        (point) => parseISO(point.timestamp) >= cutoffTime
      );
      if (smartEndTime) {
        pts = pts.filter((point) => parseISO(point.timestamp) <= smartEndTime);
      }
      filtered[bookmaker] = pts;
    }
    return filtered;
  }, [bookmakerHistory, timeRange, commenceTime, smartEndTime]);

  // Build the list of all sources to display (betting + model sources)
  const resolvedSources = useMemo((): ResolvedSource[] => {
    const sources: ResolvedSource[] = [];

    // Always include betting odds as a labeled source
    if (history && history.length > 0) {
      const bettingConfig = FALLBACK_SOURCE_CONFIG.betting;
      sources.push({
        key: "betting",
        dataKey: "homeDelta",
        displayName: bettingConfig.display_name,
        color: bettingConfig.color,
        dashPattern: bettingConfig.dash_pattern,
        type: bettingConfig.type,
        snapshotCount: history.length,
      });
    }

    if (winProbHistory && Object.keys(winProbHistory).length > 0) {
      for (const [key, points] of Object.entries(winProbHistory)) {
        if (points.length === 0) continue;

        // Hide stat model when most data points used wall-clock estimation
        // (imprecise fallback for games where ESPN name matching fails).
        if (key === "stat_model" && points.length >= 3) {
          const wallClockCount = points.filter(
            (p) => p.game_state?.time_source === "wall_clock"
          ).length;
          if (wallClockCount > points.length * 0.5) continue;
        }

        const meta = winProbSources?.[key];
        const fallback = FALLBACK_SOURCE_CONFIG[key];
        sources.push({
          key,
          dataKey: `wp_${key}_delta`,
          displayName: meta?.display_name ?? fallback?.display_name ?? key,
          color: meta?.color ?? fallback?.color ?? "#6b7280",
          dashPattern: meta?.dash_pattern ?? fallback?.dash_pattern ?? "4 4",
          type: meta?.type ?? fallback?.type ?? "model",
          snapshotCount: points.length,
        });
      }
    } else if (espnHistory && espnHistory.length > 0) {
      sources.push({
        key: "espn",
        dataKey: "espnDelta",
        displayName: "ESPN",
        color: "#f97316",
        dashPattern: "6 3",
        type: "model",
        snapshotCount: espnHistory.length,
      });
    }

    return sources;
  }, [history, winProbHistory, winProbSources, espnHistory]);

  // Non-betting sources
  const nonBettingSources = useMemo(
    () => resolvedSources.filter((s) => s.key !== "betting"),
    [resolvedSources]
  );

  // ── Display mode detection ──
  // Multi-source mode: when we have at least 1 non-betting source with data
  const isMultiSource = nonBettingSources.length > 0;

  // Filter win prob history based on time range
  const filteredWinProbHistory = useMemo(() => {
    if (!winProbHistory || Object.keys(winProbHistory).length === 0) return {};
    if (timeRange === "all") return winProbHistory;
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    const filtered: Record<string, WinProbHistoryPoint[]> = {};
    for (const [source, points] of Object.entries(winProbHistory)) {
      let pts = points.filter(
        (point) => parseISO(point.timestamp) >= cutoffTime
      );
      if (smartEndTime) {
        pts = pts.filter((point) => parseISO(point.timestamp) <= smartEndTime);
      }
      filtered[source] = pts;
    }
    return filtered;
  }, [winProbHistory, timeRange, commenceTime, smartEndTime]);

  // Filter ESPN history (legacy fallback)
  const filteredEspnHistory = useMemo(() => {
    if (!espnHistory || espnHistory.length === 0) return [];
    if (timeRange === "all") return espnHistory;
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    let filtered = espnHistory.filter(
      (point) => parseISO(point.timestamp) >= cutoffTime
    );
    if (smartEndTime) {
      filtered = filtered.filter((point) => parseISO(point.timestamp) <= smartEndTime);
    }
    return filtered;
  }, [espnHistory, timeRange, commenceTime, smartEndTime]);

  // Filter aggregate line — use commenceTime (not smartStartTime) because the
  // aggregate line is already a clean backend-computed weighted median without
  // the noisy flat pre-game data that smartStartTime is designed to skip.
  const filteredAggregateLine = useMemo(() => {
    if (!aggregateLine || aggregateLine.length === 0) return [];
    if (timeRange === "all") return aggregateLine;
    const cutoffTime = commenceTime ? parseISO(commenceTime) : new Date();
    let filtered = aggregateLine.filter(
      (point) => parseISO(point.timestamp) >= cutoffTime
    );
    if (smartEndTime) {
      filtered = filtered.filter((point) => parseISO(point.timestamp) <= smartEndTime);
    }
    return filtered;
  }, [aggregateLine, timeRange, commenceTime, smartEndTime]);

  const useNewWinProbData = Object.keys(filteredWinProbHistory).length > 0;
  const bookmakers = useMemo(
    () => Object.keys(filteredBookmakerHistory),
    [filteredBookmakerHistory]
  );

  // Transform data: convert probabilities to delta from 50%
  // Bucket by minute so each "h:mm a" time label is unique — required for
  // Recharts ReferenceLine (period markers) to match categorical XAxis values.
  const chartData: ChartDataPoint[] = useMemo(() => {
    const dataMap = new Map<string, ChartDataPoint>();

    /** Round an ISO timestamp to the start of its minute. */
    const toMinuteKey = (timestamp: string): string => {
      const d = parseISO(timestamp);
      // Zero out seconds and milliseconds
      d.setSeconds(0, 0);
      return d.toISOString();
    };

    const ensurePoint = (timestamp: string): ChartDataPoint => {
      const minuteKey = toMinuteKey(timestamp);
      let point = dataMap.get(minuteKey);
      if (!point) {
        point = {
          timestamp: minuteKey,
          time: format(parseISO(minuteKey), "h:mm a"),
          homeDelta: null,
          espnDelta: null,
          bainLuckDelta: null,
        };
        dataMap.set(minuteKey, point);
      }
      return point;
    };

    // Add aggregate data points (betting odds consensus)
    for (const point of filteredHistory) {
      const homeProb =
        point.home_probability !== null ? point.home_probability * 100 : null;
      const delta = homeProb !== null ? homeProb - 50 : null;

      const dp = ensurePoint(point.timestamp);
      dp.homeDelta = delta;

      // Expand valid_until
      if (point.valid_until) {
        const endTime = parseISO(point.valid_until);
        const startTime = parseISO(point.timestamp);
        if (endTime.getTime() - startTime.getTime() > 60000) {
          const endDp = ensurePoint(point.valid_until);
          if (endDp.homeDelta === null) endDp.homeDelta = delta;
        }
      }
    }

    // Add bookmaker lines (single line per bookmaker - home prob delta)
    for (const [bookmaker, points] of Object.entries(
      filteredBookmakerHistory
    )) {
      for (const point of points) {
        const homeProb =
          point.home_probability !== null
            ? point.home_probability * 100
            : null;
        const delta = homeProb !== null ? homeProb - 50 : null;

        const dp = ensurePoint(point.timestamp);
        dp[`${bookmaker}_delta`] = delta;

        // Expand valid_until
        if (point.valid_until) {
          const endTime = parseISO(point.valid_until);
          const startTime = parseISO(point.timestamp);
          if (endTime.getTime() - startTime.getTime() > 60000) {
            const endDp = ensurePoint(point.valid_until);
            if (endDp[`${bookmaker}_delta`] === undefined) {
              endDp[`${bookmaker}_delta`] = delta;
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
        if (point[`${bookmaker}_delta`] === undefined) {
          point[`${bookmaker}_delta`] = null;
        }
      }
    }

    // Add win probability source data (new multi-source or legacy ESPN)
    if (useNewWinProbData) {
      for (const [sourceKey, points] of Object.entries(filteredWinProbHistory)) {
        const dataKey = `wp_${sourceKey}_delta`;
        for (const point of points) {
          const homeProb =
            point.home_probability !== null ? point.home_probability * 100 : null;
          const delta = homeProb !== null ? homeProb - 50 : null;

          const dp = ensurePoint(point.timestamp);
          dp[dataKey] = delta;
        }
      }

      // Ensure all source keys exist on all data points
      const allDataPoints = Array.from(dataMap.values());
      for (const point of allDataPoints) {
        for (const source of nonBettingSources) {
          if (point[source.dataKey] === undefined) {
            point[source.dataKey] = null;
          }
        }
      }
    } else {
      // Legacy ESPN data
      for (const point of filteredEspnHistory) {
        const espnHome =
          point.home_probability !== null ? point.home_probability * 100 : null;
        const delta = espnHome !== null ? espnHome - 50 : null;

        const dp = ensurePoint(point.timestamp);
        dp.espnDelta = delta;
      }
    }

    // ── Compute Bain Luck aggregated line (multi-source mode) ──
    // Prefer backend aggregate_line (weighted median with staleness decay)
    // when available; fall back to naive frontend averaging.
    if (isMultiSource) {
      if (filteredAggregateLine && filteredAggregateLine.length > 0) {
        // Use backend-computed aggregate line
        for (const point of filteredAggregateLine) {
          const homeProb = point.home_probability * 100;
          const delta = homeProb - 50;
          const dp = ensurePoint(point.timestamp);
          dp.bainLuckDelta = delta;
        }
      } else {
        // Fallback: average of all available source deltas at each timestamp
        const sourceDataKeys = resolvedSources.map((s) => s.dataKey);
        for (const point of Array.from(dataMap.values())) {
          const values: number[] = [];
          for (const key of sourceDataKeys) {
            const val = point[key];
            if (typeof val === "number" && val !== null) {
              values.push(val);
            }
          }
          point.bainLuckDelta = values.length > 0
            ? values.reduce((a, b) => a + b, 0) / values.length
            : null;
        }
      }
    }

    // ── Enrich chart points with game state (score, period, clock) ──
    // Sources: ESPN history (has score/period/clock) and win_prob_history game_state
    // ESPN history is the richest source for game context
    for (const snap of filteredEspnHistory) {
      const dp = dataMap.get(toMinuteKey(snap.timestamp));
      if (dp) {
        if (snap.home_score != null) dp._homeScore = snap.home_score;
        if (snap.away_score != null) dp._awayScore = snap.away_score;
        if (snap.period) dp._period = snap.period;
        if (snap.game_clock) dp._clock = snap.game_clock;
      }
    }

    // Win prob history game_state as secondary source
    if (useNewWinProbData) {
      for (const points of Object.values(filteredWinProbHistory)) {
        for (const pt of points) {
          const gs = pt.game_state;
          if (!gs) continue;
          const dp = dataMap.get(toMinuteKey(pt.timestamp));
          if (!dp) continue;
          if (dp._homeScore == null && gs.home_score != null)
            dp._homeScore = gs.home_score as number;
          if (dp._awayScore == null && gs.away_score != null)
            dp._awayScore = gs.away_score as number;
          if (!dp._period && gs.period) dp._period = gs.period as string;
          if (!dp._clock && gs.clock) dp._clock = gs.clock as string;
        }
      }
    }

    // Map scoring plays onto chart data points
    if (scoringPlays && scoringPlays.length > 0) {
      const sortedPoints = Array.from(dataMap.values()).sort(
        (a, b) => parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime()
      );
      for (const play of scoringPlays) {
        if (!play.timestamp) continue;
        const playTime = parseISO(play.timestamp).getTime();
        let closestIdx = 0;
        let closestDist = Infinity;
        for (let i = 0; i < sortedPoints.length; i++) {
          const dist = Math.abs(parseISO(sortedPoints[i].timestamp).getTime() - playTime);
          if (dist < closestDist) {
            closestDist = dist;
            closestIdx = i;
          }
        }
        // Only attach if within 2 minutes
        if (closestDist < 120000) {
          sortedPoints[closestIdx]._scoringPlay = play;
        }
      }
    }

    // Fill missing minutes for uniform x-axis spacing.
    // Both OddsChart and ScoreDifferentialChart use categorical XAxis where
    // each category gets equal pixel width. Without filling gaps, the two
    // charts have different numbers of categories, causing period markers
    // to appear at different pixel positions. Filling every minute ensures
    // both charts have identical category sets.
    if (timeRange === "live") {
      const allTimestamps = Array.from(dataMap.keys()).sort();
      if (allTimestamps.length >= 2) {
        const first = parseISO(allTimestamps[0]);
        const last = parseISO(allTimestamps[allTimestamps.length - 1]);
        const cursor = new Date(first.getTime());
        cursor.setMinutes(cursor.getMinutes() + 1);
        while (cursor <= last) {
          ensurePoint(cursor.toISOString());
          cursor.setMinutes(cursor.getMinutes() + 1);
        }
      }
    }

    // Forward-fill game state: carry most recent score/period/clock to subsequent points
    const sorted = Array.from(dataMap.values()).sort(
      (a, b) => parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime()
    );
    let lastScore: { home: number | null; away: number | null } = { home: null, away: null };
    let lastPeriod: string | null = null;
    let lastClock: string | null = null;
    for (const pt of sorted) {
      if (pt._homeScore != null) lastScore.home = pt._homeScore as number;
      else pt._homeScore = lastScore.home;
      if (pt._awayScore != null) lastScore.away = pt._awayScore as number;
      else pt._awayScore = lastScore.away;
      if (pt._period) lastPeriod = pt._period as string;
      else pt._period = lastPeriod;
      if (pt._clock) lastClock = pt._clock as string;
      else pt._clock = lastClock;
    }

    return sorted;
  }, [filteredHistory, filteredBookmakerHistory, filteredWinProbHistory, filteredEspnHistory, useNewWinProbData, nonBettingSources, isMultiSource, resolvedSources, filteredAggregateLine, scoringPlays, timeRange]);

  // Report the chart's actual rendered time domain to parent so
  // ScoreDifferentialChart can match its x-axis exactly.
  useEffect(() => {
    if (!onRenderedDomain || chartData.length === 0) return;
    const first = chartData[0].timestamp;
    const last = chartData[chartData.length - 1].timestamp;
    onRenderedDomain(first, last);
  }, [chartData, onRenderedDomain]);

  // Build scoring play annotations that map to chart data points
  const scoringPlayAnnotations = useMemo(() => {
    if (!scoringPlays || scoringPlays.length === 0 || chartData.length === 0) return [];

    // In multi-source mode, use the Bain Luck aggregated delta; otherwise use homeDelta
    const primaryDeltaKey = isMultiSource ? "bainLuckDelta" : "homeDelta";

    return scoringPlays
      .filter((play) => play.timestamp)
      .map((play) => {
        const playTime = parseISO(play.timestamp).getTime();
        let closestIdx = 0;
        let closestDist = Infinity;
        for (let i = 0; i < chartData.length; i++) {
          const dist = Math.abs(parseISO(chartData[i].timestamp).getTime() - playTime);
          if (dist < closestDist) {
            closestDist = dist;
            closestIdx = i;
          }
        }
        const closestPoint = chartData[closestIdx];
        const yValue = closestPoint[primaryDeltaKey] as number | null;
        if (yValue === null) return null;

        return {
          time: closestPoint.time,
          scoringPlayDelta: yValue,
          description: play.description,
          team: play.team,
          type: play.type,
          home_score: play.home_score,
          away_score: play.away_score,
          period: play.period,
          clock: play.clock,
        };
      })
      .filter((p): p is NonNullable<typeof p> => p !== null);
  }, [scoringPlays, chartData, isMultiSource]);

  // Filter period boundaries to match chart time range and map to chart time format
  const filteredPeriodBoundaries = useMemo(() => {
    if (!periodBoundaries || periodBoundaries.length === 0 || chartData.length === 0) return [];
    const chartStart = parseISO(chartData[0].timestamp).getTime();
    const chartEnd = parseISO(chartData[chartData.length - 1].timestamp).getTime();

    return periodBoundaries
      .filter((b) => {
        const t = parseISO(b.timestamp).getTime();
        return t >= chartStart && t <= chartEnd;
      })
      .map((b) => ({
        ...b,
        time: format(parseISO(b.timestamp), "h:mm a"),
      }));
  }, [periodBoundaries, chartData]);

  // Auto-zoom: compute dynamic Y-axis domain based on actual data range
  const { yDomain, yTicks } = useMemo(() => {
    const allDeltas = chartData
      .flatMap((d) => {
        const vals: number[] = [];
        // Collect all delta values from all sources
        for (const key of Object.keys(d)) {
          if (key.endsWith("Delta") || key.endsWith("_delta")) {
            const v = d[key];
            if (typeof v === "number") vals.push(v);
          }
        }
        return vals;
      });
    if (allDeltas.length === 0) return { yDomain: [-50, 50] as [number, number], yTicks: [-50, -25, 0, 25, 50] };

    const dataMin = Math.min(...allDeltas);
    const dataMax = Math.max(...allDeltas);
    // Add 5-point padding, round to nearest 5, ensure 0 is included
    let lo = Math.floor((dataMin - 5) / 5) * 5;
    let hi = Math.ceil((dataMax + 5) / 5) * 5;
    // Ensure 0 is always in range
    if (lo > 0) lo = 0;
    if (hi < 0) hi = 0;
    // Clamp to [-50, 50]
    lo = Math.max(-50, lo);
    hi = Math.min(50, hi);
    // Generate ticks at 10-point intervals
    const ticks: number[] = [];
    for (let t = lo; t <= hi; t += 10) {
      ticks.push(t);
    }
    // Ensure 0 is always a tick
    if (!ticks.includes(0)) ticks.push(0);
    ticks.sort((a, b) => a - b);
    return { yDomain: [lo, hi] as [number, number], yTicks: ticks };
  }, [chartData]);

  // ── Compute lead change points (50% crossings) ──
  // Instead of creating a separate data array (which breaks Recharts categorical
  // X-axis domain), we stamp `leadChangeDelta` directly onto chartData points.
  const leadChangeCount = useMemo(() => {
    if (chartData.length < 2) return 0;
    const key = isMultiSource ? "bainLuckDelta" : "homeDelta";
    // Clear any previous stamps
    for (const pt of chartData) {
      delete pt.leadChangeDelta;
    }
    let count = 0;
    let prevDelta: number | null = null;
    for (const pt of chartData) {
      const delta = pt[key] as number | null;
      if (delta === null) continue;
      if (prevDelta !== null) {
        if ((prevDelta > 0 && delta <= 0) || (prevDelta < 0 && delta >= 0)) {
          pt.leadChangeDelta = 0; // Stamp onto chartData point at y=0 (50% line)
          count++;
        }
      }
      prevDelta = delta;
    }
    return count;
  }, [chartData, isMultiSource]);

  // ── Current probability callout (last non-null data point) ──
  // Stamp `calloutDelta` directly onto the chartData point (same reason as above).
  const currentCallout = useMemo(() => {
    if (chartData.length === 0) return null;
    const key = isMultiSource ? "bainLuckDelta" : "homeDelta";
    // Clear any previous stamps
    for (const pt of chartData) {
      delete pt.calloutDelta;
    }
    // Walk backwards to find last non-null value
    for (let i = chartData.length - 1; i >= 0; i--) {
      const delta = chartData[i][key] as number | null;
      if (delta !== null) {
        const homeProb = 50 + delta;
        chartData[i].calloutDelta = delta; // Stamp onto chartData point
        return {
          time: chartData[i].time,
          delta,
          homeProb: Math.round(homeProb),
          awayProb: Math.round(100 - homeProb),
        };
      }
    }
    return null;
  }, [chartData, isMultiSource]);

  // Early return for empty data across ALL sources (not just sportsbook odds)
  // If "Since Start" filter caused empty data, auto-reset to "all"
  if (chartData.length === 0) {
    if (timeRange === "live" && history && history.length > 0) {
      // Data exists but all pre-start — reset filter silently
      setTimeRange("all");
      setHasUserOverridden(false);
      return null; // Will re-render with "all" data
    }
    const isPreGame = eventStatus === "scheduled";
    return (
      <div className="h-64 flex flex-col items-center justify-center bg-surface-elevated rounded-lg text-text-muted gap-2">
        {isPreGame ? (
          <>
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="opacity-30">
              <circle cx="24" cy="24" r="22" stroke="currentColor" strokeWidth="2" strokeDasharray="4 4" />
              <path d="M24 14v10l7 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <p className="text-sm font-medium">Chart available at game time</p>
            <p className="text-xs">Win probability will update live once the game starts</p>
          </>
        ) : (
          <p className="text-sm">No history data available</p>
        )}
      </div>
    );
  }

  // When sportsbook odds are missing but other sources exist, the chart
  // should use a non-betting source as the primary fill area.
  const hasBookmakerData = history && history.length > 0;

  // The primary delta key for the area fill gradient.
  // When sportsbook odds are missing but other sources exist, fall back to
  // the first available non-betting source for the fill area.
  const primaryDeltaKey = isMultiSource
    ? "bainLuckDelta"
    : hasBookmakerData
      ? "homeDelta"
      : nonBettingSources.length > 0
        ? nonBettingSources[0].dataKey
        : "homeDelta";

  // Compute gradient offset for area fill-by-value
  const gradientOffset = (() => {
    const deltas = chartData
      .map((d) => d[primaryDeltaKey] as number | null)
      .filter((v): v is number => v !== null);
    if (deltas.length === 0) return 0.5;
    const dataMax = Math.max(...deltas);
    const dataMin = Math.min(...deltas);
    if (dataMax <= 0) return 0;
    if (dataMin >= 0) return 1;
    return dataMax / (dataMax - dataMin);
  })();

  // Short team names
  const homeShort = homeTeam.split(" ").pop() || homeTeam;
  const awayShort = awayTeam.split(" ").pop() || awayTeam;

  // Custom Y-axis tick formatter: shows probability for each team
  const formatYTick = (value: number): string => {
    const prob = 50 + Math.abs(value);
    return `${prob}%`;
  };

  // Custom tooltip showing actual probabilities
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
      const formatProb = (delta: number) => {
        const homeProb = delta + 50;
        const awayProb = 100 - homeProb;
        return `${homeTeam}: ${homeProb.toFixed(1)}% | ${awayTeam}: ${awayProb.toFixed(1)}%`;
      };

      // Look up game state from chartData for this time label
      const matchingPoint = chartData.find((d) => d.time === label);
      const hasGameState = matchingPoint && (matchingPoint._homeScore != null || matchingPoint._period);

      // Bain Luck aggregated line (multi-source mode)
      const bainLuckEntry = isMultiSource
        ? payload.find((e) => e.dataKey === "bainLuckDelta" && e.value !== null)
        : null;

      // Find entries for each resolved source
      const sourceEntries = resolvedSources
        .map((source) => {
          const entry = payload.find(
            (e) => e.dataKey === source.dataKey && e.value !== null
          );
          return entry ? { ...source, value: entry.value } : null;
        })
        .filter((e): e is ResolvedSource & { value: number } => e !== null);

      // Bookmaker entries (only shown in sportsbooks-only mode)
      const bookmakerEntries = !isMultiSource
        ? payload.filter(
            (e) =>
              e.dataKey !== "homeDelta" &&
              e.dataKey !== "bainLuckDelta" &&
              !e.dataKey.startsWith("wp_") &&
              e.dataKey !== "espnDelta" &&
              e.value !== null
          )
        : [];

      return (
        <div className="bg-surface-card p-3 rounded-lg shadow-lg border border-white/10 max-w-sm">
          {/* Game state header — score, period, clock */}
          {hasGameState ? (
            <div className="mb-2 pb-2 border-b border-white/10">
              <div className="flex items-center justify-between gap-3">
                {matchingPoint._homeScore != null && matchingPoint._awayScore != null ? (
                  <span className="text-sm font-bold text-text-primary font-mono">
                    {homeShort} {matchingPoint._homeScore as number} – {matchingPoint._awayScore as number} {awayShort}
                  </span>
                ) : (
                  <span className="text-xs text-text-muted">{label}</span>
                )}
                {matchingPoint._period && (
                  <span className="text-xs text-text-muted whitespace-nowrap">
                    {matchingPoint._period as string}
                    {matchingPoint._clock ? ` ${matchingPoint._clock as string}` : ""}
                  </span>
                )}
              </div>
              {!(matchingPoint._homeScore != null && matchingPoint._awayScore != null) && (
                <p className="text-[10px] text-text-muted mt-0.5">{label}</p>
              )}
            </div>
          ) : (
            <p className="text-xs text-text-muted mb-2">{label}</p>
          )}
          {/* Scoring play annotation */}
          {scoringPlayAnnotations.length > 0 && (() => {
            const match = scoringPlayAnnotations.find((p) => p.time === label);
            if (!match) return null;
            return (
              <div className="mb-2 pb-2 border-b border-white/10">
                <p className="text-xs font-semibold text-red-600 flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-red-500" />
                  {match.description || match.type}
                </p>
                {match.home_score != null && match.away_score != null && (
                  <p className="text-xs text-text-muted mt-0.5">
                    {match.period && `${match.period} `}
                    {match.clock && `${match.clock} — `}
                    Score: {match.home_score}-{match.away_score}
                  </p>
                )}
              </div>
            );
          })()}

          {/* Multi-source mode: Bain Luck aggregated first, then individual sources */}
          {isMultiSource && bainLuckEntry && (
            <div className="mb-2 pb-2 border-b border-white/10">
              <p className="text-xs text-text-muted mb-0.5">
                {BAIN_LUCK_CONFIG.displayName}
                <span className="text-text-muted ml-1">(aggregated)</span>
              </p>
              <p className="text-sm font-semibold" style={{ color: BAIN_LUCK_CONFIG.color }}>
                {formatProb(bainLuckEntry.value)}
              </p>
            </div>
          )}

          {/* Individual sources */}
          {sourceEntries.length > 0 && (
            <div className="space-y-1">
              {isMultiSource && (
                <p className="text-xs text-text-muted mb-0.5">Sources:</p>
              )}
              {sourceEntries.map((source) => (
                <div key={source.key}>
                  <p className="text-xs text-text-muted mb-0.5">
                    {source.displayName}
                    <span className="text-text-muted ml-1">
                      ({source.type})
                    </span>
                  </p>
                  <p
                    className={`text-xs font-medium ${
                      !isMultiSource && source.key === "betting"
                        ? "text-sm font-semibold text-text-primary"
                        : ""
                    }`}
                    style={
                      isMultiSource || source.key !== "betting"
                        ? { color: source.color }
                        : undefined
                    }
                  >
                    {formatProb(source.value)}
                  </p>
                </div>
              ))}
            </div>
          )}

          {/* Bookmaker breakdown (sportsbooks-only mode) */}
          {bookmakerEntries.length > 0 && (
            <div className="mt-2 pt-2 border-t border-white/10">
              <p className="text-xs text-text-muted mb-1">By sportsbook:</p>
              {bookmakerEntries.map((entry) => {
                const bookmaker = entry.dataKey.replace("_delta", "");
                const homeProb = entry.value + 50;
                const awayProb = 100 - homeProb;
                return (
                  <p key={bookmaker} className="text-xs text-text-muted">
                    {bookmaker}: {homeProb.toFixed(0)}% /{" "}
                    {awayProb.toFixed(0)}%
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
    <div className={fillContainer ? "flex flex-col h-full gap-1" : "space-y-3"}>
      {/* Time range selector */}
      <div className="flex flex-wrap items-center gap-1 shrink-0">
        {TIME_RANGE_OPTIONS.map((option) => {
          const isDisabled = option.value === "live" && !hasPostStartData;
          return (
          <button
            key={option.value}
            disabled={isDisabled}
            onClick={() => {
              if (isDisabled) return;
              const previousRange = timeRange;
              setTimeRange(option.value);
              setHasUserOverridden(true);
              if (eventId) {
                track('chart_time_range', {
                  chart_type: 'probability_trend',
                  event_id: eventId,
                  range: option.value,
                  previous_range: previousRange,
                  has_data: filteredHistory.length > 0,
                  data_points_count: filteredHistory.length,
                });
              }
            }}
            className={`font-medium rounded-full transition-colors ${
              isDisabled
                ? "opacity-30 cursor-not-allowed px-3 py-1.5 text-xs bg-surface-elevated text-text-secondary"
                : fillContainer
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
          );
        })}
      </div>

      {/* Team labels flanking the chart */}
      <div className="flex items-center justify-between text-sm font-semibold px-8 shrink-0">
        <span className="flex items-center gap-1" style={{ color: homeTeamColor || "#16a34a" }}>
          {homeTeamLogo && (
            <img src={homeTeamLogo} alt="" width={16} height={16} className="w-4 h-4 object-contain" />
          )}
          {homeShort} favored ↑
        </span>
        <span className="flex items-center gap-1" style={{ color: awayTeamColor || "#2563eb" }}>
          {awayTeamLogo && (
            <img src={awayTeamLogo} alt="" width={16} height={16} className="w-4 h-4 object-contain" />
          )}
          {awayShort} favored ↓
        </span>
      </div>

      {/* Probability Chart */}
      <div className={fillContainer ? "w-full flex-1 min-h-0" : "w-full h-80"}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 5, right: 10, left: fillContainer ? 5 : 0, bottom: 5 }}
            onMouseMove={(state: { activeTooltipIndex?: number }) => {
              if (!onActivePointChange) return;
              const idx = state?.activeTooltipIndex;
              if (idx == null || idx < 0 || idx >= chartData.length) {
                onActivePointChange(null);
                return;
              }
              const pt = chartData[idx];
              const primaryDeltaKey = isMultiSource ? "bainLuckDelta" : "homeDelta";
              const delta = pt[primaryDeltaKey] as number | null;
              const homeProb = delta != null ? (50 + delta) / 100 : 0.5;
              onActivePointChange({
                timestamp: pt.timestamp,
                homeProb,
                awayProb: 1 - homeProb,
                homeScore: pt._homeScore as number | null | undefined,
                awayScore: pt._awayScore as number | null | undefined,
                period: pt._period as string | null | undefined,
                clock: pt._clock as string | null | undefined,
                scoringPlay: pt._scoringPlay as ScoringPlay | null | undefined,
              });
            }}
            onMouseLeave={() => {
              if (onActivePointChange) onActivePointChange(null);
            }}
          >
            <defs>
              <linearGradient id={`probFillGradient-${eventId ?? 0}`} x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset={gradientOffset}
                  stopColor={homeTeamColor || "#22c55e"}
                  stopOpacity={0.3}
                />
                <stop
                  offset={gradientOffset}
                  stopColor={awayTeamColor || "#3b82f6"}
                  stopOpacity={0.3}
                />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: "#9ca3af" }}
              tickLine={false}
              axisLine={{ stroke: "rgba(255,255,255,0.12)" }}
              interval={
                chartData.length <= 10 ? 0 : "preserveStartEnd"
              }
              minTickGap={50}
            />
            <YAxis
              domain={yDomain}
              ticks={yTicks}
              tick={{ fontSize: 10, fill: "#9ca3af" }}
              tickLine={false}
              axisLine={{ stroke: "rgba(255,255,255,0.12)" }}
              tickFormatter={formatYTick}
            />
            {/* 50% reference line */}
            <ReferenceLine
              y={0}
              stroke="rgba(255,255,255,0.25)"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              label={{
                value: "50%",
                position: "right",
                style: { fontSize: 10, fill: "rgba(255,255,255,0.4)" },
              }}
            />
            {/* Period boundary markers — rendered in front of data area */}
            {filteredPeriodBoundaries.map((b) => (
              <ReferenceLine
                key={`period-${b.label}-${b.timestamp}`}
                x={b.time}
                stroke="rgba(255,255,255,0.3)"
                strokeWidth={1.5}
                strokeDasharray="6 4"
                isFront
                label={{
                  value: b.label,
                  position: "insideTopLeft",
                  style: { fontSize: 11, fill: "rgba(255,255,255,0.6)", fontWeight: 700 },
                }}
              />
            ))}
            <Tooltip content={<CustomTooltip />} />

            {/* ── MODE B: Sportsbooks-only — individual bookmaker lines (thin grey) ── */}
            {!isMultiSource && bookmakers.map((bookmaker) => (
              <Line
                key={`${bookmaker}_delta`}
                type="monotone"
                dataKey={`${bookmaker}_delta`}
                stroke="rgba(255,255,255,0.2)"
                strokeWidth={1}
                dot={false}
                activeDot={{ r: 3, fill: "rgba(255,255,255,0.5)" }}
                connectNulls
                legendType="none"
              />
            ))}

            {/* ── MODE A: Multi-source — individual source lines (thin, colored, semi-transparent) ── */}
            {isMultiSource && resolvedSources.map((source) => (
              <Line
                key={source.dataKey}
                type="monotone"
                dataKey={source.dataKey}
                name={source.displayName}
                stroke={source.color}
                strokeWidth={1.5}
                strokeOpacity={0.5}
                strokeDasharray={source.dashPattern ?? undefined}
                dot={false}
                activeDot={{ r: 3, fill: source.color }}
                connectNulls
              />
            ))}

            {/* ── MODE B: Sportsbooks-only — non-betting source lines (when no multi-source) ── */}
            {!isMultiSource && nonBettingSources.map((source) => (
              <Line
                key={source.dataKey}
                type="monotone"
                dataKey={source.dataKey}
                name={source.displayName}
                stroke={source.color}
                strokeWidth={2.5}
                strokeDasharray={source.dashPattern ?? undefined}
                dot={false}
                activeDot={{ r: 4, fill: source.color }}
                connectNulls
              />
            ))}

            {/* Legacy ESPN line (when winProbHistory not available and not multi-source) */}
            {!isMultiSource && !useNewWinProbData && filteredEspnHistory.length > 0 && (
              <Line
                type="monotone"
                dataKey="espnDelta"
                name="ESPN Model"
                stroke="#f97316"
                strokeWidth={2.5}
                strokeDasharray="6 3"
                dot={false}
                activeDot={{ r: 4, fill: "#f97316" }}
                connectNulls
              />
            )}

            {/* Area fill — tracks the primary line (Bain Luck in multi-source, betting in sportsbooks-only) */}
            <Area
              type="linear"
              dataKey={primaryDeltaKey}
              stroke="none"
              fill={`url(#probFillGradient-${eventId ?? 0})`}
              connectNulls
              legendType="none"
              dot={false}
              activeDot={false}
              isAnimationActive={false}
              strokeWidth={0}
            />

            {/* ── MODE A: Multi-source — aggregated Bain Luck line (prominent, on top) ── */}
            {isMultiSource && (
              <Line
                type="monotone"
                dataKey="bainLuckDelta"
                name={BAIN_LUCK_CONFIG.displayName}
                stroke={BAIN_LUCK_CONFIG.color}
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 5, fill: BAIN_LUCK_CONFIG.color }}
                connectNulls
              />
            )}

            {/* ── MODE B: Sportsbooks-only — betting odds line (solid, on top) ── */}
            {!isMultiSource && (
              <Line
                type="monotone"
                dataKey="homeDelta"
                name="Betting Odds"
                stroke="#e5e7eb"
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 5, fill: "#e5e7eb" }}
                connectNulls
              />
            )}

            {/* Scoring play annotations — dots at key moments */}
            {scoringPlayAnnotations.length > 0 && (
              <Scatter
                data={scoringPlayAnnotations}
                dataKey="scoringPlayDelta"
                fill="#ef4444"
                shape={(props: { cx?: number; cy?: number; payload?: typeof scoringPlayAnnotations[number] }) => {
                  const { cx = 0, cy = 0 } = props;
                  return (
                    <circle
                      cx={cx}
                      cy={cy}
                      r={4}
                      fill="#ef4444"
                      stroke="#ffffff"
                      strokeWidth={1.5}
                      style={{ cursor: "pointer" }}
                    />
                  );
                }}
                legendType="none"
              />
            )}

            {/* Lead change markers — diamonds at 50% crossings */}
            {leadChangeCount > 0 && (
              <Scatter
                dataKey="leadChangeDelta"
                fill="none"
                shape={(props: { cx?: number; cy?: number }) => {
                  const { cx = 0, cy = 0 } = props;
                  return (
                    <g>
                      <polygon
                        points={`${cx},${cy - 6} ${cx + 5},${cy} ${cx},${cy + 6} ${cx - 5},${cy}`}
                        fill="rgba(255,255,255,0.9)"
                        stroke="rgba(255,255,255,0.5)"
                        strokeWidth={1}
                      />
                      <polygon
                        points={`${cx},${cy - 3} ${cx + 2.5},${cy} ${cx},${cy + 3} ${cx - 2.5},${cy}`}
                        fill="#fbbf24"
                      />
                    </g>
                  );
                }}
                legendType="none"
              />
            )}

            {/* Current probability callout — dot at the last data point */}
            {currentCallout && (
              <Scatter
                dataKey="calloutDelta"
                fill="none"
                shape={(props: { cx?: number; cy?: number }) => {
                  const { cx = 0, cy = 0 } = props;
                  const fillColor = isMultiSource
                    ? BAIN_LUCK_CONFIG.color
                    : "#e5e7eb";
                  return (
                    <g>
                      {/* Outer glow */}
                      <circle cx={cx} cy={cy} r={8} fill={fillColor} fillOpacity={0.2} />
                      {/* Inner dot */}
                      <circle cx={cx} cy={cy} r={5} fill={fillColor} stroke="#0C0F14" strokeWidth={2} />
                      {/* Probability label */}
                      <text
                        x={cx + 12}
                        y={cy}
                        textAnchor="start"
                        dominantBaseline="central"
                        fill={fillColor}
                        fontSize={11}
                        fontWeight={700}
                        fontFamily="monospace"
                      >
                        {currentCallout.homeProb}%
                      </text>
                    </g>
                  );
                }}
                legendType="none"
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Source legend */}
      <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 shrink-0">
        {/* Multi-source mode: Bain Luck aggregated line first */}
        {isMultiSource && (
          <div className="flex items-center gap-1.5">
            <svg width="20" height="4" className="shrink-0">
              <line
                x1="0" y1="2" x2="20" y2="2"
                stroke={BAIN_LUCK_CONFIG.color}
                strokeWidth="3"
              />
            </svg>
            <span className="text-xs font-semibold" style={{ color: BAIN_LUCK_CONFIG.color }}>
              {BAIN_LUCK_CONFIG.displayName}
            </span>
          </div>
        )}

        {/* Individual sources */}
        {resolvedSources.map((source) => {
          const inner = (
            <>
              <svg width="20" height="4" className="shrink-0">
                <line
                  x1="0" y1="2" x2="20" y2="2"
                  stroke={source.color}
                  strokeWidth={isMultiSource ? "1.5" : "2.5"}
                  strokeDasharray={source.dashPattern ?? undefined}
                  strokeOpacity={isMultiSource ? 0.6 : 1}
                />
              </svg>
              <span className={`text-xs ${isMultiSource ? "text-text-muted" : "text-gray-500 hover:text-gray-700"}`}>
                {source.displayName}
                <span className="text-text-muted ml-0.5">({source.type})</span>
              </span>
            </>
          );
          return eventId ? (
            <Link
              key={source.key}
              href={`/events/${eventId}/models`}
              className="flex items-center gap-1.5 hover:underline"
            >
              {inner}
            </Link>
          ) : (
            <div key={source.key} className="flex items-center gap-1.5">
              {inner}
            </div>
          );
        })}

        {/* Bookmaker legend (sportsbooks-only mode) */}
        {!isMultiSource && bookmakers.length > 0 && (
          <div className="flex items-center gap-1.5">
            <svg width="20" height="4" className="shrink-0">
              <line
                x1="0" y1="2" x2="20" y2="2"
                stroke="rgba(255,255,255,0.2)"
                strokeWidth="1"
              />
            </svg>
            <span className="text-xs text-text-muted">
              Individual sportsbooks
            </span>
          </div>
        )}

        {/* Scoring plays legend */}
        {scoringPlayAnnotations.length > 0 && (
          <div className="flex items-center gap-1.5">
            <svg width="10" height="10" className="shrink-0">
              <circle cx="5" cy="5" r="4" fill="#ef4444" stroke="#fff" strokeWidth="1" />
            </svg>
            <span className="text-xs text-text-muted">
              Scoring plays
            </span>
          </div>
        )}

        {/* Lead changes legend */}
        {leadChangeCount > 0 && (
          <div className="flex items-center gap-1.5">
            <svg width="10" height="10" className="shrink-0">
              <polygon points="5,1 9,5 5,9 1,5" fill="#fbbf24" />
            </svg>
            <span className="text-xs text-text-muted">
              Lead change{leadChangeCount > 1 ? "s" : ""} ({leadChangeCount})
            </span>
          </div>
        )}
      </div>

      {/* Tap for details */}
      <p className="text-xs text-text-muted text-center shrink-0">
        Tap/hover for details
      </p>
    </div>
  );
}
