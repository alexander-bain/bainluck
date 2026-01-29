"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetchEvent, fetchEventHistory, formatProbability } from "@/lib/api";
import ProbabilityBar from "@/components/ProbabilityBar";
import OddsChart from "@/components/OddsChart";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import { getLeagueDisplay } from "@/lib/sportCategories";

interface EventPageProps {
  params: { id: string };
}

const LIVE_REFRESH_INTERVAL = 60000;
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
          Back to events
        </Link>

        {/* Freshness indicator */}
        <div className="flex items-center gap-2 text-micro text-slate">
          <div className="flex items-center gap-1.5">
            {isLive && (
              <span className="w-2 h-2 rounded-full bg-emerald animate-pulse-live" />
            )}
            <span>Next update in</span>
          </div>
          <span className="font-mono tabular-nums">{countdown}s</span>
        </div>
      </div>

      {/* Hero Section */}
      <div className="bg-white rounded-card shadow-card p-6">
        {/* Sport badge */}
        {event.sport && (
          <span className="text-micro text-slate bg-mist px-2 py-0.5 rounded inline-block mb-4">
            {getLeagueDisplay(event.sport)}
          </span>
        )}

        {/* Game time */}
        <div className="text-center mb-6">
          {isLive ? (
            <div className="flex items-center justify-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald animate-pulse-live" />
              <span className="text-title-2 text-emerald">Live</span>
            </div>
          ) : (
            <>
              <div className="text-caption text-slate mb-1">
                {formatStartTime(event.commence_time)}
              </div>
              {gameCountdown && (
                <div className="text-display text-graphite">
                  {gameCountdown}
                </div>
              )}
            </>
          )}
        </div>

        {/* Teams with probabilities - hero layout */}
        <div className="space-y-4">
          {/* Home Team */}
          <div className="flex items-center justify-between">
            <div>
              <h2 className={`text-title-2 ${homeFavorite ? "text-graphite" : "text-slate"}`}>
                {event.home_team}
              </h2>
              {isLive && event.home_score !== null && (
                <span className="text-title-1 text-graphite">{event.home_score}</span>
              )}
            </div>
            <span
              className={`font-mono text-display tabular-nums ${
                homeFavorite ? "text-graphite" : "text-silver"
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
          <div className="flex items-center justify-between">
            <div>
              <h2 className={`text-title-2 ${!homeFavorite ? "text-graphite" : "text-slate"}`}>
                {event.away_team}
              </h2>
              {isLive && event.away_score !== null && (
                <span className="text-title-1 text-graphite">{event.away_score}</span>
              )}
            </div>
            <span
              className={`font-mono text-display tabular-nums ${
                !homeFavorite ? "text-graphite" : "text-silver"
              }`}
            >
              {formatProbability(awayProb)}
            </span>
          </div>
        </div>

        {/* Data freshness strip */}
        {odds?.captured_at && (
          <div className="mt-6 pt-4 border-t border-mist flex justify-between text-micro text-slate">
            <span>
              Updated {new Date(odds.captured_at).toLocaleTimeString("en-US", {
                hour: "numeric",
                minute: "2-digit",
              })}
            </span>
            {odds.bookmaker && (
              <span>Source: {odds.bookmaker}</span>
            )}
          </div>
        )}
      </div>

      {/* Projected Score (only on detail, not list per design brief) */}
      {odds && odds.projected_home_score !== null && odds.projected_away_score !== null && (
        <div className="bg-white rounded-card shadow-card p-6">
          <h3 className="text-caption-strong text-slate mb-4">Projected Final</h3>
          <div className="flex items-center justify-center gap-8">
            <div className="text-center">
              <div className="font-mono text-title-1 text-graphite">
                {Math.round(odds.projected_home_score)}
              </div>
              <div className="text-micro text-slate mt-1">
                {event.home_team.split(" ").pop()}
              </div>
            </div>
            <div className="text-title-2 text-silver">-</div>
            <div className="text-center">
              <div className="font-mono text-title-1 text-graphite">
                {Math.round(odds.projected_away_score)}
              </div>
              <div className="text-micro text-slate mt-1">
                {event.away_team.split(" ").pop()}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Betting Lines (only on detail per design brief) */}
      {odds && (odds.spread !== null || odds.over_under !== null) && (
        <div className="bg-white rounded-card shadow-card p-6">
          <h3 className="text-caption-strong text-slate mb-4">Lines</h3>
          <div className="grid grid-cols-2 gap-4">
            {odds.spread !== null && (
              <div className="text-center p-4 bg-snow rounded-lg">
                <p className="text-micro text-slate mb-1">Spread</p>
                <p className="font-mono text-title-2 text-graphite">
                  {odds.spread > 0 ? `+${odds.spread}` : odds.spread}
                </p>
              </div>
            )}
            {odds.over_under !== null && (
              <div className="text-center p-4 bg-snow rounded-lg">
                <p className="text-micro text-slate mb-1">Total</p>
                <p className="font-mono text-title-2 text-graphite">
                  {odds.over_under}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Trend Chart */}
      <div className="bg-white rounded-card shadow-card p-6">
        <h3 className="text-caption-strong text-slate mb-4">Last 24 Hours</h3>
        {historyLoading ? (
          <div className="h-48 flex items-center justify-center">
            <LoadingSpinner size="sm" />
          </div>
        ) : historyError ? (
          <div className="h-48 flex items-center justify-center text-caption text-slate">
            Unable to load history
          </div>
        ) : historyData?.history?.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-caption text-slate">
            Tracking will begin when odds are available
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
