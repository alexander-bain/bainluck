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
import {
  makeEnsurePoint,
  toMinuteKey,
  fillMinuteGaps,
  CATEGORY_LABEL_FORMAT,
} from "@/lib/chartTimeline";
// #1003 guard: the single 0–1 ⇄ 0–100 axis conversion (see eventKeyStats).
import { homeProbToChartAxis, chartAxisToHomeProb } from "@/lib/eventKeyStats";
import { separateLinesLabel, sourceHex, sourceLabel } from "@/lib/sourceColors";
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
  // #2442: the NAME now comes from the source registry (`sourceLabel`), the
  // same place the colour comes from, so this map no longer carries a second
  // spelling of it. `sourceLabel("betting")` is "Sportsbooks".
  betting: { display_name: sourceLabel("betting"), color: sourceHex("betting"), dash_pattern: null, type: "market" },
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
  /** #3419: the format `sharedTicks` were built with. Categories and period
   *  markers must use the SAME string or a tick lands on the wrong column. */
  chartLabelFormat?: string;
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
 * ═══ THE FAINT LINES STAY ANONYMOUS ON THE CHART — ALEX RULED 3B (UX-P154) ═══
 *
 * ⚠️ DO NOT REBUILD END-OF-LINE SOURCE LABELS HERE. This paragraph exists
 * because the argument for them is genuinely good and the next lane to read
 * this chart will make it again.
 *
 * UX-P152 read Alex's *"a faint gray line per source behind it, LABELED
 * (Kalshi / Polymarket / ESPN / sportsbook), barely-there but readable"*
 * (2026-08-28) as a request for an annotation ON the plot, built one
 * (`SourceEndLabel`: each series' name written in its own colour at its own
 * last real point), and put it beside the shipped treatment as panels 3A and
 * 3B for Alex to choose between.
 *
 * **Alex ratified 3B — the shipped `+ N sources` press — over 3A** (review of
 * P149/P150/P151/P152, relayed through the UX-P154 runner directive:
 * *"Panel 3B ('+ N sources' press) is RATIFIED over 3A."*). So 3A is reverted
 * in full: the label component, the last-real-point index, and the per-series
 * `label` prop are gone, and the chart is exactly what it was before UX-P152
 * touched it — the blend at width 3 on top, the source lines at width 1 /
 * opacity 0.28 behind it (L2-131, UX-P022), named only inside the legend.
 *
 * WHAT 3A WAS RIGHT ABOUT, so the finding is not lost with the code: an
 * end-of-line label is the only annotation that can carry WHEN a source stopped
 * being quoted — a sportsbook dropping out of a blowout has its line stop, and
 * a legend cannot show that. That remains true and unsurfaced. It is a real
 * gap, and the next attempt at it should start from that gap rather than from
 * "the faint lines are anonymous", which Alex has now considered and accepted.
 */

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
  chartLabelFormat,
  externalTimeRange,
  onTimeRangeChange,
  completedAt,
}: OddsChartProps) {
  // #3419: the axis is categorical on this label, so it must be spelled the
  // same way the parent spelled its ticks. Absent a parent domain the window is
  // this chart's own min..max, which is what the 12-hour default assumes.
  const labelFormat = chartLabelFormat ?? CATEGORY_LABEL_FORMAT;
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

  // Source legend collapses to "Bain Luck + N sources" by default (L2-163 Item 1,
  // Ruling 1/4): the blend is labeled and dominant; the faint source lines stay
  // unlabeled until the reader expands the legend (or isolates one via hover).
  const [legendExpanded, setLegendExpanded] = useState(false);
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
          // #2442: registry first. The payload serves `"Betting Odds"` for
          // the sportsbook source, and a runtime string is invisible to the
          // shipped-copy scan — so the name is resolved here, not trusted.
          displayName: sourceLabel(key, meta?.display_name ?? fallback?.display_name ?? key),
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

  // ── #1003: the blend line is the BACKEND blend, or it is nothing ──
  // `bainLuckDelta` used to fall back to an unweighted frontend mean of whatever
  // per-source series happened to be loaded, and still rendered under the
  // "Bain Luck (aggregated)" name. An unweighted mean is NOT the blend —
  // production weights are betting 3.0, ESPN 1.5, stat_model 1.0,
  // Kalshi/Polymarket/MLB 0.8 — so that line, its tooltip row, its callout and
  // the live hero it feeds via `onActivePointChange` could all print a number
  // the hero and the Discover card never show. Standing ruling #1 is
  // card == hero == chart, one number per question, and a fabricated mean
  // wearing the blend's name is the 57-vs-20 bug with better manners.
  //
  // The two gates disagreed by construction, which is why the path existed:
  // the backend emits `aggregate_line` only when `len(agg_sources) > 1`
  // (bookmaker consensus counts as one), while the chart drew the aggregated
  // line whenever `nonBettingSources.length > 0` (bookmakers do not count).
  //
  // Now: no backend blend, no blend line. The chart falls back to the same
  // primary series it uses in sportsbooks-only mode, which is a real measured
  // source that is labelled as itself.
  const showBlendLine = isMultiSource && filteredAggregateLine.length > 0;

  // The primary series every "what is the number here" reader uses: the fill
  // gradient, the lead-change count, the current-probability callout, and the
  // hover payload sent to the live hero. Single definition so those four can
  // never disagree about which line the chart is actually about.
  const primarySeriesKey: string = showBlendLine
    ? "bainLuckDelta"
    : history && history.length > 0
      ? "homeDelta"
      : nonBettingSources.length > 0
        ? nonBettingSources[0].dataKey
        : "homeDelta";

  /**
   * The primary series' value at one chart point, or null where it has none
   * (#3425).
   *
   * The three readers below each used to test the raw property against `null`,
   * which is not the same question. `ensurePoint` seeds only `homeDelta`,
   * `espnDelta` and `bainLuckDelta`, so when `primarySeriesKey` is a per-source
   * key — every single-source chart, since that branch picks
   * `nonBettingSources[0].dataKey` — a gap-filled minute carries no such
   * property at all and reads `undefined`. Forward-fill does not cover it
   * either: minutes BEFORE the first real point have no `lastKnown` to carry,
   * and a shared domain routinely opens before the data (a ticker-derived
   * `commence_time` put 15h56m of them in front of /events/15300276).
   *
   * `undefined !== null` is true, so the old guards admitted it and a
   * `(v): v is number` annotation asserted it was a number. `Math.max` of that
   * is NaN, which is how every event page emitted
   * `<stop offset="NaN">` — eight-plus console errors a load, and a fill the
   * browser then declined to paint.
   */
  const primaryValueAt = (pt: ChartDataPoint): number | null => {
    const v = pt[primarySeriesKey];
    return typeof v === "number" && Number.isFinite(v) ? v : null;
  };

  const useNewWinProbData = Object.keys(filteredWinProbHistory).length > 0;
  const bookmakers = useMemo(
    () => Object.keys(filteredBookmakerHistory),
    [filteredBookmakerHistory]
  );

  /**
   * Every ChartDataPoint key this chart can draw as a line.
   *
   * One list, two readers: the forward-fill below carries these keys across
   * gap-filled minutes, and `filteredPeriodBoundaries` uses them to find where
   * the ink actually starts. Those two must agree — a key the chart plots but
   * the boundary guard does not know about would let a chip sit left of the
   * line, and a key the guard counts but nothing plots would put one over blank
   * axis (CERT-1984). Keeping them one definition is the guarantee.
   */
  const plottedProbKeys = useMemo(() => {
    const keys = ["homeDelta", "bainLuckDelta", "espnDelta"];
    for (const source of nonBettingSources) keys.push(source.dataKey);
    for (const bookmaker of Object.keys(filteredBookmakerHistory)) {
      keys.push(`${bookmaker}_delta`);
    }
    return keys;
  }, [nonBettingSources, filteredBookmakerHistory]);

  // Transform data: convert probabilities to delta from 50%
  // Bucket by minute so each category label is unique (see `labelFormat`,
  // #3419) — required for
  // Recharts ReferenceLine (period markers) to match categorical XAxis values.
  const chartData: ChartDataPoint[] = useMemo(() => {
    const dataMap = new Map<string, ChartDataPoint>();

    const ensurePoint = makeEnsurePoint<ChartDataPoint>(dataMap, () => ({
      homeDelta: null,
      espnDelta: null,
      bainLuckDelta: null,
    }), labelFormat);

    // Add aggregate data points (betting odds consensus). Values are the raw
    // home win probability on a 0–100 axis (single-axis, not ±50 delta).
    for (const point of filteredHistory) {
      const delta =
        point.home_probability !== null
          ? homeProbToChartAxis(point.home_probability)
          : null;

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
            ? homeProbToChartAxis(point.home_probability)
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
            point.home_probability !== null
              ? homeProbToChartAxis(point.home_probability)
              : null;

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
          point.home_probability !== null
            ? homeProbToChartAxis(point.home_probability)
            : null;

        const dp = ensurePoint(point.timestamp);
        dp.espnDelta = delta;
      }
    }

    // ── Compute Bain Luck aggregated line (multi-source mode) ──
    // The backend aggregate_line is a weighted median with staleness decay —
    // the same blend the hero and the Discover card render.
    // #1003: ONLY the backend-computed aggregate line. There is deliberately no
    // frontend fallback — see `showBlendLine` above. If the backend did not
    // compute a blend, `bainLuckDelta` stays null and no blend line is drawn.
    if (showBlendLine) {
      for (const point of filteredAggregateLine) {
        const delta = homeProbToChartAxis(point.home_probability);
        const dp = ensurePoint(point.timestamp);
        dp.bainLuckDelta = delta;
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

    // Every key this chart draws (see `plottedProbKeys`) gets forward-filled.
    const probKeys = plottedProbKeys;

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
  // #1003: `resolvedSources` and `isMultiSource` dropped — both were read only
  // by the naive-mean fallback that no longer exists. `showBlendLine` added: it
  // now decides whether `bainLuckDelta` is written at all. (`timeRange` is also
  // unread here, but it predates this change and is left alone.)
  }, [filteredHistory, filteredBookmakerHistory, filteredWinProbHistory, filteredEspnHistory, useNewWinProbData, nonBettingSources, showBlendLine, filteredAggregateLine, scoringPlays, timeRange, periodBoundaries, plottedProbKeys]);

  // Report the chart's actual rendered time domain to parent so
  // ScoreDifferentialChart can match its x-axis exactly.
  useEffect(() => {
    if (!onRenderedDomain || chartData.length === 0) return;
    const first = chartData[0].timestamp;
    const last = chartData[chartData.length - 1].timestamp;
    onRenderedDomain(first, last);
  }, [chartData, onRenderedDomain]);



  /**
   * The extent of the DRAWN LINE — the first and last category actually
   * carrying a plotted value — as opposed to `chartData`'s extent, which also
   * holds null-valued odds buckets, gap-filled minutes and marker timestamps
   * this component inserts itself (CERT-1984).
   */
  const drawnExtent = useMemo(() => {
    const isDrawn = (p: ChartDataPoint) =>
      plottedProbKeys.some((key) => typeof p[key] === "number");
    const first = chartData.findIndex(isDrawn);
    if (first === -1) return null;
    let last = chartData.length - 1;
    while (last > first && !isDrawn(chartData[last])) last--;
    return {
      firstIdx: first,
      lastIdx: last,
      startMs: parseISO(chartData[first].timestamp).getTime(),
      endMs: parseISO(chartData[last].timestamp).getTime(),
    };
  }, [chartData, plottedProbKeys]);

  // Compute "Game Start" reference line time (formatted to match chart categories)
  const gameStartTime = useMemo(() => {
    if (!commenceTime || chartData.length === 0 || !drawnExtent) return null;
    const startMs = parseISO(commenceTime).getTime();
    // Bound against the DRAWN LINE, not `chartData`'s extent (CERT-1984, and
    // #3419 for this marker). The old test used chartData[0], which is the
    // chart's own gap fill — and since #3419 made that fill inclusive of the
    // shared domain's start, `commence_time` became chartData[0] BY
    // CONSTRUCTION, so the test could no longer fail. That is the same
    // circularity CERT-1984 removed from the period markers: a marker creates
    // the very category it is then judged to be inside.
    //
    // It matters because `commence_time` is exactly the field that is wrong
    // when a start was never reported. On /events/15300276 it is a
    // ticker-derived midnight 15h56m before the first Kalshi point, so a
    // "Start" flag pinned to it told the reader the match began on a night it
    // had not yet begun. No ink at that instant, no claim about it.
    if (startMs < drawnExtent.startMs || startMs > drawnExtent.endMs) return null;
    // Round to minute for categorical match
    const d = parseISO(commenceTime);
    d.setSeconds(0, 0);
    return format(d, labelFormat);
  }, [commenceTime, chartData, labelFormat, drawnExtent]);

  // Filter period boundaries to match chart time range, deduplicate close markers,
  // and alternate label positions to prevent overlapping text.
  const filteredPeriodBoundaries = useMemo(() => {
    if (!periodBoundaries || periodBoundaries.length === 0 || chartData.length === 0) return [];

    // Bound against the DRAWN LINE, not the chart's data extent (CERT-1984).
    //
    // `chartData` is not the line. It holds a row per odds bucket even when the
    // aggregate probability came back null, plus gap-filled minutes, plus the
    // boundary timestamps this component itself inserts so Recharts can match a
    // categorical ReferenceLine. Measuring the extent of THAT is circular: a
    // boundary over an empty plot creates the very category it is then judged to
    // be inside, which is how a "1H" chip came to hang over a blank chart.
    //
    // So find the first and last point carrying a value we actually plot. The
    // server drops markers no chart can place, but it cannot know which of the
    // two charts sharing this array is the blank one — only we do. Shared with
    // the "Start" marker via `drawnExtent` so the two bounds cannot drift.
    if (!drawnExtent) return [];
    const chartStart = drawnExtent.startMs;
    const chartEnd = drawnExtent.endMs;

    // Label spacing below is a PIXEL problem, so it is measured on the x-axis —
    // the full data extent — and not on the drawn subset above. Narrowing it to
    // the ink would shrink `minSpacing` and let back the label smear UX-P022 fixed.
    const chartDuration =
      parseISO(chartData[chartData.length - 1].timestamp).getTime() -
      parseISO(chartData[0].timestamp).getTime();

    // Minimum spacing before two markers are collapsed into one.
    //
    // UX-P022: this used to be `max(duration * 3%, 2 minutes)`. Label collision
    // is a function of PIXELS, but the 2-minute floor is a function of TIME, and
    // the two only agree at one chart length. On a 3-hour game 2 minutes is
    // ~1% of the width and far too tight; on a 21-minute live game it is ~10% of
    // the width, so two markers 2 minutes apart were both kept and their labels
    // printed on top of each other — the unreadable "T9|1" smear on a live Red
    // Sox chart.
    //
    // Spacing is now purely proportional, so it means the same thing at every
    // chart length: markers must be at least 7% of the visible width apart, which
    // is comfortably wider than a 2–4 character period label at 11px.
    const minSpacing = chartDuration * 0.07;

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

    return deduped.map((b) => ({
      ...b,
      time: format(parseISO(b.timestamp), labelFormat),
      // UX-P022: labels used to ALTERNATE insideTopLeft / insideTopRight. That
      // reads like it spreads them out, but it does the opposite — a left-anchored
      // label grows rightward and the next right-anchored one grows leftward, so
      // adjacent labels grow TOWARD each other and meet in the middle. Anchoring
      // every label on the same side makes the gap between two markers the actual
      // space available to the first one's text, which is what the spacing rule
      // above assumes.
      labelPosition: "insideTopLeft",
    }));
  }, [periodBoundaries, chartData, plottedProbKeys, labelFormat, drawnExtent]);

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
    const key = primarySeriesKey;
    // Clear any previous stamps
    for (const pt of chartData) {
      delete pt.leadChangeDelta;
    }
    let count = 0;
    let prevDelta: number | null = null;
    for (const pt of chartData) {
      const delta = primaryValueAt(pt);
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
  }, [chartData, primarySeriesKey]);

  // ── Current probability callout (last non-null data point) ──
  // Stamp `calloutDelta` directly onto the chartData point (same reason as above).
  const currentCallout = useMemo(() => {
    if (chartData.length === 0) return null;
    const key = primarySeriesKey;
    // Clear any previous stamps
    for (const pt of chartData) {
      delete pt.calloutDelta;
    }
    // Walk backwards to find last non-null value
    for (let i = chartData.length - 1; i >= 0; i--) {
      const delta = primaryValueAt(chartData[i]);
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
  }, [chartData, primarySeriesKey]);

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
            {/* Ruling 142: "will update … once the game starts" promised a
                future state. Say what the chart plots instead. */}
            <p className="text-xs">This chart plots win probability minute by minute.</p>
          </>
        ) : (
          <p className="text-sm">No history data available</p>
        )}
      </div>
    );
  }

  // Compute gradient offset for area fill-by-value.
  // #1003: reads `primarySeriesKey`. This used to be a second, independently
  // written copy of the same ladder — it fell back to a non-betting source when
  // sportsbooks were missing, while the callout and the hover payload fell back
  // to `homeDelta`. One definition now, so the fill, the callout, the
  // lead-change count and the live hero cannot disagree about which line the
  // chart is actually about.
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
      const bainLuckEntry = showBlendLine
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
          {showBlendLine && bainLuckEntry && (
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
                  {/* #2442: the `(market)` / `(model)` suffix is our OWN
                      taxonomy, printed at the reader. It is the same class
                      L2-157 stripped from the hero — "internal ranking taxonomy
                      pills are NOT user information" — and on a tennis page it
                      rendered as `Betting Odds (market)`, one of the six
                      gambling formats Alex counted on one screen. The source
                      NAME is the useful half and it stays; `source.type` is
                      still carried on the object and still drives styling. */}
                  <p className="text-xs text-text-muted mb-0.5">
                    {source.displayName}
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
    <div
      className={fillContainer ? "flex flex-col h-full gap-1" : "space-y-3"}
      /* HOW MANY PERIOD CHIPS THIS CHART WILL DRAW, on the wrapper (CERT-1984).
         Same reason as ScoreDifferentialChart's `data-*-series`: recharts renders
         nothing inside `ResponsiveContainer` without a viewport, so a server
         render — all a guard or the capture rig can see — cannot observe a
         `<ReferenceLine>`. A guard that looked for the missing "1H" label would
         pass on both arms and be worth nothing. This is the count actually
         rendered below, after the drawn-line bound. */
      data-period-boundaries={filteredPeriodBoundaries.length}
    >
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
        {/* ═══ THE GUTTER IS AN AXIS, NOT TWO MORE SERIES NAMES (#2448) ═══

            Alex, on `/events/15293846`: *"the y-axis is labelled with both
            player names vertically, while the single plotted line is labelled
            `Betting Odds` — three labels, one line."*

            He was right about what he saw and the names were not the error. The
            axis genuinely runs from "the away player wins" at 0% to "the home
            player wins at 100%", so both names belong in the gutter — they are
            its two POLES. What was missing is the only thing that turns two
            names into an axis: a DIRECTION. Without it a reader has two names,
            a 0–100 scale and a line, and no rule connecting them; every one of
            the three labels is equally likely to be the line's.

            One caret per pole fixes it and adds no words. `↑ BERRETTINI` at the
            top and `↓ WAWRINKA` at the bottom says "up is Berrettini", which is
            exactly the missing rule, and the section heading above the chart
            ("Win Probability") already names the quantity while the legend
            below names the source. Three ideas, each said once, instead of
            three names competing to be the same one.

            `aria-hidden` on the caret and a real sentence in `sr-only`: a
            screen reader cannot see which end of a gutter a label is at, so the
            glyph carries nothing for it and the sentence carries everything. */}
        <div className="flex flex-col items-center justify-between py-3 shrink-0" style={{ width: 28 }}>
          <div
            className="flex items-center gap-1"
            style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
            data-testid="chart-axis-pole"
            data-pole="home"
          >
            <span className="sr-only">
              The line rises towards {homeShort}: the top of this axis is {homeShort} at 100%.
            </span>
            {homeTeamLogo && (
              <img src={homeTeamLogo} alt="" width={12} height={12} className="object-contain" style={{ transform: "rotate(90deg)" }} />
            )}
            <span
              aria-hidden="true"
              className="text-[11px] font-bold uppercase tracking-wider"
              style={{ color: homeTeamColor || "#16a34a" }}
            >
              {"↑"} {homeShort}
            </span>
          </div>
          <div
            className="flex items-center gap-1"
            style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
            data-testid="chart-axis-pole"
            data-pole="away"
          >
            <span className="sr-only">
              The line falls towards {awayShort}: the bottom of this axis is {awayShort} at 100%.
            </span>
            {awayTeamLogo && (
              <img src={awayTeamLogo} alt="" width={12} height={12} className="object-contain" style={{ transform: "rotate(90deg)" }} />
            )}
            <span
              aria-hidden="true"
              className="text-[11px] font-bold uppercase tracking-wider"
              style={{ color: awayTeamColor || "#2563eb" }}
            >
              {"↓"} {awayShort}
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
              const delta = pt[primarySeriesKey] as number | null;
              const homeProb = delta != null ? chartAxisToHomeProb(delta) : 0.5; // 0–100 axis → 0–1
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
            {/*
              #3425: the `probFillGradient-<id>` <defs> block that stood here is
              gone. It was DEAD — one definition, and not a single
              `fill="url(#probFillGradient-…)"` anywhere in the frontend, no
              <Area>, nothing. It painted nothing and never had, but it emitted
              its two <stop offset="NaN"> on every event page (8+ console errors
              a load), because its offset came from a `dataMax / (dataMax -
              dataMin)` written for the old mirrored ±50 delta axis and read
              through a guard that let `undefined` through.

              Deleted rather than repaired: computing a correct split for a
              gradient nothing references would be inventing a visual nobody
              asked for and changing every event page's fill to do it. If the
              two-tone fill is wanted back, it is a design decision with a fresh
              offset — the midpoint on today's 0–100 axis is 50, not 0.
            */}
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
            {/* 50% reference line.

                #3525: IT USED TO CARRY A `50%` LABEL AND THAT LABEL WAS NEVER
                ONCE READ BY ANYONE. `position: "right"` puts a label OUTSIDE the
                plot's right edge, and this chart's right margin is 10px against
                a ~22px label, so what actually reached the page was a bare `5`
                clipped at the card boundary, floating beside the dashes at the
                50% gridline with nothing to attach it to. Alex's reading of it —
                a digit a reader can take for a score or a set count — is the
                whole cost, and there was no benefit on the other side of it:
                `yTicks` already includes 50 and the left axis already prints
                `50%` on this exact line, so the label was a duplicate even in the
                world where it rendered. Deleted rather than moved inside, because
                moving it in would put a second `50%` on a chart that already has
                one. The guard is on the class: no rendered text outside a
                chart's plot bounds. */}
            <ReferenceLine
              y={50}
              stroke="rgba(0,0,0,0.2)"
              strokeWidth={1.5}
              strokeDasharray="4 4"
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
            {/* Final marker — exactly one, at the game-end snapshot (settled only).
                THE LINE, AND DELIBERATELY NO LABEL (#3541).

                It used to carry `value: "Final"` at `insideTopLeft`, and what
                reached every settled event page was a bare `F`. `finalMarkerTime`
                is the LAST chart category, which since the right-hand buffer was
                removed is the plot's right rule — and `insideTopLeft` anchors the
                text `start` there, so it grows out of the svg and is clipped to
                its first glyph. That is structural, not a breakpoint: the same
                orphan `F` is on the 1280px shot as on the 390px one, because the
                svg ends 10px past the rule at every width.

                Anchoring it inside instead is the expensive answer and buys
                nothing. `insideTopRight` grows the text LEFT out of the right
                rule, into the space UX-P022 above reserves for the last period
                boundary — and `minSpacing` (7% of the chart) is sized for labels
                that all grow the same way, while the Final marker is deduped only
                against final-LIKE boundaries, so a `Q4` or `T9` can sit right
                beside it. Making the spacing rule bidirectional would be real
                work to restore a word the page already says twice: the hero
                carries a FINAL chip, and the line's own position at the end of
                the timeline is the part that carries information. So the marker
                keeps its full stop and loses its caption.

                Guarded by `chartTextStaysInsideThePlot.test.tsx`, which pins BOTH
                halves — no text off the right edge, and this line still drawn. */}
            {finalMarkerTime && (
              <ReferenceLine
                x={finalMarkerTime}
                stroke="rgba(0,0,0,0.35)"
                strokeWidth={1.5}
                isFront
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
            {isMultiSource && resolvedSources.map((source) => {
              const isPrimarySource = source.dataKey === primarySeriesKey;
              return (
              <Line
                key={source.dataKey}
                type="linear"
                dataKey={source.dataKey}
                name={source.displayName}
                stroke={source.color}
                // UX-P022: these were pinned at width 1 / opacity 0.28 in BOTH
                // states. At that weight, on a light card, a source line that
                // tracks the blend closely is invisible — so pressing
                // "+ N sources" listed the sources in the legend and changed
                // NOTHING on the graph. The control looked broken because, as
                // far as the reader could tell, it was.
                //
                // Collapsed still means blend-dominant (L2-131, and "the blend
                // is the product"). Expanding is the reader explicitly asking to
                // see the spread, so the lines become legible — a deliberate
                // comparison surface, entered on purpose, not shown by default.
                //
                // #3151/#3111: de-emphasis is only correct when something else
                // DOMINATES. `isMultiSource` is true at ONE non-betting source
                // (its own comment says so), and `showBlendLine` needs a backend
                // aggregate — so a Kalshi-only match took this branch with no
                // blend line above it, and the only line on the plot was a 1px
                // 28%-opacity dash. Measured in the production DOM for
                // /events/15300276: 559 points, `stroke-opacity: 0.28`, a
                // correct 852px path nobody can see. It reads as an empty chart.
                //
                // `primarySeriesKey` already names the series the lead-change
                // count and the current-probability callout are computed from.
                // Drawing THAT one at full weight is what keeps the line the
                // reader sees and the numbers printed beside it the same line.
                // When a blend IS drawn it owns `primarySeriesKey`, no source
                // matches, and every source stays faint exactly as before.
                strokeWidth={isPrimarySource ? 2.5 : legendExpanded ? 1.75 : 1}
                strokeOpacity={isPrimarySource ? 1 : legendExpanded ? 0.85 : 0.28}
                strokeDasharray={source.dashPattern ?? undefined}
                dot={false}
                activeDot={{ r: isPrimarySource ? 4 : 3, fill: source.color }}
                connectNulls
              />
              );
            })}

            {/* MODE B's non-betting branch used to stand here, drawing
                `nonBettingSources` at strokeWidth 2.5 under `!isMultiSource`.
                It could never run: `isMultiSource` IS `nonBettingSources.length
                > 0`, so `!isMultiSource` guarantees the array it maps is empty.
                The single-source case it was written for always fell into MODE
                A above instead and was drawn faint — which is #3151/#3111.
                Removed rather than left as a second place to fix the same bug;
                MODE A now handles the primary source at full weight. */}

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
            {showBlendLine && (
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
                name={sourceLabel("betting")}
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
                  const fillColor = showBlendLine
                    ? BAIN_LUCK_CONFIG.color
                    : sourceHex("betting");
                  return (
                    <g>
                      {/* Outer glow */}
                      <circle cx={cx} cy={cy} r={8} fill={fillColor} fillOpacity={0.2} />
                      {/* Inner dot */}
                      <circle cx={cx} cy={cy} r={5} fill={fillColor} stroke="#FFFFFF" strokeWidth={2} />
                      {/* Probability label.

                          #3525 (found by its guard, not by the issue): this
                          was `cx + 12`, anchored `start`, and it had NEVER
                          rendered. The callout marks the LAST data point, and
                          since the right-hand buffer was removed the last data
                          point IS the plot's right edge — so `cx + 12` is
                          always past it, and the svg clips its own overflow.
                          What a reader got was the dot with no number, which is
                          the one thing the callout exists to say; it is visible
                          in `artifacts-live-073/sabalenka-townsend.png`, a
                          ringed green dot at 81% with nothing beside it.

                          It goes on the LEFT unconditionally rather than
                          flipping on a measurement, because there is nothing to
                          measure: the anchor point is the right edge by
                          construction, so the right-hand side is never the
                          answer. 12px clears the dot's 8px glow.

                          #3561, THE HALO: once the number rendered, it rendered
                          ON the line. `cy` is the last data point and the series
                          TERMINATES there, so a label centred on `cy` sits
                          exactly where the line arrives — a collision by
                          construction, not a property of one specimen. It
                          bisected the digits and turned `41%` into `41°`.

                          Lifting it vertically is the obvious answer and is
                          wrong: on a steeply-arriving series the line just left
                          of the dot is ABOVE `cy`, so a lift walks the label
                          into the line instead of out of it, and it would need a
                          clamp against the plot ceiling as well. The label has
                          to stay on the dot's row — it is labelling the dot — so
                          it is made legible OVER ink instead. A painted-under
                          white stroke is slope-independent and needs no
                          geometry. */}
                      <text
                        x={cx - 12}
                        y={cy}
                        textAnchor="end"
                        dominantBaseline="central"
                        fill={fillColor}
                        stroke="#FFFFFF"
                        strokeWidth={3}
                        paintOrder="stroke"
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
        {/* Multi-source mode: Bain Luck aggregated line first (always labeled).
            #1003: gated on showBlendLine, not isMultiSource — a legend entry for a
            line the chart did not draw is the same false claim as the line. */}
        {showBlendLine && (
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

        {/* Multi-source: the individual source lines stay collapsed behind an
            expander so the blend dominates (L2-163 Item 1). Sportsbooks-only mode
            keeps its flat legend (there is no blend to dominate). */}
        {isMultiSource && resolvedSources.length > 0 && !legendExpanded && (
          <button
            type="button"
            onClick={() => setLegendExpanded(true)}
            className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors"
            aria-expanded={false}
          >
            + {resolvedSources.length} source{resolvedSources.length !== 1 ? "s" : ""}
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} className="shrink-0">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        )}

        {/* Individual sources — always shown in sportsbooks-only mode; in
            multi-source mode only once the reader expands the legend. */}
        {(!isMultiSource || legendExpanded) && resolvedSources.map((source) => {
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

        {/* Collapse control when expanded (multi-source only) */}
        {isMultiSource && legendExpanded && resolvedSources.length > 0 && (
          <button
            type="button"
            onClick={() => setLegendExpanded(false)}
            className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors"
            aria-expanded={true}
          >
            Hide
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} className="shrink-0 rotate-180">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        )}

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
            {/* #2442: ONE name per supplier. This legend said "Individual
                sportsbooks" while the page footer said "Sportsbooks" and the
                line itself said "Betting Odds" — three names for one source on
                one screen. The registry decides the noun; the qualifier carries
                the only thing this legend adds, which is that these are the
                separate lines rather than their average.
                #3563: that qualifier used to be `Each {label.toLowerCase()}`,
                which composed with the registry's plural into the non-sentence
                "Each sportsbooks" on every sportsbooks-only page. The phrasing
                now agrees with no number at all — see `separateLinesLabel`. */}
            <span className="text-xs text-text-muted">
              {separateLinesLabel("betting")}
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

      {/* #2448: `Tap/hover for details` DELETED.
          Alex read it as body text under a chart, which is what it was — a
          caption whose entire content was an instruction about our own UI. It
          told a mouse user to hover and a phone user to tap, said nothing about
          the match, and sat in the same visual slot the page uses for facts. A
          tooltip that needs a caption announcing tooltips is not made
          discoverable by the caption; it is made noisy. Nothing replaces it. */}
    </div>
  );
}
