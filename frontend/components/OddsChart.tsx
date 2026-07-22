"use client";

import { useState, useMemo, useEffect } from "react";
import {
  ComposedChart,
  Line,
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
import { makeEnsurePoint, toMinuteKey, fillMinuteGaps } from "@/lib/chartTimeline";
import { sourceHex } from "@/lib/sourceColors";
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
// Colors come from the one source-color registry (@/lib/sourceColors) — the
// deliberate dark, high-contrast "betting" slate (L2-131) is now the canonical
// odds_api hex there. Only the display name / dash / type stay local.
const FALLBACK_SOURCE_CONFIG: Record<string, { display_name: string; color: string; dash_pattern: string | null; type: "model" | "market" }> = {
  betting: { display_name: "Betting Odds", color: sourceHex("betting"), dash_pattern: null, type: "market" },
  espn: { display_name: "ESPN", color: sourceHex("espn"), dash_pattern: "6 3", type: "model" },
  stat_model: { display_name: "Bain Luck Model", color: sourceHex("stat_model"), dash_pattern: "4 4", type: "model" },
  kalshi: { display_name: "Kalshi", color: sourceHex("kalshi"), dash_pattern: "8 4", type: "market" },
  polymarket: { display_name: "Polymarket", color: sourceHex("polymarket"), dash_pattern: "8 4", type: "market" },
  fangraphs: { display_name: "MLB Model", color: sourceHex("fangraphs"), dash_pattern: "4 4", type: "model" },
};

/** Bain Luck aggregated (blend) line config */
const BAIN_LUCK_CONFIG = {
  color: sourceHex("blend"), // emerald-600 — the one blend line
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
  /** Home team abbreviation (e.g. "BOS") from ESPN */
  homeTeamAbbrev?: string;
  /** Away team abbreviation (e.g. "OKC") from ESPN */
  awayTeamAbbrev?: string;
  /** Callback when user hovers/scrubs chart — null when mouse leaves */
  onActivePointChange?: (point: ActiveChartPoint | null) => void;
  /** Callback reporting the chart's actual rendered time domain (first & last timestamps).
   *  Used by ScoreDifferentialChart to match its x-axis exactly. */
  onRenderedDomain?: (startISO: string, endISO: string) => void;
  /** Shared chart domain from parent — when set, overrides internal domain computation
   *  so OddsChart and ScoreDiffChart have identical x-axes. */
  chartStartTime?: string;
  chartEndTime?: string;
  sharedTicks?: string[];
  /** External time range from parent — when set, syncs both charts' All/Since Start toggle */
  externalTimeRange?: "all" | "live";
  onTimeRangeChange?: (range: "all" | "live") => void;
  /** Authoritative game end time from the backend (set when any source confirms game over) */
  completedAt?: string;
}

type TimeRange = "all" | "live";

const TIME_RANGE_OPTIONS: { value: TimeRange; label: string }[] = [
  { value: "all", label: "All" },
  { value: "live", label: "Since Start" },
];

interface ChartDataPoint {
  timestamp: string;
  time: string;
  // NOTE: the `*Delta` field names are legacy. As of L2-131 these hold the raw
  // HOME win probability on a single 0–100 axis (not a delta from 50), so the
  // chart reads as one clean 0–100 scale instead of the old mirrored ±50 axis.
  /** Home win probability, 0–100 */
  homeDelta: number | null;
  /** ESPN home win probability, 0–100 (legacy) */
  espnDelta: number | null;
  /** Bain Luck aggregated win probability, 0–100 (multi-source mode) */
  bainLuckDelta: number | null;
  /** Game state carried through for interactive play-by-play card */
  _homeScore?: number | null;
  _awayScore?: number | null;
  _period?: string | null;
  _clock?: string | null;
  /** True when `_clock` was carried forward from an earlier snapshot (#925). */
  _clockApprox?: boolean;
  _scoringPlay?: ScoringPlay | null;
  [key: string]: string | number | boolean | null | undefined | ScoringPlay;
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
  homeTeamAbbrev,
  awayTeamAbbrev,
  onActivePointChange,
  onRenderedDomain,
  chartStartTime,
  chartEndTime,
  sharedTicks,
  externalTimeRange,
  onTimeRangeChange,
  completedAt,
}: OddsChartProps) {
  const isClosed = eventStatus === "closed" || eventStatus === "completed";
  const { track } = useAnalyticsContext();

  const hasPostStartData = useMemo(() => {
    if (!commenceTime) return false;
    const cutoffTime = parseISO(commenceTime);
    // Check sportsbook history
    if (history?.some((point) => parseISO(point.timestamp) >= cutoffTime)) return true;
    // Check win prob history (ESPN, Kalshi, stat model, etc.)
    if (winProbHistory) {
      for (const pts of Object.values(winProbHistory)) {
        if (pts?.some((p) => parseISO(p.timestamp) >= cutoffTime)) return true;
      }
    }
    // Check ESPN history
    if (espnHistory?.some((p) => parseISO(p.timestamp) >= cutoffTime)) return true;
    return false;
  }, [history, winProbHistory, espnHistory, commenceTime]);

  const defaultTimeRange: TimeRange =
    (isClosed || isLive) && hasPostStartData ? "live" : "all";
  const [internalTimeRange, setInternalTimeRange] = useState<TimeRange>(defaultTimeRange);

  // Use external time range when provided (syncs both charts), fall back to internal
  const timeRange = externalTimeRange ?? internalTimeRange;
  const handleTimeRangeChange = (range: TimeRange) => {
    if (onTimeRangeChange) onTimeRangeChange(range);
    else setInternalTimeRange(range);
  };

  // Sync timeRange when data loads asynchronously — useState only uses
  // its initial value on mount, so if history arrives after first render
  // the default stays "all" even when it should be "live"
  const [hasUserOverridden, setHasUserOverridden] = useState(false);

  // Lead-change diamonds are OFF by default (L2-131): they clutter the one clean
  // blend line. A toggle surfaces them for the games where they tell a story.
  const [showLeadChanges, setShowLeadChanges] = useState(false);
  useEffect(() => {
    if (!hasUserOverridden && !externalTimeRange && defaultTimeRange === "live") {
      setInternalTimeRange("live");
    }
  }, [defaultTimeRange, hasUserOverridden, externalTimeRange]);

  // For "Since Start" mode, use commenceTime directly as the start cutoff.
  // Previously used a "smartStartTime" that scanned for the first 2% odds
  // change — but with sparse betting data (one point every ~30 min), this
  // often skipped 1-2 hours past the actual game start, showing 6:20 PM
  // instead of 4:30 PM for a game that started at 4:30 PM.
  // commenceTime is the actual game start from ESPN/StatPal/Odds API —
  // use it directly.

  // Determine chart end boundary for completed games.
  // Use last game data point (ESPN/odds), NOT completedAt which is a backend
  // processing timestamp often 30-45 minutes after the game actually ended.
  const smartEndTime = useMemo(() => {
    if (!isClosed) return null;

    const gameEndCandidates: Date[] = [];

    // ESPN history — most reliable game-end signal
    if (espnHistory && espnHistory.length > 0) {
      gameEndCandidates.push(parseISO(espnHistory[espnHistory.length - 1].timestamp));
    }

    // Game-end data sources only — sportsbooks/prediction markets poll late
    const GAME_END_SOURCES = new Set(["espn", "stat_model", "fangraphs", "mlb"]);
    if (winProbHistory) {
      for (const [source, points] of Object.entries(winProbHistory)) {
        if (points.length > 0 && GAME_END_SOURCES.has(source)) {
          gameEndCandidates.push(parseISO(points[points.length - 1].timestamp));
        }
      }
    }

    if (gameEndCandidates.length > 0) {
      const latestGameEnd = gameEndCandidates.reduce((a, b) => (a > b ? a : b));

      // Also check sportsbook data — if it extends slightly beyond game-end
      // sources, include it. This prevents premature cutoff when ESPN data
      // is sparse (e.g., baseball chart cutting off at 8th inning while
      // sportsbooks have data through the 9th).
      let endTime = latestGameEnd;
      const MAX_EXTENSION_MS = 10 * 60 * 1000; // 10 min max extension
      if (history && history.length > 0) {
        const lastBetting = parseISO(history[history.length - 1].timestamp);
        if (lastBetting > latestGameEnd && lastBetting.getTime() - latestGameEnd.getTime() <= MAX_EXTENSION_MS) {
          endTime = lastBetting;
        }
      }

      // End AT the final snapshot — no trailing buffer (L2-131 / gotcha #22).
      // The old +5 min pad forward-filled a flat tail that read like the game
      // kept going after it ended.
      return new Date(endTime.getTime());
    }

    // No game-end sources — end at the last sportsbook snapshot.
    if (history && history.length > 0) {
      const lastBetting = parseISO(history[history.length - 1].timestamp);
      return new Date(lastBetting.getTime());
    }

    // Last resort: completedAt (backend timestamp, not ideal)
    if (completedAt) {
      return new Date(parseISO(completedAt).getTime());
    }

    return null;
  }, [isClosed, completedAt, espnHistory, winProbHistory, history]);

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

    const ensurePoint = makeEnsurePoint<ChartDataPoint>(dataMap, () => ({
      homeDelta: null,
      espnDelta: null,
      bainLuckDelta: null,
    }));

    // Add aggregate data points (betting odds consensus). Values are the raw
    // home win probability on a 0–100 axis (single-axis, not ±50 delta).
    for (const point of filteredHistory) {
      const delta =
        point.home_probability !== null ? point.home_probability * 100 : null;

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
        const delta =
          point.home_probability !== null
            ? point.home_probability * 100
            : null;

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
          const delta =
            point.home_probability !== null ? point.home_probability * 100 : null;

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
        const delta =
          point.home_probability !== null ? point.home_probability * 100 : null;

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
          const delta = point.home_probability * 100;
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
    // each category gets equal pixel width. Without filling gaps, the charts
    // have non-linear x-axes (chunks of time appear compressed or expanded).
    // Filling every minute ensures linear time and identical category sets.
    {
      let first: Date | null = null;
      let last: Date | null = null;

      if (chartStartTime && chartEndTime) {
        // Use shared domain from parent for perfect chart alignment
        first = parseISO(chartStartTime);
        last = parseISO(chartEndTime);
      } else {
        const allTimestamps = Array.from(dataMap.keys()).sort();
        if (allTimestamps.length >= 2) {
          first = parseISO(allTimestamps[0]);
          last = parseISO(allTimestamps[allTimestamps.length - 1]);
        }
      }

      if (first && last) {
        fillMinuteGaps(first, last, ensurePoint);
      }
    }

    // Ensure period boundary timestamps exist as chart data points.
    // ReferenceLine on a categorical x-axis only renders when the x value
    // matches an existing category. Without this, boundaries that fall
    // between data points silently vanish.
    if (periodBoundaries && periodBoundaries.length > 0) {
      for (const b of periodBoundaries) {
        ensurePoint(b.timestamp);
      }
    }

    // Forward-fill probability data: carry last known value through gap-filled
    // minutes so lines appear continuous instead of showing visual gaps.
    // Without this, gap-filled minutes have null deltas and Recharts must rely
    // on connectNulls to draw a thin interpolation — which can look broken
    // when there are many consecutive nulls (e.g., sparse MLB betting data).
    // Forward-filling is semantically correct: the probability IS the last
    // known value until a new data point arrives.
    const sorted = Array.from(dataMap.values()).sort(
      (a, b) => parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime()
    );

    // Collect all probability delta keys to forward-fill
    const probKeys: string[] = ["homeDelta", "bainLuckDelta", "espnDelta"];
    for (const source of nonBettingSources) {
      probKeys.push(source.dataKey);
    }
    for (const bookmaker of Object.keys(filteredBookmakerHistory)) {
      probKeys.push(`${bookmaker}_delta`);
    }

    const lastKnown: Record<string, number | null> = {};
    for (const key of probKeys) {
      lastKnown[key] = null;
    }
    for (const pt of sorted) {
      for (const key of probKeys) {
        const val = pt[key];
        if (typeof val === "number") {
          lastKnown[key] = val;
        } else if (lastKnown[key] !== null) {
          pt[key] = lastKnown[key];
        }
      }
    }

    // Forward-fill game state: carry most recent score/period/clock to subsequent points
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
      // Track clock exactness: a point that carries its OWN clock is exact; a
      // gap-filled minute inherits the last clock and must be flagged approximate
      // so the readout never shows a stale carry-forward as if live (#925).
      if (pt._clock) {
        lastClock = pt._clock as string;
        pt._clockApprox = false;
      } else {
        pt._clock = lastClock;
        pt._clockApprox = lastClock != null;
      }
    }

    return sorted;
  }, [filteredHistory, filteredBookmakerHistory, filteredWinProbHistory, filteredEspnHistory, useNewWinProbData, nonBettingSources, isMultiSource, resolvedSources, filteredAggregateLine, scoringPlays, timeRange, periodBoundaries]);

  // Report the chart's actual rendered time domain to parent so
  // ScoreDifferentialChart can match its x-axis exactly.
  useEffect(() => {
    if (!onRenderedDomain || chartData.length === 0) return;
    const first = chartData[0].timestamp;
    const last = chartData[chartData.length - 1].timestamp;
    onRenderedDomain(first, last);
  }, [chartData, onRenderedDomain]);



  // Compute "Game Start" reference line time (formatted to match chart categories)
  const gameStartTime = useMemo(() => {
    if (!commenceTime || chartData.length === 0) return null;
    const startMs = parseISO(commenceTime).getTime();
    const chartStartMs = parseISO(chartData[0].timestamp).getTime();
    const chartEndMs = parseISO(chartData[chartData.length - 1].timestamp).getTime();
    // Only show if the start time falls within the chart's visible range
    if (startMs < chartStartMs || startMs > chartEndMs) return null;
    // Round to minute for categorical match
    const d = parseISO(commenceTime);
    d.setSeconds(0, 0);
    return format(d, "h:mm a");
  }, [commenceTime, chartData]);

  // Filter period boundaries to match chart time range, deduplicate close markers,
  // and alternate label positions to prevent overlapping text.
  const filteredPeriodBoundaries = useMemo(() => {
    if (!periodBoundaries || periodBoundaries.length === 0 || chartData.length === 0) return [];
    const chartStart = parseISO(chartData[0].timestamp).getTime();
    const chartEnd = parseISO(chartData[chartData.length - 1].timestamp).getTime();
    const chartDuration = chartEnd - chartStart;

    // Minimum spacing: 3% of chart duration (prevents overlapping labels)
    const minSpacing = Math.max(chartDuration * 0.03, 120_000); // At least 2 minutes

    const filtered = periodBoundaries
      .filter((b) => {
        const t = parseISO(b.timestamp).getTime();
        if (t < chartStart || t > chartEnd) return false;
        // Drop any "Final"-like boundary — the single explicit Final marker below
        // owns the game-end label, so there is exactly one (L2-131).
        if (/^(final|ft|f|full\s*time)$/i.test(b.label.trim())) return false;
        return true;
      })
      .sort((a, b) => parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime());

    // Deduplicate: when two boundaries are too close, keep the later one
    // (e.g., "End of Q2" and "HT" at nearly the same time -> keep "HT")
    const deduped: typeof filtered = [];
    for (const b of filtered) {
      const t = parseISO(b.timestamp).getTime();
      if (deduped.length > 0) {
        const prevT = parseISO(deduped[deduped.length - 1].timestamp).getTime();
        if (t - prevT < minSpacing) {
          // Replace previous with this one (prefer later label like "HT" over "Q2 end")
          deduped[deduped.length - 1] = b;
          continue;
        }
      }
      deduped.push(b);
    }

    return deduped.map((b, i) => ({
      ...b,
      time: format(parseISO(b.timestamp), "h:mm a"),
      // Alternate label positions: even=top-left, odd=top-right
      labelPosition: i % 2 === 0 ? "insideTopLeft" : "insideTopRight",
    }));
  }, [periodBoundaries, chartData]);

  // "Final" marker (settled games only): a single vertical line at the last
  // chart category — i.e. the final snapshot, which is now the chart's right
  // edge (buffer removed). Exactly one, deduped against period boundaries above.
  const finalMarkerTime = useMemo(() => {
    if (!isClosed || chartData.length === 0) return null;
    return chartData[chartData.length - 1].time;
  }, [isClosed, chartData]);

  // Single 0–100 win-probability axis (L2-131): the line is the HOME team's win
  // probability read straight up the scale. This replaces the old mirrored ±50
  // dual-axis where the same "80%" appeared both above and below center.
  const yDomain: [number, number] = [0, 100];
  const yTicks = [0, 25, 50, 75, 100];

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
        // A lead change is a crossing of the 50% line (0–100 axis).
        if ((prevDelta > 50 && delta <= 50) || (prevDelta < 50 && delta >= 50)) {
          pt.leadChangeDelta = 50; // Stamp at y=50 (the 50% line)
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
        const homeProb = delta; // 0–100 axis: the value IS the home probability
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
      handleTimeRangeChange("all");
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
  const homeShort = homeTeamAbbrev || homeTeam.split(" ").pop() || homeTeam;
  const awayShort = awayTeamAbbrev || awayTeam.split(" ").pop() || awayTeam;

  // Y-axis tick formatter: the value is already the home win probability (0–100).
  const formatYTick = (value: number): string => `${value}%`;

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
        const homeProb = delta; // 0–100 axis: value is the home probability
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
        <div className="bg-surface-card p-3 rounded-lg shadow-lg border border-surface-border max-w-sm">
          {/* Game state header — score, period, clock */}
          {hasGameState ? (
            <div className="mb-2 pb-2 border-b border-surface-border">
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
          {/* Scoring play annotation (tooltip only — no dots on chart) */}
          {matchingPoint?._scoringPlay && (() => {
            const play = matchingPoint._scoringPlay as ScoringPlay;
            return (
              <div className="mb-2 pb-2 border-b border-surface-border">
                <p className="text-xs font-semibold text-amber-400 flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-amber-400" />
                  {play.description || play.type}
                </p>
              </div>
            );
          })()}

          {/* Multi-source mode: Bain Luck aggregated first, then individual sources */}
          {isMultiSource && bainLuckEntry && (
            <div className="mb-2 pb-2 border-b border-surface-border">
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
            <div className="mt-2 pt-2 border-t border-surface-border">
              <p className="text-xs text-text-muted mb-1">By sportsbook:</p>
              {bookmakerEntries.map((entry) => {
                const bookmaker = entry.dataKey.replace("_delta", "");
                const homeProb = entry.value; // 0–100 axis
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
              handleTimeRangeChange(option.value);
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

        {/* Lead-change toggle — only offered when there are crossings to show.
            Hidden in the compact fillContainer (fullscreen) layout. */}
        {!fillContainer && leadChangeCount > 0 && (
          <button
            onClick={() => setShowLeadChanges((v) => !v)}
            className={`ml-auto flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
              showLeadChanges
                ? "bg-text-primary text-surface-deep"
                : "bg-surface-elevated text-text-secondary hover:bg-surface-border"
            }`}
            title={showLeadChanges ? "Hide lead changes" : "Show lead changes"}
            aria-pressed={showLeadChanges}
          >
            <svg width="9" height="9" viewBox="0 0 10 10" className="shrink-0">
              <polygon points="5,0 10,5 5,10 0,5" fill="currentColor" />
            </svg>
            Lead changes ({leadChangeCount})
          </button>
        )}
      </div>

      {/* Probability Chart with vertical team labels */}
      <div className={`flex ${fillContainer ? "flex-1 min-h-0" : "h-80"}`}>
        {/* Vertical team labels on left side of chart */}
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
            margin={{ top: 15, right: 10, left: 0, bottom: 5 }}
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
              const homeProb = delta != null ? delta / 100 : 0.5; // 0–100 axis → 0–1
              onActivePointChange({
                timestamp: pt.timestamp,
                homeProb,
                awayProb: 1 - homeProb,
                homeScore: pt._homeScore as number | null | undefined,
                awayScore: pt._awayScore as number | null | undefined,
                period: pt._period as string | null | undefined,
                clock: pt._clock as string | null | undefined,
                clockApprox: pt._clockApprox as boolean | undefined,
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
              domain={yDomain}
              ticks={yTicks}
              width={44}
              tick={{ fontSize: 13, fill: "#4B5563" }}
              tickLine={false}
              axisLine={{ stroke: "rgba(0,0,0,0.1)" }}
              tickFormatter={formatYTick}
            />
            {/* 50% reference line */}
            <ReferenceLine
              y={50}
              stroke="rgba(0,0,0,0.2)"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              label={{
                value: "50%",
                position: "right",
                style: { fontSize: 10, fill: "rgba(0,0,0,0.4)", fontWeight: 600 },
              }}
            />
            {/* Game Start marker — solid line at commence_time */}
            {gameStartTime && filteredPeriodBoundaries.length === 0 && (
              <ReferenceLine
                x={gameStartTime}
                stroke="rgba(0,0,0,0.25)"
                strokeWidth={1.5}
                isFront
                label={{
                  value: "Start",
                  position: "insideTopLeft",
                  style: { fontSize: 11, fill: "rgba(0,0,0,0.6)", fontWeight: 700 },
                }}
              />
            )}
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
                  style: { fontSize: 11, fill: "rgba(0,0,0,0.65)", fontWeight: 700 },
                }}
              />
            ))}
            {/* Final marker — exactly one, at the game-end snapshot (settled only) */}
            {finalMarkerTime && (
              <ReferenceLine
                x={finalMarkerTime}
                stroke="rgba(0,0,0,0.35)"
                strokeWidth={1.5}
                isFront
                label={{
                  value: "Final",
                  position: "insideTopLeft",
                  style: { fontSize: 11, fill: "rgba(0,0,0,0.7)", fontWeight: 700 },
                }}
              />
            )}
            <Tooltip content={<CustomTooltip />} />

            {/* ── MODE B: Sportsbooks-only — individual bookmaker lines (thin grey) ── */}
            {!isMultiSource && bookmakers.map((bookmaker) => (
              <Line
                key={`${bookmaker}_delta`}
                type="linear"
                dataKey={`${bookmaker}_delta`}
                stroke="rgba(0,0,0,0.15)"
                strokeWidth={1}
                dot={false}
                activeDot={{ r: 3, fill: "rgba(0,0,0,0.3)" }}
                connectNulls
                legendType="none"
              />
            ))}

            {/* ── MODE A: Multi-source — individual source lines (near-invisible so
                the one blended Bain Luck line clearly dominates, per L2-131) ── */}
            {isMultiSource && resolvedSources.map((source) => (
              <Line
                key={source.dataKey}
                type="linear"
                dataKey={source.dataKey}
                name={source.displayName}
                stroke={source.color}
                strokeWidth={1}
                strokeOpacity={0.28}
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
                type="linear"
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
                type="linear"
                dataKey="espnDelta"
                name="ESPN Model"
                stroke={sourceHex("espn")}
                strokeWidth={2.5}
                strokeDasharray="6 3"
                dot={false}
                activeDot={{ r: 4, fill: sourceHex("espn") }}
                connectNulls
              />
            )}

            {/* Area fill removed — was causing green semi-circle artifacts */}

            {/* ── MODE A: Multi-source — aggregated Bain Luck line (prominent, on top) ── */}
            {isMultiSource && (
              <Line
                type="linear"
                dataKey="bainLuckDelta"
                name={BAIN_LUCK_CONFIG.displayName}
                stroke={BAIN_LUCK_CONFIG.color}
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 5, fill: BAIN_LUCK_CONFIG.color }}
                connectNulls
              />
            )}

            {/* ── MODE B: Sportsbooks-only — betting odds line (solid, prominent, on top).
                Dark slate (#0f172a), NOT the old near-white #e5e7eb that vanished on
                the light-mode card (L2-131 "the blend line absent/gray"). ── */}
            {!isMultiSource && (
              <Line
                type="linear"
                dataKey="homeDelta"
                name="Betting Odds"
                stroke={sourceHex("betting")}
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 5, fill: sourceHex("betting") }}
                connectNulls
              />
            )}



            {/* Lead change markers — diamonds at 50% crossings (default off) */}
            {showLeadChanges && leadChangeCount > 0 && (
              <Scatter
                dataKey="leadChangeDelta"
                fill="none"
                shape={(props: { cx?: number; cy?: number; payload?: Record<string, unknown> }) => {
                  if (props.payload?.leadChangeDelta == null) return <g />;
                  const { cx = 0, cy = 0 } = props;
                  return (
                    <g>
                      <polygon
                        points={`${cx},${cy - 6} ${cx + 5},${cy} ${cx},${cy + 6} ${cx - 5},${cy}`}
                        fill="rgba(0,0,0,0.7)"
                        stroke="rgba(0,0,0,0.3)"
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
                shape={(props: { cx?: number; cy?: number; payload?: Record<string, unknown> }) => {
                  if (props.payload?.calloutDelta == null) return <g />;
                  const { cx = 0, cy = 0 } = props;
                  const fillColor = isMultiSource
                    ? BAIN_LUCK_CONFIG.color
                    : sourceHex("betting");
                  return (
                    <g>
                      {/* Outer glow */}
                      <circle cx={cx} cy={cy} r={8} fill={fillColor} fillOpacity={0.2} />
                      {/* Inner dot */}
                      <circle cx={cx} cy={cy} r={5} fill={fillColor} stroke="#FFFFFF" strokeWidth={2} />
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
                  strokeWidth={isMultiSource ? "1" : "2.5"}
                  strokeDasharray={source.dashPattern ?? undefined}
                  strokeOpacity={isMultiSource ? 0.4 : 1}
                />
              </svg>
              <span className={`text-xs ${isMultiSource ? "text-text-muted" : "text-text-secondary hover:text-text-primary"}`}>
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
                stroke="rgba(0,0,0,0.15)"
                strokeWidth="1"
              />
            </svg>
            <span className="text-xs text-text-muted">
              Individual sportsbooks
            </span>
          </div>
        )}



        {/* Lead changes legend (only when the toggle is on) */}
        {showLeadChanges && leadChangeCount > 0 && (
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
