"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import useSWR from "swr";
import { fetchEvent, fetchEventHistory, formatProbability } from "@/lib/api";
import ProbabilityBar from "@/components/ProbabilityBar";
const OddsChart = dynamic(() => import("@/components/OddsChart"), { ssr: false });
const ScoreDifferentialChart = dynamic(() => import("@/components/ScoreDifferentialChart"), { ssr: false });
const BookmakerTable = dynamic(() => import("@/components/BookmakerTable"), { ssr: false });
const RelatedFutures = dynamic(() => import("@/components/RelatedFutures"), { ssr: false });
const LineMovementExplainer = dynamic(() => import("@/components/LineMovementExplainer"), { ssr: false });
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import Tooltip from "@/components/Tooltip";
import { getLeagueDisplay, getEmojiForLeague } from "@/lib/sportCategories";
import {
  useAnalytics,
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
  usePinnedEvents,
} from "@/hooks";
import { isCloseGame, calculateMinutesToStart } from "@/lib/analytics";
import { derivePeriodBoundaries } from "@/lib/periodMarkers";

interface EventPageProps {
  params: { id: string };
}

const LIVE_REFRESH_INTERVAL = 32000; // Match backend LIVE_POLL_INTERVAL (32s)
const SCHEDULED_REFRESH_INTERVAL = 120000;

