"use client";

import { useMemo } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetchEvents, fetchSports } from "@/lib/api";
import EventCard from "@/components/EventCard";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { buildLeagueSections } from "@/lib/sports/leagueSections";

interface SportPageProps {
  params: { key: string };
}

export default function SportPage({ params }: SportPageProps) {
  const sportKey = params.key;

  // Analytics hooks must be called before conditional returns
  usePageTracking({
    pageType: 'sport',
    pageTitle: `${sportKey} Odds`,
    additionalParams: { sport: sportKey },
    deps: [sportKey],
  });
  useScrollDepth({ pageType: 'sport' });
  useEngagementTime({ pageType: 'sport' });

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
    { refreshInterval: 30000, keepPreviousData: true, revalidateOnFocus: false }
  );

  // Memoised on the SWR payload, not re-derived: `?? []` mints a new array
  // identity on every render, which would make the `sections` memo below
  // recompute every time (react-hooks/exhaustive-deps).
  const events = useMemo(() => eventsData?.events ?? [], [eventsData]);

  // #2948 — `/api/events` is `commence_time` ASCENDING, so without this every
  // finished game precedes every live and upcoming one, by construction rather
  // than by accident. Live first, then the games still to play, then results
  // (D54 = A). The bucket rule is `eventSectionKey`'s, shared with `/sports`
  // and My Stuff so the three cannot drift.
  const sections = useMemo(() => buildLeagueSections(events), [events]);

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        href="/"
        className="inline-flex items-center text-sm text-text-secondary hover:text-text-primary transition-colors"
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
        <h1 className="text-3xl font-bold text-text-primary mb-2">
          {sport?.name || sportKey.replace(/_/g, " ").toUpperCase()}
        </h1>
        {/* #2948 — the old subtitle read "Upcoming games with win
            probabilities", which was false of 17 of the 32 cards below it.
            What is true of every composition is the ORDER, which is also the
            thing a reader needs told. */}
        <p className="text-text-secondary">
          {sport?.group && `${sport.group} • `}
          Win probabilities for live and upcoming games. Finished games below.
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
            <div
              className="text-center py-12 text-text-secondary"
              data-empty-state-name="league-no-upcoming-events"
            >
              <p className="text-lg mb-2">No games</p>
              {/* Ruling 142: what this page lists, not when it will list more.
                  #2948 — it lists finished games too now, so it stops saying
                  "scheduled". */}
              <p className="text-sm">This page lists games for this league.</p>
            </div>
          ) : (
            <div className="space-y-8">
              {sections.map((section) => (
                <section key={section.key} data-league-section={section.key}>
                  <h2
                    className="text-lg font-semibold text-text-primary mb-3"
                    data-league-section-title={section.key}
                  >
                    {section.title}
                    <span className="ml-2 text-sm font-normal text-text-secondary">
                      {section.events.length}
                    </span>
                  </h2>
                  <div className="grid gap-4 md:grid-cols-2">
                    {section.events.map((event) => (
                      <EventCard key={event.id} event={event} showSport={false} />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}

          {/* Event count */}
          {events.length > 0 && (
            <p className="text-center text-sm text-text-secondary pt-4">
              Showing {events.length} event{events.length !== 1 ? "s" : ""}
            </p>
          )}
        </>
      )}
    </div>
  );
}
