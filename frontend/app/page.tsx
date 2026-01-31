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
  getFeatureReason,
  formatTimeUntil,
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
  const [recentlyClosedCollapsed, setRecentlyClosedCollapsed] = useState<boolean>(false);
  const [archivedCollapsed, setArchivedCollapsed] = useState<boolean>(true);

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

  // Filter events by category if selected, separating by temporal category
  const { filteredEvents, recentlyClosedEvents, archivedEvents } = useMemo(() => {
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

    const now = new Date();
    // Separate finished events into recently closed (<24h) and archived (>24h)
    const active = events.filter((e) => e.status !== "completed" && e.status !== "closed");

    const finishedEvents = events.filter((e) => e.status === "completed" || e.status === "closed");

    const recentlyClosed = finishedEvents
      .filter((e) => {
        const eventDate = new Date(e.commence_time);
        const hoursAgo = (now.getTime() - eventDate.getTime()) / (1000 * 60 * 60);
        return hoursAgo <= 24;
      })
      .sort((a, b) => new Date(b.commence_time).getTime() - new Date(a.commence_time).getTime());

    const archived = finishedEvents
      .filter((e) => {
        const eventDate = new Date(e.commence_time);
        const hoursAgo = (now.getTime() - eventDate.getTime()) / (1000 * 60 * 60);
        return hoursAgo > 24;
      })
      .sort((a, b) => new Date(b.commence_time).getTime() - new Date(a.commence_time).getTime());

    return { filteredEvents: active, recentlyClosedEvents: recentlyClosed, archivedEvents: archived };
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
              {featuredEvents.length > 0 && (() => {
                // Count live vs upcoming
                const liveCount = featuredEvents.filter((e) => getFeatureReason(e) === "live").length;
                const upcomingCount = featuredEvents.length - liveCount;
                const sectionTitle = liveCount > 0 && upcomingCount > 0
                  ? "Live & Starting Soon"
                  : liveCount > 0
                  ? "Live Games"
                  : "Starting Soon";

                return (
                  <section>
                    <div className="flex items-center gap-2 mb-4">
                      <span className="text-lg">{liveCount > 0 ? "🔴" : "⏰"}</span>
                      <h2 className="text-title-3 font-semibold text-graphite">
                        {sectionTitle}
                      </h2>
                      {liveCount > 0 && (
                        <span className="text-caption text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full font-medium">
                          {liveCount} live
                        </span>
                      )}
                      {upcomingCount > 0 && (
                        <span className="text-caption text-slate bg-mist/50 px-2 py-0.5 rounded">
                          {upcomingCount} upcoming
                        </span>
                      )}
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
                );
              })()}

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

          {/* Recently Closed Games Section */}
          {recentlyClosedEvents.length > 0 && (
            <section className="border-t border-mist pt-6">
              <button
                onClick={() => setRecentlyClosedCollapsed(!recentlyClosedCollapsed)}
                className="flex items-center gap-2 mb-4 w-full text-left group"
              >
                <span className="text-lg">✅</span>
                <h2 className="text-title-3 font-semibold text-slate">
                  Recently Finished
                </h2>
                <span className="text-caption text-slate bg-mist/50 px-2 py-0.5 rounded">
                  {recentlyClosedEvents.length}
                </span>
                <span className="ml-auto text-slate group-hover:text-graphite transition-colors">
                  {recentlyClosedCollapsed ? (
                    <ChevronRight className="w-5 h-5" />
                  ) : (
                    <ChevronDown className="w-5 h-5" />
                  )}
                </span>
              </button>

              {!recentlyClosedCollapsed && (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {recentlyClosedEvents.map((event) => (
                    <EventCard
                      key={`recent-${event.id}`}
                      event={event}
                      showSport={!selectedCategory && !selectedSport}
                    />
                  ))}
                </div>
              )}
            </section>
          )}

          {/* Archived Games Section */}
          {archivedEvents.length > 0 && (
            <section className="border-t border-mist/50 pt-6">
              <button
                onClick={() => setArchivedCollapsed(!archivedCollapsed)}
                className="flex items-center gap-2 mb-4 w-full text-left group"
              >
                <span className="text-lg">📦</span>
                <h2 className="text-title-3 font-semibold text-silver">
                  Archived
                </h2>
                <span className="text-caption text-silver bg-mist/30 px-2 py-0.5 rounded">
                  {archivedEvents.length}
                </span>
                <span className="ml-auto text-silver group-hover:text-slate transition-colors">
                  {archivedCollapsed ? (
                    <ChevronRight className="w-5 h-5" />
                  ) : (
                    <ChevronDown className="w-5 h-5" />
                  )}
                </span>
              </button>

              {!archivedCollapsed && (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {archivedEvents.map((event) => (
                    <EventCard
                      key={`archived-${event.id}`}
                      event={event}
                      showSport={!selectedCategory && !selectedSport}
                    />
                  ))}
                </div>
              )}
            </section>
          )}

          {/* Event count */}
          {(filteredEvents.length > 0 || recentlyClosedEvents.length > 0 || archivedEvents.length > 0) && (
            <p className="text-center text-caption text-silver pt-4">
              {filteredEvents.length} upcoming
              {recentlyClosedEvents.length > 0 && ` · ${recentlyClosedEvents.length} recent`}
              {archivedEvents.length > 0 && ` · ${archivedEvents.length} archived`}
            </p>
          )}
        </>
      )}
    </div>
  );
}

