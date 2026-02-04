"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetchEvent, fetchEventHistory, formatProbability } from "@/lib/api";
import ProbabilityBar from "@/components/ProbabilityBar";
import OddsChart from "@/components/OddsChart";
import ScoreChart from "@/components/ScoreChart";
import ActualScoreChart from "@/components/ActualScoreChart";
import BookmakerTable from "@/components/BookmakerTable";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import { getLeagueDisplay, getEmojiForLeague } from "@/lib/sportCategories";
import {
  useAnalytics,
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import { isCloseGame, calculateMinutesToStart } from "@/lib/analytics";

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
    pageTitle: event ? `${event.home_team} vs ${event.away_team} - OddsTracker` : 'Event - OddsTracker',
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
  const homeProb = odds?.home_probability;
  const awayProb = odds?.away_probability;
  const homeFavorite = (homeProb ?? 0) >= (awayProb ?? 0);
  const gameIsBlowout = isLive && isBlowout(homeProb);
  const sportEmoji = event.sport ? getEmojiForLeague(event.sport) : "🏆";

  // Analyze sources from history data
  const sourceAnalysis = analyzeSourcesFromHistory(historyData?.bookmaker_history);

  // Calculate countdown progress percentage
  const countdownProgress = ((refreshInterval / 1000 - countdown) / (refreshInterval / 1000)) * 100;

  return (
    <div className="space-y-6">
      {/* Navigation */}
      <div className="flex items-center justify-between">
        <Link
          href="/"
          onClick={() => trackNavigationClick('back', `/events/${eventId}`, '/')}
          className="inline-flex items-center text-caption text-slate hover:text-graphite transition-colors"
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
                <span className="flex items-center gap-1.5 bg-emerald-100 text-emerald-700 px-2 py-1 rounded-full text-xs font-semibold">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  LIVE
                </span>
              )}
              <span className="text-slate">Next update:</span>
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
              <span className="absolute inset-0 flex items-center justify-center text-xs font-mono font-bold text-graphite">
                {countdown}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Hero Section */}
      <div className={`rounded-card shadow-card p-6 ${
        effectivelyLive
          ? "bg-gradient-to-br from-emerald-50 to-white border-2 border-emerald-200"
          : isFinished
          ? "bg-slate-50 border border-slate-200"
          : "bg-white"
      }`}>
        {/* Sport badge with emoji */}
        <div className="flex items-center justify-between mb-4">
          {event.sport && (
            <span className="text-sm bg-slate/10 px-3 py-1 rounded-full flex items-center gap-2">
              <span className="text-lg">{sportEmoji}</span>
              <span className="text-slate font-medium">
                {getLeagueDisplay(event.sport)}
              </span>
            </span>
          )}

          {/* Status badge */}
          {isCompleted && (
            <span className="flex items-center gap-1 bg-slate/20 text-slate px-3 py-1 rounded-full text-sm font-medium">
              ✅ Closed
            </span>
          )}
          {isClosed && (
            <span className="flex items-center gap-1 bg-slate/20 text-slate px-3 py-1 rounded-full text-sm font-medium">
              ✅ Closed
            </span>
          )}
        </div>

        {/* Game time/status */}
        <div className="text-center mb-6">
          {effectivelyLive ? (
            <div className="space-y-2">
              <div className="flex items-center justify-center gap-2">
                <span className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-2xl font-bold text-emerald-600">🔴 LIVE</span>
              </div>
              <div className="text-sm text-slate">
                Started {formatStartTime(event.commence_time)}
              </div>
              {gameIsBlowout && (
                <div className="flex items-center justify-center gap-2 text-amber-600 bg-amber-50 px-3 py-1 rounded-full text-sm mx-auto w-fit">
                  <span>⚠️</span>
                  <span>Blowout — odds may update less frequently</span>
                </div>
              )}
            </div>
          ) : isFinished ? (
            <div className="text-slate space-y-1">
              <div className="text-lg font-medium">
                📅 {new Date(event.commence_time).toLocaleDateString("en-US", {
                  weekday: "short",
                  month: "short",
                  day: "numeric",
                })} at {new Date(event.commence_time).toLocaleTimeString("en-US", {
                  hour: "numeric",
                  minute: "2-digit",
                  timeZoneName: "short",
                })}
              </div>
              <div className="text-caption">Game finished • Books closed</div>
            </div>
          ) : (
            <div className="space-y-2">
              {/* Clean start time display with countdown */}
              {gameCountdown && (
                <div className="text-2xl font-bold text-graphite">
                  ⏱️ Starts in {gameCountdown}
                </div>
              )}
              <div className="text-lg text-graphite">
                📅 {new Date(event.commence_time).toLocaleDateString("en-US", {
                  weekday: "short",
                  month: "short",
                  day: "numeric",
                })} at {new Date(event.commence_time).toLocaleTimeString("en-US", {
                  hour: "numeric",
                  minute: "2-digit",
                  timeZoneName: "short",
                })}
              </div>
            </div>
          )}
        </div>

        {/* ESPN info: broadcast, game clock */}
        {event.espn && (
          <div className="flex flex-wrap items-center justify-center gap-3 mb-4 text-sm">
            {event.espn.broadcast && (
              <span className="flex items-center gap-1.5 bg-slate/5 px-3 py-1 rounded-full text-slate">
                📺 {event.espn.broadcast}
              </span>
            )}
            {effectivelyLive && event.espn.game_clock && event.espn.period && (
              <span className="flex items-center gap-1.5 bg-emerald-50 px-3 py-1 rounded-full text-emerald-700 font-medium">
                {event.espn.period} &middot; {event.espn.game_clock}
              </span>
            )}
            {effectivelyLive && event.espn.win_probability != null && (
              <span className="flex items-center gap-1.5 bg-orange-50 px-3 py-1 rounded-full text-orange-700 text-xs font-medium"
                    title="ESPN predictive model win probability">
                ESPN: {(event.espn.win_probability * 100).toFixed(0)}% {event.home_team.split(" ").pop()}
              </span>
            )}
          </div>
        )}

        {/* Score display for live/finished games */}
        {(isLive || isFinished) && event.home_score !== null && event.away_score !== null && (
          <div className="mb-6 py-4 bg-white/50 rounded-lg">
            <div className="flex items-center justify-center gap-6">
              <div className="text-center">
                <div className={`text-4xl font-bold font-mono ${
                  effectivelyLive ? "text-emerald-600" : "text-graphite"
                }`}>
                  {event.home_score}
                </div>
                <div className="text-sm text-slate mt-1">
                  {event.home_team.split(" ").pop()}
                </div>
              </div>
              <div className="text-2xl text-slate">—</div>
              <div className="text-center">
                <div className={`text-4xl font-bold font-mono ${
                  effectivelyLive ? "text-emerald-600" : "text-graphite"
                }`}>
                  {event.away_score}
                </div>
                <div className="text-sm text-slate mt-1">
                  {event.away_team.split(" ").pop()}
                </div>
              </div>
            </div>
            {isFinished && (
              <div className="text-center mt-2 text-xs text-slate">
                Score when books closed (may not be final)
              </div>
            )}
          </div>
        )}

        {/* Pulse - Game Excitement Metric */}
        {(isFinished || isLive) && event.pulse && (
          <div className={`mb-6 py-4 px-5 rounded-lg border ${
            event.pulse.score >= 81
              ? "bg-gradient-to-r from-red-50 to-orange-50 border-red-200"
              : event.pulse.score >= 61
              ? "bg-gradient-to-r from-orange-50 to-amber-50 border-orange-200"
              : event.pulse.score >= 41
              ? "bg-gradient-to-r from-amber-50 to-yellow-50 border-amber-200"
              : "bg-gradient-to-r from-slate-50 to-gray-50 border-slate-200"
          }`}>
            <div className="flex items-center justify-between mb-3">
              <h3 className={`text-sm font-semibold flex items-center gap-2 ${
                event.pulse.score >= 81
                  ? "text-red-800"
                  : event.pulse.score >= 61
                  ? "text-orange-800"
                  : event.pulse.score >= 41
                  ? "text-amber-800"
                  : "text-slate-700"
              }`}>
                {event.pulse.emoji} {isLive ? "Live Pulse" : "Game Pulse"}
                {isLive && (
                  <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                )}
              </h3>
              <span className={`px-3 py-1 rounded-full text-sm font-bold ${
                event.pulse.score >= 81
                  ? "bg-red-200 text-red-800"
                  : event.pulse.score >= 61
                  ? "bg-orange-200 text-orange-800"
                  : event.pulse.score >= 41
                  ? "bg-amber-200 text-amber-800"
                  : "bg-slate-200 text-slate-700"
              }`}>
                {event.pulse.score} / 100
              </span>
            </div>

            <div className="text-center mb-4">
              <div className={`text-2xl font-bold ${
                event.pulse.score >= 81
                  ? "text-red-700"
                  : event.pulse.score >= 61
                  ? "text-orange-700"
                  : event.pulse.score >= 41
                  ? "text-amber-700"
                  : "text-slate-600"
              }`}>
                {event.pulse.label}
              </div>
              <div className={`text-sm mt-1 ${
                event.pulse.score >= 61 ? "text-orange-600" : "text-slate-500"
              }`}>
                {isLive ? "Pulse strength so far" : `Status: ${event.pulse.status}`}
              </div>
            </div>

            {/* Pulse Components Breakdown */}
            {event.pulse.components && (
              <div className="grid grid-cols-3 gap-3 mt-4 pt-4 border-t border-slate-200">
                <div className="text-center">
                  <div className="text-xs text-slate-500 uppercase tracking-wide">Heart Rate</div>
                  <div className="text-lg font-mono font-semibold text-slate-700">
                    {Math.round(event.pulse.components.heart_rate * 100)}%
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-xs text-slate-500 uppercase tracking-wide">Amplitude</div>
                  <div className="text-lg font-mono font-semibold text-slate-700">
                    {Math.round(event.pulse.components.amplitude * 100)}%
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-xs text-slate-500 uppercase tracking-wide">Vitals</div>
                  <div className="text-lg font-mono font-semibold text-slate-700">
                    {Math.round(event.pulse.components.vitals * 100)}%
                  </div>
                </div>
                {event.pulse.components.lead_changes > 0 && (
                  <div className="col-span-3 text-center pt-2 border-t border-slate-200">
                    <span className="inline-flex items-center gap-1 text-sm text-orange-700 bg-orange-100 px-2 py-0.5 rounded">
                      🔄 {event.pulse.components.lead_changes} Lead Change{event.pulse.components.lead_changes > 1 ? 's' : ''}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Teams with probabilities */}
        <div className="space-y-4">
          {/* Home Team */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h2 className={`text-xl font-semibold ${homeFavorite ? "text-graphite" : "text-slate"}`}>
                {event.home_team}
              </h2>
              {homeFavorite && homeProb && homeProb > 0.5 && (
                <span className="text-xs bg-graphite/10 text-graphite px-2 py-0.5 rounded">
                  Favorite
                </span>
              )}
            </div>
            <span
              className={`font-mono text-3xl font-bold tabular-nums ${
                homeFavorite ? "text-graphite" : "text-silver"
              }`}
            >
              {formatProbability(homeProb)}
            </span>
          </div>

          {/* Probability Bar with color */}
          <ProbabilityBar
            homeProbability={homeProb}
            awayProbability={awayProb}
            homeTeam={event.home_team}
            awayTeam={event.away_team}
            showLabels={false}
            size="lg"
            isLive={effectivelyLive}
          />

          {/* Away Team */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h2 className={`text-xl font-semibold ${!homeFavorite ? "text-graphite" : "text-slate"}`}>
                {event.away_team}
              </h2>
              {!homeFavorite && awayProb && awayProb > 0.5 && (
                <span className="text-xs bg-graphite/10 text-graphite px-2 py-0.5 rounded">
                  Favorite
                </span>
              )}
            </div>
            <span
              className={`font-mono text-3xl font-bold tabular-nums ${
                !homeFavorite ? "text-graphite" : "text-silver"
              }`}
            >
              {formatProbability(awayProb)}
            </span>
          </div>
        </div>

        {/* Data freshness strip */}
        {odds?.captured_at && (
          <div className="mt-6 pt-4 border-t border-mist/50 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-sm text-slate">
              <span className="flex items-center gap-1">
                🕐 Updated {new Date(odds.captured_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })} at {new Date(odds.captured_at).toLocaleTimeString("en-US", {
                  hour: "numeric",
                  minute: "2-digit",
                })}
              </span>
              <div className="flex items-center gap-4 text-xs text-silver">
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
                        className="cursor-help border-b border-dotted border-silver hover:text-slate hover:border-slate transition-colors px-1 py-0.5 -mx-1"
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
          </div>
        )}
      </div>

      {/* Actual Score Chart - for live/finished games */}
      {(isLive || isFinished) && event.home_score !== null && event.away_score !== null && (
        <div className="bg-white rounded-card shadow-card p-6">
          <h3 className="text-sm font-semibold text-slate mb-4 flex items-center gap-2">
            🏆 Actual Score
          </h3>
          <ActualScoreChart
            scoreHistory={historyData?.score_history}
            homeTeam={event.home_team}
            awayTeam={event.away_team}
            currentHomeScore={event.home_score}
            currentAwayScore={event.away_score}
            commenceTime={event.commence_time}
            isLive={effectivelyLive}
            lastScoreUpdate={odds?.captured_at}
            eventId={event.id}
          />
        </div>
      )}

      {/* Projected Score Trend Chart - shown independently if there's history data */}
      {historyData?.history && historyData.history.length > 0 && (
        <div className="bg-white rounded-card shadow-card p-6">
          <h3 className="text-sm font-semibold text-slate mb-4 flex items-center gap-2">
            📊 Projected Score Trend
          </h3>
          <ScoreChart
            history={historyData.history}
            homeTeam={event.home_team}
            awayTeam={event.away_team}
            commenceTime={event.commence_time}
            isLive={effectivelyLive}
            bookmakerHistory={historyData?.bookmaker_history}
            eventStatus={event.status}
          />
        </div>
      )}

      {/* Trend Chart */}
      <div className="bg-white rounded-card shadow-card p-6">
        <h3 className="text-sm font-semibold text-slate mb-4 flex items-center gap-2">
          📉 Probability Trend
        </h3>
        {historyLoading ? (
          <div className="h-48 flex items-center justify-center">
            <LoadingSpinner size="sm" />
          </div>
        ) : historyError ? (
          <div className="h-48 flex flex-col items-center justify-center text-sm text-slate gap-2">
            <span>Unable to load history</span>
            <span className="text-xs text-silver">
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
          <div className="h-48 flex items-center justify-center text-sm text-slate">
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
            eventStatus={event.status}
          />
        )}
      </div>

      {/* Win Probabilities by Sportsbook */}
      {event.bookmaker_odds && event.bookmaker_odds.length > 0 && (
        <div className="bg-white rounded-card shadow-card p-6">
          <h3 className="text-sm font-semibold text-slate mb-4 flex items-center gap-2">
            📊 Win Probabilities by Sportsbook
          </h3>
          <BookmakerTable
            bookmakerOdds={event.bookmaker_odds}
            homeTeam={event.home_team}
            awayTeam={event.away_team}
          />
        </div>
      )}
    </div>
  );
}
