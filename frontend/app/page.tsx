"use client";

import { useState } from "react";
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
  getCategoryName,
} from "@/lib/sportCategories";

type SortOption = "time" | "closeness";

export default function HomePage() {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSport, setSelectedSport] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortOption>("time");

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

  // Filter events by category if selected
  let filteredEvents = eventsData?.events ?? [];
  if (selectedCategory && !selectedSport) {
    const category = SPORT_CATEGORIES.find((c) => c.key === selectedCategory);
    if (category) {
      filteredEvents = filteredEvents.filter((e) =>
        e.sport && category.prefixes.some((prefix) => e.sport!.startsWith(prefix))
      );
    } else if (selectedCategory === "other") {
      filteredEvents = filteredEvents.filter((e) =>
        e.sport && !getCategoryForLeague(e.sport)
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

  // Group events by date
  const groupedEvents = groupByDate(sortedEvents);

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

          {/* Sort dropdown */}
          <div className="flex items-center gap-2">
            <label className="text-caption text-slate">Sort:</label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              className="text-caption border border-mist rounded px-3 py-1.5 bg-white text-graphite focus:outline-none focus:ring-1 focus:ring-ink"
            >
              <option value="time">Game Time</option>
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

      {/* Events List */}
      {!eventsLoading && !eventsError && (
        <>
          {sortedEvents.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-body text-slate mb-2">No upcoming events</p>
              <p className="text-caption text-silver">
                {selectedSport || selectedCategory
                  ? "Try selecting a different sport"
                  : "Check back later for more games"}
              </p>
            </div>
          ) : (
            <div className="space-y-8">
              {Object.entries(groupedEvents).map(([date, events]) => (
                <div key={date}>
                  {/* Date header */}
                  <h2 className="text-caption-strong text-slate mb-4">
                    {date}
                  </h2>

                  {/* Events grid - responsive per design brief */}
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

          {/* Event count */}
          {sortedEvents.length > 0 && (
            <p className="text-center text-caption text-silver pt-4">
              {sortedEvents.length} event{sortedEvents.length !== 1 ? "s" : ""}
            </p>
          )}
        </>
      )}
    </div>
  );
}

/**
 * Group events by date.
 * Returns: { date: Event[] }
 */
function groupByDate(events: Event[]): Record<string, Event[]> {
  const groups: Record<string, Event[]> = {};

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

    if (!groups[dateKey]) {
      groups[dateKey] = [];
    }
    groups[dateKey].push(event);
  }

  return groups;
}
