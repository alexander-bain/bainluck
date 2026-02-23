"use client";

import { useState, useMemo, useCallback, useEffect } from "react";
import useSWR from "swr";
import { fetchSports, fetchEventsByIds, fetchFuturesByIds, fetchFeed } from "@/lib/api";
import type { Event, FuturesMarket, FuturesMarketDetailResponse, FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";
import EventCard from "@/components/EventCard";
import FuturesCard from "@/components/FuturesCard";
import FeedCard from "@/components/FeedCard";
import OnboardingBanner from "@/components/OnboardingBanner";
import SportFilter from "@/components/SportFilter";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import {
  SPORT_CATEGORIES,
  getCategoryForLeague,
  getCategoryForFutures,
  getLeagueDisplay,
  getLeagueTier,
} from "@/lib/sportCategories";
import {
  useAnalytics,
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
  usePinnedEvents,
  usePinnedFutures,
} from "@/hooks";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FeedLeagueGroup {
  leagueKey: string;
  leagueName: string;
  tier: 1 | 2 | 3;
  items: FeedItem[];
}

interface FeedSportGroup {
  categoryKey: string;
  categoryName: string;
  emoji: string;
  tier: 1 | 2 | 3;
  leagues: FeedLeagueGroup[];
  futuresItems: FeedItem[];
  totalEvents: number;
  totalFutures: number;
}

// ---------------------------------------------------------------------------
// Homepage
// ---------------------------------------------------------------------------

export default function HomePage() {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSport, setSelectedSport] = useState<string | null>(null);
  const [expandedSports, setExpandedSports] = useState<Set<string>>(new Set());
  const [expandedLeagues, setExpandedLeagues] = useState<Set<string>>(new Set());

  // Analytics
  const { trackSectionToggle } = useAnalytics();

  // Pinned events
  const { pinnedIds, isPinned, togglePin, isMaxReached } = usePinnedEvents();

  // Pinned futures
  const {
    pinnedIds: pinnedFuturesIds,
    isPinned: isFuturesPinned,
    togglePin: toggleFuturesPin,
    isMaxReached: isFuturesMaxReached
  } = usePinnedFutures();

  // Track page view
  usePageTracking({
    pageType: 'home',
    pageTitle: 'Bain Luck - Home',
  });

  useScrollDepth({ pageType: 'home' });
  useEngagementTime({ pageType: 'home' });

  // =========================================================================
  // Data fetching — 2 primary calls instead of 4
  // =========================================================================

  const {
    data: sportsData,
    error: sportsError,
    isLoading: sportsLoading,
  } = useSWR("sports", fetchSports);

  // The feed is now the single source of truth for events + futures ranking.
  // It includes personalization scoring, diversity enforcement, and highlight labels.
  const {
    data: feedData,
    error: feedError,
    isLoading: feedLoading,
    mutate: refreshFeed,
  } = useSWR(
    ["feed", selectedCategory, selectedSport],
    () => fetchFeed({
      limit: 500,
      sport: selectedSport ?? selectedCategory ?? undefined,
    }),
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
    // Merge: look in feed data first, then in separately fetched events
    const feedEventMap = new Map<number, Event>();
    if (feedData) {
      for (const item of feedData.items) {
        if (item.type === "event") {
          const d = item.data as FeedEventData;
          // Convert FeedEventData to a minimal Event shape for EventCard
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
  // Group feed items by sport category for sport sections
  // =========================================================================

  const sportGroups = useMemo((): FeedSportGroup[] => {
    if (!feedData) return [];

    const groups = new Map<string, FeedSportGroup>();

    const getOrCreateGroup = (categoryKey: string, categoryName: string, emoji: string, tier: 1 | 2 | 3): FeedSportGroup => {
      if (!groups.has(categoryKey)) {
        groups.set(categoryKey, {
          categoryKey,
          categoryName,
          emoji,
          tier,
          leagues: [],
          futuresItems: [],
          totalEvents: 0,
          totalFutures: 0,
        });
      }
      return groups.get(categoryKey)!;
    };

    for (const item of feedData.items) {
      if (item.type === "event") {
        const data = item.data as FeedEventData;
        const sportKey = data.sport;
        if (!sportKey) continue;

        const category = getCategoryForLeague(sportKey);
        const categoryKey = category?.key ?? "other";
        const group = getOrCreateGroup(
          categoryKey,
          category?.name ?? "Other",
          category?.emoji ?? "🏆",
          category?.tier ?? 3
        );

        group.totalEvents++;

        let league = group.leagues.find(l => l.leagueKey === sportKey);
        if (!league) {
          league = {
            leagueKey: sportKey,
            leagueName: getLeagueDisplay(sportKey),
            tier: getLeagueTier(sportKey),
            items: [],
          };
          group.leagues.push(league);
        }
        league.items.push(item);

      } else {
        // Futures
        const data = item.data as FeedFuturesData;
        const category = data.llm_sport_category
          ? SPORT_CATEGORIES.find(c => c.key === data.llm_sport_category || c.prefixes.some(p => (data.sport ?? "").startsWith(p)))
          : data.sport
          ? getCategoryForLeague(data.sport)
          : null;

        const categoryKey = category?.key ?? data.llm_sport_category ?? "other";
        const group = getOrCreateGroup(
          categoryKey,
          category?.name ?? (data.llm_sport_category
            ? data.llm_sport_category.charAt(0).toUpperCase() + data.llm_sport_category.slice(1)
            : "Other"),
          category?.emoji ?? "🏆",
          category?.tier ?? 3
        );

        group.futuresItems.push(item);
        group.totalFutures++;
      }
    }

    const groupsArray = Array.from(groups.values());

    // Sort leagues within each group by tier, then by name
    for (const group of groupsArray) {
      group.leagues.sort((a, b) => {
        if (a.tier !== b.tier) return a.tier - b.tier;
        return a.leagueName.localeCompare(b.leagueName);
      });
    }

    // Sort groups: by tier, then by total items
    return groupsArray.sort((a, b) => {
      if (a.tier !== b.tier) return a.tier - b.tier;
      return (b.totalEvents + b.totalFutures) - (a.totalEvents + a.totalFutures);
    });
  }, [feedData]);

  // =========================================================================
  // Auto-expand sports with live events
  // =========================================================================

  const [hasAutoExpanded, setHasAutoExpanded] = useState(false);
  useEffect(() => {
    if (hasAutoExpanded || sportGroups.length === 0) return;

    const sportsWithLive = new Set<string>();
    const leaguesWithLive = new Set<string>();

    for (const group of sportGroups) {
      for (const league of group.leagues) {
        if (league.items.some(item => (item.data as FeedEventData).status === "live")) {
          sportsWithLive.add(group.categoryKey);
          leaguesWithLive.add(league.leagueKey);
        }
      }
    }

    // If no live events, expand the top 2 sport groups by default
    if (sportsWithLive.size === 0 && sportGroups.length > 0) {
      const topSports = sportGroups.slice(0, 2).map(g => g.categoryKey);
      for (const key of topSports) {
        sportsWithLive.add(key);
        const group = sportGroups.find(g => g.categoryKey === key);
        if (group) {
          // Expand first league in each group
          for (const league of group.leagues.slice(0, 1)) {
            leaguesWithLive.add(league.leagueKey);
          }
        }
      }
    }

    if (sportsWithLive.size > 0) {
      setExpandedSports(sportsWithLive);
      setExpandedLeagues(leaguesWithLive);
    }
    setHasAutoExpanded(true);
  }, [sportGroups, hasAutoExpanded]);

  // =========================================================================
  // Toggle handlers
  // =========================================================================

  const toggleSportExpand = useCallback((categoryKey: string, categoryName: string, eventCount: number) => {
    setExpandedSports((prev) => {
      const next = new Set(prev);
      const isExpanding = !next.has(categoryKey);
      if (next.has(categoryKey)) next.delete(categoryKey);
      else next.add(categoryKey);
      trackSectionToggle(isExpanding ? 'expand' : 'collapse', 'sport_category', categoryName, categoryKey, eventCount);
      return next;
    });
  }, [trackSectionToggle]);

  const toggleLeagueExpand = useCallback((leagueKey: string, leagueName: string, eventCount: number) => {
    setExpandedLeagues((prev) => {
      const next = new Set(prev);
      const isExpanding = !next.has(leagueKey);
      if (next.has(leagueKey)) next.delete(leagueKey);
      else next.add(leagueKey);
      trackSectionToggle(isExpanding ? 'expand' : 'collapse', 'league', leagueName, leagueKey, eventCount);
      return next;
    });
  }, [trackSectionToggle]);

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

  const sports = sportsData?.sports ?? [];

  // =========================================================================
  // Render
  // =========================================================================

  return (
    <div className="space-y-5">
      {/* Filters */}
      <div className="sticky top-[53px] bg-surface-deep/95 backdrop-blur-sm py-3 -mx-3 px-3 md:-mx-6 md:px-6 z-40">
        <SportFilter
          sports={sports}
          selectedSport={selectedSport}
          selectedCategory={selectedCategory}
          onSelectSport={setSelectedSport}
          onSelectCategory={setSelectedCategory}
          loading={sportsLoading}
        />
      </div>

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
                {selectedSport || selectedCategory
                  ? "Try selecting a different sport"
                  : "Check back soon — we surface the best stuff automatically"}
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

              {/* Sport Category Sections — now powered by the personalized feed */}
              {sportGroups.map((sportGroup) => {
                const totalItems = sportGroup.totalEvents + sportGroup.totalFutures;
                const futuresKey = `${sportGroup.categoryKey}-futures`;
                const isFuturesExpanded = expandedLeagues.has(futuresKey);
                const liveCount = sportGroup.leagues.reduce(
                  (sum, league) => sum + league.items.filter(item =>
                    (item.data as FeedEventData).status === "live"
                  ).length, 0
                );
                const isSportExpanded = expandedSports.has(sportGroup.categoryKey);
                const isFlatLeague = sportGroup.leagues.length === 1 && sportGroup.totalFutures === 0;
                const isFuturesOnly = sportGroup.totalEvents === 0 && sportGroup.totalFutures > 0;

                return (
                  <section key={sportGroup.categoryKey}>
                    <button
                      onClick={() => toggleSportExpand(sportGroup.categoryKey, sportGroup.categoryName, totalItems)}
                      className="flex items-center gap-2 mb-3 w-full text-left group"
                    >
                      <span className="text-sm">{sportGroup.emoji}</span>
                      <h2 className="text-sm font-semibold text-text-primary">
                        {sportGroup.categoryName}
                      </h2>
                      <span className="text-micro text-text-muted bg-surface-elevated px-2 py-0.5 rounded">
                        {sportGroup.totalEvents > 0 && sportGroup.totalFutures > 0
                          ? `${sportGroup.totalEvents} + ${sportGroup.totalFutures} futures`
                          : sportGroup.totalFutures > 0
                          ? `${sportGroup.totalFutures} futures`
                          : sportGroup.totalEvents}
                      </span>
                      {liveCount > 0 && !isSportExpanded && (
                        <span className="text-micro-xs bg-accent-live/15 text-accent-live px-1.5 py-0.5 rounded font-semibold animate-pulse">
                          {liveCount} live
                        </span>
                      )}
                      <span className="ml-auto text-text-muted group-hover:text-text-secondary transition-colors">
                        {isSportExpanded ? (
                          <ChevronDown className="w-4 h-4" />
                        ) : (
                          <ChevronRight className="w-4 h-4" />
                        )}
                      </span>
                    </button>

                    {isSportExpanded && (
                      <div className="space-y-4">
                        {sportGroup.leagues.map((league) => {
                          const isExpanded = isFlatLeague || expandedLeagues.has(league.leagueKey);

                          return (
                            <div key={league.leagueKey}>
                              {!isFlatLeague && (
                                <button
                                  onClick={() => toggleLeagueExpand(league.leagueKey, league.leagueName, league.items.length)}
                                  className="flex items-center gap-2 mb-2 w-full text-left group"
                                >
                                  <span className="text-text-muted group-hover:text-text-secondary transition-colors">
                                    {isExpanded ? (
                                      <ChevronDown className="w-3.5 h-3.5" />
                                    ) : (
                                      <ChevronRight className="w-3.5 h-3.5" />
                                    )}
                                  </span>
                                  <h3 className="text-sm font-medium text-text-secondary">
                                    {league.leagueName}
                                  </h3>
                                  {league.tier === 1 && (
                                    <span className="text-micro-xs bg-accent-warning/15 text-accent-warning px-1 py-0.5 rounded">
                                      Major
                                    </span>
                                  )}
                                  <span className="text-micro text-text-muted">
                                    {league.items.length}
                                  </span>
                                </button>
                              )}

                              {/* Lazy rendering: only render cards when league is expanded */}
                              {isExpanded && (
                                <div
                                  className={`grid gap-3 ${isFlatLeague ? "" : "ml-5"}`}
                                  style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))" }}
                                >
                                  {league.items.map((item) => (
                                    <FeedCard
                                      key={`feed-event-${(item.data as FeedEventData).id}`}
                                      item={item}
                                    />
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        })}

                        {/* Futures section */}
                        {sportGroup.futuresItems.length > 0 && (() => {
                          const showFuturesDirectly = isFuturesOnly;
                          const futuresVisible = showFuturesDirectly || isFuturesExpanded;

                          return (
                            <div>
                              {!showFuturesDirectly && (
                                <button
                                  onClick={() => toggleLeagueExpand(futuresKey, "Futures", sportGroup.futuresItems.length)}
                                  className="flex items-center gap-2 mb-2 w-full text-left group"
                                >
                                  <span className="text-text-muted group-hover:text-text-secondary transition-colors">
                                    {isFuturesExpanded ? (
                                      <ChevronDown className="w-3.5 h-3.5" />
                                    ) : (
                                      <ChevronRight className="w-3.5 h-3.5" />
                                    )}
                                  </span>
                                  <h3 className="text-sm font-medium text-text-secondary">
                                    Futures
                                  </h3>
                                  <span className="text-micro-xs bg-accent-futures/15 text-accent-futures px-1 py-0.5 rounded">
                                    Outrights
                                  </span>
                                  <span className="text-micro text-text-muted">
                                    {sportGroup.futuresItems.length}
                                  </span>
                                </button>
                              )}

                              {futuresVisible && (
                                <div
                                  className={`grid gap-3 ${showFuturesDirectly ? "" : "ml-5"}`}
                                  style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))" }}
                                >
                                  {sportGroup.futuresItems.map((item) => (
                                    <FeedCard
                                      key={`feed-futures-${(item.data as FeedFuturesData).id}`}
                                      item={item}
                                    />
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        })()}
                      </div>
                    )}
                  </section>
                );
              })}
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

function ChevronDown({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  );
}

function ChevronRight({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}
