"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { fetchEvent, fetchEventHistory, fetchGameMarkets, fetchTeamProgression, formatProbability } from "@/lib/api";
import type { TeamProgressionResponse } from "@/lib/types";
const ChartSkeleton = () => <div className="animate-pulse h-48 bg-surface-card rounded-xl" />;
const OddsChart = dynamic(() => import("@/components/OddsChart"), { ssr: false, loading: ChartSkeleton });
const ScoreDifferentialChart = dynamic(() => import("@/components/ScoreDifferentialChart"), { ssr: false, loading: ChartSkeleton });
const BookmakerTable = dynamic(() => import("@/components/BookmakerTable"), { ssr: false });
const RelatedFutures = dynamic(() => import("@/components/RelatedFutures"), { ssr: false });
const GamePlayCard = dynamic(() => import("@/components/GamePlayCard"), { ssr: false });
const SeriesProbability = dynamic(() => import("@/components/SeriesProbability"), { ssr: false });
const TotalPointsSpectrum = dynamic(() => import("@/components/TotalPointsSpectrum"), { ssr: false });
const PlayerPropsDashboard = dynamic(() => import("@/components/PlayerPropsDashboard"), { ssr: false, loading: ChartSkeleton });
// UX-P098: the rail LEADS the props body, so it is a static import — a dynamic
// one would paint a skeleton in the one slot the page is supposed to answer first.
import PropDivergenceRail from "@/components/PropDivergenceRail";
const SpecialEventMarkets = dynamic(() => import("@/components/SpecialEventMarkets"), { ssr: false });
const MarketMapSection = dynamic(() => import("@/components/MarketMapSection"), { ssr: false, loading: ChartSkeleton });
// UX-P152: the tournament's sections OF this page. Dynamic and below the fold —
// 94 events on the whole site render it and none of them should pay for it in
// the initial bundle.
const TournamentExtensions = dynamic(() => import("@/components/event/TournamentExtensions"), { ssr: false });
// L2-118 Phase 1: the archetype-agnostic props body (SCRIPT / DIVERGENCE / WHAT HIT).
const PropsSection = dynamic(() => import("@/components/event/PropsSection"), { ssr: false });
import type { PropMark } from "@/components/event/PropsSection";
import { indexPropRowsByScriptKey, verifyScriptGrade } from "@/lib/propGrade";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import SectionErrorBoundary from "@/components/SectionErrorBoundary";
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
import { formatLiveClockLabel } from "@/lib/gameTimeLabel";
import type { ActiveChartPoint } from "@/lib/types";
import TeamNameLink from "@/components/TeamNameLink";
import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";
import { SignalBars } from "@/components/discover/shared";
import { confidenceFromSources } from "@/lib/confidence";
import {
  SPORT_KEY_TO_LEAGUE_PATH,
  hasAnyWinProbData,
  formatCountdown,
  resolveProbability,
  computeSharedChartDomain,
  computeRealStartTime,
  computeLastChartPoint,
} from "@/lib/eventKeyStats";

interface EventPageProps {
  params: { id: string };
}

const LIVE_REFRESH_INTERVAL = 32000; // Match backend LIVE_POLL_INTERVAL (32s)
const SCHEDULED_REFRESH_INTERVAL = 120000;