/**
 * Temporal categories for event organization
 */
type TemporalCategory = "today" | "tomorrow" | "this_week" | "upcoming" | "recently_closed" | "archived";

interface TemporalGroup {
  key: TemporalCategory;
  label: string;
  emoji: string;
  events: Event[];
  collapsed?: boolean;
}

/**
 * Get temporal category for an event
 */
function getTemporalCategory(event: Event): TemporalCategory {
  const now = new Date();
  const eventDate = new Date(event.commence_time);
  const isFinished = event.status === "completed" || event.status === "closed";

  if (isFinished) {
    // Check how long ago it finished
    const hoursAgo = (now.getTime() - eventDate.getTime()) / (1000 * 60 * 60);
    return hoursAgo <= 24 ? "recently_closed" : "archived";
  }

  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const dayAfterTomorrow = new Date(today);
  dayAfterTomorrow.setDate(dayAfterTomorrow.getDate() + 2);
  const nextWeek = new Date(today);
  nextWeek.setDate(nextWeek.getDate() + 7);

  const eventDay = new Date(eventDate.getFullYear(), eventDate.getMonth(), eventDate.getDate());

  if (eventDay.getTime() === today.getTime()) return "today";
  if (eventDay.getTime() === tomorrow.getTime()) return "tomorrow";
  if (eventDay < nextWeek) return "this_week";
  return "upcoming";
}

/**
 * Group events by temporal category
 */
function groupByTemporal(events: Event[]): TemporalGroup[] {
  const categoryConfig: { key: TemporalCategory; label: string; emoji: string; collapsed?: boolean }[] = [
    { key: "today", label: "Today", emoji: "📅" },
    { key: "tomorrow", label: "Tomorrow", emoji: "📆" },
    { key: "this_week", label: "This Week", emoji: "🗓️" },
    { key: "upcoming", label: "Later", emoji: "⏳" },
    { key: "recently_closed", label: "Recently Closed", emoji: "✅" },
    { key: "archived", label: "Archived", emoji: "📦", collapsed: true },
  ];

  const groups: Record<TemporalCategory, Event[]> = {
    today: [],
    tomorrow: [],
    this_week: [],
    upcoming: [],
    recently_closed: [],
    archived: [],
  };

  for (const event of events) {
    const category = getTemporalCategory(event);
    groups[category].push(event);
  }

  // Sort events within each group by commence time
  for (const key of Object.keys(groups) as TemporalCategory[]) {
    groups[key].sort((a, b) =>
      new Date(a.commence_time).getTime() - new Date(b.commence_time).getTime()
    );
  }

  // Return only non-empty groups
  return categoryConfig
    .filter((config) => groups[config.key].length > 0)
    .map((config) => ({
      ...config,
      events: groups[config.key],
    }));
}

/**
 * Group events by date (legacy function for time/closeness views).
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
