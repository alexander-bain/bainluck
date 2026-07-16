"use client";

import { Suspense, useState, useEffect, useRef } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { markSearchDestination } from "@/lib/searchFunnel";
import Link from "next/link";
import { searchEvents, fetchSearchSuggestions } from "@/lib/api";
import { getLeagueDisplay, getEmojiForLeague } from "@/lib/sportCategories";
import { usePinnedEvents, usePinnedFutures, usePageTracking, useScrollDepth, useEngagementTime, useAnalytics } from "@/hooks";
import EventCard from "@/components/EventCard";
import FuturesCard from "@/components/FuturesCard";
import SearchFamilyCard from "@/components/SearchFamilyCard";
import { familyShownIds } from "@/components/searchFamilyDisplay";
import CategoryBrowser from "@/components/CategoryBrowser";
import LoadingState from "@/components/LoadingState";
import ErrorState from "@/components/ErrorState";
import { buildTeamPageUrl } from "@/lib/teamUrls";
import { eventPath } from "@/lib/eventKey";
import type { SearchResponse, SearchSuggestion, SearchTeam } from "@/lib/types";

function SearchLoading() {
  return <LoadingState message="Loading search..." />;
}

function SuggestionChips({ suggestions }: { suggestions: SearchSuggestion[] }) {
  const router = useRouter();

  if (suggestions.length === 0) return null;

  return (
    <div className="mt-6">
      <h2 className="text-sm font-medium text-text-secondary mb-3">Right now</h2>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s, i) => (
          <button
            key={`${s.query}-${i}`}
            onClick={() => {
              if (s.type === "event" && s.event_id) {
                router.push(`/events/${s.event_id}`);
              } else if (s.type === "futures" && s.market_id) {
                router.push(`/futures/${s.market_id}`);
              } else {
                router.push(`/search?q=${encodeURIComponent(s.query)}`);
              }
            }}
            className="px-3 py-2 rounded-full bg-surface-card border border-surface-border text-sm text-text-primary hover:border-text-primary hover:bg-surface-elevated transition-colors text-left"
          >
            <span className="font-medium">{s.query}</span>
            <span className="text-text-secondary ml-1.5">{s.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function TeamCard({ team }: { team: SearchTeam }) {
  const url = buildTeamPageUrl(team.name, team.sport_key);
  if (!url) return null;

  const sportLabel = team.sport_key
    ? team.sport_key.split("_").slice(1).join(" ").toUpperCase()
    : null;

  return (
    <Link
      href={url}
      className="flex items-center gap-3 p-3 bg-surface-card border border-surface-border rounded-card hover:shadow-md hover:border-accent-brand/30 transition-all"
    >
      {team.logo ? (
        <img
          src={team.logo}
          alt=""
          className="w-10 h-10 object-contain flex-shrink-0"
          crossOrigin="anonymous"
        />
      ) : (
        <div className="w-10 h-10 rounded-lg bg-surface-elevated flex items-center justify-center text-sm font-bold text-text-muted flex-shrink-0">
          {team.abbreviation || team.name.charAt(0)}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-text-primary truncate">{team.name}</div>
        <div className="text-xs text-text-secondary">
          {team.record && <span>{team.record}</span>}
          {team.record && sportLabel && <span> · </span>}
          {sportLabel && <span>{sportLabel}</span>}
        </div>
      </div>
    </Link>
  );
}

function SectionHeader({ title, count }: { title: string; count: number }) {
  return (
    <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-3 flex items-center gap-2">
      <span>{title}</span>
      <span className="text-text-muted">({count})</span>
    </h2>
  );
}

function SearchContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const query = searchParams.get("q") || "";
  const sportFilter = searchParams.get("sport") || undefined;
  const pageParam = searchParams.get("page");
  const currentPage = pageParam ? parseInt(pageParam, 10) : 1;

  const { track } = useAnalytics();
  usePageTracking({ pageType: 'search', pageTitle: 'Search', deps: [query] });
  useScrollDepth({ pageType: 'search' });
  useEngagementTime({ pageType: 'search' });

  // SEARCH funnel step 1 (measurement_spec §2): fire once per mount when the
  // search surface opens, noting whether it opened already carrying a query.
  const searchOpenedRef = useRef(false);
  useEffect(() => {
    if (searchOpenedRef.current) return;
    searchOpenedRef.current = true;
    track('search_opened', { has_query: query.length >= 2, surface: 'search' });
  }, [query, track]);

  const [results, setResults] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);

  const { isPinned, togglePin, isMaxReached } = usePinnedEvents();
  const {
    isPinned: isFuturesPinned,
    togglePin: toggleFuturesPin,
    isMaxReached: isFuturesMaxReached
  } = usePinnedFutures();

  useEffect(() => {
    if (!query || query.length < 2) {
      setResults(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    searchEvents({
      q: query,
      sport: sportFilter,
      page: currentPage,
      per_page: 25,
    })
      .then((data) => {
        setResults(data);
        setIsLoading(false);
        track('search_submit', {
          query,
          results_count: data.results?.length ?? 0,
          futures_count: data.futures?.length ?? 0,
          surface: 'search',
        });
      })
      .catch((err) => {
        setError(err.message);
        setIsLoading(false);
      });
  }, [query, sportFilter, currentPage]);

  useEffect(() => {
    if (query && query.length >= 2) return;
    setSuggestionsLoading(true);
    fetchSearchSuggestions()
      .then((data) => {
        setSuggestions(data.suggestions);
        setSuggestionsLoading(false);
      })
      .catch(() => {
        setSuggestionsLoading(false);
      });
  }, [query]);

  const setFilter = (sport: string | undefined) => {
    const params = new URLSearchParams();
    params.set("q", query);
    if (sport) params.set("sport", sport);
    router.push(`/search?${params.toString()}`);
  };

  const goToPage = (page: number) => {
    const params = new URLSearchParams();
    params.set("q", query);
    if (sportFilter) params.set("sport", sportFilter);
    params.set("page", page.toString());
    router.push(`/search?${params.toString()}`);
  };

  // Zero-state
  if (!query || query.length < 2) {
    return (
      <div className="max-w-3xl mx-auto">
        {suggestionsLoading ? (
          <div className="text-center py-8">
            <p className="text-sm text-text-secondary">Loading suggestions...</p>
          </div>
        ) : (
          <SuggestionChips suggestions={suggestions} />
        )}
        <div className="mt-8">
          <CategoryBrowser />
        </div>
      </div>
    );
  }

  if (isLoading) {
    return <LoadingState message={`Searching for "${query}"...`} />;
  }

  if (error) {
    return (
      <ErrorState
        message={error}
        onRetry={() => window.location.reload()}
      />
    );
  }

  const hasTeams = results?.teams && results.teams.length > 0;
  const hasFutures = results?.futures && results.futures.length > 0;
  const hasEvents = results?.results && results.results.length > 0;
  // #999 L2-65: event concepts (tournament pages) as first-class results.
  const eventConcepts = results?.event_concepts ?? [];
  const hasEventConcepts = eventConcepts.length > 0;

  // #993 L2-42: composed families render first; the market_ids shown inside a
  // family (headline + its shown members) are filtered from the flat list so
  // nothing double-renders. Backend is the composition source of truth.
  const families = results?.futures_families ?? [];
  const shownIds = familyShownIds(families);
  const flatFutures = (results?.futures ?? []).filter((m) => !shownIds.has(m.id));
  const hasFamilies = families.length > 0;
  const hasFlatFutures = flatFutures.length > 0;

  if (!results || (!hasEvents && !hasFutures && !hasTeams && !hasEventConcepts)) {
    return (
      <div>
        <div className="text-center py-12">
          <div className="text-4xl mb-4">🤷</div>
          <h1 className="text-title-2 text-text-primary mb-2">No Results</h1>
          <p className="text-text-secondary">
            No teams, games, or markets found for &quot;{query}&quot;
            {sportFilter && ` in ${getLeagueDisplay(sportFilter)}`}
          </p>
          {sportFilter && (
            <button
              onClick={() => setFilter(undefined)}
              className="mt-4 text-sm text-text-primary underline hover:no-underline"
            >
              Clear sport filter
            </button>
          )}
        </div>
      </div>
    );
  }

  const totalCount = (results.teams?.length ?? 0)
    + (results.pagination?.total_results ?? 0)
    + (results.futures?.length ?? 0);

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <Link
          href="/"
          className="text-sm text-text-secondary hover:text-text-primary mb-2 inline-block"
        >
          ← Back
        </Link>
        <h1 className="text-title-1 text-text-primary">
          Results for &quot;{query}&quot;
        </h1>
        <p className="text-text-secondary mt-1">
          {totalCount} result{totalCount !== 1 ? "s" : ""}
          {hasTeams && ` · ${results.teams.length} team${results.teams.length !== 1 ? "s" : ""}`}
          {hasEvents && ` · ${results.pagination.total_results} game${results.pagination.total_results !== 1 ? "s" : ""}`}
          {hasFutures && ` · ${results.futures.length} market${results.futures.length !== 1 ? "s" : ""}`}
        </p>
      </div>

      {/* Fuzzy correction banner */}
      {results.did_you_mean && (
        <div className="mb-4 text-sm text-text-secondary">
          Showing results for <span className="font-medium text-text-primary">{results.did_you_mean}</span>
        </div>
      )}

      {/* Sport filters */}
      {results.sports.length > 1 && (
        <div className="mb-6 flex flex-wrap gap-2">
          <button
            onClick={() => setFilter(undefined)}
            className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
              !sportFilter
                ? "bg-text-primary text-surface-deep"
                : "bg-surface-card border border-surface-border text-text-secondary hover:border-text-primary"
            }`}
          >
            All
          </button>
          {results.sports.map((sport) => (
            <button
              key={sport.key}
              onClick={() => setFilter(sport.key)}
              className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors flex items-center gap-1 ${
                sportFilter === sport.key
                  ? "bg-text-primary text-surface-deep"
                  : "bg-surface-card border border-surface-border text-text-secondary hover:border-text-primary"
              }`}
            >
              <span>{getEmojiForLeague(sport.key)}</span>
              <span>{sport.name}</span>
              <span className="text-xs opacity-75">({sport.count})</span>
            </button>
          ))}
        </div>
      )}

      {/* Events section — tournament concept pages, first-class above markets (L2-65) */}
      {hasEventConcepts && (
        <section className="mb-8">
          <SectionHeader title="Events" count={eventConcepts.length} />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {eventConcepts.map((ec, index) => (
              <Link
                key={ec.key}
                href={eventPath(ec.key)}
                onClick={() => {
                  track("search_result_click", { query, result_type: "event_concept", result_id: ec.key, position: index, surface: "search" });
                  markSearchDestination({ query, result_type: "event_concept", result_id: ec.key, rank: index });
                }}
                className="flex items-center justify-between gap-2 rounded-card border border-surface-border bg-surface-card px-4 py-3 shadow-card hover:border-text-muted transition-colors group"
              >
                <div className="min-w-0">
                  <div className="text-[11px] uppercase tracking-wide text-text-muted">{ec.domain}</div>
                  <div className="text-sm font-semibold text-text-primary truncate group-hover:text-accent-brand transition-colors">
                    {ec.name}
                  </div>
                </div>
                <span className="text-text-muted group-hover:text-accent-brand transition-colors" aria-hidden="true">→</span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Teams section */}
      {hasTeams && (
        <section className="mb-8">
          <SectionHeader title="Teams" count={results.teams.length} />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {results.teams.map((team) => (
              <TeamCard key={team.id} team={team} />
            ))}
          </div>
        </section>
      )}

      {/* Games section */}
      {hasEvents && (
        <section className="mb-8">
          <SectionHeader title="Games" count={results.pagination.total_results} />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {results.results.map((event, index) => (
              <div key={event.id} onClick={() => {
                track('search_result_click', {
                  query: query,
                  result_type: 'event',
                  result_id: event.id,
                  position: index,
                  surface: 'search',
                });
                markSearchDestination({ query, result_type: 'event', result_id: event.id, rank: index });
              }}>
                <EventCard
                  event={event}
                  showSport={!sportFilter}
                  sourceSection="search_results"
                  positionIndex={index}
                  isPinned={isPinned(event.id)}
                  onPinToggle={togglePin}
                  pinDisabled={isMaxReached}
                />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* #993 L2-42: composed topical families (backend-composed) render first */}
      {hasFamilies && (
        <section className="mb-8">
          <SectionHeader title="Answers" count={families.length} />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {families.map((family) => (
              <SearchFamilyCard
                key={family.family_key}
                family={family}
                onRowClick={(result_type, result_id) => {
                  track('search_result_click', {
                    query: query,
                    result_type,
                    result_id,
                    position: 0,
                    surface: 'search',
                  });
                  markSearchDestination({ query, result_type, result_id, rank: 0 });
                }}
              />
            ))}
          </div>
        </section>
      )}

      {/* Futures & Markets section (flat — family-shown markets filtered out) */}
      {hasFlatFutures && (
        <section className="mb-8">
          <SectionHeader title="Futures & Markets" count={flatFutures.length} />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {flatFutures.map((market, index) => (
              <div key={market.id} onClick={() => {
                track('search_result_click', {
                  query: query,
                  result_type: 'futures',
                  result_id: market.id,
                  position: index,
                  surface: 'search',
                });
                markSearchDestination({ query, result_type: 'futures', result_id: market.id, rank: index });
              }}>
                <FuturesCard
                  market={market}
                  showSport={!sportFilter}
                  isPinned={isFuturesPinned(market.id)}
                  onPinToggle={toggleFuturesPin}
                  pinDisabled={isFuturesMaxReached}
                />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Pagination */}
      {results.pagination.total_pages > 1 && (
        <div className="mt-8 flex justify-center gap-2">
          <button
            onClick={() => goToPage(currentPage - 1)}
            disabled={!results.pagination.has_prev}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              results.pagination.has_prev
                ? "bg-surface-card border border-surface-border text-text-primary hover:bg-surface-elevated"
                : "bg-surface-deep text-text-muted cursor-not-allowed"
            }`}
          >
            ← Previous
          </button>
          <span className="px-4 py-2 text-sm text-text-secondary">
            Page {currentPage} of {results.pagination.total_pages}
          </span>
          <button
            onClick={() => goToPage(currentPage + 1)}
            disabled={!results.pagination.has_next}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              results.pagination.has_next
                ? "bg-surface-card border border-surface-border text-text-primary hover:bg-surface-elevated"
                : "bg-surface-deep text-text-muted cursor-not-allowed"
            }`}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<SearchLoading />}>
      <SearchContent />
    </Suspense>
  );
}
