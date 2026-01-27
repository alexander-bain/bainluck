"use client";

import Link from "next/link";
import useSWR from "swr";
import { fetchEvents, fetchSports } from "@/lib/api";
import EventCard from "@/components/EventCard";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";

interface SportPageProps {
  params: { key: string };
}

export default function SportPage({ params }: SportPageProps) {
  const sportKey = params.key;

  // Fetch sport info
  const { data: sportsData } = useSWR("sports", fetchSports);
  const sport = sportsData?.sports.find((s) => s.key === sportKey);

  // Fetch events for this sport
  const {
    data: eventsData,
    error: eventsError,
    isLoading: eventsLoading,
    mutate: refreshEvents,
  } = useSWR(
    ["events", sportKey],
    () => fetchEvents({ sport: sportKey, days: 14 }),
    { refreshInterval: 30000 }
  );

  const events = eventsData?.events ?? [];

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        href="/"
        className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900 transition-colors"
      >
        <svg
          className="w-4 h-4 mr-1"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15 19l-7-7 7-7"
          />
        </svg>
        All events
      </Link>

      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          {sport?.name || sportKey.replace(/_/g, " ").toUpperCase()}
        </h1>
        <p className="text-gray-600">
          {sport?.group && `${sport.group} • `}
          Upcoming games with win probabilities
        </p>
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

      {/* Events Grid */}
      {!eventsLoading && !eventsError && (
        <>
          {events.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <p className="text-lg mb-2">No upcoming events</p>
              <p className="text-sm">Check back later for more games</p>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {events.map((event) => (
                <EventCard key={event.id} event={event} showSport={false} />
              ))}
            </div>
          )}

          {/* Event count */}
          {events.length > 0 && (
            <p className="text-center text-sm text-gray-500 pt-4">
              Showing {events.length} event{events.length !== 1 ? "s" : ""}
            </p>
          )}
        </>
      )}
    </div>
  );
}
