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
import {
  LEAGUE_WINDOW_DAYS,
  LEAGUE_OFFSEASON_HORIZON_DAYS,
  needsWiderHorizon,
} from "@/lib/sports/leagueHorizon";

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
    () => fetchEvents({ sport: sportKey, days: LEAGUE_WINDOW_DAYS }),
    { refreshInterval: 30000, keepPreviousData: true, revalidateOnFocus: false }
  );

  // Memoised on the SWR payload, not re-derived: `?? []` mints a new array
  // identity on every render, which would make the `sections` memo below
  // recompute every time (react-hooks/exhaustive-deps).
  const nearTermEvents = useMemo(() => eventsData?.events ?? [], [eventsData]);

  // #3028 — the 14-day window is shorter than an offseason. When the league is
  // not playing (nothing live, next game more than a week out) that window is
  // the reason the page looks empty, so ask again with a horizon that reaches
  // the schedule we already hold. The condition and both constants live in
  // `lib/sports/leagueHorizon.ts` with the measurements that chose them.
  //
  // Gated on `eventsData` rather than on the array: before the first response
  // there is nothing to widen FROM, and an undefined payload would otherwise
  // read as "no games in the near term" and fire a second request on every
  // in-season page load.
  const wantsWiderHorizon = useMemo(
    () => Boolean(eventsData) && needsWiderHorizon(nearTermEvents),
    [eventsData, nearTermEvents]
  );

  const {
    data: widerData,
    error: widerError,
    isLoading: widerLoading,
  } = useSWR(
    wantsWiderHorizon ? ["events", sportKey, LEAGUE_OFFSEASON_HORIZON_DAYS] : null,
    () => fetchEvents({ sport: sportKey, days: LEAGUE_OFFSEASON_HORIZON_DAYS }),
    {
      // A schedule three months out does not move every 30 seconds, and this
      // request only exists on pages whose league is dormant — polling it at
      // the live cadence would spend the fast interval on the one case that
      // cannot use it.
      refreshInterval: 300000,
      keepPreviousData: true,
      revalidateOnFocus: false,
    }
  );

  // The widened payload is a superset of the near-term one (same endpoint,
  // longer window), so it REPLACES rather than merges. If it fails, the page
  // still renders whatever the near-term window found instead of inheriting
  // the second request's error — a dormant league showing one card is worse
  // than it should be, but it is not broken.
  const events = useMemo(
    () => (widerData?.events ?? nearTermEvents),
    [widerData, nearTermEvents]
  );

  // Don't flash "No games" underneath a widened request that is about to
  // answer with 36 of them. `keepPreviousData` covers the refresh case; this
  // covers the first load.
  const isLoading = eventsLoading || (wantsWiderHorizon && widerLoading);

  // The widened window only announces itself once it has actually returned
  // something the near-term window could not have shown.
  const showingWiderHorizon =
    wantsWiderHorizon && !widerError && (widerData?.events?.length ?? 0) > 0;

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
        {/* #3028 — the widened window says so. A reader who lands on an NBA
            page in September and sees an October fixture at the top is owed
            the reason; the alternative is a page that silently answers a
            different question from the one every other league page answers.
            Says only what was measured — nothing about seasons or breaks,
            which this page cannot know.

            It deliberately does NOT open with "No games": that is the dead
            page's own first line, and a reader who saw it yesterday should not
            meet the same three words at the top of a page that is now full of
            fixtures. The empty state and this notice describe opposite
            outcomes and must not share an opening. */}
        {showingWiderHorizon && (
          <p
            className="text-sm text-text-secondary mt-2"
            data-league-horizon="widened"
          >
            Nothing scheduled in the next week — showing every upcoming game we
            hold.
          </p>
        )}
      </div>

      {/* Error State */}
      {eventsError && (
        <ErrorMessage
          message={eventsError.message}
          onRetry={() => refreshEvents()}
        />
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="py-12">
          <LoadingSpinner text="Loading events..." />
        </div>
      )}

      {/* Events Grid */}
      {!isLoading && !eventsError && (
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