function formatCountdown(targetTime: string): string {
  const target = new Date(targetTime);
  const now = new Date();
  const diff = target.getTime() - now.getTime();

  if (diff <= 0) return "Started";

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

// Check if odds suggest a blowout (one team >85%)
function isBlowout(homeProb: number | null | undefined): boolean {
  if (homeProb === null || homeProb === undefined) return false;
  return homeProb > 0.85 || homeProb < 0.15;
}

interface SourceAnalysis {
  sources: string[];
  hasSignificantDivergence: boolean;
  divergenceWarning: string | null;
  maxDivergence: number;
}

interface PredictionMarketDivergence {
  hasDivergence: boolean;
  source: string; // "Kalshi" or "Polymarket"
  sourceKey: string; // "kalshi" or "polymarket"
  marketProb: number; // prediction market probability (home)
  bookProb: number; // sportsbook consensus probability (home)
  delta: number; // absolute difference
  direction: string; // e.g., "Kalshi says 65% vs books at 58%"
  homeTeam: string;
}

// Detect divergence between prediction market odds and sportsbook consensus
function analyzePredictionMarketDivergence(
  winProbHistory: Record<string, Array<{
    timestamp: string;
    home_probability: number | null;
  }>> | undefined,
  winProbSources: Record<string, { display_name: string }> | undefined,
  currentHomeProb: number | null,
  homeTeam: string,
): PredictionMarketDivergence | null {
  if (!winProbHistory || currentHomeProb === null) return null;

  const predictionSources = ["kalshi", "polymarket"];
  let biggestDivergence: PredictionMarketDivergence | null = null;

  for (const sourceKey of predictionSources) {
    const points = winProbHistory[sourceKey];
    if (!points || points.length === 0) continue;

    // Get the latest point with a valid probability
    let latestProb: number | null = null;
    for (let i = points.length - 1; i >= 0; i--) {
      if (points[i].home_probability !== null) {
        latestProb = points[i].home_probability;
        break;
      }
    }
    if (latestProb === null) continue;

    const delta = Math.abs(latestProb - currentHomeProb);
    // Only flag if >5% divergence
    if (delta < 0.05) continue;

    const displayName = winProbSources?.[sourceKey]?.display_name || sourceKey;

    if (!biggestDivergence || delta > biggestDivergence.delta) {
      const marketPct = Math.round(latestProb * 100);
      const bookPct = Math.round(currentHomeProb * 100);
      const teamShort = homeTeam.split(" ").pop() || homeTeam;

      biggestDivergence = {
        hasDivergence: true,
        source: displayName,
        sourceKey,
        marketProb: latestProb,
        bookProb: currentHomeProb,
        delta,
        direction: `${displayName} has ${teamShort} at ${marketPct}% vs sportsbooks at ${bookPct}%`,
        homeTeam,
      };
    }
  }

  return biggestDivergence;
}

// Analyze sources from history data to detect divergence
function analyzeSourcesFromHistory(
  bookmakerHistory: Record<string, Array<{
    timestamp: string;
    home_probability: number | null;
  }>> | undefined
): SourceAnalysis {
  if (!bookmakerHistory || Object.keys(bookmakerHistory).length === 0) {
    return {
      sources: [],
      hasSignificantDivergence: false,
      divergenceWarning: null,
      maxDivergence: 0,
    };
  }

  // Get unique bookmakers from the bookmaker_history keys
  const sources = Object.keys(bookmakerHistory);

  // Look at recent data (last hour) to detect divergence
  const oneHourAgo = Date.now() - 60 * 60 * 1000;

  // Group by bookmaker and get their latest probabilities
  const bookmakerProbs: Record<string, number> = {};
  for (const [bookmaker, points] of Object.entries(bookmakerHistory)) {
    // Get the most recent point within the last hour
    const recentPoints = points.filter(
      (p) => new Date(p.timestamp).getTime() > oneHourAgo && p.home_probability !== null
    );
    if (recentPoints.length > 0) {
      // Use the latest point
      const latest = recentPoints[recentPoints.length - 1];
      if (latest.home_probability !== null) {
        bookmakerProbs[bookmaker] = latest.home_probability;
      }
    }
  }

  const probValues = Object.values(bookmakerProbs);
  if (probValues.length < 2) {
    return {
      sources,
      hasSignificantDivergence: false,
      divergenceWarning: null,
      maxDivergence: 0,
    };
  }

  const maxProb = Math.max(...probValues);
  const minProb = Math.min(...probValues);
  const maxDivergence = Math.abs(maxProb - minProb);

  // Significant divergence if >10% difference
  const hasSignificantDivergence = maxDivergence > 0.1;

  let divergenceWarning: string | null = null;
  if (maxDivergence > 0.15) {
    // Find outlier bookmaker
    const outliers = Object.entries(bookmakerProbs).filter(([, prob]) => {
      const distFromMax = Math.abs(prob - maxProb);
      const distFromMin = Math.abs(prob - minProb);
      return distFromMax < 0.02 || distFromMin < 0.02;
    });
    if (outliers.length === 1) {
      divergenceWarning = `${outliers[0][0]} shows different odds than other sources`;
    } else {
      divergenceWarning = "Sources show significantly different odds";
    }
  }

  return {
    sources,
    hasSignificantDivergence,
    divergenceWarning,
    maxDivergence,
  };
}

export default function EventPage({ params }: EventPageProps) {
  const eventId = parseInt(params.id, 10);
  const [countdown, setCountdown] = useState<number>(0);
  const [gameCountdown, setGameCountdown] = useState<string>("");
  const [lastRefresh, setLastRefresh] = useState<number>(Date.now());
  const hasTrackedDetailView = useRef(false);

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
      const remaining = Math.max(0, refreshInterval - elapsed);
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

  // Derive period boundaries from history data for chart annotations
  const periodBoundaries = useMemo(() => {
    return derivePeriodBoundaries(
      historyData?.espn_history,
      historyData?.win_prob_history,
      historyData?.scoring_plays,
    );
  }, [historyData?.espn_history, historyData?.win_prob_history, historyData?.scoring_plays]);

  if (eventLoading) {
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
  } else {
    // Scheduled: current betting consensus
    homeProb = odds?.home_probability ?? null;
    awayProb = odds?.away_probability ?? null;
    const count = odds?.bookmaker_count ?? 0;
    if (count > 0) {
      probSourceLabel = `${count} sportsbook${count !== 1 ? "s" : ""}`;
    }
  }

  const homeFavorite = (homeProb ?? 0) >= (awayProb ?? 0);
  const gameIsBlowout = isLive && isBlowout(homeProb);
  const sportEmoji = event.sport ? getEmojiForLeague(event.sport) : "🏆";

  // Analyze sources from history data
  const sourceAnalysis = analyzeSourcesFromHistory(historyData?.bookmaker_history);

  // Detect prediction market vs sportsbook divergence
  const predictionDivergence = analyzePredictionMarketDivergence(
    historyData?.win_prob_history,
    historyData?.win_prob_sources,
    homeProb,
    event.home_team,
  );

  // Calculate countdown progress percentage
  const countdownProgress = ((refreshInterval / 1000 - countdown) / (refreshInterval / 1000)) * 100;

  return (
    <div className="space-y-4">
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
                <span className="flex items-center gap-1.5 bg-emerald-500/15 text-emerald-400 px-2 py-1 rounded-full text-xs font-semibold">
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

      {/* Hero Section */}
      <div className={`rounded-card shadow-card p-4 sm:p-5 ${
        effectivelyLive
          ? "bg-gradient-to-br from-emerald-50 to-white border-2 border-emerald-200"
          : isFinished
          ? "bg-slate-50 border border-slate-200"
          : "bg-surface-card"
      }`}>
        {/* Top bar: sport badge, status, pin */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            {/* Pin button */}
            <button
              onClick={() => togglePin(eventId)}
              disabled={isMaxReached && !eventIsPinned}
              className={`
                p-1.5 rounded-full transition-all
                ${eventIsPinned
                  ? 'text-amber-500 bg-amber-50 hover:bg-amber-100'
                  : 'text-text-secondary/40 hover:text-text-secondary hover:bg-slate/10'
                }
                ${isMaxReached && !eventIsPinned ? 'cursor-not-allowed opacity-30' : ''}
                focus:outline-none focus:ring-2 focus:ring-amber-300
              `}
              title={eventIsPinned ? 'Unpin event' : isMaxReached ? 'Maximum 6 pins' : 'Pin event'}
              aria-label={eventIsPinned ? 'Unpin event' : 'Pin event'}
            >
              <PinIcon filled={eventIsPinned} className="w-5 h-5" />
            </button>

            {event.sport && (
              <span className="text-sm bg-slate/10 px-3 py-1 rounded-full flex items-center gap-2">
                <span className="text-lg">{sportEmoji}</span>
                <span className="text-text-secondary font-medium">
                  {getLeagueDisplay(event.sport)}
                </span>
              </span>
            )}
          </div>

          {/* Status badge */}
          {isCompleted && (
            <span className="flex items-center gap-1 bg-slate/20 text-text-secondary px-3 py-1 rounded-full text-sm font-medium">
              Closed
            </span>
          )}
          {isClosed && (
            <span className="flex items-center gap-1 bg-slate/20 text-text-secondary px-3 py-1 rounded-full text-sm font-medium">
              Closed
            </span>
          )}
        </div>

        {/* Game time/status - compact for live */}
        <div className="text-center mb-3">
          {effectivelyLive ? (
            <div className="flex flex-wrap items-center justify-center gap-2 text-sm">
              <span className="flex items-center gap-1.5 text-emerald-600 font-bold">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                LIVE
              </span>
              {event.espn?.game_clock && event.espn?.period && (
                <>
                  <span className="text-text-secondary/40">·</span>
                  <span className="font-medium text-emerald-400">
                    {event.espn.period} · {event.espn.game_clock}
                  </span>
                </>
              )}
              {event.espn?.broadcast && (
                <>
                  <span className="text-text-secondary/40">·</span>
                  <span className="text-text-secondary">
                    {event.espn.broadcast}
                  </span>
                </>
              )}
              {!event.espn?.game_clock && (
                <>
                  <span className="text-text-secondary/40">·</span>
                  <span className="text-text-secondary">
                    Started {formatStartTime(event.commence_time)}
                  </span>
                </>
              )}
              {gameIsBlowout && (
                <span className="text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full text-xs">
                  Blowout — odds less frequent
                </span>
              )}
            </div>
          ) : isFinished ? (
            <div className="text-text-secondary space-y-0.5">
              <div className="text-base font-medium">
                {new Date(event.commence_time).toLocaleDateString("en-US", {
                  weekday: "short",
                  month: "short",
                  day: "numeric",
                })} at {new Date(event.commence_time).toLocaleTimeString("en-US", {
                  hour: "numeric",
                  minute: "2-digit",
                  timeZoneName: "short",
                })}
              </div>
              <div className="text-caption">Game finished</div>
            </div>
          ) : (
            <div className="space-y-1">
              {gameCountdown && (
                <div className="text-2xl font-bold text-text-primary">
                  Starts in {gameCountdown}
                </div>
              )}
              <div className="text-base text-text-primary">
                {new Date(event.commence_time).toLocaleDateString("en-US", {
                  weekday: "short",
                  month: "short",
                  day: "numeric",
                })} at {new Date(event.commence_time).toLocaleTimeString("en-US", {
                  hour: "numeric",
                  minute: "2-digit",
                  timeZoneName: "short",
                })}
              </div>
              {event.espn?.broadcast && (
                <div className="text-sm text-text-secondary">{event.espn.broadcast}</div>
              )}
            </div>
          )}
        </div>

        {/* Score display for live/finished games */}
        {(isLive || isFinished) && event.home_score !== null && event.away_score !== null && (
          <div className="mb-3 py-3 bg-surface-card/50 rounded-lg">
            <div className="flex items-center justify-center gap-6">
              <div className="text-center">
                <div className={`text-4xl font-bold font-mono ${
                  effectivelyLive ? "text-emerald-600" : "text-text-primary"
                }`}>
                  {event.home_score}
                </div>
                <div className="text-sm text-text-secondary mt-0.5">
                  {event.home_team.split(" ").pop()}
                </div>
              </div>
              <div className="text-2xl text-text-secondary">—</div>
              <div className="text-center">
                <div className={`text-4xl font-bold font-mono ${
                  effectivelyLive ? "text-emerald-600" : "text-text-primary"
                }`}>
                  {event.away_score}
                </div>
                <div className="text-sm text-text-secondary mt-0.5">
                  {event.away_team.split(" ").pop()}
                </div>
              </div>
            </div>
            {isFinished && (
              <div className="text-center mt-1.5 text-xs text-text-secondary">
                Score when books closed (may not be final)
              </div>
            )}
          </div>
        )}

        {/* Teams with probabilities — most important live info */}
        <div className="space-y-3">
          {/* Home Team */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {event.home_team_data?.logo_large ? (
                <img
                  src={event.home_team_data.logo_large}
                  alt=""
                  width={32}
                  height={32}
                  loading="lazy"
                  className="w-8 h-8 object-contain"
                />
              ) : (
                <div
                  className="w-8 h-8 rounded flex-shrink-0 flex items-center justify-center text-xs font-bold text-white/90"
                  style={{ backgroundColor: event.home_team_data?.primary_color || "#94A3B8" }}
                >
                  {event.home_team.split(" ").map(w => w.charAt(0)).join("").slice(0, 2).toUpperCase()}
                </div>
              )}
              <div>
                <h2 className={`text-xl font-semibold ${homeFavorite ? "text-text-primary" : "text-text-secondary"}`}>
                  {event.home_team}
                </h2>
                {(event.standings_context?.home || event.home_team_data?.record) && (
                  <span className="text-xs text-text-muted">
                    {event.standings_context?.home || event.home_team_data?.record}
                  </span>
                )}
              </div>
              {homeFavorite && homeProb && homeProb > 0.5 && (
                <span className="text-xs bg-graphite/10 text-text-primary px-2 py-0.5 rounded">
                  Favorite
                </span>
              )}
            </div>
            <span
              className={`font-mono text-3xl font-bold tabular-nums ${
                homeFavorite ? "text-text-primary" : "text-text-muted"
              }`}
            >
              {formatProbability(homeProb)}
            </span>
          </div>

          {/* Probability Bar with team colors */}
          <ProbabilityBar
            homeProbability={homeProb}
            awayProbability={awayProb}
            homeTeam={event.home_team}
            awayTeam={event.away_team}
            showLabels={false}
            size="lg"
            isLive={effectivelyLive}
            homeColor={event.home_team_data?.primary_color || undefined}
            awayColor={event.away_team_data?.primary_color || undefined}
          />

          {/* Stakes context from standings */}
          {event.standings_context?.stakes && (
            <div className="text-center">
              <span className="text-xs text-text-muted bg-graphite/5 px-2 py-0.5 rounded">
                {event.standings_context.stakes}
              </span>
            </div>
          )}

          {/* Away Team */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {event.away_team_data?.logo_large ? (
                <img
                  src={event.away_team_data.logo_large}
                  alt=""
                  width={32}
                  height={32}
                  loading="lazy"
                  className="w-8 h-8 object-contain"
                />
              ) : (
                <div
                  className="w-8 h-8 rounded flex-shrink-0 flex items-center justify-center text-xs font-bold text-white/90"
                  style={{ backgroundColor: event.away_team_data?.primary_color || "#64748B" }}
                >
                  {event.away_team.split(" ").map(w => w.charAt(0)).join("").slice(0, 2).toUpperCase()}
                </div>
              )}
              <div>
                <h2 className={`text-xl font-semibold ${!homeFavorite ? "text-text-primary" : "text-text-secondary"}`}>
                  {event.away_team}
                </h2>
                {(event.standings_context?.away || event.away_team_data?.record) && (
                  <span className="text-xs text-text-muted">
                    {event.standings_context?.away || event.away_team_data?.record}
                  </span>
                )}
              </div>
              {!homeFavorite && awayProb && awayProb > 0.5 && (
                <span className="text-xs bg-graphite/10 text-text-primary px-2 py-0.5 rounded">
                  Favorite
                </span>
              )}
            </div>
            <span
              className={`font-mono text-3xl font-bold tabular-nums ${
                !homeFavorite ? "text-text-primary" : "text-text-muted"
              }`}
            >
              {formatProbability(awayProb)}
            </span>
          </div>
        </div>

        {/* Source label + ESPN model comparison + opening odds */}
        <div className="mt-2 text-center space-y-1">
          {probSourceLabel && (
            <div>
              <span className="text-[11px] text-text-muted tracking-wide">
                {isFinished ? probSourceLabel : `Betting odds consensus · ${probSourceLabel}`}
              </span>
            </div>
          )}
          {effectivelyLive && event.espn?.win_probability != null && (
            <div>
              <span
                className="text-[11px] text-orange-600 tracking-wide cursor-help"
                title="ESPN's predictive model calculates win probability independently from betting odds, using their own game simulation"
              >
                ESPN model: {(event.espn.win_probability * 100).toFixed(0)}% {event.home_team.split(" ").pop()}
              </span>
            </div>
          )}
          {isLive && openingHomeProb !== null && (
            <div>
              <span className="text-[11px] text-text-muted tracking-wide">
                Opened {formatProbability(openingHomeProb)} / {formatProbability(openingAwayProb)}
              </span>
            </div>
          )}
        </div>

        {/* Excitement Index (EI) - Game Excitement Metric (compact) */}
        {(isFinished || isLive) && (event.ei || event.pulse) && (() => {
          const ei = (event.ei || event.pulse)!;
          return (
          <div className={`mt-4 py-3 px-4 rounded-lg border ${
            ei.score >= 81
              ? "bg-gradient-to-r from-red-50 to-orange-50 border-red-500/30"
              : ei.score >= 61
              ? "bg-gradient-to-r from-orange-50 to-amber-50 border-orange-200"
              : ei.score >= 41
              ? "bg-gradient-to-r from-amber-50 to-yellow-50 border-amber-200"
              : "bg-gradient-to-r from-slate-50 to-gray-50 border-slate-200"
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className={`text-sm font-semibold flex items-center gap-2 ${
                  ei.score >= 81
                    ? "text-red-800"
                    : ei.score >= 61
                    ? "text-orange-800"
                    : ei.score >= 41
                    ? "text-amber-800"
                    : "text-text-secondary-700"
                }`}>
                  {ei.emoji} {isLive ? "Live Excitement" : "Excitement Index"}
                  {isLive && (
                    <span className="w-2 h-2 rounded-full bg-red-500/150 animate-pulse" />
                  )}
                </h3>
                <span className={`text-sm font-medium ${
                  ei.score >= 81
                    ? "text-red-400"
                    : ei.score >= 61
                    ? "text-orange-700"
                    : ei.score >= 41
                    ? "text-amber-700"
                    : "text-text-secondary-600"
                }`}>
                  — {ei.label}
                </span>
              </div>
              <span className={`px-2.5 py-0.5 rounded-full text-sm font-bold ${
                ei.score >= 81
                  ? "bg-red-200 text-red-800"
                  : ei.score >= 61
                  ? "bg-orange-200 text-orange-800"
                  : ei.score >= 41
                  ? "bg-amber-200 text-amber-800"
                  : "bg-surface-border text-text-secondary-700"
              }`}>
                {ei.score} / 100
              </span>
            </div>

            {/* EI Metadata Breakdown - inline */}
            {ei.metadata && (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 pt-2 border-t border-slate-200/60 text-xs">
                {ei.metadata.raw_ei != null && (
                  <Tooltip content="Cumulative probability distance — how much the odds traveled" position="top">
                    <span className="text-text-secondary-500 cursor-help">
                      Travel <span className="font-mono font-semibold text-text-secondary-700">{ei.metadata.raw_ei.toFixed(2)}</span>
                    </span>
                  </Tooltip>
                )}
                {ei.metadata.lead_changes > 0 && (
                  <Tooltip content="How many times the favorite switched" position="top">
                    <span className="text-orange-700 cursor-help">
                      {ei.metadata.lead_changes} lead change{ei.metadata.lead_changes > 1 ? 's' : ''}
                    </span>
                  </Tooltip>
                )}
                {ei.metadata.comeback_factor != null && ei.metadata.comeback_factor > 0 && (
                  <Tooltip content="Winner's lowest probability during the game — lower means bigger comeback" position="top">
                    <span className="text-text-secondary-500 cursor-help">
                      Comeback <span className="font-mono font-semibold text-text-secondary-700">{Math.round(ei.metadata.comeback_factor * 100)}%</span>
                    </span>
                  </Tooltip>
                )}
              </div>
            )}
          </div>
          );
        })()}

        {/* Data freshness strip */}
        {odds?.captured_at && (
          <div className="mt-4 pt-3 border-t border-surface-border/50 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-sm text-text-secondary">
              <span className="flex items-center gap-1">
                🕐 Updated {new Date(odds.captured_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })} at {new Date(odds.captured_at).toLocaleTimeString("en-US", {
                  hour: "numeric",
                  minute: "2-digit",
                })}
              </span>
              <div className="flex items-center gap-4 text-xs text-text-muted">
                {odds.spread !== null && (
                  <span className="font-mono">
                    Spread {odds.spread > 0 ? `+${odds.spread}` : odds.spread}
                  </span>
                )}
                {odds.over_under !== null && (
                  <span className="font-mono">
                    O/U {odds.over_under}
                  </span>
                )}
                {(() => {
                  // Get bookmaker count from current_odds (most reliable)
                  // Get names from bookmaker_odds or history for tooltip
                  const bookmakerNames = event.bookmaker_odds?.map(b => b.bookmaker)
                    || (historyData?.bookmaker_history ? Object.keys(historyData.bookmaker_history) : []);
                  const count = odds.bookmaker_count || bookmakerNames.length || 0;
                  if (count > 0) {
                    return (
                      <span
                        className="cursor-help border-b border-dotted border-silver hover:text-text-secondary hover:border-text-secondary transition-colors px-1 py-0.5 -mx-1"
                        title={bookmakerNames.length > 0 ? bookmakerNames.join(", ") : undefined}
                      >
                        {count} source{count !== 1 ? "s" : ""}
                      </span>
                    );
                  }
                  return null;
                })()}
              </div>
            </div>
            {sourceAnalysis.divergenceWarning && (
              <div className="flex items-center gap-2 text-xs text-amber-700 bg-amber-50 px-3 py-1.5 rounded">
                <span>⚠️</span>
                <span>{sourceAnalysis.divergenceWarning}</span>
              </div>
            )}
            {predictionDivergence && (
              <div className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded ${
                predictionDivergence.delta >= 0.10
                  ? "text-purple-800 bg-purple-500/15 border border-purple-200"
                  : "text-blue-700 bg-blue-50"
              }`}>
                <span>{predictionDivergence.delta >= 0.10 ? "📊" : "🔀"}</span>
                <span>
                  {predictionDivergence.direction}
                  {predictionDivergence.delta >= 0.10 && (
                    <span className="ml-1 font-semibold">
                      ({Math.round(predictionDivergence.delta * 100)}% gap)
                    </span>
                  )}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Score Differential Chart - combines projected spread and actual score diff */}
      {historyData?.history && historyData.history.length > 0 && (
        <div className="bg-surface-card rounded-card shadow-card p-3 sm:p-4">
          <h3 className="text-sm font-semibold text-text-secondary mb-2 flex items-center gap-2">
            Score Differential
          </h3>
          <ScoreDifferentialChart
            history={historyData.history}
            homeTeam={event.home_team}
            awayTeam={event.away_team}
            commenceTime={event.commence_time}
            isLive={effectivelyLive}
            bookmakerHistory={historyData?.bookmaker_history}
            scoreHistory={historyData?.score_history}
            currentHomeScore={event.home_score}
            currentAwayScore={event.away_score}
            eventStatus={event.status}
            periodBoundaries={periodBoundaries}
            homeTeamColor={event.home_team_data?.primary_color || undefined}
            awayTeamColor={event.away_team_data?.primary_color || undefined}
            homeTeamLogo={event.home_team_data?.logo_small || undefined}
            awayTeamLogo={event.away_team_data?.logo_small || undefined}
          />
        </div>
      )}

      {/* Trend Chart */}
      <div className="bg-surface-card rounded-card shadow-card p-4 sm:p-5">
        <h3 className="text-sm font-semibold text-text-secondary mb-3 flex items-center gap-2">
          Win Probability
        </h3>
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
        ) : historyData?.history?.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-sm text-text-secondary">
            📊 Tracking will begin when odds are available
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
            eventId={eventId}
            eventStatus={event.status}
            periodBoundaries={periodBoundaries}
            homeTeamColor={event.home_team_data?.primary_color || undefined}
            awayTeamColor={event.away_team_data?.primary_color || undefined}
            homeTeamLogo={event.home_team_data?.logo_small || undefined}
            awayTeamLogo={event.away_team_data?.logo_small || undefined}
          />
        )}
      </div>

      {/* Win Probabilities by Sportsbook */}
      {event.bookmaker_odds && event.bookmaker_odds.length > 0 && (
        <div className="bg-surface-card rounded-card shadow-card p-4 sm:p-5">
          <h3 className="text-sm font-semibold text-text-secondary mb-3 flex items-center gap-2">
            Win Probabilities by Sportsbook
          </h3>
          <BookmakerTable
            bookmakerOdds={event.bookmaker_odds}
            homeTeam={event.home_team}
            awayTeam={event.away_team}
          />
        </div>
      )}

      {/* Line Movement Analysis — AI-powered odds movement explanations */}
      <LineMovementExplainer
        eventId={eventId}
        homeTeam={event.home_team}
        awayTeam={event.away_team}
        eventStatus={event.status}
      />

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
      />
    </div>
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
