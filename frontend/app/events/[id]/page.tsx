"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetchEvent, fetchEventHistory, formatProbability, formatMoneyline, formatGameTime } from "@/lib/api";
import ProbabilityBar from "@/components/ProbabilityBar";
import OddsChart from "@/components/OddsChart";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";

interface EventPageProps {
  params: { id: string };
}

// Refresh intervals
const LIVE_REFRESH_INTERVAL = 60000; // 60 seconds for live games (matches backend polling)
const SCHEDULED_REFRESH_INTERVAL = 120000; // 2 minutes for scheduled games

export default function EventPage({ params }: EventPageProps) {
  const eventId = parseInt(params.id, 10);
  const [countdown, setCountdown] = useState<number>(0);
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

  // Countdown timer effect
  useEffect(() => {
    const interval = setInterval(() => {
      const elapsed = Date.now() - lastRefresh;
      const remaining = Math.max(0, refreshInterval - elapsed);
      setCountdown(Math.ceil(remaining / 1000));
    }, 100);

    return () => clearInterval(interval);
  }, [lastRefresh, refreshInterval]);

  // Fetch odds history
  const {
    data: historyData,
    error: historyError,
    isLoading: historyLoading,
  } = useSWR(
    event ? ["history", eventId] : null,
    () => fetchEventHistory(eventId, 48),
    { refreshInterval: 60000 } // Refresh every minute
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
          <span className="text-gray-400">•</span>
          <span className="font-mono tabular-nums w-6 text-right">{countdown}s</span>
        </div>
      </div>

      {/* Event Header */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <div className="flex items-center gap-3 mb-4">
          {event.sport && (
            <span className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-0.5 rounded uppercase">
              {event.sport.replace(/_/g, " ")}
            </span>
          )}
          {isLive && (
            <span className="text-xs font-bold text-red-600 bg-red-50 px-2 py-0.5 rounded animate-pulse">
              LIVE
            </span>
          )}
          <span className="text-sm text-gray-500">
            {formatGameTime(event.commence_time)}
          </span>
        </div>

        {/* Teams with large probabilities */}
        <div className="space-y-6">
          {/* Home Team */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className={`w-3 h-3 rounded-full ${
                  homeFavorite ? "bg-green-500" : "bg-gray-300"
                }`}
              />
              <div>
                <h2 className="text-2xl font-bold text-gray-900">
                  {event.home_team}
                </h2>
                <p className="text-sm text-gray-500">Home</p>
              </div>
              {isLive && event.home_score !== null && (
                <span className="text-4xl font-bold text-gray-900 ml-4">
                  {event.home_score}
                </span>
              )}
            </div>
            <div className="text-right">
              <span
                className={`text-4xl font-bold ${
                  homeFavorite ? "text-green-600" : "text-gray-500"
                }`}
              >
                {formatProbability(homeProb)}
              </span>
            </div>
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
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className={`w-3 h-3 rounded-full ${
                  !homeFavorite ? "bg-blue-500" : "bg-gray-300"
                }`}
              />
              <div>
                <h2 className="text-2xl font-bold text-gray-900">
                  {event.away_team}
                </h2>
                <p className="text-sm text-gray-500">Away</p>
              </div>
              {isLive && event.away_score !== null && (
                <span className="text-4xl font-bold text-gray-900 ml-4">
                  {event.away_score}
                </span>
              )}
            </div>
            <div className="text-right">
              <span
                className={`text-4xl font-bold ${
                  !homeFavorite ? "text-blue-600" : "text-gray-500"
                }`}
              >
                {formatProbability(awayProb)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Additional Odds Info */}
      {odds && (odds.spread !== null || odds.over_under !== null || odds.projected_home_score !== null) && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            Betting Lines
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {odds.spread !== null && (
              <div className="text-center p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-500 mb-1">Spread</p>
                <p className="text-xl font-bold text-gray-900">
                  {odds.spread > 0 ? `+${odds.spread}` : odds.spread}
                </p>
              </div>
            )}
            {odds.over_under !== null && (
              <div className="text-center p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-500 mb-1">Over/Under</p>
                <p className="text-xl font-bold text-gray-900">
                  {odds.over_under}
                </p>
              </div>
            )}
            {odds.projected_home_score !== null && odds.projected_away_score !== null && (
              <div className="text-center p-4 bg-gray-50 rounded-lg col-span-2">
                <p className="text-sm text-gray-500 mb-1">Projected Score</p>
                <p className="text-xl font-bold text-gray-900">
                  {Math.round(odds.projected_home_score)} - {Math.round(odds.projected_away_score)}
                </p>
              </div>
            )}
          </div>
          {odds.bookmaker && (
            <p className="text-xs text-gray-400 mt-4 text-center">
              Odds from {odds.bookmaker} • Updated {new Date(odds.captured_at).toLocaleTimeString()}
            </p>
          )}
        </div>
      )}

      {/* Odds History Chart */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Probability History (48 hours)
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
