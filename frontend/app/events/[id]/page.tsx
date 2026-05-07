"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import useSWR from "swr";
import { format as fmtDate } from "date-fns";
import { fetchEvent, fetchEventHistory, fetchGameMarkets, fetchTeamProgression, formatProbability } from "@/lib/api";
import type { GameMarketsResponse } from "@/lib/api";
import type { TeamProgressionResponse } from "@/lib/types";
const OddsChart = dynamic(() => import("@/components/OddsChart"), { ssr: false });
const ScoreDifferentialChart = dynamic(() => import("@/components/ScoreDifferentialChart"), { ssr: false });
const BookmakerTable = dynamic(() => import("@/components/BookmakerTable"), { ssr: false });
const RelatedFutures = dynamic(() => import("@/components/RelatedFutures"), { ssr: false });
// SeasonOutlook removed — Playoff Path card in RelatedFutures now uses LeagueContextService
const LineMovementExplainer = dynamic(() => import("@/components/LineMovementExplainer"), { ssr: false });
const GamePlayCard = dynamic(() => import("@/components/GamePlayCard"), { ssr: false });
const SeriesProbability = dynamic(() => import("@/components/SeriesProbability"), { ssr: false });
const TotalPointsSpectrum = dynamic(() => import("@/components/TotalPointsSpectrum"), { ssr: false });
const PlayerPropsDashboard = dynamic(() => import("@/components/PlayerPropsDashboard"), { ssr: false });
const SpecialEventMarkets = dynamic(() => import("@/components/SpecialEventMarkets"), { ssr: false });
const MarketMapSection = dynamic(() => import("@/components/MarketMapSection"), { ssr: false });
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import ErrorMessage from "@/components/ErrorMessage";
import Tooltip from "@/components/Tooltip";
import RelatedByTag from "@/components/RelatedByTag";
import { getLeagueDisplay, getCategoryForLeague } from "@/lib/sportCategories";
import { espnTeamLogoByName } from "@/lib/images";
import {
  useAnalytics,
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
  usePinnedEvents,
} from "@/hooks";
import { isCloseGame, calculateMinutesToStart } from "@/lib/analytics";
import { derivePeriodBoundaries } from "@/lib/periodMarkers";
import type { ActiveChartPoint } from "@/lib/types";
import TeamNameLink from "@/components/TeamNameLink";

// Maps Odds API sport keys to sport hierarchy paths
const SPORT_KEY_TO_LEAGUE_PATH: Record<string, { path: string; label: string }> = {
  basketball_nba: { path: "/sport/basketball/nba", label: "NBA" },
  americanfootball_nfl: { path: "/sport/football/nfl", label: "NFL" },
  baseball_mlb: { path: "/sport/baseball/mlb", label: "MLB" },
  icehockey_nhl: { path: "/sport/hockey/nhl", label: "NHL" },
  basketball_ncaab: { path: "/sport/basketball/ncaab", label: "NCAA Basketball" },
  americanfootball_ncaaf: { path: "/sport/football/ncaaf", label: "NCAA Football" },
  basketball_wnba: { path: "/sport/basketball/wnba", label: "WNBA" },
  soccer_usa_mls: { path: "/sport/soccer/mls", label: "MLS" },
  soccer_epl: { path: "/sport/soccer/epl", label: "EPL" },
  soccer_spain_la_liga: { path: "/sport/soccer/laliga", label: "La Liga" },
  soccer_uefa_champs_league: { path: "/sport/soccer/ucl", label: "Champions League" },
  soccer_germany_bundesliga: { path: "/sport/soccer/bundesliga", label: "Bundesliga" },
  basketball_wncaab: { path: "/sport/basketball/wncaab", label: "NCAA Basketball" },
};

interface EventPageProps {
  params: { id: string };
}

const LIVE_REFRESH_INTERVAL = 32000; // Match backend LIVE_POLL_INTERVAL (32s)
const SCHEDULED_REFRESH_INTERVAL = 120000;

/** Check if history response has ANY win probability data beyond sportsbook odds. */
function _hasAnyWinProbData(data: any): boolean {
  if (!data) return false;
  if (data.espn_history && data.espn_history.length > 0) return true;
  if (data.win_prob_history) {
    for (const points of Object.values(data.win_prob_history)) {
      if (Array.isArray(points) && points.length > 0) return true;
    }
  }
  return false;
}

function formatCountdown(targetTime: string): string {
  const target = new Date(targetTime);
  const now = new Date();
  const diff = target.getTime() - now.getTime();

  if (diff <= 0) return "";

  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function formatStartTime(commenceTime: string): string {
  const date = new Date(commenceTime);
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);

  const timeStr = date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });

  if (date.toDateString() === today.toDateString()) {
    return `Today at ${timeStr}`;
  } else if (date.toDateString() === tomorrow.toDateString()) {
    return `Tomorrow at ${timeStr}`;
  } else {
    const dateStr = date.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
    return `${dateStr} at ${timeStr}`;
  }
}


// Pick key season stats to display based on sport
function getKeyStats(
  stats: Record<string, number | string> | null | undefined,
  sportKey: string | undefined
): Array<{ label: string; value: string | number }> {
  if (!stats) return [];
  const result: Array<{ label: string; value: string | number }> = [];
  const s = sportKey?.toLowerCase() || "";

  if (s.includes("basketball")) {
    if (stats.ppg != null) result.push({ label: "PPG", value: stats.ppg });
    if (stats.rpg != null) result.push({ label: "RPG", value: stats.rpg });
    if (stats.apg != null) result.push({ label: "APG", value: stats.apg });
    if (stats.opp_ppg != null) result.push({ label: "Opp PPG", value: stats.opp_ppg });
  } else if (s.includes("football")) {
    if (stats.points_per_game != null) result.push({ label: "PTS/G", value: stats.points_per_game });
    if (stats.yards_per_game != null) result.push({ label: "YDS/G", value: stats.yards_per_game });
    if (stats.opp_points_per_game != null) result.push({ label: "Opp PTS/G", value: stats.opp_points_per_game });
  } else if (s.includes("baseball")) {
    if (stats.batting_avg != null) result.push({ label: "AVG", value: stats.batting_avg });
    if (stats.era != null) result.push({ label: "ERA", value: stats.era });
    if (stats.runs_per_game != null) result.push({ label: "R/G", value: stats.runs_per_game });
  } else if (s.includes("hockey")) {
    if (stats.goals_for_per_game != null) result.push({ label: "GF/G", value: stats.goals_for_per_game });
    if (stats.goals_against_per_game != null) result.push({ label: "GA/G", value: stats.goals_against_per_game });
    if (stats.power_play_pct != null) result.push({ label: "PP%", value: stats.power_play_pct });
  } else if (s.includes("soccer")) {
    if (stats.goals_per_game != null) result.push({ label: "G/G", value: stats.goals_per_game });
    if (stats.clean_sheets != null) result.push({ label: "CS", value: stats.clean_sheets });
    if (stats.goals_against_per_game != null) result.push({ label: "GA/G", value: stats.goals_against_per_game });
  } else {
    // Generic: show first 3 numeric stats
    for (const [key, val] of Object.entries(stats)) {
      if (result.length >= 3) break;
      if (typeof val === "number" || (typeof val === "string" && !isNaN(Number(val)))) {
        result.push({ label: key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()), value: val });
      }
    }
  }
  return result.slice(0, 4);
}

