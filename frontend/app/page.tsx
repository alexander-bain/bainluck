"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetchEvents, fetchSports } from "@/lib/api";
import type { Event, Sport } from "@/lib/types";
import EventCard from "@/components/EventCard";
import SportFilter from "@/components/SportFilter";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import {
  SPORT_CATEGORIES,
  getCategoryForLeague,
  getLeagueDisplay,
  isLeagueSupported,
  type SportCategory,
} from "@/lib/sportCategories";

type SortOption = "time" | "closeness";

export default function HomePage() {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSport, setSelectedSport] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortOption>("time");

  // Fetch sports list
  const {
    data: sportsData,
    error: sportsError,
    isLoading: sportsLoading,
  } = useSWR("sports", fetchSports);

  // Fetch events (fetch all, filter client-side for category filtering)
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

  // Filter events by category if selected but no specific sport
  // Also enforce MECE - only show events with supported leagues
  let filteredEvents = (eventsData?.events ?? []).filter((e) =>
    e.sport && isLeagueSupported(e.sport)
  );
  if (selectedCategory && !selectedSport) {
    const category = SPORT_CATEGORIES.find((c) => c.key === selectedCategory);
    if (category) {
      filteredEvents = filteredEvents.filter((e) =>
        e.sport && category.leagues.includes(e.sport)
      );
    }
  }

  // Sort events
  const sortedEvents = [...filteredEvents].sort((a, b) => {
    if (sortBy === "closeness") {
      const aCloseness = Math.abs(
        (a.current_odds?.home_probability ?? 0.5) - 0.5
      );
      const bCloseness = Math.abs(
        (b.current_odds?.home_probability ?? 0.5) - 0.5
      );
      return aCloseness - bCloseness;
    }
    return new Date(a.commence_time).getTime() - new Date(b.commence_time).getTime();
  });

  // Group events by date, then by sport category, then by league
  const groupedEvents = groupByDateAndSport(sortedEvents, selectedCategory !== null);

  const sports = sportsData?.sports ?? [];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          Upcoming Games
        </h1>
        <p className="text-gray-600">
          Win probabilities updated every 30 seconds
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-4">
        <SportFilter
          sports={sports}
          selectedSport={selectedSport}
          selectedCategory={selectedCategory}
          onSelectSport={setSelectedSport}
          onSelectCategory={setSelectedCategory}
          loading={sportsLoading}
        />

        {/* Sort dropdown */}
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">Sort by:</label>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortOption)}
            className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-gray-900"
          >
            <option value="time">Game Time</option>
            <option value="closeness">Closest Odds</option>
          </select>
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

      {/* Events List */}
      {!eventsLoading && !eventsError && (
        <>
          {sortedEvents.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <p className="text-lg mb-2">No upcoming events found</p>
              <p className="text-sm">
                {selectedSport || selectedCategory
                  ? "Try selecting a different sport"
                  : "Check back later for more games"}
              </p>
            </div>
          ) : (
            <div className="space-y-8">
              {Object.entries(groupedEvents).map(([date, sportGroups]) => (
                <div key={date}>
                  {/* Date header */}
                  <h2 className="text-lg font-semibold text-gray-700 mb-4 sticky top-[73px] bg-gray-50 py-2 -mx-4 px-4 z-10">
                    {date}
                  </h2>

                  {/* Sport groups within this date */}
                  <div className="space-y-6">
                    {Object.entries(sportGroups).map(([sportKey, leagueGroups]) => {
                      const category = getCategoryForLeague(Object.keys(leagueGroups)[0]);
                      const emoji = category?.emoji || "🏆";
                      const sportName = category?.name || sportKey;

                      return (
                        <div key={sportKey} className="space-y-4">
                          {/* Sport header with emoji */}
                          <div className="flex items-center gap-2">
                            <span className="text-xl">{emoji}</span>
                            <h3 className="text-md font-medium text-gray-600">
                              {sportName}
                            </h3>
                          </div>

                          {/* League groups within this sport */}
                          {Object.entries(leagueGroups).map(([leagueKey, events]) => (
                            <div key={leagueKey} className="pl-4 border-l-2 border-gray-200">
                              {/* League label (only if multiple leagues in sport) */}
                              {Object.keys(leagueGroups).length > 1 && (
                                <p className="text-xs text-gray-500 mb-2 font-medium">
                                  {getLeagueDisplay(leagueKey)}
                                </p>
                              )}

                              {/* Events grid */}
                              <div className="grid gap-4 md:grid-cols-2">
                                {events.map((event) => (
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
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Event count */}
          {sortedEvents.length > 0 && (
            <p className="text-center text-sm text-gray-500 pt-4">
              Showing {sortedEvents.length} event{sortedEvents.length !== 1 ? "s" : ""}
            </p>
          )}
        </>
      )}
    </div>
  );
}

/**
 * Group events by date, then by sport category, then by league.
 * Returns: { date: { categoryKey: { leagueKey: Event[] } } }
 */
function groupByDateAndSport(
  events: Event[],
  skipSportGrouping: boolean
): Record<string, Record<string, Record<string, Event[]>>> {
  const groups: Record<string, Record<string, Record<string, Event[]>>> = {};

  for (const event of events) {
    const date = new Date(event.commence_time);
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    // Date key
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

    // Sport category key
    const category = event.sport ? getCategoryForLeague(event.sport) : undefined;
    const categoryKey = category?.key || "other";

    // League key
    const leagueKey = event.sport || "unknown";

    // Initialize nested structure
    if (!groups[dateKey]) {
      groups[dateKey] = {};
    }
    if (!groups[dateKey][categoryKey]) {
      groups[dateKey][categoryKey] = {};
    }
    if (!groups[dateKey][categoryKey][leagueKey]) {
      groups[dateKey][categoryKey][leagueKey] = [];
    }

    groups[dateKey][categoryKey][leagueKey].push(event);
  }

  // Sort categories within each date by a predefined order
  const categoryOrder = SPORT_CATEGORIES.map((c) => c.key);

  for (const dateKey of Object.keys(groups)) {
    const sortedCategories: Record<string, Record<string, Event[]>> = {};
    const categoryKeys = Object.keys(groups[dateKey]).sort((a, b) => {
      const aIndex = categoryOrder.indexOf(a);
      const bIndex = categoryOrder.indexOf(b);
      if (aIndex === -1 && bIndex === -1) return 0;
      if (aIndex === -1) return 1;
      if (bIndex === -1) return -1;
      return aIndex - bIndex;
    });

    for (const catKey of categoryKeys) {
      sortedCategories[catKey] = groups[dateKey][catKey];
    }
    groups[dateKey] = sortedCategories;
  }

  return groups;
}
