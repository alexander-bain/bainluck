"use client";

import { useState, useMemo, useCallback } from "react";
import useSWR from "swr";
import { fetchEvents, fetchSports } from "@/lib/api";
import type { Event } from "@/lib/types";
import EventCard from "@/components/EventCard";
import SportFilter from "@/components/SportFilter";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import {
  SPORT_CATEGORIES,
  getCategoryForLeague,
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
} from "@/hooks";

type DateFilter = "today" | "yesterday" | "upcoming";

const DATE_FILTER_OPTIONS: { value: DateFilter; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
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
  totalEvents: number;
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

  // Helper to check if a date is today, yesterday, or upcoming
  const getEventDateCategory = (commenceTime: string): "today" | "yesterday" | "upcoming" | "past" => {
    const eventDate = new Date(commenceTime);
    const now = new Date();

    // Get start of today (midnight)
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    // Get start of yesterday
    const yesterdayStart = new Date(todayStart);
    yesterdayStart.setDate(yesterdayStart.getDate() - 1);
    // Get start of tomorrow
    const tomorrowStart = new Date(todayStart);
    tomorrowStart.setDate(tomorrowStart.getDate() + 1);

    if (eventDate >= todayStart && eventDate < tomorrowStart) {
      return "today";
    } else if (eventDate >= yesterdayStart && eventDate < todayStart) {
      return "yesterday";
    } else if (eventDate >= tomorrowStart) {
      return "upcoming";
    } else {
      return "past"; // Older than yesterday
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
      } else if (dateFilter === "yesterday") {
        return dateCategory === "yesterday";
      } else {
        // "upcoming" - future events (tomorrow and beyond)
        return dateCategory === "upcoming";
      }
    });

    // Sort by commence time
    return events.sort((a, b) =>
      new Date(a.commence_time).getTime() - new Date(b.commence_time).getTime()
    );
  }, [eventsData?.events, selectedCategory, selectedSport, dateFilter]);

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

  // Group events by sport category, then by league
  const sportGroups = useMemo((): SportGroup[] => {
    const groups = new Map<string, SportGroup>();

    for (const event of filteredEvents) {
      if (!event.sport) continue;

      const category = getCategoryForLeague(event.sport);
      const categoryKey = category?.key ?? "other";
      const categoryName = category?.name ?? "Other";
      const categoryEmoji = category?.emoji ?? "🏆";
      const categoryTier = category?.tier ?? 3;

      if (!groups.has(categoryKey)) {
        groups.set(categoryKey, {
          categoryKey,
          categoryName,
          emoji: categoryEmoji,
          tier: categoryTier,
          leagues: [],
          totalEvents: 0,
        });
      }

      const sportGroup = groups.get(categoryKey)!;
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

    // Sort sport groups by tier, then by total events
    return groupsArray.sort((a, b) => {
      if (a.tier !== b.tier) return a.tier - b.tier;
      return b.totalEvents - a.totalEvents;
    });
  }, [filteredEvents]);

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
          {filteredEvents.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-body text-slate mb-2">
                No events for {dateFilter === "today" ? "today" : dateFilter === "yesterday" ? "yesterday" : "upcoming dates"}
              </p>
              <p className="text-caption text-silver">
                {selectedSport || selectedCategory
                  ? "Try selecting a different sport or date"
                  : "Try a different date filter"}
              </p>
            </div>
          ) : (
            /* Smart View: Featured + Sport Groups */
            <div className="space-y-8">
              {/* Highlights Section */}
              {featuredEvents.length > 0 && (() => {
                // Categorize featured events using backend highlight data
                const liveEvents = featuredEvents.filter((e) =>
                  e.highlight?.flags?.is_live || e.status === "live"
                );
                const upsetEvents = featuredEvents.filter((e) =>
                  e.highlight?.flags?.favorite_switched && !e.highlight?.flags?.is_live
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
                        />
                      ))}
                    </div>
                  </section>
                );
              })()}

              {/* Sport Category Sections */}
              {sportGroups.map((sportGroup) => (
                <section key={sportGroup.categoryKey}>
                  {/* Sport Header */}
                  <button
                    onClick={() => toggleSportExpand(sportGroup.categoryKey, sportGroup.categoryName, sportGroup.totalEvents)}
                    className="flex items-center gap-2 mb-4 w-full text-left group"
                  >
                    <span className="text-lg">{sportGroup.emoji}</span>
                    <h2 className="text-title-3 font-semibold text-graphite">
                      {sportGroup.categoryName}
                    </h2>
                    <span className="text-caption text-slate bg-mist/50 px-2 py-0.5 rounded">
                      {sportGroup.totalEvents}
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
                      {sportGroup.leagues.map((league) => {
                        // Auto-expand if only one league in this sport
                        const isSingleLeague = sportGroup.leagues.length === 1;
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
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </section>
              ))}
            </div>
          )}

          {/* Event count */}
          {filteredEvents.length > 0 && (
            <p className="text-center text-caption text-silver pt-4">
              {filteredEvents.length} event{filteredEvents.length !== 1 ? "s" : ""}
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