export default function EventPage({ params }: EventPageProps) {
  const eventId = parseInt(params.id, 10);
  const searchParams = useSearchParams();
  const sharedSource = searchParams.get("utm_source");
  const sharedMedium = searchParams.get("utm_medium") || undefined;
  const sharedCampaign = searchParams.get("utm_campaign") || undefined;
  const isSharedLink = sharedSource === "share";
  const [countdown, setCountdown] = useState<number>(0);
  const [gameCountdown, setGameCountdown] = useState<string>("");
  const [lastRefresh, setLastRefresh] = useState<number>(Date.now());
  const hasTrackedDetailView = useRef(false);
  const hasTrackedSharedOpen = useRef(false);
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

  // UX-P051 (#1710) — which of ESPN's two clock fields the phase badge may
  // believe. `espn.period` is ESPN's status detail, and while ESPN still has the
  // game as scheduled that detail is a sentence ("Mon, August 10th at 8:00 PM
  // EDT") shipped with `game_clock: "0.0"` — both untrustworthy together.
  const liveClockLabel = formatLiveClockLabel(event?.espn?.period, event?.espn?.game_clock, " · ");

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
    if (event && isSharedLink && !hasTrackedSharedOpen.current) {
      hasTrackedSharedOpen.current = true;
      track("shared_link_open", {
        content_type: "event",
        item_id: event.id,
        source: sharedSource,
        medium: sharedMedium,
        campaign: sharedCampaign,
      });
    }
  }, [event, isSharedLink, sharedCampaign, sharedMedium, sharedSource, track]);

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
    ["history", eventId],
    () => fetchEventHistory(eventId, 48),
    { refreshInterval: isLive ? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL }
  );

  // Game-level markets (totals spectrum, player props)
  const { data: gameMarkets } = useSWR(
    ["game-markets", eventId],
    () => fetchGameMarkets(eventId),
    { refreshInterval: isLive ? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL }
  );

  // Team championship progression (playoff path from grid data — always available for both teams)
  const { data: teamProgression } = useSWR<TeamProgressionResponse>(
    ["team-progression", eventId],
    () => fetchTeamProgression(eventId),
    { revalidateOnFocus: false, dedupingInterval: 300000 }
  );

  // Compute real game start time from livescores data (see eventKeyStats.ts)
  const realStartTime = useMemo(
    () => computeRealStartTime(event?.commence_time, historyData),
    [event?.commence_time, historyData?.score_history, historyData?.espn_history, historyData?.win_prob_history],
  );

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

  // Shared chart domain (see eventKeyStats.ts)
  const sharedChartDomain = useMemo(
    () => computeSharedChartDomain(historyData, chartTimeRange, event?.status, event?.commence_time, event?.sport || undefined),
    [historyData, chartTimeRange, event?.commence_time, event?.status, event?.sport],
  );

  // Most recent chart point for GamePlayCard (see eventKeyStats.ts)
  const lastChartPoint = useMemo<ActiveChartPoint | null>(
    () => computeLastChartPoint(historyData, event?.home_score, event?.away_score),
    [historyData, event?.home_score, event?.away_score],
  );

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

  // Resolve display probability based on game status (see eventKeyStats.ts)
  const {
    homeProb,
    awayProb,
    probSourceLabel,
    openingHomeProb,
    openingAwayProb,
    // #2085 — the whole percents to PRINT for each pair, decided together at
    // the one place that knows which source each pair came from.
    homePct,
    awayPct,
    openingHomePct,
    openingAwayPct,
  } = resolveProbability(event, historyData, lastChartPoint, isLive, isFinished);

  // #490: hero confidence signal (1-3 bars), computed client-side from the win-
  // prob sources already on the event + whether the line moved off open. Mirrors
  // the feed-card backend formula (frontend/lib/confidence.ts).
  const heroConfidence = confidenceFromSources({
    sourceCount: event.win_probability_sources
      ? Object.keys(event.win_probability_sources).length
      : 0,
    hasMovement:
      homeProb !== null &&
      openingHomeProb !== null &&
      Math.abs(homeProb - openingHomeProb) > 0.001,
  });

  // L2-112 Item 1: settled events get a winner treatment (final score + winner
  // chip), NOT a stale pregame percentage. Mirrors the futures settled-hero rule
  // (FuturesHero.tsx) — the probability journey stays in the chart below.
  // Winner is derived from the final score, not the pregame favorite.
  const settledWinnerName =
    isFinished && bestHomeScore !== null && bestAwayScore !== null && bestHomeScore !== bestAwayScore
      ? (bestHomeScore > bestAwayScore
          ? (event.home_team.split(" ").pop() || event.home_team)
          : (event.away_team.split(" ").pop() || event.away_team))
      : null;

  // L2-131 Item 1: the settled hero gains the pregame mark — the winner's
  // pre-game win probability ("were 35% pregame"). This is what makes an upset
  // read surprising at a glance. Data = the opening blend (opening_odds).
  const settledWinnerPregameProb =
    settledWinnerName !== null && openingHomeProb !== null && openingAwayProb !== null
      ? (bestHomeScore! > bestAwayScore! ? openingHomeProb : openingAwayProb)
      : null;
  const settledWinnerWasUnderdog =
    settledWinnerPregameProb !== null && settledWinnerPregameProb < 0.4;

  // Calculate countdown progress percentage
  const countdownProgress = ((refreshInterval / 1000 - countdown) / (refreshInterval / 1000)) * 100;

  // L2-112 Item 4: the Score Differential card must hide when there is no
  // projected OR actual score data — otherwise ScoreDifferentialChart returns
  // null (or its "Score data is not available" message) inside a card shell,
  // leaving an empty heading. Mirror the child's real data requirement
  // (hasProjectedScoreData || hasActualScoreData) at the parent gate.
  //
  // L2-157 Item 4 (the 15165209 exhibit): "Score Differential" is an IN-GAME
  // concept — actual score divergence over time. Pregame it renders as empty
  // chrome (a bare header over a flat 0-0 ESPN snapshot or a projected-spread
  // line masquerading as innings), which is worse than no chrome (the
  // nothing>unhelpful ruling). Suppress it entirely until the game is in-game
  // or later; the pregame odds-movement story lives in the Win Probability
  // timeline above (time x-axis, with its own clean "tracking will begin" state).
  const hasScoreDiffData = (effectivelyLive || isFinished || hasStarted) && !!historyData && (
    (historyData.history ?? []).some(
      (p) => p.projected_home_score != null && p.projected_away_score != null
    ) ||
    (historyData.score_history?.length ?? 0) > 0 ||
    (historyData.espn_history ?? []).some(
      (p) => p.home_score != null && p.away_score != null
    )
  );

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

      {isSharedLink && (
        <div className="rounded-card border border-accent-brand/20 bg-accent-brand/5 px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-text-primary">Shared from Discover</p>
            <p className="text-xs text-text-secondary">Explore the rest of today&apos;s probability stories.</p>
          </div>
          <Link
            href="/discover"
            className="inline-flex items-center justify-center rounded-lg bg-accent-brand px-3 py-2 text-sm font-semibold text-white hover:opacity-90 transition-opacity"
          >
            Open Discover
          </Link>
        </div>
      )}

      {/* Hero Section — v2 design */}
      {/* UX-P055: the hero is the answer, so it is the LAST thing worth losing —
          which is exactly why it gets its own boundary rather than sharing the
          route's. A hero that throws must not also cost the reader the chart,
          the props and the script. */}
      <SectionErrorBoundary label="The score and probability" resetKey={event}>
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
                {/* UX-P051 (#1710): the phase badge read both fields raw and
                    printed "Mon, August 10th at 8:00 PM EDT · 0.0" on a game
                    ESPN had not started.

                    ITS BOTH-REQUIRED RULE IS DELIBERATELY REPLACED, not
                    preserved — that is a stated behaviour change. `period &&
                    game_clock ?` was never a principle, and once a clock already
                    spelled inside the period is dropped as a duplicate, keeping
                    it would have made this badge read "LIVE" on every NBA/WNBA
                    game (measured: "10:00 - 1st Quarter" + "10:00"). It also
                    means a baseball game whose detail is "Top 2nd" with no clock
                    now says so instead of the generic word. */}
                {liveClockLabel || "LIVE"}
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

        {/* L2-157 (Alex ruling): internal ranking taxonomy pills
            ("competitive / regular season / Playoff Race / Major") are NOT user
            information and are stripped from the hero. The hero's real estate is
            game state — pregame start time + broadcast (above), LIVE the score
            (below). Tags are still computed backend-side for ranking. */}

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
                /* L2-163 Item 2a: once there's a real score it is the hero's
                   biggest element after the probability — Alex's 0-4 exhibit
                   rendered it nearly invisible at text-2xl. */
                <span className="text-4xl sm:text-[42px] font-black text-text-primary tabular-nums font-mono leading-none mt-1">
                  {bestHomeScore}
                </span>
              )}
            </div>

            {/* Center: Giant Probability (live/pregame) OR winner treatment (settled) */}
            <div className="flex flex-col items-center px-2 sm:px-4 flex-shrink-0">
              {isFinished ? (
                /* Settled: winner name + chip, no big number (mirrors FuturesHero's
                   resolved rule). The score is shown under each team; the win-prob
                   journey stays in the chart below. */
                /* UX-P043 (#1649): the settled hero's stable hook. The browser
                   pack read `event-hero-probability` as "the hero rendered",
                   but that testid lives on the !isFinished branch only — by
                   design, since "settled means settled: heroes show winners".
                   In the evening the first game on /sports IS final, so the
                   pack failed 4/4 on a hero working exactly as intended. This
                   makes the settled treatment provable in its own right rather
                   than something the pack has to route around. */
                <div
                  className="flex flex-col items-center gap-1.5"
                  data-testid="event-hero-settled"
                  data-winner={settledWinnerName ?? ""}
                >
                  {settledWinnerName ? (
                    <>
                      <span className="text-base sm:text-lg font-semibold text-text-primary tracking-tight text-center">
                        {settledWinnerName}
                      </span>
                      <span className="text-[11px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-accent-live/15 text-accent-live">
                        Won
                      </span>
                      {settledWinnerPregameProb !== null && (
                        <span
                          className={`text-[11px] ${
                            settledWinnerWasUnderdog
                              ? "text-amber-600 font-semibold"
                              : "text-text-muted"
                          }`}
                        >
                          {settledWinnerWasUnderdog ? "Upset · " : ""}
                          were {Math.round(settledWinnerPregameProb * 100)}% pregame
                        </span>
                      )}
                    </>
                  ) : (
                    <span className="text-[11px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-text-muted/15 text-text-secondary">
                      {bestHomeScore !== null && bestAwayScore !== null ? "Final · Tied" : "Final"}
                    </span>
                  )}
                </div>
              ) : (
              // #2085: the two sides are ONE decision — see
              // `EventHeroProbabilityPair` and `resolveProbability`. This used
              // to be four spans rounding `homeProb` and `awayProb`
              // independently, which prints 101 whenever `home * 100` lands on
              // a half-percent (8.2% of scheduled/live events, measured).
              <EventHeroProbabilityPair
                homeProb={homeProb}
                awayProb={awayProb}
                homePct={homePct}
                awayPct={awayPct}
                homeColor={event.home_team_data?.primary_color}
                awayColor={event.away_team_data?.primary_color}
                probSourceLabel={probSourceLabel}
              />
              )}

              {/* Trend indicator — change since opening (live/pregame only) */}
              {!isFinished && openingHomeProb !== null && homeProb !== null && (() => {
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

              {/* Opening odds (faint) — live/pregame only */}
              {!isFinished && openingHomeProb !== null && (
                <div className="mt-1.5">
                  <span className="text-[11px] text-text-muted">
                    {/* #2085 — same pair, same rule. `opening_odds` derives its
                        away side as `1 - home` on the backend too, so this line
                        printed 101 for exactly the same reason the hero did. */}
                    Opened {formatProbability(openingHomeProb, { rendered: openingHomePct })} {"–"} {formatProbability(openingAwayProb, { rendered: openingAwayPct })}
                  </span>
                </div>
              )}

              {/* Source label — live/pregame only */}
              {!isFinished && probSourceLabel && (
                <div className="mt-1 flex items-center gap-1.5">
                  <span className="text-[11px] text-text-muted">
                    {probSourceLabel}
                  </span>
                  {heroConfidence && <SignalBars tier={heroConfidence.tier} />}
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
                /* L2-163 Item 2a: score is the hero's biggest element after the
                   probability once the game is underway. */
                <span className="text-4xl sm:text-[42px] font-black text-text-primary tabular-nums font-mono leading-none mt-1">
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

      </SectionErrorBoundary>

      {/* Win Probability Chart */}
      {/* UX-P055: per-section boundaries. The children below are deliberately
          NOT re-indented — a wrapper that reflows ~900 lines buries the one
          thing a reviewer needs to check, which is where each boundary opens
          and closes. `resetKey` is the fetched object, whose identity changes
          only on a refetch, so a section that failed on a bad payload retries
          when the next one lands instead of staying dead for the session. */}
      <SectionErrorBoundary label="The win probability chart" resetKey={historyData}>
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
            {/* L2-112 Item 1: chart-card "Final" removed — the hero phase badge +
                winner chip already mark the game final (killed the "Final … Final"
                dup Alex flagged). The fullscreen modal keeps its own label. */}
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
          ) : historyData?.history?.length === 0 && !hasAnyWinProbData(historyData) ? (
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

      </SectionErrorBoundary>

      {/* Source Comparison removed — not useful, sources already visible in OddsChart */}

      {/* Score Differential Chart — only when projected/actual score data exists (L2-112 Item 4) */}
      {hasScoreDiffData && (
        <SectionErrorBoundary label="The score differential chart" resetKey={historyData}>
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
        </SectionErrorBoundary>
      )}

      {/* Market Map cards — Margin Map + Total Map */}
      {gameMarkets && ((gameMarkets.spreads?.length ?? 0) > 0 || gameMarkets.totals.length > 0) && (
        <SectionErrorBoundary label="The market maps" resetKey={gameMarkets}>
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
          espnHistory={historyData?.espn_history as Array<{ period?: string; home_score?: number; away_score?: number; timestamp?: string }>}
        />
        </SectionErrorBoundary>
      )}

      {/* Game Markets — Player Props + Matchups + Special Markets */}
      {gameMarkets && (gameMarkets.player_props.length > 0 || (gameMarkets.matchups?.length ?? 0) > 0 || (gameMarkets.other?.length ?? 0) >= 3) && (
        <div className="space-y-3">

          {/* UX-P055: #1722's actual crash site. This is the one boundary that
              is not speculative — an unpriced `other` row here took the whole
              route down on 2026-08-10, and 7 of 8 sampled settled MLB events
              carry 55-73 rows of that shape. */}
          {gameMarkets.player_props.length > 0 && (
            <>
            {/* UX-P098 (UX-AMBITION-1 slice 1) — THE DIVERGENCE leads.
                Alex's V1: the pregame page opens with the five questions that
                are actually live, not the whole prop set. On a real MLB payload
                that set is FORTY props; leading with it is the wall this
                replaces. The full set is one click away, below. */}
            <SectionErrorBoundary label="What's moving" resetKey={gameMarkets}>
            <PropDivergenceRail
              playerProps={gameMarkets.player_props}
              status={event.status}
            />
            </SectionErrorBoundary>

            <SectionErrorBoundary label="Player props" resetKey={gameMarkets}>
            <details className="group bg-surface-card rounded-card shadow-card overflow-hidden">
              <summary className="cursor-pointer select-none px-4 sm:px-5 py-3 text-[13px] font-semibold text-text-primary marker:content-none">
                All {gameMarkets.player_props.length} props
                <span className="ml-1.5 text-[11px] font-normal text-text-muted group-open:hidden">
                  show
                </span>
                <span className="ml-1.5 text-[11px] font-normal text-text-muted hidden group-open:inline">
                  hide
                </span>
              </summary>
              <PlayerPropsDashboard
                data={gameMarkets}
                eventStatus={event.status}
                homeTeam={event.home_team}
                awayTeam={event.away_team}
                homeColor={event.home_team_data?.primary_color || undefined}
                awayColor={event.away_team_data?.primary_color || undefined}
                boxScore={event.box_score_data}
              />
            </details>
            </SectionErrorBoundary>
            </>
          )}

          {/* Matchups — H2H and 3-ball markets (golf) */}
          {(gameMarkets.matchups?.length ?? 0) > 0 && (
            <SectionErrorBoundary label="Matchups" resetKey={gameMarkets}>
            <div className="bg-surface-card rounded-card shadow-card overflow-hidden">
              <div className="px-4 sm:px-5 py-3 border-b border-surface-border/30">
                <h3 className="text-[13px] font-semibold text-text-primary">Matchups</h3>
              </div>
              <div className="divide-y divide-surface-border/30">
                {gameMarkets.matchups!.map((matchup, idx) => (
                  <div key={idx} className="px-4 sm:px-5 py-3">
                    <div className="flex items-center justify-between mb-2.5">
                      <span className="text-xs font-medium text-text-secondary">{matchup.market_name}</span>
                      {/* L2-52: source-name badge removed (blend-only). */}
                    </div>
                    <div className="space-y-2">
                      {matchup.outcomes.map((outcome, oidx) => {
                        const pct = Math.round(outcome.probability * 100);
                        const isLeader = outcome.probability === Math.max(...matchup.outcomes.map(o => o.probability));
                        return (
                          <div key={oidx} className="flex items-center gap-3">
                            <span className={`text-xs font-medium w-[140px] sm:w-[180px] truncate ${isLeader ? "text-text-primary" : "text-text-secondary"}`}>
                              {outcome.name}
                            </span>
                            <div className="flex-1 h-5 bg-surface-elevated rounded-full overflow-hidden relative">
                              <div
                                className="h-full rounded-full transition-all duration-300"
                                style={{
                                  width: `${Math.max(pct, 2)}%`,
                                  backgroundColor: isLeader ? "#10B981" : "#94A3B8",
                                  opacity: isLeader ? 1 : 0.5,
                                }}
                              />
                            </div>
                            <span className={`text-xs font-bold tabular-nums w-10 text-right ${isLeader ? "text-text-primary" : "text-text-muted"}`}>
                              {pct}%
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            </SectionErrorBoundary>
          )}

          {/* Special Event Markets (auto-categorized other markets) */}
          {(gameMarkets.other?.length ?? 0) >= 3 && (
            <SectionErrorBoundary label="Special markets" resetKey={gameMarkets}>
              <SpecialEventMarkets data={gameMarkets} eventStatus={event.status} />
            </SectionErrorBoundary>
          )}
        </div>
      )}

      {/* THE SCRIPT → THE DIVERGENCE → WHAT HIT (L2-118 Phase 1, duel = first
          consumer). Now live on the #195 payload: gameMarkets.props_script is a
          first-class GameMarketsResponse field carrying the PropMark contract.
          The section self-gates on an empty array; PropsSection returns null when
          items is empty. Forward-only marks render honest "pending" chips. */}
      {(() => {
        const propsScript = gameMarkets?.props_script;
        if (!Array.isArray(propsScript) || propsScript.length === 0) return null;
        // #1650: hold the WHAT HIT row to the same authority as the Player
        // Props card above it, using the raw typed rows on this same payload.
        const rawPropRowsByKey = indexPropRowsByScriptKey(gameMarkets?.player_props);
        return (
          <SectionErrorBoundary label="The script" resetKey={gameMarkets}>
          <PropsSection
            eventStatus={event.status}
            items={propsScript.map((p, i): PropMark => {
              const verified = verifyScriptGrade(p, rawPropRowsByKey);
              return {
                key: p.key ?? i,
                label: p.label,
                pregame_mark: p.pregame_mark ?? null,
                current: p.current ?? null,
                graded_result: verified.graded_result,
                graded_label: verified.graded_label,
              };
            })}
          />
          </SectionErrorBoundary>
        );
      })()}

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
          <SectionErrorBoundary label="The series picture" resetKey={event}>
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
          </SectionErrorBoundary>
        );
      })()}

      {/* TOURNAMENT EXTENSIONS (UX-P152) — the sections a tournament adds to an
          ORDINARY event page, below the graph, for an event that belongs to a
          container: each player's chance of reaching each later round, and the
          match's other questions.

          Alex, 2026-08-28: "I thought that tournaments were containers for
          related events." They are, and this is a section of the event page
          rather than a page of its own — UX-P149's separate
          /tournaments/{slug}/matches/{key} surface is deleted, and a US Open
          match card now routes here like any other game card.

          Renders nothing for every event that is not in a registered
          tournament, and makes no request for one whose sport key rules it out. */}
      <SectionErrorBoundary label="Tournament" resetKey={eventId}>
        <TournamentExtensions eventId={eventId} sportKey={event.sport} />
      </SectionErrorBoundary>

      {/* Related Futures — bigger picture context (below charts) */}
      <SectionErrorBoundary label="Related futures" resetKey={eventId}>
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
      </SectionErrorBoundary>

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
          <SectionErrorBoundary label="Related content" resetKey={event.id}>
            <RelatedByTag
              tags={[`sport:${cat.key}`]}
              excludeId={event.id}
              excludeType="event"
              limit={4}
              title={`More ${cat.name}`}
            />
          </SectionErrorBoundary>
        ) : null;
      })()}

      {/* Fullscreen Chart Modal */}
      {chartFullscreen && (
        <div className="fixed inset-0 z-50 bg-surface-card flex flex-col">
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