export default function EventPage({ params }: EventPageProps) {
  const eventId = parseInt(params.id, 10);
  const [countdown, setCountdown] = useState<number>(0);
  const [gameCountdown, setGameCountdown] = useState<string>("");
  const [lastRefresh, setLastRefresh] = useState<number>(Date.now());
  const hasTrackedDetailView = useRef(false);
  const [activeChartPoint, setActiveChartPoint] = useState<ActiveChartPoint | null>(null);
  const [oddsChartDomain, setOddsChartDomain] = useState<{ start: string; end: string } | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [chartFullscreen, setChartFullscreen] = useState(false);
  const [chartTimeRange, setChartTimeRange] = useState<"all" | "live">("live");
  const handleRenderedDomain = useCallback((start: string, end: string) => {
    setOddsChartDomain((prev) => {
      if (prev && prev.start === start && prev.end === end) return prev;
      return { start, end };
    });
  }, []);

  // Analytics
  const { track, trackNavigationClick, recordEvent } = useAnalytics();

  // Pinned events
  const { isPinned, togglePin, isMaxReached } = usePinnedEvents();
  const eventIsPinned = isPinned(eventId);

  const {
    data: event,
    error: eventError,
    isLoading: eventLoading,
    mutate: refreshEvent,
  } = useSWR(
    ["event", eventId],
    () => fetchEvent(eventId),
    {
      refreshInterval: (data) =>
        data?.status === "live" ? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL,
      onSuccess: () => setLastRefresh(Date.now()),
    }
  );

  // Check if the game has actually started (commence_time is in the past)
  const hasStarted = event?.commence_time
    ? new Date(event.commence_time).getTime() <= Date.now()
    : false;

  // Only consider "live" if the status is "live" AND the game has actually started
  // This guards against cases where the backend status might be incorrect
  const isLive = event?.status === "live" && hasStarted;
  const isCompleted = event?.status === "completed";
  const isClosed = event?.status === "closed";
  const isFinished = isCompleted || isClosed;
  const refreshInterval = isLive ? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL;

  // Effectively live = event is live status
  const effectivelyLive = isLive;

  // Track page view with event-specific parameters
  usePageTracking({
    pageType: 'event_detail',
    pageTitle: event ? `${event.home_team} vs ${event.away_team} - Bain Luck` : 'Event - Bain Luck',
    additionalParams: event ? {
      event_id: event.id,
      sport: event.sport || undefined,
      league: event.sport || undefined,
      event_status: event.status,
    } : {},
    deps: [event?.id],
  });

  // Track scroll depth
  useScrollDepth({
    pageType: 'event_detail',
    eventId: event?.id,
    enabled: !!event,
  });

  // Track engagement time
  useEngagementTime({
    pageType: 'event_detail',
    eventId: event?.id,
    enabled: !!event,
  });

  // Track event detail view (once per page load)
  useEffect(() => {
    if (event && !hasTrackedDetailView.current) {
      hasTrackedDetailView.current = true;

      // Check staleness for analytics (not shown to user)
      const now = new Date();
      const commenceTime = new Date(event.commence_time);
      const hoursSinceStart = (now.getTime() - commenceTime.getTime()) / (1000 * 60 * 60);
      const isNeedsReview = event.status === "live" && hoursSinceStart > 4;

      let isStale = false;
      if (event.current_odds?.captured_at) {
        const lastUpdate = new Date(event.current_odds.captured_at);
        const minutesSinceUpdate = (now.getTime() - lastUpdate.getTime()) / (1000 * 60);
        isStale = minutesSinceUpdate > 30;
      }

      track('event_detail_view', {
        event_id: event.id,
        sport: event.sport || 'unknown',
        league: event.sport || 'unknown',
        home_team: event.home_team,
        away_team: event.away_team,
        status: event.status,
        home_probability: event.current_odds?.home_probability ?? null,
        away_probability: event.current_odds?.away_probability ?? null,
        is_close_game: isCloseGame(event.current_odds?.home_probability),
        is_live: event.status === 'live',
        is_stale: isStale,
        is_needs_review: isNeedsReview,
        bookmaker_count: event.current_odds?.bookmaker_count ?? event.bookmaker_odds?.length ?? 0,
        minutes_to_start: calculateMinutesToStart(event.commence_time),
        entry_method: document.referrer.includes(window.location.hostname) ? 'card_click' : 'direct',
      });

      // Record for session stats
      recordEvent(event.id, event.sport || undefined);
    }
  }, [event, track, recordEvent]);

  useEffect(() => {
    const interval = setInterval(() => {
      const elapsed = Date.now() - lastRefresh;
      const remaining = refreshInterval - (elapsed % refreshInterval);
      setCountdown(Math.ceil(remaining / 1000));
    }, 100);
    return () => clearInterval(interval);
  }, [lastRefresh, refreshInterval]);

  useEffect(() => {
    if (!event?.commence_time || isLive || isFinished) {
      setGameCountdown("");
      return;
    }
    const updateCountdown = () => {
      setGameCountdown(formatCountdown(event.commence_time));
    };
    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);
    return () => clearInterval(interval);
  }, [event?.commence_time, isLive, isFinished]);

  const {
    data: historyData,
    error: historyError,
    isLoading: historyLoading,
    mutate: refreshHistory,
  } = useSWR(
    event ? ["history", eventId] : null,
    () => fetchEventHistory(eventId, 48),
    { refreshInterval: isLive ? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL }
  );

  // Game-level markets (totals spectrum, player props)
  const { data: gameMarkets } = useSWR(
    event ? ["game-markets", eventId] : null,
    () => fetchGameMarkets(eventId),
    { refreshInterval: isLive ? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL }
  );

  // Team championship progression (playoff path from grid data — always available for both teams)
  const { data: teamProgression } = useSWR<TeamProgressionResponse>(
    event ? ["team-progression", eventId] : null,
    () => fetchTeamProgression(eventId),
    { revalidateOnFocus: false, dedupingInterval: 300000 }
  );

  // Compute real game start time: use earliest livescores data point when it's
  // notably later than the Odds API commence_time (which can be off by minutes).
  // Priority: StatPal score_history (most frequent) > ESPN > win_prob_history
  const realStartTime = useMemo(() => {
    const nominal = event?.commence_time;
    if (!nominal) return undefined;
    const nominalMs = new Date(nominal).getTime();

    // Find earliest livescores data point across all sources
    let earliestLive = Infinity;
    // StatPal livescores — most frequent updates, best source for real start
    if (historyData?.score_history?.length) {
      const first = new Date(historyData.score_history[0].timestamp).getTime();
      if (first < earliestLive) earliestLive = first;
    }
    // ESPN history
    if (historyData?.espn_history?.length) {
      const first = new Date(historyData.espn_history[0].timestamp).getTime();
      if (first < earliestLive) earliestLive = first;
    }
    // Win prob history (all sources)
    if (historyData?.win_prob_history) {
      for (const points of Object.values(historyData.win_prob_history)) {
        if (points.length > 0) {
          const first = new Date(points[0].timestamp).getTime();
          if (first < earliestLive) earliestLive = first;
        }
      }
    }

    // If livescores start is >3min later than nominal, use livescores start
    if (earliestLive !== Infinity && earliestLive > nominalMs + 3 * 60 * 1000) {
      return new Date(earliestLive).toISOString();
    }
    return nominal;
  }, [event?.commence_time, historyData?.score_history, historyData?.espn_history, historyData?.win_prob_history]);

  // Derive period boundaries from history data for chart annotations
  const periodBoundaries = useMemo(() => {
    return derivePeriodBoundaries(
      historyData?.espn_history,
      historyData?.win_prob_history,
      historyData?.scoring_plays,
      realStartTime,
      historyData?.period_markers,
    );
  }, [historyData?.espn_history, historyData?.win_prob_history, historyData?.scoring_plays, realStartTime, historyData?.period_markers]);

  // Shared chart domain — time-range-aware, passed to both OddsChart and ScoreDiffChart
  // so they have IDENTICAL x-axes, tick labels, and period markers.
  const sharedChartDomain = useMemo(() => {
    if (!historyData) return null;
    const timestamps: number[] = [];
    for (const pt of historyData.history ?? []) {
      const t = new Date(pt.timestamp).getTime();
      if (!isNaN(t)) timestamps.push(t);
    }
    for (const pts of Object.values(historyData.win_prob_history ?? {})) {
      for (const pt of pts) {
        const t = new Date(pt.timestamp).getTime();
        if (!isNaN(t)) timestamps.push(t);
      }
    }
    for (const pt of historyData.espn_history ?? []) {
      const t = new Date(pt.timestamp).getTime();
      if (!isNaN(t)) timestamps.push(t);
    }
    for (const pts of Object.values(historyData.bookmaker_history ?? {})) {
      for (const pt of pts) {
        const t = new Date(pt.timestamp).getTime();
        if (!isNaN(t)) timestamps.push(t);
      }
    }
    if (timestamps.length === 0) return null;

    const allStart = new Date(Math.min(...timestamps));
    let end = new Date(Math.max(...timestamps));

    // For completed games, derive end time ONLY from game-end sources.
    // Sportsbooks, Kalshi, and Polymarket continue polling 30-45 min after
    // the final whistle, so using their timestamps extends the chart too far.
    const isCompleted = event?.status === "completed" || event?.status === "closed";
    if (isCompleted) {
      const GAME_END_SOURCES = new Set(["espn", "stat_model", "fangraphs", "mlb"]);
      const gameEndTs: number[] = [];

      for (const pt of historyData.espn_history ?? []) {
        const t = new Date(pt.timestamp).getTime();
        if (!isNaN(t)) gameEndTs.push(t);
      }
      for (const [source, pts] of Object.entries(historyData.win_prob_history ?? {})) {
        if (!GAME_END_SOURCES.has(source)) continue;
        for (const pt of pts) {
          const t = new Date(pt.timestamp).getTime();
          if (!isNaN(t)) gameEndTs.push(t);
        }
      }

      if (gameEndTs.length > 0) {
        const lastGameData = new Date(Math.max(...gameEndTs));
        lastGameData.setMinutes(lastGameData.getMinutes() + 2);
        end = lastGameData;
      } else if (event?.commence_time) {
        // Fallback for non-US sports (soccer, cricket, tennis) with no ESPN/model data.
        // Estimate game end from commence_time + sport-specific duration.
        const ct = new Date(event.commence_time);
        if (!isNaN(ct.getTime())) {
          const sport = event.sport || "";
          const isSoccer = sport.startsWith("soccer");
          const isTennis = sport.startsWith("tennis");
          const isCricket = sport.startsWith("cricket");
          const durationMin = isSoccer ? 110 : isTennis ? 180 : isCricket ? 240 : 150;
          const estimated = new Date(ct.getTime() + durationMin * 60_000);
          end = estimated < end ? estimated : end;
        }
      } else if (historyData.completed_at) {
        const ca = new Date(historyData.completed_at);
        if (!isNaN(ca.getTime())) {
          end = ca;
        }
      }
    }

    // "Since Start" mode: start from commenceTime (game start)
    const gameStart = event?.commence_time ? new Date(event.commence_time) : null;
    const liveStart = gameStart && !isNaN(gameStart.getTime()) ? gameStart : allStart;

    const start = chartTimeRange === "live" ? liveStart : allStart;
    start.setSeconds(0, 0);
    end.setSeconds(0, 0);
    // Compute explicit X-axis ticks at clean time boundaries so both charts
    // render identical tick labels. Uses 30-min intervals for games <3h,
    // 60-min for longer games, snapped to round clock times (:00, :30).
    const durationMs = end.getTime() - start.getTime();
    const durationMin = durationMs / 60000;
    let intervalMin = durationMin < 180 ? 30 : 60;
    while (durationMin / intervalMin > 10) intervalMin *= 2;

    const ticks: string[] = [];
    ticks.push(fmtDate(start, "h:mm a"));

    const cursor = new Date(start);
    const curMins = cursor.getMinutes();
    const nextBoundary = Math.ceil((curMins + 1) / intervalMin) * intervalMin;
    cursor.setMinutes(nextBoundary, 0, 0);
    while (cursor < end) {
      ticks.push(fmtDate(cursor, "h:mm a"));
      cursor.setMinutes(cursor.getMinutes() + intervalMin);
    }

    const endLabel = fmtDate(end, "h:mm a");
    if (ticks[ticks.length - 1] !== endLabel) {
      ticks.push(endLabel);
    }

    return { start: start.toISOString(), end: end.toISOString(), ticks };
  }, [historyData, chartTimeRange, event?.commence_time]);

  // Compute the most recent chart point for GamePlayCard default display
  const lastChartPoint = useMemo<ActiveChartPoint | null>(() => {
    if (!historyData) return null;
    // Use the last ESPN history point for score/period/clock
    const espn = historyData.espn_history;
    const lastEspn = espn?.length ? espn[espn.length - 1] : null;
    // Use the last win prob history point for probability — win_prob_history is Record<string, WinProbHistoryPoint[]>
    const wpHistory = historyData.win_prob_history;
    let lastWp: { home_probability: number | null; timestamp: string } | null = null;
    if (wpHistory) {
      for (const pts of Object.values(wpHistory)) {
        if (pts.length) {
          const last = pts[pts.length - 1];
          if (!lastWp || last.timestamp > lastWp.timestamp) {
            lastWp = last;
          }
        }
      }
    }
    // Use latest history point for odds-based probability
    const hist = historyData.history;
    const lastHist = hist?.length ? hist[hist.length - 1] : null;

    const homeProb = lastWp?.home_probability
      ?? (lastHist?.home_probability != null ? lastHist.home_probability / 100 : null)
      ?? 0.5;

    return {
      timestamp: lastEspn?.timestamp || lastWp?.timestamp || lastHist?.timestamp || "",
      homeProb,
      awayProb: 1 - homeProb,
      homeScore: lastEspn?.home_score ?? event?.home_score ?? null,
      awayScore: lastEspn?.away_score ?? event?.away_score ?? null,
      period: lastEspn?.period?.toString() ?? null,
      clock: lastEspn?.game_clock ?? null,
    };
  }, [historyData, event?.home_score, event?.away_score]);

  // Best-known scores: prefer latest ESPN history (more frequent updates) over event SWR
  const bestHomeScore = lastChartPoint?.homeScore ?? event?.home_score ?? null;
  const bestAwayScore = lastChartPoint?.awayScore ?? event?.away_score ?? null;

  // Loading timeout — if the event hasn't loaded after 12s, show error with retry
  const [loadingTimedOut, setLoadingTimedOut] = useState(false);
  useEffect(() => {
    if (!eventLoading) {
      setLoadingTimedOut(false);
      return;
    }
    const timer = setTimeout(() => setLoadingTimedOut(true), 12000);
    return () => clearTimeout(timer);
  }, [eventLoading]);

  if (eventLoading) {
    if (loadingTimedOut) {
      return (
        <ErrorMessage
          title="Loading timed out"
          message="The event is taking too long to load. Try refreshing."
          onRetry={() => {
            setLoadingTimedOut(false);
            refreshEvent();
          }}
        />
      );
    }
    return (
      <div className="py-12">
        <LoadingSpinner text="Loading event..." />
      </div>
    );
  }

  if (eventError || !event) {
    return (
      <ErrorMessage
        title="Event not found"
        message={eventError?.message || "Unable to load event details"}
        onRetry={() => refreshEvent()}
      />
    );
  }

  const odds = event.current_odds;
  const opening = event.opening_odds;

  // Determine the probability to display based on game status:
  // - Scheduled: current betting consensus
  // - Live: current live odds (from history cross-check for reliability) + opening reference
  // - Completed/Closed: opening odds (what was expected before the game)
  let homeProb: number | null = null;
  let awayProb: number | null = null;
  let probSourceLabel: string | null = null;
  let openingHomeProb = opening?.home_probability ?? null;
  let openingAwayProb = opening?.away_probability ?? null;

  if (isFinished) {
    // Completed/closed: show opening odds — "what was expected"
    homeProb = openingHomeProb;
    awayProb = openingAwayProb;
    if (homeProb !== null) {
      probSourceLabel = "Pre-game odds";
    } else {
      // Fallback if no opening odds stored (old events)
      homeProb = odds?.home_probability ?? null;
      awayProb = odds?.away_probability ?? null;
    }
  } else if (isLive) {
    // Live: show current odds, cross-checked against history for accuracy
    homeProb = odds?.home_probability ?? null;
    awayProb = odds?.away_probability ?? null;
    const count = odds?.bookmaker_count ?? 0;

    if (historyData?.history && historyData.history.length > 0) {
      let latestValidHistory: typeof historyData.history[0] | null = null;
      for (let i = historyData.history.length - 1; i >= 0; i--) {
        if (historyData.history[i].home_probability !== null && historyData.history[i].home_probability !== undefined) {
          latestValidHistory = historyData.history[i];
          break;
        }
      }
      if (latestValidHistory) {
        const historyHome = latestValidHistory.home_probability!;
        const historyBookmakers = latestValidHistory.bookmaker_count ?? 0;
        if (homeProb === null || Math.abs(historyHome - homeProb) > 0.05) {
          homeProb = historyHome;
          awayProb = latestValidHistory.away_probability ?? (1 - historyHome);
          if (historyBookmakers > 0) {
            probSourceLabel = `Live · ${historyBookmakers} sportsbook${historyBookmakers !== 1 ? "s" : ""}`;
          }
        }
      }
    }
    if (!probSourceLabel && count > 0) {
      probSourceLabel = `Live · ${count} sportsbook${count !== 1 ? "s" : ""}`;
    }
    // Fallback label when aggregate probability comes from non-sportsbook sources
    if (!probSourceLabel && homeProb !== null && odds?.source === "aggregate") {
      probSourceLabel = "Live · Aggregate";
    }
  } else {
    // Scheduled: current betting consensus
    homeProb = odds?.home_probability ?? null;
    awayProb = odds?.away_probability ?? null;
    const count = odds?.bookmaker_count ?? 0;
    if (count > 0) {
      probSourceLabel = `${count} sportsbook${count !== 1 ? "s" : ""}`;
    } else if (homeProb !== null && odds?.source === "aggregate") {
      probSourceLabel = "Aggregate";
    }
  }

  // Fallback: if no sportsbook odds, use win_prob_history (ESPN/stat_model/Kalshi)
  // For finished events, skip this fallback if the value is essentially 100%/0%
  // (post-game completion probability, not a meaningful pre-game prediction)
  if (homeProb === null && lastChartPoint && lastChartPoint.homeProb !== 0.5
      && !(isFinished && (lastChartPoint.homeProb > 0.95 || lastChartPoint.homeProb < 0.05))) {
    homeProb = lastChartPoint.homeProb;
    awayProb = lastChartPoint.awayProb;
    // Determine source label from win_prob_sources
    const wpSources = historyData?.win_prob_sources;
    if (wpSources && Object.keys(wpSources).length > 0) {
      const sourceNames = Object.keys(wpSources).map(s =>
        s === "stat_model" ? "Model" : s === "espn" ? "ESPN" : s.charAt(0).toUpperCase() + s.slice(1)
      );
      probSourceLabel = isLive
        ? `Live · ${sourceNames.join(", ")}`
        : sourceNames.join(", ");
    }
  }

  const homeFavorite = (homeProb ?? 0) >= (awayProb ?? 0);

  // Calculate countdown progress percentage
  const countdownProgress = ((refreshInterval / 1000 - countdown) / (refreshInterval / 1000)) * 100;

  return (
    <ErrorBoundary fallback={
      <ErrorMessage
        title="Something went wrong"
        message="This page encountered an error. Try refreshing."
        onRetry={() => window.location.reload()}
      />
    }>
    <div className="space-y-3">
      {/* Navigation */}
      <div className="flex items-center justify-between">
        <Link
          href="/"
          onClick={() => trackNavigationClick('back', `/events/${eventId}`, '/')}
          className="inline-flex items-center text-caption text-text-secondary hover:text-text-primary transition-colors"
        >
          <svg
            className="w-4 h-4 mr-1"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 19l-7-7 7-7"
            />
          </svg>
          ← Back to events
        </Link>

        {/* Visual countdown timer */}
        {!isFinished && (
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-sm">
              {effectivelyLive && (
                <span className="flex items-center gap-1.5 bg-emerald-500/15 text-emerald-600 px-2 py-1 rounded-full text-xs font-semibold">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  LIVE
                </span>
              )}
              <span className="text-text-secondary">Next update:</span>
            </div>
            {/* Circular countdown */}
            <div className="relative w-10 h-10">
              <svg className="w-10 h-10 transform -rotate-90">
                <circle
                  cx="20"
                  cy="20"
                  r="16"
                  fill="none"
                  stroke="#E5E7EB"
                  strokeWidth="3"
                />
                <circle
                  cx="20"
                  cy="20"
                  r="16"
                  fill="none"
                  stroke={effectivelyLive ? "#10B981" : "#6B7280"}
                  strokeWidth="3"
                  strokeDasharray={`${countdownProgress} 100`}
                  strokeLinecap="round"
                  className="transition-all duration-100"
                />
              </svg>
              <span className="absolute inset-0 flex items-center justify-center text-xs font-mono font-bold text-text-primary">
                {countdown}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Hero Section — v2 design */}
      <div className="rounded-card shadow-card overflow-hidden bg-surface-card">
        {/* Top meta row: phase + broadcast + date/time */}
        <div className="px-4 sm:px-5 py-2 flex items-center justify-between border-b border-surface-border/30">
          <div className="flex items-center gap-2">
            {/* Pin button */}
            <button
              onClick={() => togglePin(eventId)}
              disabled={isMaxReached && !eventIsPinned}
              className={`
                p-1 rounded-full transition-all
                ${eventIsPinned
                  ? 'text-amber-500'
                  : 'text-text-muted/40 hover:text-text-secondary'
                }
                ${isMaxReached && !eventIsPinned ? 'cursor-not-allowed opacity-30' : ''}
                focus:outline-none
              `}
              title={eventIsPinned ? 'Unpin event' : isMaxReached ? 'Maximum 6 pins' : 'Pin event'}
              aria-label={eventIsPinned ? 'Unpin event' : 'Pin event'}
            >
              <PinIcon filled={eventIsPinned} className="w-4 h-4" />
            </button>

            {/* Phase badge */}
            {effectivelyLive ? (
              <span className="flex items-center gap-1 text-[10px] font-semibold text-emerald-600">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                {event.espn?.period && event.espn?.game_clock
                  ? `${event.espn.period} · ${event.espn.game_clock}`
                  : "LIVE"
                }
              </span>
            ) : isFinished ? (
              <span className="text-[10px] font-semibold text-text-muted">Final</span>
            ) : (
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                <span className="text-[10px] text-amber-500 font-medium">
                  {gameCountdown && !hasStarted ? `Starts in ${gameCountdown}` : "Pregame"}
                </span>
              </span>
            )}
          </div>

          {/* Broadcast + date/time + freshness */}
          <div className="flex items-center gap-2">
            {event.espn?.broadcast && (
              <span className="px-1.5 py-0.5 rounded bg-surface-elevated text-[10px] font-semibold text-text-secondary tracking-wide">
                {event.espn.broadcast}
              </span>
            )}
            {effectivelyLive ? (
              <span className="text-[10px] text-text-muted flex items-center gap-1">
                <svg className="w-3 h-3 text-text-quaternary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                <span className="tabular-nums font-mono">{countdown}s</span>
              </span>
            ) : (
              <span className="text-[10px] text-text-muted">
                {new Date(event.commence_time).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })} · {new Date(event.commence_time).toLocaleTimeString("en-US", {
                  hour: "numeric",
                  minute: "2-digit",
                  timeZoneName: "short",
                })}
              </span>
            )}
          </div>
        </div>

        {/* Tag chips — contextual labels from taxonomy */}
        {event.event_tags && event.event_tags.length > 0 && (() => {
          const displayTags = event.event_tags.filter((t: string) => {
            const ns = t.split(":")[0];
            return ["importance", "signal", "timing", "tier", "ei", "stakes", "narrative", "audience", "competitive_structure"].includes(ns);
          });
          const filteredTags = displayTags.filter((t: string) => {
            return t !== "competitive_structure:head_to_head"
              && t !== "audience:local_interest"
              && t !== "stakes:meaningless";
          });
          if (filteredTags.length === 0) return null;

          const tagLabels: Record<string, string> = {
            "importance:championship": "Championship",
            "importance:playoff": "Playoff",
            "importance:exhibition": "Exhibition",
            "signal:close_matchup": "Close Game",
            "signal:upset": "Upset",
            "signal:line_moving": "Line Moving",
            "signal:blowout": "Blowout",
            "timing:primetime": "Primetime",
            "timing:national_tv": "National TV",
            "timing:weekend": "Weekend",
            "tier:1": "Major",
            "tier:2": "Tier 2",
            "ei:must_watch": "Must-Watch",
            "ei:incredible": "Incredible",
            "ei:exciting": "Exciting",
            "stakes:elimination": "Elimination",
            "stakes:clinch": "Clinch Scenario",
            "stakes:playoff_race": "Playoff Race",
            "stakes:title_defense": "Title Defense",
            "stakes:must_win": "Must-Win",
            "stakes:record_chase": "Record Chase",
            "stakes:seeding": "Seeding",
            "stakes:streak": "Streak",
            "narrative:rivalry": "Rivalry",
            "narrative:historic_rivalry": "Historic Rivalry",
            "narrative:revenge_game": "Revenge Game",
            "narrative:cinderella": "Cinderella",
            "narrative:upset_alert": "Upset Alert",
            "narrative:comeback": "Comeback",
            "narrative:rematch": "Rematch",
            "narrative:david_vs_goliath": "David vs. Goliath",
            "narrative:farewell_tour": "Farewell Tour",
            "narrative:winning_streak": "Winning Streak",
            "narrative:losing_streak": "Losing Streak",
            "narrative:debut": "Debut",
            "narrative:return_from_injury": "Return from Injury",
            "audience:national_interest": "National Interest",
            "audience:crossover_appeal": "Crossover Appeal",
            "audience:viral_potential": "Viral Potential",
            "audience:casual_friendly": "Casual-Friendly",
            "competitive_structure:knockout": "Knockout",
            "competitive_structure:single_elimination": "Single Elimination",
            "competitive_structure:bracket": "Bracket",
            "competitive_structure:series": "Series",
            "competitive_structure:best_of_7": "Best of 7",
            "competitive_structure:group_stage": "Group Stage",
          };

          const tagColors: Record<string, string> = {
            importance: "bg-purple-50 text-purple-600",
            signal: "bg-orange-50 text-orange-600",
            timing: "bg-yellow-50 text-yellow-700",
            tier: "bg-blue-50 text-blue-600",
            ei: "bg-emerald-50 text-emerald-600",
            stakes: "bg-red-50 text-red-600",
            narrative: "bg-amber-50 text-amber-600",
            audience: "bg-cyan-50 text-cyan-600",
            competitive_structure: "bg-indigo-50 text-indigo-600",
          };

          return (
            <div className="flex flex-wrap gap-1.5 justify-center px-4 pt-2">
              {filteredTags.map((tag: string) => {
                const ns = tag.split(":")[0];
                const color = tagColors[ns] || "bg-slate/10 text-text-muted";
                const label = tagLabels[tag] || tag.split(":")[1]?.replace(/_/g, " ");
                return (
                  <span
                    key={tag}
                    className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${color}`}
                  >
                    {label}
                  </span>
                );
              })}
            </div>
          );
        })()}

        {/* Teams + Score + Giant Probability — v2 centered layout */}
        <div className="px-5 sm:px-6 py-4 sm:py-5">
          <div className="flex items-center justify-between">
            {/* Home Team */}
            <div className="flex flex-col items-center flex-1">
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center mb-1.5 overflow-hidden"
                style={{ backgroundColor: `${event.home_team_data?.primary_color || "#94A3B8"}15` }}
              >
                {(event.home_team_data?.logo_large || espnTeamLogoByName(event.home_team, event.sport_key)) ? (
                  <img
                    src={event.home_team_data?.logo_large || espnTeamLogoByName(event.home_team, event.sport_key)!}
                    alt=""
                    width={48}
                    height={48}
                    loading="lazy"
                    className="w-12 h-12 object-contain"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; (e.target as HTMLImageElement).nextElementSibling?.classList.remove("hidden"); }}
                  />
                ) : null}
                <span
                  className={`text-sm font-extrabold ${(event.home_team_data?.logo_large || espnTeamLogoByName(event.home_team, event.sport_key)) ? "hidden" : ""}`}
                  style={{ color: event.home_team_data?.primary_color || "#94A3B8" }}
                >
                  {event.home_team.split(" ").map(w => w.charAt(0)).join("").slice(0, 3).toUpperCase()}
                </span>
              </div>
              <TeamNameLink
                name={event.home_team}
                sportKey={event.sport}
                className="text-xs font-semibold text-text-primary hover:underline"
              >
                {event.home_team.split(" ").pop()}
              </TeamNameLink>
              {(event.standings_context?.home || event.home_team_data?.record) && (
                <span className="text-[11px] text-text-muted">
                  {event.standings_context?.home || event.home_team_data?.record}
                </span>
              )}
              {(isLive || isFinished || hasStarted) && bestHomeScore !== null && (
                <span className="text-2xl font-bold text-text-primary tabular-nums font-mono mt-0.5">
                  {bestHomeScore}
                </span>
              )}
            </div>

            {/* Center: Giant Probability */}
            <div className="flex flex-col items-center px-2 sm:px-4 flex-shrink-0">
              <div className="flex items-baseline">
                <span
                  className="text-[48px] sm:text-[52px] font-black tracking-tight leading-none tabular-nums"
                  style={{ color: event.home_team_data?.primary_color || "#111827" }}
                >
                  {homeProb !== null ? Math.round(homeProb * 100) : "—"}
                </span>
                <span
                  className="text-lg font-bold leading-none ml-0.5"
                  style={{ color: event.home_team_data?.primary_color || "#111827" }}
                >
                  %
                </span>
                <span className="text-lg font-light text-text-muted mx-1.5 self-center">{"–"}</span>
                <span
                  className="text-[48px] sm:text-[52px] font-black tracking-tight leading-none tabular-nums"
                  style={{ color: event.away_team_data?.primary_color || "#94A3B8" }}
                >
                  {awayProb !== null ? Math.round(awayProb * 100) : "—"}
                </span>
                <span
                  className="text-lg font-bold leading-none ml-0.5"
                  style={{ color: event.away_team_data?.primary_color || "#94A3B8" }}
                >
                  %
                </span>
              </div>

              {/* Trend indicator — change since opening */}
              {openingHomeProb !== null && homeProb !== null && (() => {
                const delta = homeProb - openingHomeProb;
                const absDelta = Math.abs(delta);
                if (absDelta < 0.01) return null; // Less than 1% change — not meaningful
                const homeShort = event.home_team.split(" ").pop() || event.home_team;
                const isPositive = delta > 0;
                return (
                  <div className="flex items-center gap-1.5 mt-2">
                    <svg
                      className={`w-3.5 h-3.5 ${isPositive ? "text-emerald-500" : "text-red-500"}`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      {isPositive ? (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
                      ) : (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                      )}
                    </svg>
                    <span className={`text-xs font-semibold ${isPositive ? "text-emerald-600" : "text-red-500"}`}>
                      {isPositive ? "+" : ""}{Math.round(delta * 100)}% {homeShort} since open
                    </span>
                  </div>
                );
              })()}

              {/* Opening odds (faint) */}
              {openingHomeProb !== null && (
                <div className="mt-1.5">
                  <span className="text-[11px] text-text-muted">
                    Opened {formatProbability(openingHomeProb)} {"–"} {formatProbability(openingAwayProb)}
                  </span>
                </div>
              )}

              {/* Source label */}
              {probSourceLabel && (
                <div className="mt-1">
                  <span className="text-[11px] text-text-muted">
                    {probSourceLabel}
                  </span>
                </div>
              )}

              {/* Projected final score — derived from spread + total, no gambling jargon */}
              {historyData?.pm_spread_data?.projected_final &&
                event.status !== "completed" && event.status !== "closed" &&
                historyData.pm_spread_data.projected_final.home_score > 0 &&
                historyData.pm_spread_data.projected_final.away_score > 0 && (
                <div className="mt-1.5">
                  <span className="text-[11px] text-text-muted">
                    Projected final: {Math.round(historyData.pm_spread_data.projected_final.home_score)}{"\u2009\u2013\u2009"}{Math.round(historyData.pm_spread_data.projected_final.away_score)}
                  </span>
                </div>
              )}
            </div>

            {/* Away Team */}
            <div className="flex flex-col items-center flex-1">
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center mb-1.5 overflow-hidden"
                style={{ backgroundColor: `${event.away_team_data?.primary_color || "#64748B"}15` }}
              >
                {(event.away_team_data?.logo_large || espnTeamLogoByName(event.away_team, event.sport_key)) ? (
                  <img
                    src={event.away_team_data?.logo_large || espnTeamLogoByName(event.away_team, event.sport_key)!}
                    alt=""
                    width={48}
                    height={48}
                    loading="lazy"
                    className="w-12 h-12 object-contain"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; (e.target as HTMLImageElement).nextElementSibling?.classList.remove("hidden"); }}
                  />
                ) : null}
                <span
                  className={`text-sm font-extrabold ${(event.away_team_data?.logo_large || espnTeamLogoByName(event.away_team, event.sport_key)) ? "hidden" : ""}`}
                  style={{ color: event.away_team_data?.primary_color || "#64748B" }}
                >
                  {event.away_team.split(" ").map(w => w.charAt(0)).join("").slice(0, 3).toUpperCase()}
                </span>
              </div>
              <TeamNameLink
                name={event.away_team}
                sportKey={event.sport}
                className="text-xs font-semibold text-text-primary hover:underline"
              >
                {event.away_team.split(" ").pop()}
              </TeamNameLink>
              {(event.standings_context?.away || event.away_team_data?.record) && (
                <span className="text-[11px] text-text-muted">
                  {event.standings_context?.away || event.away_team_data?.record}
                </span>
              )}
              {(isLive || isFinished || hasStarted) && bestAwayScore !== null && (
                <span className="text-2xl font-bold text-text-primary tabular-nums font-mono mt-0.5">
                  {bestAwayScore}
                </span>
              )}
            </div>
          </div>

          {/* Stakes context from standings */}
          {event.standings_context?.stakes && (
            <div className="text-center mt-3">
              <span className="text-[10px] text-text-muted bg-surface-elevated px-2 py-0.5 rounded">
                {event.standings_context.stakes}
              </span>
            </div>
          )}

        </div>



      </div>

      {/* Win Probability Chart */}
      <div className="bg-surface-card rounded-card shadow-card overflow-hidden">
        {/* Chart Header — v2: title + freshness */}
        <div className="px-4 sm:px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="text-[13px] font-semibold text-text-primary">Win Probability</h2>
            {effectivelyLive && (
              <div className="flex items-center gap-1.5">
                <div className="relative w-[18px] h-[18px]">
                  <svg className="w-[18px] h-[18px] transform -rotate-90" viewBox="0 0 18 18">
                    <circle cx="9" cy="9" r="7" fill="none" stroke="#E5E7EB" strokeWidth="2" />
                    <circle cx="9" cy="9" r="7" fill="none" stroke="#10B981" strokeWidth="2"
                      strokeDasharray="44" strokeDashoffset={44 - (countdownProgress / 100) * 44}
                      strokeLinecap="round" className="transition-all duration-100" />
                  </svg>
                </div>
                <span className="text-[10px] text-text-muted tabular-nums font-mono">{countdown}s</span>
              </div>
            )}
            {isFinished && (
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-text-muted" />
                <span className="text-[10px] text-text-muted font-medium">Final</span>
              </div>
            )}
          </div>
          <button
            onClick={() => setChartFullscreen(true)}
            className="p-1.5 rounded-md hover:bg-surface-elevated text-text-muted hover:text-text-primary transition-colors"
            title="Fullscreen"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="10 2 14 2 14 6" />
              <polyline points="6 14 2 14 2 10" />
              <line x1="14" y1="2" x2="9.5" y2="6.5" />
              <line x1="2" y1="14" x2="6.5" y2="9.5" />
            </svg>
          </button>
        </div>

        {/* Chart Content */}
        <div className="p-4 sm:p-5">
          {historyLoading ? (
            <div className="h-48 flex items-center justify-center">
              <LoadingSpinner size="sm" />
            </div>
          ) : historyError ? (
            <div className="h-48 flex flex-col items-center justify-center text-sm text-text-secondary gap-2">
              <span>Unable to load history</span>
              <span className="text-xs text-text-muted">
                {historyError.message || 'Unknown error'}
              </span>
              <button
                onClick={() => refreshHistory()}
                className="text-xs text-blue-600 hover:underline mt-2"
              >
                Retry
              </button>
            </div>
          ) : historyData?.history?.length === 0 && !_hasAnyWinProbData(historyData) ? (
            <div className="h-48 flex items-center justify-center text-sm text-text-secondary">
              Tracking will begin when odds are available
            </div>
          ) : (
            <OddsChart
              history={historyData?.history ?? []}
              homeTeam={event.home_team}
              awayTeam={event.away_team}
              commenceTime={event.commence_time}
              isLive={effectivelyLive}
              bookmakerHistory={historyData?.bookmaker_history}
              espnHistory={historyData?.espn_history}
              winProbHistory={historyData?.win_prob_history}
              winProbSources={historyData?.win_prob_sources}
              scoringPlays={historyData?.scoring_plays}
              aggregateLine={historyData?.aggregate_line ?? undefined}
              completedAt={historyData?.completed_at ?? undefined}
              eventId={eventId}
              eventStatus={event.status}
              periodBoundaries={periodBoundaries}
              homeTeamColor={event.home_team_data?.primary_color || undefined}
              awayTeamColor={event.away_team_data?.primary_color || undefined}
              homeTeamLogo={event.home_team_data?.logo_small || undefined}
              awayTeamLogo={event.away_team_data?.logo_small || undefined}
              homeTeamAbbrev={event.home_team_data?.abbreviation || undefined}
              awayTeamAbbrev={event.away_team_data?.abbreviation || undefined}
              onActivePointChange={setActiveChartPoint}
              onRenderedDomain={handleRenderedDomain}
              chartStartTime={sharedChartDomain?.start}
              chartEndTime={sharedChartDomain?.end}
              sharedTicks={sharedChartDomain?.ticks}
              externalTimeRange={chartTimeRange}
              onTimeRangeChange={setChartTimeRange}
            />
          )}
          {/* Game Play Card — shows score/period/play as user hovers the chart */}
          {(effectivelyLive || isFinished || hasStarted) && historyData ? (
            <GamePlayCard
              activePoint={activeChartPoint}
              homeTeam={event.home_team}
              awayTeam={event.away_team}
              homeTeamColor={event.home_team_data?.primary_color || undefined}
              awayTeamColor={event.away_team_data?.primary_color || undefined}
              homeTeamLogo={event.home_team_data?.logo_small || undefined}
              awayTeamLogo={event.away_team_data?.logo_small || undefined}
              lastPoint={lastChartPoint}
            />
          ) : null}
        </div>

        {/* Chart footer: Legend + Sources toggle */}
        {event.bookmaker_odds && event.bookmaker_odds.length > 0 && (
          <>
            <div className="px-4 sm:px-5 py-2 border-t border-surface-border flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-1.5">
                  <div className="w-4 h-[2px] rounded" style={{ backgroundColor: event.home_team_data?.primary_color || '#10B981' }} />
                  <span className="text-[10px] text-text-muted">BainLuck</span>
                </div>
                {historyData?.bookmaker_history && Object.keys(historyData.bookmaker_history).length > 0 && (
                  <div className="flex items-center gap-1.5">
                    <div className="w-4 h-[2px] rounded bg-text-muted/40" />
                    <span className="text-[10px] text-text-muted">Sportsbooks</span>
                  </div>
                )}
                {historyData?.win_prob_sources && Object.keys(historyData.win_prob_sources).some(k => k.toLowerCase().includes('kalshi')) && (
                  <div className="flex items-center gap-1.5">
                    <div className="w-4 h-[2px] rounded bg-violet-400" />
                    <span className="text-[10px] text-text-muted">Kalshi</span>
                  </div>
                )}
              </div>
              <button
                onClick={() => setSourcesOpen(!sourcesOpen)}
                className="flex items-center gap-1 px-2 py-1 rounded-md hover:bg-surface-elevated transition-colors"
              >
                <span className="text-[10px] text-text-muted font-medium">Sources</span>
                <svg
                  className={`w-3 h-3 text-text-muted transition-transform duration-200 ${sourcesOpen ? 'rotate-180' : ''}`}
                  fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>

            {/* Sources panel (collapsible) */}
            {sourcesOpen && (
              <div className="border-t border-surface-border">
                <div className="px-4 py-3">
                  <BookmakerTable
                    bookmakerOdds={event.bookmaker_odds}
                    homeTeam={event.home_team}
                    awayTeam={event.away_team}
                  />
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Source Comparison removed — not useful, sources already visible in OddsChart */}

      {/* Score Differential Chart - combines projected spread and actual score diff */}
      {historyData && ((historyData.history?.length ?? 0) > 0 || (historyData.score_history?.length ?? 0) > 0 || (historyData.espn_history?.length ?? 0) > 0) && (
        <div className="bg-surface-card rounded-card shadow-card p-3 sm:p-4">
          <h3 className="text-sm font-semibold text-text-secondary mb-2 flex items-center gap-2">
            Score Differential
          </h3>
          <ScoreDifferentialChart
            history={historyData.history || []}
            homeTeam={event.home_team}
            awayTeam={event.away_team}
            commenceTime={event.commence_time}
            isLive={effectivelyLive}
            bookmakerHistory={historyData?.bookmaker_history}
            scoreHistory={historyData?.score_history}
            espnHistory={historyData?.espn_history}
            currentHomeScore={event.home_score}
            currentAwayScore={event.away_score}
            eventStatus={event.status}
            periodBoundaries={periodBoundaries}
            homeTeamColor={event.home_team_data?.primary_color || undefined}
            awayTeamColor={event.away_team_data?.primary_color || undefined}
            homeTeamLogo={event.home_team_data?.logo_small || undefined}
            awayTeamLogo={event.away_team_data?.logo_small || undefined}
            homeTeamAbbrev={event.home_team_data?.abbreviation || undefined}
            awayTeamAbbrev={event.away_team_data?.abbreviation || undefined}
            chartStartTime={sharedChartDomain?.start}
            chartEndTime={sharedChartDomain?.end}
            sharedTicks={sharedChartDomain?.ticks}
            externalTimeRange={chartTimeRange}
            onTimeRangeChange={setChartTimeRange}
            pmSpreadData={historyData?.pm_spread_data}
          />
        </div>
      )}

      {/* Market Map cards — Margin Map + Total Map */}
      {gameMarkets && ((gameMarkets.spreads?.length ?? 0) > 0 || gameMarkets.totals.length > 0) && (
        <MarketMapSection
          gameMarkets={gameMarkets}
          eventStatus={event.status}
          homeTeam={event.home_team}
          awayTeam={event.away_team}
          homeAbbr={event.home_team_data?.abbreviation || undefined}
          awayAbbr={event.away_team_data?.abbreviation || undefined}
          homeColor={event.home_team_data?.primary_color || undefined}
          awayColor={event.away_team_data?.primary_color || undefined}
          homeLogo={event.home_team_data?.logo_small || undefined}
          awayLogo={event.away_team_data?.logo_small || undefined}
          homeWinProb={event.current_odds?.home_probability ?? undefined}
          awayWinProb={event.current_odds?.away_probability ?? undefined}
          homeSpread={event.current_odds?.home_spread ?? null}
          overUnder={event.current_odds?.over_under ?? null}
          sportKey={event.sport || undefined}
          espnHistory={historyData?.espn_history}
        />
      )}

      {/* Game Markets — Player Props + Special Markets */}
      {gameMarkets && (gameMarkets.player_props.length > 0 || (gameMarkets.other?.length ?? 0) >= 3) && (
        <div className="space-y-3">

          {gameMarkets.player_props.length > 0 && (
            <PlayerPropsDashboard
              data={gameMarkets}
              eventStatus={event.status}
              homeTeam={event.home_team}
              awayTeam={event.away_team}
              homeColor={event.home_team_data?.primary_color || undefined}
              awayColor={event.away_team_data?.primary_color || undefined}
              boxScore={event.box_score_data}
            />
          )}

          {/* Special Event Markets (auto-categorized other markets) */}
          {(gameMarkets.other?.length ?? 0) >= 3 && (
            <SpecialEventMarkets data={gameMarkets} eventStatus={event.status} />
          )}
        </div>
      )}
      {/* Standalone pace when no game markets section at all */}
      {gameMarkets && gameMarkets.totals.length === 0 && gameMarkets.player_props.length === 0 && gameMarkets.pace && gameMarkets.pace.projected_total && (
        <div className="bg-surface-card rounded-xl border border-surface-border px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-text-primary">{event.sport?.startsWith('baseball') ? 'Total Runs' : event.sport?.startsWith('icehockey') || event.sport?.startsWith('soccer') ? 'Total Goals' : 'Total Points'} Pace</span>
            <span className="text-base font-extrabold text-blue-500 tracking-tight">
              {gameMarkets.pace.projected_total}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1 text-text-secondary text-micro">
            <span>{gameMarkets.pace.total_scored} scored</span>
            <span className="text-text-muted">&middot;</span>
            <span>{gameMarkets.pace.time_remaining_display}</span>
            <span className="text-text-muted">&middot;</span>
            <span>{Math.round(gameMarkets.pace.fraction_elapsed * 100)}% elapsed</span>
          </div>
        </div>
      )}

      {/* Line Movement Analysis — disabled until we have non-obvious insights.
          Current version just states the obvious ("Team X won, odds went up").
          TODO: Revamp with causal analysis, key moments, context. See backlog. */}

      {/* Series Probability — playoff series context */}
      {event.event_tags && (
        event.event_tags.includes("competitive_structure:series") ||
        event.event_tags.includes("competitive_structure:best_of_7")
      ) && event.current_odds?.home_probability != null && (() => {
        // Detect series wins from ESPN data or default to 0-0
        const homeSeriesWins = (event.espn as any)?.series_home_wins ?? 0;
        const awaySeriesWins = (event.espn as any)?.series_away_wins ?? 0;
        const gamesToWin = event.event_tags!.includes("competitive_structure:best_of_7") ? 4 : 4;
        return (
          <SeriesProbability
            homeWinProb={event.current_odds!.home_probability!}
            homeSeriesWins={homeSeriesWins}
            awaySeriesWins={awaySeriesWins}
            gamesToWin={gamesToWin}
            homeTeam={event.home_team}
            awayTeam={event.away_team}
            homeTeamColor={event.home_team_data?.primary_color || undefined}
            awayTeamColor={event.away_team_data?.primary_color || undefined}
          />
        );
      })()}

      {/* Related Futures — bigger picture context (below charts) */}
      <RelatedFutures
        eventId={eventId}
        homeTeam={event.home_team}
        awayTeam={event.away_team}
        homeTeamColor={event.home_team_data?.primary_color || undefined}
        awayTeamColor={event.away_team_data?.primary_color || undefined}
        homeTeamLogo={event.home_team_data?.logo_small || undefined}
        awayTeamLogo={event.away_team_data?.logo_small || undefined}
        sportKey={event.sport || undefined}
        eventStatus={event.status}
        homeStandings={event.home_team_data?.standings || undefined}
        awayStandings={event.away_team_data?.standings || undefined}
        hasGameMarkets={!!gameMarkets && (gameMarkets.totals.length > 0 || gameMarkets.player_props.length > 0 || (gameMarkets.team_totals?.length ?? 0) > 0)}
        teamProgression={teamProgression || undefined}
      />

      {/* League page link */}
      {event.sport && (() => {
        const league = SPORT_KEY_TO_LEAGUE_PATH[event.sport!];
        if (!league) return null;
        return (
          <Link
            href={league.path}
            className="flex items-center justify-between px-4 py-3 rounded-xl bg-surface-card border border-surface-border hover:border-text-muted/30 transition-colors group"
          >
            <div className="flex items-center gap-2">
              <span className="text-sm">🏆</span>
              <span className="text-sm font-medium text-text-secondary group-hover:text-text-primary transition-colors">
                {league.label} Championship Grid
              </span>
            </div>
            <span className="text-text-muted group-hover:text-text-secondary transition-colors text-sm">→</span>
          </Link>
        );
      })()}

      {/* Related by sport tag — cross-content discovery */}
      {event.sport && (() => {
        const cat = getCategoryForLeague(event.sport!);
        return cat ? (
          <RelatedByTag
            tags={[`sport:${cat.key}`]}
            excludeId={event.id}
            excludeType="event"
            limit={4}
            title={`More ${cat.name}`}
          />
        ) : null;
      })()}

      {/* Fullscreen Chart Modal */}
      {chartFullscreen && (
        <div className="fixed inset-0 z-50 bg-white flex flex-col">
          <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border">
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-semibold text-text-primary">Win Probability</h2>
              {effectivelyLive && (
                <div className="flex items-center gap-1.5">
                  <div className="relative w-[18px] h-[18px]">
                    <svg className="w-[18px] h-[18px] transform -rotate-90" viewBox="0 0 18 18">
                      <circle cx="9" cy="9" r="7" fill="none" stroke="#E5E7EB" strokeWidth="2" />
                      <circle cx="9" cy="9" r="7" fill="none" stroke="#10B981" strokeWidth="2"
                        strokeDasharray="44" strokeDashoffset={44 - (countdownProgress / 100) * 44}
                        strokeLinecap="round" className="transition-all duration-100" />
                    </svg>
                  </div>
                  <span className="text-[10px] text-text-muted tabular-nums font-mono">{countdown}s</span>
                </div>
              )}
              {isFinished && (
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-text-muted" />
                  <span className="text-[10px] text-text-muted font-medium">Final</span>
                </div>
              )}
            </div>
            <button
              onClick={() => setChartFullscreen(false)}
              className="p-2 rounded-md hover:bg-surface-elevated text-text-muted hover:text-text-primary transition-colors"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="4" x2="4" y2="12" />
                <line x1="4" y1="4" x2="12" y2="12" />
              </svg>
            </button>
          </div>
          <div className="flex-1 p-4 min-h-0">
            <OddsChart
              history={historyData?.history ?? []}
              homeTeam={event.home_team}
              awayTeam={event.away_team}
              commenceTime={event.commence_time}
              isLive={effectivelyLive}
              bookmakerHistory={historyData?.bookmaker_history}
              espnHistory={historyData?.espn_history}
              winProbHistory={historyData?.win_prob_history}
              winProbSources={historyData?.win_prob_sources}
              scoringPlays={historyData?.scoring_plays}
              aggregateLine={historyData?.aggregate_line ?? undefined}
              completedAt={historyData?.completed_at ?? undefined}
              eventId={eventId}
              eventStatus={event.status}
              fillContainer
              periodBoundaries={periodBoundaries}
              homeTeamColor={event.home_team_data?.primary_color || undefined}
              awayTeamColor={event.away_team_data?.primary_color || undefined}
              homeTeamLogo={event.home_team_data?.logo_small || undefined}
              awayTeamLogo={event.away_team_data?.logo_small || undefined}
              homeTeamAbbrev={event.home_team_data?.abbreviation || undefined}
              awayTeamAbbrev={event.away_team_data?.abbreviation || undefined}
            />
          </div>
        </div>
      )}
    </div>
    </ErrorBoundary>
  );
}

/**
 * Pin icon - pushpin style
 */
function PinIcon({ filled, className }: { filled: boolean; className?: string }) {
  if (filled) {
    // Filled pushpin
    return (
      <svg className={className} viewBox="0 0 24 24" fill="currentColor">
        <path d="M16 4c0-.55-.22-1.05-.58-1.41-.37-.37-.86-.59-1.42-.59s-1.05.22-1.41.58l-6.01 6.01C5.22 9.95 4 11.59 4 13.5c0 1.1.45 2.1 1.17 2.83L2 19.5l1.41 1.41 3.17-3.17c.73.72 1.73 1.17 2.83 1.17 1.91 0 3.55-1.22 4.91-2.58l6.01-6.01c.36-.36.58-.86.58-1.41s-.22-1.05-.58-1.41c-.37-.37-.86-.59-1.42-.59s-1.05.22-1.41.58l-4.95 4.95-2.12-2.12L16 4z"/>
      </svg>
    );
  }

  // Outline pushpin
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v1H5V5z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 11v6" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 17h6" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 6h14l-2 5H7L5 6z" />
    </svg>
  );
}
