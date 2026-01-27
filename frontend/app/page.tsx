"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetchEvents, fetchSports } from "@/lib/api";
import type { Event, Sport } from "@/lib/types";
import EventCard from "@/components/EventCard";
import SportFilter from "@/components/SportFilter";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";

type SortOption = "time" | "closeness";

export default function HomePage() {
  const [selectedSport, setSelectedSport] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortOption>("time");

  // Fetch sports list
  const {
    data: sportsData,
    error: sportsError,
    isLoading: sportsLoading,
  } = useSWR("sports", fetchSports);

  // Fetch events with sport filter
  const {
    data: eventsData,
    error: eventsError,
    isLoading: eventsLoading,
    mutate: refreshEvents,
  } = useSWR(
    ["events", selectedSport],
    () => fetchEvents({ sport: selectedSport ?? undefined, days: 7 }),
    { refreshInterval: 30000 } // Auto-refresh every 30 seconds
  );

  // Sort events
  const sortedEvents = [...(eventsData?.events ?? [])].sort((a, b) => {
    if (sortBy === "closeness") {
      // Sort by how close to 50/50 (most exciting games first)
      const aCloseness = Math.abs(
        (a.current_odds?.home_probability ?? 0.5) - 0.5
      );
      const bCloseness = Math.abs(
        (b.current_odds?.home_probability ?? 0.5) - 0.5
      );
      return aCloseness - bCloseness;
    }
    // Default: sort by time
    return new Date(a.commence_time).getTime() - new Date(b.commence_time).getTime();
  });

  // Group events by date
  const groupedEvents = groupByDate(sortedEvents);

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
      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex-1">
          <SportFilter
            sports={sports}
            selectedSport={selectedSport}
            onSelectSport={setSelectedSport}
            loading={sportsLoading}
          />
        </div>

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
                {selectedSport
                  ? "Try selecting a different sport"
                  : "Check back later for more games"}
              </p>
            </div>
          ) : (
            <div className="space-y-8">
              {Object.entries(groupedEvents).map(([date, events]) => (
                <div key={date}>
                  <h2 className="text-lg font-semibold text-gray-700 mb-3 sticky top-[73px] bg-gray-50 py-2 -mx-4 px-4">
                    {date}
                  </h2>
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-2">
                    {events.map((event) => (
                      <EventCard
                        key={event.id}
                        event={event}
                        showSport={selectedSport === null}
                      />
                    ))}
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
 * Group events by date for display
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
