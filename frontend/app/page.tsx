"use client";

import { useState, useMemo, useCallback } from "react";
import useSWR from "swr";
import { fetchEvents, fetchSports, fetchFuturesMarkets, fetchEventsByIds, fetchFuturesByIds } from "@/lib/api";
import type { Event, FuturesMarket } from "@/lib/types";
import EventCard from "@/components/EventCard";
import FuturesCard from "@/components/FuturesCard";
import SportFilter from "@/components/SportFilter";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import {
  SPORT_CATEGORIES,
  getCategoryForLeague,
  getCategoryForFutures,
  getLeagueDisplay,
  getLeagueTier,
  isFeaturedEvent,
  calculateExcitementScore,
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
  // Sport sections are collapsed by default (empty set = all collapsed)
  const [expandedSports, setExpandedSports] = useState<Set<string>>(new Set());
  // League sections are also collapsed by default
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
    pageTitle: 'OddsTracker - Home',
  });

  // Track scroll depth
  useScrollDepth({ pageType: 'home' });

  // Track engagement time
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

  // Fetch futures markets
  // - "today" and "upcoming": show open futures
  // - "recent": show resolved futures (recently completed)
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

  // Helper to check if a date is today, recent (last 7 days), or upcoming
  const getEventDateCategory = (commenceTime: string): "today" | "recent" | "upcoming" => {
    const eventDate = new Date(commenceTime);
    const now = new Date();

    // Get start of today (midnight)
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    // Get start of 7 days ago (for "recent" window)
    const recentStart = new Date(todayStart);
    recentStart.setDate(recentStart.getDate() - 7);
    // Get start of tomorrow
    const tomorrowStart = new Date(todayStart);
    tomorrowStart.setDate(tomorrowStart.getDate() + 1);

    if (eventDate >= todayStart && eventDate < tomorrowStart) {
      return "today";
    } else if (eventDate >= recentStart && eventDate < todayStart) {
      return "recent";
    } else if (eventDate >= tomorrowStart) {
      return "upcoming";
    } else {
      return "recent"; // Anything older also goes to recent (API limits how far back we fetch)
    }
  };

  // Filter events by category and date filter
  const filteredEvents = useMemo(() => {
    let events = eventsData?.events ?? [];

    // Filter out events without probability data (no moneyline odds)
    events = events.filter((e) =>
      e.current_odds?.home_probability != null && e.current_odds?.away_probability != null
    );

    // First, filter by sport category if selected
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

    // Then, filter by date
    events = events.filter((e) => {
      const dateCategory = getEventDateCategory(e.commence_time);
      if (dateFilter === "today") {
        return dateCategory === "today";
      } else if (dateFilter === "recent") {
        return dateCategory === "recent";
      } else {
        // "upcoming" - future events (tomorrow and beyond)
        return dateCategory === "upcoming";
      }
    });

    // Sort by commence time
    // Recent events: most recent first (descending)
    // Today/upcoming: earliest first (ascending)
    if (dateFilter === "recent") {
      return events.sort((a, b) =>
        new Date(b.commence_time).getTime() - new Date(a.commence_time).getTime()
      );
    }
    return events.sort((a, b) =>
      new Date(a.commence_time).getTime() - new Date(b.commence_time).getTime()
    );
  }, [eventsData?.events, selectedCategory, selectedSport, dateFilter]);

  // Helper to get outcome names from a futures market
  const getOutcomeNames = (market: FuturesMarket): string[] => {
    const outcomes = market.top_outcomes || market.outcomes || [];
    return outcomes.map((o) => o.name);
  };

  // Filter futures by category (no date filter for futures)
  const filteredFutures = useMemo(() => {
    let markets = futuresData?.markets ?? [];

    // Filter by sport category if selected
    if (selectedCategory && !selectedSport) {
      if (selectedCategory === "other") {
        // "Other" category: futures that don't match any known category
        markets = markets.filter(
          (m) => !getCategoryForFutures(m.sport, m.name, getOutcomeNames(m), m.llm_sport_category)
        );
      } else {
        // Match futures to selected category using smart categorization
        markets = markets.filter((m) => {
          const category = getCategoryForFutures(m.sport, m.name, getOutcomeNames(m), m.llm_sport_category);
          return category?.key === selectedCategory;
        });
      }
    }

    // Sort by outcome count (markets with more outcomes are usually more interesting)
    return markets.sort((a, b) => (b.outcome_count || 0) - (a.outcome_count || 0));
  }, [futuresData?.markets, selectedCategory, selectedSport]);

  // Get featured events using backend highlight scoring
  const featuredEvents = useMemo(() => {
    return filteredEvents
      .filter((e) => e.highlight?.should_feature || isFeaturedEvent(e))
      .sort((a, b) => {
        // Sort by highlight score (from backend) if available, fall back to excitement score
        const scoreA = a.highlight?.score ?? calculateExcitementScore(a);
        const scoreB = b.highlight?.score ?? calculateExcitementScore(b);
        return scoreB - scoreA;
      })
      .slice(0, 6); // Max 6 featured events
  }, [filteredEvents]);

  // Find which pinned event IDs are missing from the main events list
  const missingPinnedIds = useMemo(() => {
    const loadedIds = new Set((eventsData?.events ?? []).map(e => e.id));
    return pinnedIds.filter(id => !loadedIds.has(id));
  }, [eventsData?.events, pinnedIds]);

  // Fetch pinned events that aren't in the main list (e.g., events > 7 days away)
  const { data: fetchedPinnedEvents } = useSWR(
    missingPinnedIds.length > 0 ? ["pinned-events", ...missingPinnedIds] : null,
    () => fetchEventsByIds(missingPinnedIds),
    { revalidateOnFocus: false }
  );

  // Combine pinned events from main list + separately fetched
  const pinnedEvents = useMemo(() => {
    const allEvents = eventsData?.events ?? [];
    const fetchedMap = new Map((fetchedPinnedEvents ?? []).map(e => [e.id, e]));

    return pinnedIds
      .map(id => allEvents.find(e => e.id === id) ?? fetchedMap.get(id))
      .filter((e): e is Event => e !== undefined);
  }, [eventsData?.events, fetchedPinnedEvents, pinnedIds]);

  // Find which pinned futures IDs are missing from the loaded futures list
  const missingPinnedFuturesIds = useMemo(() => {
    const loadedIds = new Set((futuresData?.markets ?? []).map(f => f.id));
    return pinnedFuturesIds.filter(id => !loadedIds.has(id));
  }, [futuresData?.markets, pinnedFuturesIds]);

  // Fetch pinned futures that aren't in the main list
  const { data: fetchedPinnedFutures } = useSWR(
    missingPinnedFuturesIds.length > 0 ? ["pinned-futures", ...missingPinnedFuturesIds] : null,
    () => fetchFuturesByIds(missingPinnedFuturesIds),
    { revalidateOnFocus: false }
  );

  // Combine pinned futures from main list + separately fetched
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

    // Helper to get or create a sport group
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

    // Add events to groups
    for (const event of filteredEvents) {
      if (!event.sport) continue;

      const sportGroup = getOrCreateGroup(event.sport);
      sportGroup.totalEvents++;

      // Find or create league group
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

    // Add futures to groups using smart categorization
    for (const market of filteredFutures) {
      // Use getCategoryForFutures which matches by sport key, market name, outcome names, AND LLM category
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

    // Sort leagues within each sport by tier, then alphabetically
    const groupsArray = Array.from(groups.values());
    for (const group of groupsArray) {
      group.leagues.sort((a, b) => {
        if (a.tier !== b.tier) return a.tier - b.tier;
        return a.leagueName.localeCompare(b.leagueName);
      });

      // Sort events within each league by game time
      for (const league of group.leagues) {
        league.events.sort((a, b) =>
          new Date(a.commence_time).getTime() - new Date(b.commence_time).getTime()
        );
      }
    }

    // Sort sport groups by tier, then by total content (events + futures)
    return groupsArray.sort((a, b) => {
      if (a.tier !== b.tier) return a.tier - b.tier;
      return (b.totalEvents + b.totalFutures) - (a.totalEvents + a.totalFutures);
    });
  }, [filteredEvents, filteredFutures]);

  const toggleSportExpand = useCallback((categoryKey: string, categoryName: string, eventCount: number) => {
    setExpandedSports((prev) => {
      const next = new Set(prev);
      const isExpanding = !next.has(categoryKey);
      if (next.has(categoryKey)) {
        next.delete(categoryKey);
      } else {
        next.add(categoryKey);
      }

      // Track analytics
      trackSectionToggle(
        isExpanding ? 'expand' : 'collapse',
        'sport_category',
        categoryName,
        categoryKey,
        eventCount
      );

      return next;
    });
  }, [trackSectionToggle]);

  const toggleLeagueExpand = useCallback((leagueKey: string, leagueName: string, eventCount: number) => {
    setExpandedLeagues((prev) => {
      const next = new Set(prev);
      const isExpanding = !next.has(leagueKey);
      if (next.has(leagueKey)) {
        next.delete(leagueKey);
      } else {
        next.add(leagueKey);
      }

      // Track analytics
      trackSectionToggle(
        isExpanding ? 'expand' : 'collapse',
        'league',
        leagueName,
        leagueKey,
        eventCount
      );

      return next;
    });
  }, [trackSectionToggle]);

  const sports = sportsData?.sports ?? [];

  return (
    <div className="space-y-6">
      {/* Filters - sticky on scroll */}
      <div className="sticky top-16 bg-snow py-3 -mx-4 px-4 md:-mx-8 md:px-8 lg:-mx-12 lg:px-12 z-40">
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
                className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
                  dateFilter === option.value
                    ? "bg-gray-900 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
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
      {eventsLoading && (
        <div className="py-12">
          <LoadingSpinner text="Loading events..." />
        </div>
      )}

      {/* Events Display */}
      {!eventsLoading && !eventsError && (
        <>
          {filteredEvents.length === 0 && filteredFutures.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-body text-slate mb-2">
                No events for {dateFilter === "today" ? "today" : dateFilter === "recent" ? "recent days" : "upcoming dates"}
              </p>
              <p className="text-caption text-silver">
                {selectedSport || selectedCategory
                  ? "Try selecting a different sport or date"
                  : "Try a different date filter"}
              </p>
            </div>
          ) : (
            /* Smart View: Pinned + Featured + Sport Groups */
            <div className="space-y-8">
              {/* Pinned Events Section */}
              {pinnedEvents.length > 0 && (
                <section>
                  <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 mb-4">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">📌</span>
                      <h2 className="text-title-3 font-semibold text-graphite">
                        Pinned
                      </h2>
                    </div>
                    <span className="text-caption text-slate">
                      {pinnedEvents.length} event{pinnedEvents.length !== 1 ? "s" : ""} you&apos;re tracking
                    </span>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 items-stretch">
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
                  </div>
                </section>
              )}

              {/* Pinned Futures Section */}
              {pinnedFutures.length > 0 && (
                <section>
                  <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 mb-4">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">📌</span>
                      <h2 className="text-title-3 font-semibold text-graphite">
                        Pinned Futures
                      </h2>
                    </div>
                    <span className="text-caption text-slate">
                      {pinnedFutures.length} market{pinnedFutures.length !== 1 ? "s" : ""} you&apos;re tracking
                    </span>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 items-stretch">
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

              {/* Highlights Section */}
              {featuredEvents.length > 0 && (() => {
                // Categorize featured events using backend highlight data
                const liveEvents = featuredEvents.filter((e) =>
                  e.highlight?.flags?.is_live || e.status === "live"
                );
                const upsetEvents = featuredEvents.filter((e) =>
                  e.highlight?.flags?.is_upset
                );
                const closeEvents = featuredEvents.filter((e) =>
                  e.highlight?.flags?.is_close_matchup && !e.highlight?.flags?.is_live
                );
                const soonEvents = featuredEvents.filter((e) =>
                  e.highlight?.flags?.is_starting_soon && !e.highlight?.flags?.is_live
                );

                // Build subtitle explanation
                const subtitleParts: string[] = [];
                if (liveEvents.length > 0) subtitleParts.push(`${liveEvents.length} live`);
                if (upsetEvents.length > 0) subtitleParts.push(`${upsetEvents.length} upset${upsetEvents.length > 1 ? "s" : ""}`);
                if (closeEvents.length > 0) subtitleParts.push(`${closeEvents.length} close`);
                if (soonEvents.length > 0) subtitleParts.push(`${soonEvents.length} soon`);

                return (
                  <section>
                    <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 mb-4">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">✨</span>
                        <h2 className="text-title-3 font-semibold text-graphite">
                          Highlights
                        </h2>
                      </div>
                      <span className="text-caption text-slate">
                        {subtitleParts.join(" · ")}
                      </span>
                    </div>
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 items-stretch">
                      {featuredEvents.map((event, index) => (
                        <EventCard
                          key={`featured-${event.id}`}
                          event={event}
                          showSport={true}
                          sourceSection="featured"
                          positionIndex={index}
                          highlightLabel={event.highlight?.label}
                          isPinned={isPinned(event.id)}
                          onPinToggle={togglePin}
                          pinDisabled={isMaxReached}
                        />
                      ))}
                    </div>
                  </section>
                );
              })()}

              {/* Sport Category Sections */}
              {sportGroups.map((sportGroup) => {
                const totalItems = sportGroup.totalEvents + sportGroup.totalFutures;
                const futuresKey = `${sportGroup.categoryKey}-futures`;
                const isFuturesExpanded = expandedLeagues.has(futuresKey);

                return (
                  <section key={sportGroup.categoryKey}>
                    {/* Sport Header */}
                    <button
                      onClick={() => toggleSportExpand(sportGroup.categoryKey, sportGroup.categoryName, totalItems)}
                      className="flex items-center gap-2 mb-4 w-full text-left group"
                    >
                      <span className="text-lg">{sportGroup.emoji}</span>
                      <h2 className="text-title-3 font-semibold text-graphite">
                        {sportGroup.categoryName}
                      </h2>
                      <span className="text-caption text-slate bg-mist/50 px-2 py-0.5 rounded">
                        {sportGroup.totalEvents > 0 && sportGroup.totalFutures > 0
                          ? `${sportGroup.totalEvents} + ${sportGroup.totalFutures} futures`
                          : sportGroup.totalFutures > 0
                          ? `${sportGroup.totalFutures} futures`
                          : sportGroup.totalEvents}
                      </span>
                      <span className="ml-auto text-slate group-hover:text-graphite transition-colors">
                        {expandedSports.has(sportGroup.categoryKey) ? (
                          <ChevronDown className="w-5 h-5" />
                        ) : (
                          <ChevronRight className="w-5 h-5" />
                        )}
                      </span>
                    </button>

                    {/* Sport Content */}
                    {expandedSports.has(sportGroup.categoryKey) && (
                      <div className="space-y-4">
                        {/* League sections */}
                        {sportGroup.leagues.map((league) => {
                          // Auto-expand if only one league in this sport (and no futures)
                          const isSingleLeague = sportGroup.leagues.length === 1 && sportGroup.totalFutures === 0;
                          const isExpanded = isSingleLeague || expandedLeagues.has(league.leagueKey);

                          return (
                            <div key={league.leagueKey}>
                              {/* League Header - clickable toggle */}
                              <button
                                onClick={() => toggleLeagueExpand(league.leagueKey, league.leagueName, league.events.length)}
                                className="flex items-center gap-2 mb-2 w-full text-left group"
                              >
                                <span className="text-slate group-hover:text-graphite transition-colors">
                                  {isExpanded ? (
                                    <ChevronDown className="w-4 h-4" />
                                  ) : (
                                    <ChevronRight className="w-4 h-4" />
                                  )}
                                </span>
                                <h3 className="text-body font-medium text-graphite">
                                  {league.leagueName}
                                </h3>
                                {league.tier === 1 && (
                                  <span className="text-micro bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
                                    Major
                                  </span>
                                )}
                                <span className="text-caption text-silver">
                                  {league.events.length} event{league.events.length !== 1 ? "s" : ""}
                                </span>
                              </button>

                              {/* League Events */}
                              {isExpanded && (
                                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 items-stretch ml-6">
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

                        {/* Futures section within sport */}
                        {sportGroup.futures.length > 0 && (
                          <div>
                            {/* Futures Header - clickable toggle */}
                            <button
                              onClick={() => toggleLeagueExpand(futuresKey, "Futures", sportGroup.futures.length)}
                              className="flex items-center gap-2 mb-2 w-full text-left group"
                            >
                              <span className="text-slate group-hover:text-graphite transition-colors">
                                {isFuturesExpanded ? (
                                  <ChevronDown className="w-4 h-4" />
                                ) : (
                                  <ChevronRight className="w-4 h-4" />
                                )}
                              </span>
                              <h3 className="text-body font-medium text-graphite">
                                Futures
                              </h3>
                              <span className="text-micro bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">
                                Outrights
                              </span>
                              <span className="text-caption text-silver">
                                {sportGroup.futures.length} market{sportGroup.futures.length !== 1 ? "s" : ""}
                              </span>
                            </button>

                            {/* Futures Markets */}
                            {isFuturesExpanded && (
                              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 items-stretch ml-6">
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
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </section>
                );
              })}
            </div>
          )}

          {/* Event and futures count */}
          {(filteredEvents.length > 0 || filteredFutures.length > 0) && (
            <p className="text-center text-caption text-silver pt-4">
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

/**
 * Simple chevron icons
 */
function ChevronDown({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  );
}

function ChevronRight({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}
