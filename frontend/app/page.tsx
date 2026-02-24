"use client";

import { useState, useMemo, useCallback, useRef } from "react";
import useSWR from "swr";
import { fetchEventsByIds, fetchFuturesByIds, fetchFeed } from "@/lib/api";
import { useAuthContext } from "@/components/AuthProvider";
import type { Event, FuturesMarketDetailResponse, FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";
import EventCard from "@/components/EventCard";
import FuturesCard from "@/components/FuturesCard";
import FeedCard from "@/components/FeedCard";
import OnboardingBanner from "@/components/OnboardingBanner";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import { getCategoryForLeague } from "@/lib/sportCategories";
import { useCategoryInterests, stepUp, stepDown } from "@/hooks/useCategoryInterests";
import {
  useAnalytics,
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
  usePinnedEvents,
  usePinnedFutures,
} from "@/hooks";

// ---------------------------------------------------------------------------
// Homepage — flat ranked feed
// ---------------------------------------------------------------------------

export default function HomePage() {
  // Analytics
  usePageTracking({ pageType: 'home', pageTitle: 'Bain Luck - Home' });
  useScrollDepth({ pageType: 'home' });
  useEngagementTime({ pageType: 'home' });

  // Auth state — used to key SWR so the feed re-fetches when auth loads
  const { user, isLoading: authLoading } = useAuthContext();

  // Pinned events
  const { pinnedIds, isPinned, togglePin, isMaxReached } = usePinnedEvents();

  // Pinned futures
  const {
    pinnedIds: pinnedFuturesIds,
    isPinned: isFuturesPinned,
    togglePin: toggleFuturesPin,
    isMaxReached: isFuturesMaxReached
  } = usePinnedFutures();

  // =========================================================================
  // Data fetching — single feed call
  // =========================================================================

  const {
    data: feedData,
    error: feedError,
    isLoading: feedLoading,
    mutate: refreshFeed,
  } = useSWR(
    // Don't fetch until auth state is resolved — avoids caching the anonymous
    // feed when the user is actually signed in (race condition).
    // Key includes user UID so SWR re-fetches when auth state changes.
    authLoading ? null : user ? ["feed", user.uid] : "feed-anon",
    () => fetchFeed({ limit: 200 }),
    { refreshInterval: 30000 }
  );

  // =========================================================================
  // Pinned items (still need individual fetches for items outside feed window)
  // =========================================================================

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
    missingPinnedIds.length > 0 ? ["pinned-events", ...missingPinnedIds] : null,
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
            sport_name: d.sport_name,
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
    missingPinnedFuturesIds.length > 0 ? ["pinned-futures", ...missingPinnedFuturesIds] : null,
    () => fetchFuturesByIds(missingPinnedFuturesIds),
  );

  const pinnedFutures = useMemo(() => {
    const fetchedMap = new Map((fetchedPinnedFutures ?? []).map(f => [f.id, f]));
    return pinnedFuturesIds
      .map(id => fetchedMap.get(id))
      .filter((f): f is FuturesMarketDetailResponse => f !== undefined);
  }, [fetchedPinnedFutures, pinnedFuturesIds]);

  // =========================================================================
  // Interest signals — thumbs up/down step through affinity levels
  // =========================================================================

  const { interests, setInterest } = useCategoryInterests();
  const [toast, setToast] = useState<string | null>(null);
  const toastTimeoutRef = useRef<NodeJS.Timeout>();

  const showToast = useCallback((message: string) => {
    setToast(message);
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    toastTimeoutRef.current = setTimeout(() => setToast(null), 2000);
  }, []);

  const handleThumbsUp = useCallback((category: string) => {
    const current = interests[category] ?? 0;
    const next = stepUp(current);
    if (next !== current) {
      setInterest(category, next);
      showToast(`Showing more ${category}`);
    }
  }, [interests, setInterest, showToast]);

  const handleThumbsDown = useCallback((category: string) => {
    const current = interests[category] ?? 0;
    const next = stepDown(current);
    if (next !== current) {
      setInterest(category, next);
      showToast(`Showing less ${category}`);
    }
  }, [interests, setInterest, showToast]);

  // =========================================================================
  // Summary stats
  // =========================================================================

  const feedStats = useMemo(() => {
    if (!feedData) return { events: 0, futures: 0, live: 0 };
    const events = feedData.items.filter(i => i.type === "event").length;
    const futures = feedData.items.filter(i => i.type === "futures").length;
    const live = feedData.items.filter(i =>
      i.type === "event" && (i.data as FeedEventData).status === "live"
    ).length;
    return { events, futures, live };
  }, [feedData]);

  // =========================================================================
  // Group feed items into visual sections
  // =========================================================================

  const feedSections = useMemo(() => {
    if (!feedData || feedData.items.length === 0) return [];

    const now = new Date();
    const threeHoursMs = 3 * 60 * 60 * 1000;

    const liveNow: FeedItem[] = [];
    const startingSoon: FeedItem[] = [];
    const justHappened: FeedItem[] = [];
    const topMarkets: FeedItem[] = [];
    const moreGames: FeedItem[] = [];

    for (const item of feedData.items) {
      if (item.type === "futures") {
        topMarkets.push(item);
      } else {
        const data = item.data as FeedEventData;
        if (data.status === "live") {
          liveNow.push(item);
        } else if (data.status === "completed" || data.status === "closed") {
          justHappened.push(item);
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
    if (justHappened.length > 0) sections.push({ key: "finished", emoji: "\uD83C\uDFC1", title: "Just Happened", accent: "text-text-secondary", items: justHappened });
    if (moreGames.length > 0) sections.push({ key: "more", emoji: "\uD83C\uDFDF\uFE0F", title: "More Games", accent: "text-text-secondary", items: moreGames });
    if (topMarkets.length > 0) sections.push({ key: "markets", emoji: "\uD83D\uDCCA", title: "Top Markets", accent: "text-accent-futures", items: topMarkets });

    return sections;
  }, [feedData]);

  // =========================================================================
  // Render
  // =========================================================================

  return (
    <div className="space-y-5">
      {/* Toast feedback */}
      {toast && (
        <div className="fixed bottom-24 md:bottom-8 left-1/2 -translate-x-1/2 z-50 px-4 py-2 bg-surface-card border border-surface-border rounded-xl shadow-lg text-xs font-medium text-text-primary animate-fade-in">
          {toast}
        </div>
      )}

      {/* Error State */}
      {feedError && (
        <ErrorMessage
          message={feedError.message}
          onRetry={() => refreshFeed()}
        />
      )}

      {/* Loading State */}
      {feedLoading && !feedData && <SkeletonGrid count={6} />}

      {/* Main Content */}
      {feedData && (
        <>
          {feedData.items.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-body text-text-secondary mb-2">
                Nothing interesting right now
              </p>
              <p className="text-caption text-text-muted">
                Check back soon — we surface the best stuff automatically
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Pinned Section */}
              {(pinnedEvents.length > 0 || pinnedFutures.length > 0) && (
                <section>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-sm">📌</span>
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
                        sourceSection="pinned"
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

              {/* Onboarding CTA */}
              <OnboardingBanner teamCount={feedData?.personalization?.team_count} />

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
                        ? `feed-event-${(item.data as FeedEventData).id}`
                        : `feed-futures-${(item.data as FeedFuturesData).id}`;
                      const category = item.type === "event"
                        ? getCategoryForLeague((item.data as FeedEventData).sport ?? "")?.key ?? "other"
                        : (item.data as FeedFuturesData).llm_sport_category ?? "other";
                      return (
                        <FeedCard
                          key={key}
                          item={item}
                          onThumbsUp={handleThumbsUp}
                          onThumbsDown={handleThumbsDown}
                          category={category}
                        />
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
          )}

          {feedData.items.length > 0 && (
            <p className="text-center text-micro text-text-muted pt-4">
              {feedStats.events > 0 && (
                <>{feedStats.events} event{feedStats.events !== 1 ? "s" : ""}</>
              )}
              {feedStats.events > 0 && feedStats.futures > 0 && " · "}
              {feedStats.futures > 0 && (
                <>{feedStats.futures} futures market{feedStats.futures !== 1 ? "s" : ""}</>
              )}
              {feedData.personalized && (
                <> · Personalized</>
              )}
            </p>
          )}
        </>
      )}
    </div>
  );
}
