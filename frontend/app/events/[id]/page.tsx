"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetchEvent, fetchEventHistory, formatProbability } from "@/lib/api";
import ProbabilityBar from "@/components/ProbabilityBar";
import OddsChart from "@/components/OddsChart";
import ScoreChart from "@/components/ScoreChart";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import { getLeagueDisplay, getEmojiForLeague } from "@/lib/sportCategories";

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
  history: Array<{
    timestamp: string;
    home_probability: number | null;
    bookmaker: string;
  }>
): SourceAnalysis {
  if (!history || history.length === 0) {
    return {
      sources: [],
      hasSignificantDivergence: false,
      divergenceWarning: null,
      maxDivergence: 0,
    };
  }

  // Get unique bookmakers
  const sources = Array.from(new Set(history.map((h) => h.bookmaker).filter(Boolean)));

  // Look at recent data (last hour) to detect divergence
  const oneHourAgo = Date.now() - 60 * 60 * 1000;
  const recentHistory = history.filter(
    (h) => new Date(h.timestamp).getTime() > oneHourAgo && h.home_probability !== null
  );

  // Group by bookmaker and get their latest probabilities
  const bookmakerProbs: Record<string, number> = {};
  for (const point of recentHistory) {
    if (point.home_probability !== null) {
      bookmakerProbs[point.bookmaker] = point.home_probability;
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

  const isLive = event?.status === "live";
  const isCompleted = event?.status === "completed";
  const refreshInterval = isLive ? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL;

  useEffect(() => {
    const interval = setInterval(() => {
      const elapsed = Date.now() - lastRefresh;
      const remaining = Math.max(0, refreshInterval - elapsed);
      setCountdown(Math.ceil(remaining / 1000));
    }, 100);
    return () => clearInterval(interval);
  }, [lastRefresh, refreshInterval]);

  useEffect(() => {
    if (!event?.commence_time || isLive || isCompleted) {
      setGameCountdown("");
      return;
    }
    const updateCountdown = () => {
      setGameCountdown(formatCountdown(event.commence_time));
    };
    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);
    return () => clearInterval(interval);
  }, [event?.commence_time, isLive, isCompleted]);

  const {
    data: historyData,
    error: historyError,
    isLoading: historyLoading,
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
  const sourceAnalysis = analyzeSourcesFromHistory(historyData?.history ?? []);

  // Calculate countdown progress percentage
  const countdownProgress = ((refreshInterval / 1000 - countdown) / (refreshInterval / 1000)) * 100;

  return (
    <div className="space-y-6">
      {/* Navigation */}
      <div className="flex items-center justify-between">
        <Link
          href="/"
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
        {!isCompleted && (
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-sm">
              {isLive && (
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
                  stroke={isLive ? "#10B981" : "#6B7280"}
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
        isLive
          ? "bg-gradient-to-br from-emerald-50 to-white border-2 border-emerald-200"
          : isCompleted
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
              ✅ Final
            </span>
          )}
        </div>

        {/* Game time/status */}
        <div className="text-center mb-6">
          {isLive ? (
            <div className="space-y-2">
              <div className="flex items-center justify-center gap-2">
                <span className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-2xl font-bold text-emerald-600">🔴 LIVE</span>
              </div>
              {gameIsBlowout && (
                <div className="flex items-center justify-center gap-2 text-amber-600 bg-amber-50 px-3 py-1 rounded-full text-sm mx-auto w-fit">
                  <span>⚠️</span>
                  <span>Blowout — odds may update less frequently</span>
                </div>
              )}
            </div>
          ) : isCompleted ? (
            <div className="text-slate">
              <div className="text-caption mb-1">Game ended</div>
              <div className="text-lg font-medium">
                {formatStartTime(event.commence_time)}
              </div>
            </div>
          ) : (
            <>
              <div className="text-caption text-slate mb-1">
                📅 {formatStartTime(event.commence_time)}
              </div>
              {gameCountdown && (
                <div className="text-display text-graphite">
                  ⏰ {gameCountdown}
                </div>
              )}
            </>
          )}
        </div>

        {/* Score display for live/completed games */}
        {(isLive || isCompleted) && event.home_score !== null && event.away_score !== null && (
          <div className="flex items-center justify-center gap-6 mb-6 py-4 bg-white/50 rounded-lg">
            <div className="text-center">
              <div className={`text-4xl font-bold font-mono ${
                isLive ? "text-emerald-600" : "text-graphite"
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
                isLive ? "text-emerald-600" : "text-graphite"
              }`}>
                {event.away_score}
              </div>
              <div className="text-sm text-slate mt-1">
                {event.away_team.split(" ").pop()}
              </div>
            </div>
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
            isLive={isLive}
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
            <div className="flex flex-wrap justify-between gap-2 text-sm text-slate">
              <span className="flex items-center gap-1">
                🕐 Updated {new Date(odds.captured_at).toLocaleTimeString("en-US", {
                  hour: "numeric",
                  minute: "2-digit",
                })}
              </span>
              {sourceAnalysis.sources.length > 0 && (
                <span className="text-xs text-silver">
                  {sourceAnalysis.sources.length} source{sourceAnalysis.sources.length !== 1 ? "s" : ""}
                </span>
              )}
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

      {/* Score Trend Chart - shown independently if there's history data */}
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
            isLive={isLive}
          />
        </div>
      )}

      {/* Betting Lines */}
      {odds && (odds.spread !== null || odds.over_under !== null) && (
        <div className="bg-white rounded-card shadow-card p-6">
          <h3 className="text-sm font-semibold text-slate mb-4 flex items-center gap-2">
            📈 Lines
          </h3>
          <div className="grid grid-cols-2 gap-4">
            {odds.spread !== null && (
              <div className="text-center p-4 bg-snow rounded-lg border border-mist">
                <p className="text-xs text-slate mb-1">Spread</p>
                <p className="font-mono text-xl font-bold text-graphite">
                  {odds.spread > 0 ? `+${odds.spread}` : odds.spread}
                </p>
              </div>
            )}
            {odds.over_under !== null && (
              <div className="text-center p-4 bg-snow rounded-lg border border-mist">
                <p className="text-xs text-slate mb-1">Over/Under</p>
                <p className="font-mono text-xl font-bold text-graphite">
                  {odds.over_under}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Trend Chart */}
      <div className="bg-white rounded-card shadow-card p-6">
        <h3 className="text-sm font-semibold text-slate mb-4 flex items-center gap-2">
          📉 Probability Trend (Last 48 Hours)
        </h3>
        {historyLoading ? (
          <div className="h-48 flex items-center justify-center">
            <LoadingSpinner size="sm" />
          </div>
        ) : historyError ? (
          <div className="h-48 flex items-center justify-center text-sm text-slate">
            Unable to load history
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
            isLive={isLive}
            bookmakerHistory={historyData?.bookmaker_history}
          />
        )}
      </div>
    </div>
  );
}
