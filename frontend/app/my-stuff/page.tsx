"use client";

import { useMemo } from "react";
import Link from "next/link";
import useSWR from "swr";
import { useAuthContext } from "@/components/AuthProvider";
import { fetchFeed } from "@/lib/api";
import type { FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";
import FeedCard from "@/components/FeedCard";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import { getCategoryForLeague } from "@/lib/sportCategories";
import { usePinnedEvents, usePinnedFutures } from "@/hooks";
import { fetchEventsByIds, fetchFuturesByIds } from "@/lib/api";
import type { Event, FuturesMarketDetailResponse } from "@/lib/types";
import EventCard from "@/components/EventCard";
import FuturesCard from "@/components/FuturesCard";

export default function MyStuffPage() {
  const { isAuthenticated, isLoading: authLoading, signInWithGoogle } = useAuthContext();

  // State A: Not authenticated
  if (!authLoading && !isAuthenticated) {
    return <SignInPrompt onSignIn={signInWithGoogle} />;
  }

  // Auth is still loading — show skeleton
  if (authLoading) {
    return <SkeletonGrid count={4} />;
  }

  // State B & C: Authenticated — render the feed
  return <MyTeamsFeed />;
}

// ---------------------------------------------------------------------------
// Sign-in prompt (State A)
// ---------------------------------------------------------------------------

function SignInPrompt({ onSignIn }: { onSignIn: () => Promise<void> }) {
  return (
    <div className="max-w-lg mx-auto">
      <div className="text-center py-16 px-4">
        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-surface-elevated flex items-center justify-center">
          <span className="text-2xl">&#9917;</span>
        </div>
        <h2 className="text-lg font-semibold text-text-primary mb-2">
          See your teams in one place
        </h2>
        <p className="text-sm text-text-secondary mb-6 max-w-xs mx-auto">
          Sign in and follow your favorite teams to track their games and championship odds.
        </p>
        <button
          onClick={onSignIn}
          className="px-6 py-2.5 bg-text-primary text-surface-deep rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Sign in with Google
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Team-filtered feed (State B + C)
// ---------------------------------------------------------------------------

function MyTeamsFeed() {
  // Pinned items
  const { pinnedIds, togglePin, isMaxReached } = usePinnedEvents();
  const {
    pinnedIds: pinnedFuturesIds,
    togglePin: toggleFuturesPin,
    isMaxReached: isFuturesMaxReached,
  } = usePinnedFutures();

  // Fetch team-only feed
  const {
    data: feedData,
    error: feedError,
    isLoading: feedLoading,
    mutate: refreshFeed,
  } = useSWR(
    "my-teams-feed",
    () => fetchFeed({ limit: 100, my_teams_only: true }),
    { refreshInterval: 15000 },
  );

  // State B check (must be after all hooks)
  const teamCount = feedData?.personalization?.team_count ?? null;

  // Pinned events from feed data
  const feedEventIds = useMemo(() => {
    if (!feedData) return new Set<number>();
    return new Set(
      feedData.items
        .filter(i => i.type === "event")
        .map(i => (i.data as FeedEventData).id)
    );
  }, [feedData]);

  const missingPinnedIds = useMemo(() => {
    return pinnedIds.filter(id => !feedEventIds.has(id));
  }, [feedEventIds, pinnedIds]);

  const { data: fetchedPinnedEvents } = useSWR(
    missingPinnedIds.length > 0 ? ["my-stuff-pinned-events", ...missingPinnedIds] : null,
    () => fetchEventsByIds(missingPinnedIds),
  );

  const pinnedEvents = useMemo(() => {
    const feedEventMap = new Map<number, Event>();
    if (feedData) {
      for (const item of feedData.items) {
        if (item.type === "event") {
          const d = item.data as FeedEventData;
          feedEventMap.set(d.id, {
            id: d.id,
            external_id: d.external_id,
            sport: d.sport,
            home_team: d.home_team,
            away_team: d.away_team,
            commence_time: d.commence_time,
            status: d.status,
            home_score: d.home_score,
            away_score: d.away_score,
            current_odds: d.current_odds ? {
              home_probability: d.current_odds.home_probability,
              away_probability: d.current_odds.away_probability,
              bookmaker_count: d.current_odds.bookmaker_count,
              projected_home_score: null,
              projected_away_score: null,
            } : undefined,
            opening_odds: d.opening_odds ? {
              home_probability: d.opening_odds.home_probability,
              away_probability: d.opening_odds.away_probability ?? null,
              favorite: d.opening_odds.favorite ?? null,
            } : undefined,
          } as Event);
        }
      }
    }
    const fetchedMap = new Map((fetchedPinnedEvents ?? []).map(e => [e.id, e]));
    return pinnedIds
      .map(id => fetchedMap.get(id) ?? feedEventMap.get(id))
      .filter((e): e is Event => e !== undefined);
  }, [feedData, fetchedPinnedEvents, pinnedIds]);

  // Pinned futures
  const feedFuturesIds = useMemo(() => {
    if (!feedData) return new Set<number>();
    return new Set(
      feedData.items
        .filter(i => i.type === "futures")
        .map(i => (i.data as FeedFuturesData).id)
    );
  }, [feedData]);

  const missingPinnedFuturesIds = useMemo(() => {
    return pinnedFuturesIds.filter(id => !feedFuturesIds.has(id));
  }, [feedFuturesIds, pinnedFuturesIds]);

  const { data: fetchedPinnedFutures } = useSWR(
    missingPinnedFuturesIds.length > 0 ? ["my-stuff-pinned-futures", ...missingPinnedFuturesIds] : null,
    () => fetchFuturesByIds(missingPinnedFuturesIds),
  );

  const pinnedFutures = useMemo(() => {
    const fetchedMap = new Map((fetchedPinnedFutures ?? []).map(f => [f.id, f]));
    return pinnedFuturesIds
      .map(id => fetchedMap.get(id))
      .filter((f): f is FuturesMarketDetailResponse => f !== undefined);
  }, [fetchedPinnedFutures, pinnedFuturesIds]);

  // Group feed items into sections
  const feedSections = useMemo(() => {
    if (!feedData || feedData.items.length === 0) return [];

    const now = new Date();
    const threeHoursMs = 3 * 60 * 60 * 1000;

    const liveNow: FeedItem[] = [];
    const startingSoon: FeedItem[] = [];
    const topMarkets: FeedItem[] = [];
    const moreGames: FeedItem[] = [];

    for (const item of feedData.items) {
      if (item.type === "futures") {
        topMarkets.push(item);
      } else {
        const data = item.data as FeedEventData;
        if (data.status === "live") {
          liveNow.push(item);
        } else if (data.status === "scheduled") {
          const gameTime = new Date(data.commence_time);
          const untilMs = gameTime.getTime() - now.getTime();
          if (untilMs > 0 && untilMs <= threeHoursMs) {
            startingSoon.push(item);
          } else {
            moreGames.push(item);
          }
        } else {
          moreGames.push(item);
        }
      }
    }

    const sections: { key: string; emoji: string; title: string; accent: string; items: FeedItem[] }[] = [];
    if (liveNow.length > 0) sections.push({ key: "live", emoji: "\uD83D\uDD34", title: "Live Now", accent: "text-accent-live", items: liveNow });
    if (startingSoon.length > 0) sections.push({ key: "soon", emoji: "\u23F0", title: "Starting Soon", accent: "text-text-secondary", items: startingSoon });
    if (topMarkets.length > 0) sections.push({ key: "markets", emoji: "\uD83D\uDCCA", title: "Top Markets", accent: "text-accent-futures", items: topMarkets });
    if (moreGames.length > 0) sections.push({ key: "more", emoji: "\uD83C\uDFDF\uFE0F", title: "More Games", accent: "text-text-secondary", items: moreGames });

    return sections;
  }, [feedData]);

  // State B: Authenticated but no teams followed
  if (feedData && teamCount === 0) {
    return <OnboardingPrompt />;
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text-primary">My Teams</h1>
        <Link
          href="/preferences"
          className="text-xs text-accent-brand font-medium hover:opacity-80 transition-opacity"
        >
          Edit
        </Link>
      </div>

      {/* Error */}
      {feedError && (
        <ErrorMessage
          message={feedError.message}
          onRetry={() => refreshFeed()}
        />
      )}

      {/* Loading */}
      {feedLoading && !feedData && <SkeletonGrid count={4} />}

      {/* Content */}
      {feedData && (
        <>
          {feedData.items.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-sm text-text-secondary mb-1">
                No games or markets right now for your teams
              </p>
              <p className="text-xs text-text-muted">
                Check back when your teams are playing
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Pinned Section */}
              {(pinnedEvents.length > 0 || pinnedFutures.length > 0) && (
                <section>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-sm">&#128204;</span>
                    <h2 className="text-sm font-semibold text-text-primary">
                      Pinned
                    </h2>
                    <span className="text-micro text-text-muted">
                      {pinnedEvents.length + pinnedFutures.length}
                    </span>
                  </div>
                  <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))" }}>
                    {pinnedEvents.map((event, index) => (
                      <EventCard
                        key={`pinned-${event.id}`}
                        event={event}
                        showSport={true}
                        sourceSection="my_stuff"
                        positionIndex={index}
                        highlightLabel={event.highlight?.label}
                        isPinned={true}
                        onPinToggle={togglePin}
                        pinDisabled={isMaxReached}
                      />
                    ))}
                    {pinnedFutures.map((market) => (
                      <FuturesCard
                        key={`pinned-futures-${market.id}`}
                        market={market}
                        showSport={true}
                        isPinned={true}
                        onPinToggle={toggleFuturesPin}
                        pinDisabled={isFuturesMaxReached}
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* Grouped feed sections */}
              {feedSections.map((section) => (
                <section key={section.key}>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-sm">{section.emoji}</span>
                    <h2 className={`text-sm font-semibold ${section.accent}`}>
                      {section.title}
                    </h2>
                    <span className="text-[11px] text-text-muted bg-surface-elevated px-1.5 py-0.5 rounded-full font-medium">
                      {section.items.length}
                    </span>
                  </div>
                  <div
                    className="grid gap-3"
                    style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))" }}
                  >
                    {section.items.map((item) => {
                      const key = item.type === "event"
                        ? `my-event-${(item.data as FeedEventData).id}`
                        : `my-futures-${(item.data as FeedFuturesData).id}`;
                      const category = item.type === "event"
                        ? getCategoryForLeague((item.data as FeedEventData).sport ?? "")?.key ?? "other"
                        : (item.data as FeedFuturesData).llm_sport_category ?? "other";
                      return (
                        <FeedCard
                          key={key}
                          item={item}
                          category={category}
                        />
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Onboarding prompt (State B)
// ---------------------------------------------------------------------------

function OnboardingPrompt() {
  return (
    <div className="max-w-lg mx-auto">
      <h1 className="text-xl font-bold text-text-primary mb-6">My Teams</h1>
      <div className="text-center py-12 px-4">
        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-surface-elevated flex items-center justify-center">
          <span className="text-2xl">&#127942;</span>
        </div>
        <h2 className="text-lg font-semibold text-text-primary mb-2">
          Follow some teams to get started
        </h2>
        <p className="text-sm text-text-secondary mb-6 max-w-xs mx-auto">
          Tell us your favorite teams and we&apos;ll show their games and championship odds here.
        </p>
        <Link
          href="/onboarding"
          className="inline-block px-6 py-2.5 bg-text-primary text-surface-deep rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Set up your teams
        </Link>
      </div>
    </div>
  );
}
