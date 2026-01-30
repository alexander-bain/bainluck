"use client";

import { useState, useMemo } from "react";
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

type ViewMode = "smart" | "time" | "closeness";

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
  const [viewMode, setViewMode] = useState<ViewMode>("smart");
  const [collapsedSports, setCollapsedSports] = useState<Set<string>>(new Set());
  const [completedCollapsed, setCompletedCollapsed] = useState<boolean>(true);

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

  // Filter events by category if selected, separating completed from active
  const { filteredEvents, completedEvents } = useMemo(() => {
    let events = eventsData?.events ?? [];
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
    // Separate finished events (completed/closed) from active (scheduled/live)
    const active = events.filter((e) => e.status !== "completed" && e.status !== "closed");
    const finished = events
      .filter((e) => e.status === "completed" || e.status === "closed")
      .sort((a, b) =>
        new Date(b.commence_time).getTime() - new Date(a.commence_time).getTime()
      );
    return { filteredEvents: active, completedEvents: finished };
  }, [eventsData?.events, selectedCategory, selectedSport]);

  // Get featured events (live + close games starting soon)
  const featuredEvents = useMemo(() => {
    return filteredEvents
      .filter((e) => isFeaturedEvent(e))
      .sort((a, b) => calculateExcitementScore(b) - calculateExcitementScore(a))
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

  // For flat view modes (time/closeness), sort events
  const sortedEvents = useMemo(() => {
    if (viewMode === "smart") return [];

    const sorted = [...filteredEvents];
    if (viewMode === "closeness") {
      sorted.sort((a, b) => {
        const aCloseness = Math.abs(
          (a.current_odds?.home_probability ?? 0.5) - 0.5
        );
        const bCloseness = Math.abs(
          (b.current_odds?.home_probability ?? 0.5) - 0.5
        );
        return aCloseness - bCloseness;
      });
    } else {
      sorted.sort((a, b) =>
        new Date(a.commence_time).getTime() - new Date(b.commence_time).getTime()
      );
    }
    return sorted;
  }, [filteredEvents, viewMode]);

  // Group flat events by date for time/closeness views
  const groupedByDate = useMemo(() => {
    if (viewMode === "smart") return {};
    return groupByDate(sortedEvents);
  }, [sortedEvents, viewMode]);

  const toggleSportCollapse = (categoryKey: string) => {
    setCollapsedSports((prev) => {
      const next = new Set(prev);
      if (next.has(categoryKey)) {
        next.delete(categoryKey);
      } else {
        next.add(categoryKey);
      }
      return next;
    });
  };

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

          {/* View mode dropdown */}
          <div className="flex items-center gap-2">
            <label className="text-caption text-slate">View:</label>
            <select
              value={viewMode}
              onChange={(e) => setViewMode(e.target.value as ViewMode)}
              className="text-caption border border-mist rounded px-3 py-1.5 bg-white text-graphite focus:outline-none focus:ring-1 focus:ring-ink"
            >
              <option value="smart">By Sport</option>
              <option value="time">By Time</option>
              <option value="closeness">Closest Odds</option>
            </select>
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
              <p className="text-body text-slate mb-2">No upcoming events</p>
              <p className="text-caption text-silver">
                {selectedSport || selectedCategory
                  ? "Try selecting a different sport"
                  : "Check back later for more games"}
              </p>
            </div>
          ) : viewMode === "smart" ? (
            /* Smart View: Featured + Sport Groups */
            <div className="space-y-8">
              {/* Featured Section */}
              {featuredEvents.length > 0 && (
                <section>
                  <div className="flex items-center gap-2 mb-4">
                    <span className="text-lg">🔥</span>
                    <h2 className="text-title-3 font-semibold text-graphite">
                      Live & Close Games
                    </h2>
                    <span className="text-caption text-slate bg-mist/50 px-2 py-0.5 rounded">
                      {featuredEvents.length}
                    </span>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {featuredEvents.map((event) => (
                      <EventCard
                        key={`featured-${event.id}`}
                        event={event}
                        showSport={true}
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* Sport Category Sections */}
              {sportGroups.map((sportGroup) => (
                <section key={sportGroup.categoryKey}>
                  {/* Sport Header */}
                  <button
                    onClick={() => toggleSportCollapse(sportGroup.categoryKey)}
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
                      {collapsedSports.has(sportGroup.categoryKey) ? (
                        <ChevronRight className="w-5 h-5" />
                      ) : (
                        <ChevronDown className="w-5 h-5" />
                      )}
                    </span>
                  </button>

                  {/* Sport Content */}
                  {!collapsedSports.has(sportGroup.categoryKey) && (
                    <div className="space-y-6 pl-7">
                      {sportGroup.leagues.map((league) => (
                        <div key={league.leagueKey}>
                          {/* League Header */}
                          <div className="flex items-center gap-2 mb-3">
                            <h3 className="text-body font-medium text-graphite">
                              {league.leagueName}
                            </h3>
                            {league.tier === 1 && (
                              <span className="text-micro bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
                                Major
                              </span>
                            )}
                            <span className="text-caption text-silver">
                              {league.events.length} game{league.events.length !== 1 ? "s" : ""}
                            </span>
                          </div>

                          {/* League Events */}
                          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                            {league.events.map((event) => (
                              <EventCard
                                key={event.id}
                                event={event}
                                showSport={false}
                              />
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              ))}
            </div>
          ) : (
            /* Flat Views: By Time or Closeness */
            <div className="space-y-8">
              {Object.entries(groupedByDate).map(([date, events]) => (
                <div key={date}>
                  <h2 className="text-caption-strong text-slate mb-4">
                    {date}
                  </h2>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {events.map((event) => (
                      <EventCard
                        key={event.id}
                        event={event}
                        showSport={!selectedCategory}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Completed Games Section */}
          {completedEvents.length > 0 && (
            <section className="border-t border-mist pt-6">
              <button
                onClick={() => setCompletedCollapsed(!completedCollapsed)}
                className="flex items-center gap-2 mb-4 w-full text-left group"
              >
                <span className="text-lg">✅</span>
                <h2 className="text-title-3 font-semibold text-slate">
                  Completed Games
                </h2>
                <span className="text-caption text-slate bg-mist/50 px-2 py-0.5 rounded">
                  {completedEvents.length}
                </span>
                <span className="ml-auto text-slate group-hover:text-graphite transition-colors">
                  {completedCollapsed ? (
                    <ChevronRight className="w-5 h-5" />
                  ) : (
                    <ChevronDown className="w-5 h-5" />
                  )}
                </span>
              </button>

              {!completedCollapsed && (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {completedEvents.map((event) => (
                    <EventCard
                      key={`completed-${event.id}`}
                      event={event}
                      showSport={!selectedCategory && !selectedSport}
                    />
                  ))}
                </div>
              )}
            </section>
          )}

          {/* Event count */}
          {(filteredEvents.length > 0 || completedEvents.length > 0) && (
            <p className="text-center text-caption text-silver pt-4">
              {filteredEvents.length} upcoming event{filteredEvents.length !== 1 ? "s" : ""}
              {completedEvents.length > 0 && ` · ${completedEvents.length} completed`}
            </p>
          )}
        </>
      )}
    </div>
  );
}

/**
 * Group events by date.
 */
function groupByDate(events: Event[]): Record<string, Event[]> {
  const groups: Record<string, Event[]> = {};

  for (const event of events) {
    const date = new Date(event.commence_time);
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    let dateKey: string;
    if (date.toDateString() === today.toDateString()) {
      dateKey = "Today";
    } else if (date.toDateString() === tomorrow.toDateString()) {
      dateKey = "Tomorrow";
    } else {
      dateKey = date.toLocaleDateString("en-US", {
        weekday: "long",
        month: "long",
        day: "numeric",
      });
    }

    if (!groups[dateKey]) {
      groups[dateKey] = [];
    }
    groups[dateKey].push(event);
  }

  return groups;
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
