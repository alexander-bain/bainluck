"use client";

import { useState, useMemo, useCallback, useEffect } from "react";
import useSWR from "swr";
import { fetchEvents, fetchSports, fetchFuturesMarkets, fetchEventsByIds, fetchFuturesByIds, fetchFeed } from "@/lib/api";
import type { Event, FuturesMarket, FeedItem } from "@/lib/types";
import EventCard from "@/components/EventCard";
import FuturesCard from "@/components/FuturesCard";
import FeedCard from "@/components/FeedCard";
import OnboardingBanner from "@/components/OnboardingBanner";
import SportFilter from "@/components/SportFilter";
import LoadingSpinner from "@/components/LoadingSpinner";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import {
  SPORT_CATEGORIES,
  getCategoryForLeague,
  getCategoryForFutures,
  getLeagueDisplay,
  getLeagueTier,
  isFeaturedEvent,
  calculateExcitementScore,
  groupBySubcategory,
  SUBCATEGORY_THRESHOLD,
} from "@/lib/sportCategories";
import {
  useAnalytics,
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
  usePinnedEvents,
  usePinnedFutures,
} from "@/hooks";

type DateFilter = "today" | "recent" | "upcoming";

const DATE_FILTER_OPTIONS: { value: DateFilter; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "recent", label: "Recent" },
  { value: "upcoming", label: "Upcoming" },
];

interface LeagueGroup {
  leagueKey: string;
  leagueName: string;
  tier: 1 | 2 | 3;
  events: Event[];
}

interface SportGroup {
  categoryKey: string;
  categoryName: string;
  emoji: string;
  tier: 1 | 2 | 3;
  leagues: LeagueGroup[];
  futures: FuturesMarket[];
  totalEvents: number;
  totalFutures: number;
}

