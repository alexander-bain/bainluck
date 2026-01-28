"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetchEvent, fetchEventHistory, formatProbability, formatGameTime } from "@/lib/api";
import ProbabilityBar from "@/components/ProbabilityBar";
import OddsChart from "@/components/OddsChart";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import { getLeagueDisplayWithEmoji } from "@/lib/sportCategories";

interface EventPageProps {
  params: { id: string };
}

// Refresh intervals
const LIVE_REFRESH_INTERVAL = 60000; // 60 seconds for live games
const SCHEDULED_REFRESH_INTERVAL = 120000; // 2 minutes for scheduled games

/**
 * Format a countdown from now until the target time
 */
function formatCountdown(targetTime: string): string {
  const target = new Date(targetTime);
  const now = new Date();
  const diff = target.getTime() - now.getTime();

  if (diff <= 0) return "Started";

  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

  if (days > 0) {
    return `${days}d ${hours}h`;
  } else if (hours > 0) {
    return `${hours}h ${minutes}m`;
  } else {
    return `${minutes}m`;
  }
}

/**
 * Format game time for display
 */
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

export default function EventPage({ params }: EventPageProps) {
  const eventId = parseInt(params.id, 10);
  const [countdown, setCountdown] = useState<number>(0);
  const [gameCountdown, setGameCountdown] = useState<string>("");
  const [lastRefresh, setLastRefresh] = useState<number>(Date.now());

  // Fetch event details
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
  const refreshInterval = isLive ? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL;

  // Countdown timer effect for refresh indicator
  useEffect(() => {
    const interval = setInterval(() => {
      const elapsed = Date.now() - lastRefresh;
      const remaining = Math.max(0, refreshInterval - elapsed);
      setCountdown(Math.ceil(remaining / 1000));
    }, 100);

    return () => clearInterval(interval);
  }, [lastRefresh, refreshInterval]);

  // Game countdown effect
  useEffect(() => {
    if (!event?.commence_time || isLive) {
      setGameCountdown("");
      return;
    }

    const updateCountdown = () => {
      setGameCountdown(formatCountdown(event.commence_time));
    };

    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);
    return () => clearInterval(interval);
  }, [event?.commence_time, isLive]);

  // Fetch odds history
  const {
    data: historyData,
    error: historyError,
    isLoading: historyLoading,
  } = useSWR(
    event ? ["history", eventId] : null,
    () => fetchEventHistory(eventId, 48),
    { refreshInterval: 60000 }
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

  const hasCurrentScores = isLive && event.home_score !== null && event.away_score !== null;
  const hasProjectedScores = odds?.projected_home_score !== null && odds?.projected_away_score !== null;

  return (
    <div className="space-y-6">
      {/* Back link and refresh indicator */}
      <div className="flex items-center justify-between">
        <Link
          href="/"
          className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900 transition-colors"
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
          Back to events
        </Link>

        {/* Auto-refresh countdown */}
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <div className="flex items-center gap-1">
            <svg
              className={`w-3 h-3 ${isLive ? "text-green-500 animate-pulse" : "text-gray-400"}`}
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <circle cx="10" cy="10" r="8" />
            </svg>
            <span>{isLive ? "Live updates" : "Auto-refresh"}</span>
          </div>
          <span className="text-gray-400">|</span>
          <span className="font-mono tabular-nums w-6 text-right">{countdown}s</span>
        </div>
      </div>

      {/* Game Time Header - Prominent display */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        {/* Sport and Status Badges */}
        <div className="flex items-center gap-3 mb-4">
          {event.sport && (
            <span className="text-sm font-medium text-gray-600">
              {getLeagueDisplayWithEmoji(event.sport)}
            </span>
          )}
          {isLive && (
            <span className="text-xs font-bold text-white bg-red-500 px-3 py-1 rounded-full animate-pulse">
              LIVE
            </span>
          )}
        </div>

        {/* Game Time - Large and Prominent */}
        <div className="text-center mb-6">
          {isLive ? (
            <div className="text-2xl font-bold text-red-600">
              Game In Progress
            </div>
          ) : (
            <>
              <div className="text-lg text-gray-600 mb-1">
                {formatStartTime(event.commence_time)}
              </div>
              {gameCountdown && (
                <div className="text-4xl font-bold text-gray-900">
                  {gameCountdown}
                </div>
              )}
              <div className="text-sm text-gray-500 mt-1">until game starts</div>
            </>
          )}
        </div>

        {/* Teams with probabilities */}
        <div className="space-y-4">
          {/* Home Team */}
          <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
            <div className="flex items-center gap-3">
              <div
                className={`w-3 h-3 rounded-full ${
                  homeFavorite ? "bg-green-500" : "bg-gray-300"
                }`}
              />
              <div>
                <h2 className="text-xl font-bold text-gray-900">
                  {event.home_team}
                </h2>
                <p className="text-xs text-gray-500">Home</p>
              </div>
            </div>
            <span
              className={`text-3xl font-bold ${
                homeFavorite ? "text-green-600" : "text-gray-500"
              }`}
            >
              {formatProbability(homeProb)}
            </span>
          </div>

          {/* Probability Bar */}
          <ProbabilityBar
            homeProbability={homeProb}
            awayProbability={awayProb}
            homeTeam={event.home_team}
            awayTeam={event.away_team}
            showLabels={false}
            size="lg"
          />

          {/* Away Team */}
          <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
            <div className="flex items-center gap-3">
              <div
                className={`w-3 h-3 rounded-full ${
                  !homeFavorite ? "bg-blue-500" : "bg-gray-300"
                }`}
              />
              <div>
                <h2 className="text-xl font-bold text-gray-900">
                  {event.away_team}
                </h2>
                <p className="text-xs text-gray-500">Away</p>
              </div>
            </div>
            <span
              className={`text-3xl font-bold ${
                !homeFavorite ? "text-blue-600" : "text-gray-500"
              }`}
            >
              {formatProbability(awayProb)}
            </span>
          </div>
        </div>
      </div>

      {/* Score Comparison Card - Current vs Projected */}
      {(hasCurrentScores || hasProjectedScores) && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            Score {isLive ? "Comparison" : "Projection"}
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Current Score (Live only) */}
            {hasCurrentScores && (
              <div className="text-center p-6 bg-gradient-to-br from-green-50 to-green-100 rounded-xl border-2 border-green-200">
                <p className="text-sm font-medium text-green-700 mb-3 uppercase tracking-wide">
                  Current Score
                </p>
                <div className="flex items-center justify-center gap-4">
                  <div className="text-center">
                    <div className="text-5xl font-bold text-green-800">
                      {event.home_score}
                    </div>
                    <div className="text-xs text-green-600 mt-1">
                      {event.home_team.split(" ").pop()}
                    </div>
                  </div>
                  <div className="text-2xl text-green-400">-</div>
                  <div className="text-center">
                    <div className="text-5xl font-bold text-green-800">
                      {event.away_score}
                    </div>
                    <div className="text-xs text-green-600 mt-1">
                      {event.away_team.split(" ").pop()}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Projected Final Score */}
            {hasProjectedScores && (
              <div className={`text-center p-6 bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl border-2 border-blue-200 ${!hasCurrentScores ? "md:col-span-2 max-w-md mx-auto w-full" : ""}`}>
                <p className="text-sm font-medium text-blue-700 mb-3 uppercase tracking-wide">
                  Projected Final
                </p>
                <div className="flex items-center justify-center gap-4">
                  <div className="text-center">
                    <div className="text-5xl font-bold text-blue-800">
                      {Math.round(odds!.projected_home_score!)}
                    </div>
                    <div className="text-xs text-blue-600 mt-1">
                      {event.home_team.split(" ").pop()}
                    </div>
                  </div>
                  <div className="text-2xl text-blue-400">-</div>
                  <div className="text-center">
                    <div className="text-5xl font-bold text-blue-800">
                      {Math.round(odds!.projected_away_score!)}
                    </div>
                    <div className="text-xs text-blue-600 mt-1">
                      {event.away_team.split(" ").pop()}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Score Difference Indicator for Live Games */}
          {hasCurrentScores && hasProjectedScores && (
            <div className="mt-4 text-center text-sm text-gray-600">
              {(() => {
                const currentDiff = event.home_score! - event.away_score!;
                const projectedDiff = Math.round(odds!.projected_home_score!) - Math.round(odds!.projected_away_score!);
                const diffDelta = projectedDiff - currentDiff;

                if (Math.abs(diffDelta) < 1) {
                  return <span className="text-gray-500">Score on pace with projection</span>;
                } else if (diffDelta > 0) {
                  return (
                    <span className="text-green-600">
                      {event.home_team.split(" ").pop()} projected to extend lead by {diffDelta.toFixed(0)} pts
                    </span>
                  );
                } else {
                  return (
                    <span className="text-blue-600">
                      {event.away_team.split(" ").pop()} projected to close gap by {Math.abs(diffDelta).toFixed(0)} pts
                    </span>
                  );
                }
              })()}
            </div>
          )}

          {odds?.bookmaker && (
            <p className="text-xs text-gray-400 mt-4 text-center">
              Based on {odds.bookmaker} lines | Updated {new Date(odds.captured_at).toLocaleTimeString()}
            </p>
          )}
        </div>
      )}

      {/* Betting Lines */}
      {odds && (odds.spread !== null || odds.over_under !== null) && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            Betting Lines
          </h3>
          <div className="grid grid-cols-2 gap-4">
            {odds.spread !== null && (
              <div className="text-center p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-500 mb-1">Spread</p>
                <p className="text-xl font-bold text-gray-900">
                  {odds.spread > 0 ? `+${odds.spread}` : odds.spread}
                </p>
                <p className="text-xs text-gray-400 mt-1">{event.home_team.split(" ").pop()}</p>
              </div>
            )}
            {odds.over_under !== null && (
              <div className="text-center p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-500 mb-1">Total</p>
                <p className="text-xl font-bold text-gray-900">
                  O/U {odds.over_under}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Odds History Chart */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Probability Trend
        </h3>
        {historyLoading ? (
          <div className="h-64 flex items-center justify-center">
            <LoadingSpinner size="sm" text="Loading chart..." />
          </div>
        ) : historyError ? (
          <div className="h-64 flex items-center justify-center text-gray-500">
            Unable to load history
          </div>
        ) : (
          <OddsChart
            history={historyData?.history ?? []}
            homeTeam={event.home_team}
            awayTeam={event.away_team}
            commenceTime={event.commence_time}
            isLive={isLive}
          />
        )}
      </div>
    </div>
  );
}