export default function HomePage() {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSport, setSelectedSport] = useState<string | null>(null);
  const [dateFilter, setDateFilter] = useState<DateFilter>("today");
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

  const {
    data: sportsData,
    error: sportsError,
    isLoading: sportsLoading,
  } = useSWR("sports", fetchSports);

  const {
    data: eventsData,
    error: eventsError,
    isLoading: eventsLoading,
    mutate: refreshEvents,
  } = useSWR(
    ["events", selectedSport],
    () => fetchEvents({ sport: selectedSport ?? undefined, days: 7 }),
    { refreshInterval: 30000 }
  );

  const futuresStatus = dateFilter === "recent" ? "resolved" : "open";
  const {
    data: futuresData,
    error: futuresError,
    isLoading: futuresLoading,
  } = useSWR(
    ["futures", selectedSport, futuresStatus],
    () => fetchFuturesMarkets({ sport: selectedSport ?? undefined, status: futuresStatus }),
    { refreshInterval: 60000 }
  );

  // Unified feed
  const {
    data: feedData,
    isLoading: feedLoading,
  } = useSWR(
    ["feed", selectedCategory],
    () => fetchFeed({ limit: 15, sport: selectedCategory ?? undefined }),
    { refreshInterval: 30000 }
  );

  const getEventDateCategory = (commenceTime: string): "today" | "recent" | "upcoming" => {
    const eventDate = new Date(commenceTime);
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const recentStart = new Date(todayStart);
    recentStart.setDate(recentStart.getDate() - 7);
    const tomorrowStart = new Date(todayStart);
    tomorrowStart.setDate(tomorrowStart.getDate() + 1);

    if (eventDate >= todayStart && eventDate < tomorrowStart) return "today";
    else if (eventDate >= recentStart && eventDate < todayStart) return "recent";
    else if (eventDate >= tomorrowStart) return "upcoming";
    else return "recent";
  };

  const filteredEvents = useMemo(() => {
    let events = eventsData?.events ?? [];

    events = events.filter((e) =>
      e.current_odds?.home_probability != null && e.current_odds?.away_probability != null
    );

    if (selectedCategory && !selectedSport) {
      const category = SPORT_CATEGORIES.find((c) => c.key === selectedCategory);
      if (category) {
        events = events.filter((e) =>
          e.sport && category.prefixes.some((prefix) => e.sport!.startsWith(prefix))
        );
      } else if (selectedCategory === "other") {
        events = events.filter((e) =>
          e.sport && !getCategoryForLeague(e.sport)
        );
      }
    }

    events = events.filter((e) => {
      const dateCategory = getEventDateCategory(e.commence_time);
      if (dateFilter === "today") return dateCategory === "today";
      else if (dateFilter === "recent") return dateCategory === "recent";
      else return dateCategory === "upcoming";
    });

    if (dateFilter === "recent") {
      return events.sort((a, b) =>
        new Date(b.commence_time).getTime() - new Date(a.commence_time).getTime()
      );
    }
    return events.sort((a, b) =>
      new Date(a.commence_time).getTime() - new Date(b.commence_time).getTime()
    );
  }, [eventsData?.events, selectedCategory, selectedSport, dateFilter]);

  const getOutcomeNames = (market: FuturesMarket): string[] => {
    const outcomes = market.top_outcomes || market.outcomes || [];
    return outcomes.map((o) => o.name);
  };

  const filteredFutures = useMemo(() => {
    let markets = futuresData?.markets ?? [];

    if (selectedCategory && !selectedSport) {
      if (selectedCategory === "other") {
        markets = markets.filter(
          (m) => !getCategoryForFutures(m.sport, m.name, getOutcomeNames(m), m.llm_sport_category)
        );
      } else {
        markets = markets.filter((m) => {
          const category = getCategoryForFutures(m.sport, m.name, getOutcomeNames(m), m.llm_sport_category);
          return category?.key === selectedCategory;
        });
      }
    }

    return markets.sort((a, b) => (b.outcome_count || 0) - (a.outcome_count || 0));
  }, [futuresData?.markets, selectedCategory, selectedSport]);

  const featuredEvents = useMemo(() => {
    return filteredEvents
      .filter((e) => e.highlight?.should_feature || isFeaturedEvent(e))
      .sort((a, b) => {
        const scoreA = a.highlight?.score ?? calculateExcitementScore(a);
        const scoreB = b.highlight?.score ?? calculateExcitementScore(b);
        return scoreB - scoreA;
      })
      .slice(0, 6);
  }, [filteredEvents]);

  // Pinned events fetch
  const missingPinnedIds = useMemo(() => {
    const loadedIds = new Set((eventsData?.events ?? []).map(e => e.id));
    return pinnedIds.filter(id => !loadedIds.has(id));
  }, [eventsData?.events, pinnedIds]);

  const { data: fetchedPinnedEvents } = useSWR(
    missingPinnedIds.length > 0 ? ["pinned-events", ...missingPinnedIds] : null,
    () => fetchEventsByIds(missingPinnedIds),
  );

  const pinnedEvents = useMemo(() => {
    const allEvents = eventsData?.events ?? [];
    const fetchedMap = new Map((fetchedPinnedEvents ?? []).map(e => [e.id, e]));
    return pinnedIds
      .map(id => allEvents.find(e => e.id === id) ?? fetchedMap.get(id))
      .filter((e): e is Event => e !== undefined);
  }, [eventsData?.events, fetchedPinnedEvents, pinnedIds]);

  // Pinned futures fetch
  const missingPinnedFuturesIds = useMemo(() => {
    const loadedIds = new Set((futuresData?.markets ?? []).map(f => f.id));
    return pinnedFuturesIds.filter(id => !loadedIds.has(id));
  }, [futuresData?.markets, pinnedFuturesIds]);

  const { data: fetchedPinnedFutures } = useSWR(
    missingPinnedFuturesIds.length > 0 ? ["pinned-futures", ...missingPinnedFuturesIds] : null,
    () => fetchFuturesByIds(missingPinnedFuturesIds),
  );

  const pinnedFutures = useMemo(() => {
    const allFutures = futuresData?.markets ?? [];
    const fetchedMap = new Map((fetchedPinnedFutures ?? []).map(f => [f.id, f]));
    return pinnedFuturesIds
      .map(id => allFutures.find(f => f.id === id) ?? fetchedMap.get(id))
      .filter((f): f is FuturesMarket => f !== undefined);
  }, [futuresData?.markets, fetchedPinnedFutures, pinnedFuturesIds]);

  // Group events and futures by sport category, then by league
  const sportGroups = useMemo((): SportGroup[] => {
    const groups = new Map<string, SportGroup>();

    const getOrCreateGroup = (sportKey: string): SportGroup => {
      const category = getCategoryForLeague(sportKey);
      const categoryKey = category?.key ?? "other";

      if (!groups.has(categoryKey)) {
        groups.set(categoryKey, {
          categoryKey,
          categoryName: category?.name ?? "Other",
          emoji: category?.emoji ?? "🏆",
          tier: category?.tier ?? 3,
          leagues: [],
          futures: [],
          totalEvents: 0,
          totalFutures: 0,
        });
      }

      return groups.get(categoryKey)!;
    };

    for (const event of filteredEvents) {
      if (!event.sport) continue;
      const sportGroup = getOrCreateGroup(event.sport);
      sportGroup.totalEvents++;

      let leagueGroup = sportGroup.leagues.find((l) => l.leagueKey === event.sport);
      if (!leagueGroup) {
        leagueGroup = {
          leagueKey: event.sport,
          leagueName: getLeagueDisplay(event.sport),
          tier: getLeagueTier(event.sport),
          events: [],
        };
        sportGroup.leagues.push(leagueGroup);
      }
      leagueGroup.events.push(event);
    }

    for (const market of filteredFutures) {
      const category = getCategoryForFutures(market.sport, market.name, getOutcomeNames(market), market.llm_sport_category);
      const categoryKey = category?.key ?? "other";

      if (!groups.has(categoryKey)) {
        groups.set(categoryKey, {
          categoryKey,
          categoryName: category?.name ?? "Other",
          emoji: category?.emoji ?? "🏆",
          tier: category?.tier ?? 3,
          leagues: [],
          futures: [],
          totalEvents: 0,
          totalFutures: 0,
        });
      }

      const sportGroup = groups.get(categoryKey)!;
      sportGroup.futures.push(market);
      sportGroup.totalFutures++;
    }

    const groupsArray = Array.from(groups.values());
    for (const group of groupsArray) {
      group.leagues.sort((a, b) => {
        if (a.tier !== b.tier) return a.tier - b.tier;
        return a.leagueName.localeCompare(b.leagueName);
      });
      for (const league of group.leagues) {
        league.events.sort((a, b) =>
          new Date(a.commence_time).getTime() - new Date(b.commence_time).getTime()
        );
      }
    }

    return groupsArray.sort((a, b) => {
      if (a.tier !== b.tier) return a.tier - b.tier;
      return (b.totalEvents + b.totalFutures) - (a.totalEvents + a.totalFutures);
    });
  }, [filteredEvents, filteredFutures]);

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

  const [hasAutoExpanded, setHasAutoExpanded] = useState(true);
  useEffect(() => {
    if (hasAutoExpanded || sportGroups.length === 0) return;

    const sportsWithLive = new Set<string>();
    const leaguesWithLive = new Set<string>();

    for (const group of sportGroups) {
      for (const league of group.leagues) {
        if (league.events.some(e => e.status === "live")) {
          sportsWithLive.add(group.categoryKey);
          leaguesWithLive.add(league.leagueKey);
        }
      }
    }

    if (sportsWithLive.size > 0) {
      setExpandedSports(sportsWithLive);
      setExpandedLeagues(leaguesWithLive);
    }
    setHasAutoExpanded(true);
  }, [sportGroups, hasAutoExpanded]);

  const sports = sportsData?.sports ?? [];

  return (
    <div className="space-y-5">
      {/* Filters */}
      <div className="sticky top-[53px] bg-surface-deep/95 backdrop-blur-sm py-3 -mx-3 px-3 md:-mx-6 md:px-6 z-40">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <SportFilter
            sports={sports}
            selectedSport={selectedSport}
            selectedCategory={selectedCategory}
            onSelectSport={setSelectedSport}
            onSelectCategory={setSelectedCategory}
            loading={sportsLoading}
          />

          {/* Date filter pills */}
          <div className="flex items-center gap-1">
            {DATE_FILTER_OPTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => setDateFilter(option.value)}
                className={`px-3 py-1.5 text-micro font-medium rounded-full transition-colors ${
                  dateFilter === option.value
                    ? "bg-text-primary text-surface-deep"
                    : "bg-surface-elevated text-text-secondary hover:text-text-primary"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Error State */}
      {eventsError && (
        <ErrorMessage
          message={eventsError.message}
          onRetry={() => refreshEvents()}
        />
      )}

      {/* Loading State */}
      {eventsLoading && <SkeletonGrid count={6} />}

      {/* Events Display */}
      {!eventsLoading && !eventsError && (
        <>
          {filteredEvents.length === 0 && filteredFutures.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-body text-text-secondary mb-2">
                No events for {dateFilter === "today" ? "today" : dateFilter === "recent" ? "recent days" : "upcoming dates"}
              </p>
              <p className="text-caption text-text-muted">
                {selectedSport || selectedCategory
                  ? "Try selecting a different sport or date"
                  : "Try a different date filter"}
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

              {/* Right Now Feed */}
              {feedData && feedData.items.length > 0 && (
                <section>
                  <div className="flex items-center gap-2 mb-3">
                    <h2 className="text-sm font-semibold text-text-primary">
                      Right Now
                    </h2>
                    <span className="text-micro text-text-muted">
                      {(() => {
                        const eventCount = feedData.items.filter(i => i.type === "event").length;
                        const futuresCount = feedData.items.filter(i => i.type === "futures").length;
                        const liveCount = feedData.items.filter(i =>
                          i.type === "event" && (i.data as import("@/lib/types").FeedEventData).status === "live"
                        ).length;
                        const parts: string[] = [];
                        if (liveCount > 0) parts.push(`${liveCount} live`);
                        if (eventCount > 0) parts.push(`${eventCount} games`);
                        if (futuresCount > 0) parts.push(`${futuresCount} futures`);
                        return parts.join(" · ");
                      })()}
                    </span>
                  </div>
                  <div className="space-y-2">
                    {feedData.items.map((item, index) => (
                      <FeedCard
                        key={`feed-${item.type}-${item.type === "event" ? (item.data as import("@/lib/types").FeedEventData).id : (item.data as import("@/lib/types").FeedFuturesData).id}`}
                        item={item}
                      />
                    ))}
                  </div>
                </section>
              )}
              {feedLoading && !feedData && (
                <section>
                  <div className="flex items-center gap-2 mb-3">
                    <h2 className="text-sm font-semibold text-text-primary">Right Now</h2>
                  </div>
                  <div className="space-y-2">
                    {[1, 2, 3, 4, 5].map((i) => (
                      <div key={i} className="h-20 rounded-card bg-surface-card animate-pulse" />
                    ))}
                  </div>
                </section>
              )}

              {/* Sport Category Sections */}
              {sportGroups.map((sportGroup) => {
                const totalItems = sportGroup.totalEvents + sportGroup.totalFutures;
                const futuresKey = `${sportGroup.categoryKey}-futures`;
                const isFuturesExpanded = expandedLeagues.has(futuresKey);
                const liveCount = sportGroup.leagues.reduce(
                  (sum, league) => sum + league.events.filter(e => e.status === "live").length, 0
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
                                  onClick={() => toggleLeagueExpand(league.leagueKey, league.leagueName, league.events.length)}
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
                                    {league.events.length}
                                  </span>
                                </button>
                              )}

                              {isExpanded && (
                                <div
                                  className={`grid gap-3 items-stretch ${isFlatLeague ? "" : "ml-5"}`}
                                  style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))" }}
                                >
                                  {league.events.map((event, index) => (
                                    <EventCard
                                      key={event.id}
                                      event={event}
                                      showSport={false}
                                      sourceSection="sport_category"
                                      positionIndex={index}
                                      isPinned={isPinned(event.id)}
                                      onPinToggle={togglePin}
                                      pinDisabled={isMaxReached}
                                    />
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        })}

                        {/* Futures section */}
                        {sportGroup.futures.length > 0 && (() => {
                          const subcategories = groupBySubcategory(sportGroup.futures, sportGroup.categoryKey);
                          const useSubcategories = sportGroup.futures.length >= SUBCATEGORY_THRESHOLD && subcategories.length > 1;
                          const showFuturesDirectly = isFuturesOnly;
                          const futuresVisible = showFuturesDirectly || isFuturesExpanded;

                          return (
                            <div>
                              {!showFuturesDirectly && (
                                <button
                                  onClick={() => toggleLeagueExpand(futuresKey, "Futures", sportGroup.futures.length)}
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
                                    {sportGroup.futures.length}
                                  </span>
                                </button>
                              )}

                              {futuresVisible && (() => {
                                if (!useSubcategories) {
                                  return (
                                    <div
                                      className={`grid gap-3 items-stretch ${showFuturesDirectly ? "" : "ml-5"}`}
                                      style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))" }}
                                    >
                                      {sportGroup.futures.map((market) => (
                                        <FuturesCard
                                          key={`futures-${market.id}`}
                                          market={market}
                                          showSport={false}
                                          isPinned={isFuturesPinned(market.id)}
                                          onPinToggle={toggleFuturesPin}
                                          pinDisabled={isFuturesMaxReached}
                                        />
                                      ))}
                                    </div>
                                  );
                                }

                                return (
                                  <div className={`space-y-2 ${showFuturesDirectly ? "" : "ml-5"}`}>
                                    {subcategories.map((sub) => {
                                      const subKey = `${futuresKey}:${sub.key}`;
                                      const isSubExpanded = expandedLeagues.has(subKey);

                                      return (
                                        <div key={subKey}>
                                          <button
                                            onClick={() => toggleLeagueExpand(subKey, sub.displayName, sub.markets.length)}
                                            className="flex items-center gap-2 mb-2 w-full text-left group"
                                          >
                                            <span className="text-text-muted group-hover:text-text-secondary transition-colors">
                                              {isSubExpanded ? (
                                                <ChevronDown className="w-3.5 h-3.5" />
                                              ) : (
                                                <ChevronRight className="w-3.5 h-3.5" />
                                              )}
                                            </span>
                                            <span className="text-sm font-medium text-text-secondary">
                                              {sub.displayName}
                                            </span>
                                            <span className="text-micro text-text-muted">
                                              {sub.markets.length}
                                            </span>
                                          </button>
                                          {isSubExpanded && (
                                            <div
                                              className="grid gap-3 items-stretch ml-5"
                                              style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))" }}
                                            >
                                              {sub.markets.map((market) => (
                                                <FuturesCard
                                                  key={`futures-${market.id}`}
                                                  market={market}
                                                  showSport={false}
                                                  isPinned={isFuturesPinned(market.id)}
                                                  onPinToggle={toggleFuturesPin}
                                                  pinDisabled={isFuturesMaxReached}
                                                />
                                              ))}
                                            </div>
                                          )}
                                        </div>
                                      );
                                    })}
                                  </div>
                                );
                              })()}
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

          {(filteredEvents.length > 0 || filteredFutures.length > 0) && (
            <p className="text-center text-micro text-text-muted pt-4">
              {filteredEvents.length > 0 && (
                <>{filteredEvents.length} event{filteredEvents.length !== 1 ? "s" : ""}</>
              )}
              {filteredEvents.length > 0 && filteredFutures.length > 0 && " · "}
              {filteredFutures.length > 0 && (
                <>{filteredFutures.length} futures market{filteredFutures.length !== 1 ? "s" : ""}</>
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
