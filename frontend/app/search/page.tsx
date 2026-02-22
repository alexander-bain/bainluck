"use client";

import { Suspense, useState, useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { searchEvents, fetchSearchSuggestions } from "@/lib/api";
import { getLeagueDisplay, getEmojiForLeague } from "@/lib/sportCategories";
import { usePinnedEvents, usePinnedFutures } from "@/hooks";
import EventCard from "@/components/EventCard";
import FuturesCard from "@/components/FuturesCard";
import SearchBar from "@/components/SearchBar";
import type { SearchResponse, SearchSuggestion } from "@/lib/types";

function SearchLoading() {
  return (
    <div className="text-center py-12">
      <div className="text-4xl mb-4 animate-pulse">🔍</div>
      <p className="text-text-secondary">Loading search...</p>
    </div>
  );
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

function SearchContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const query = searchParams.get("q") || "";
  const sportFilter = searchParams.get("sport") || undefined;
  const pageParam = searchParams.get("page");
  const currentPage = pageParam ? parseInt(pageParam, 10) : 1;

  const [results, setResults] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);

  // Pinned events
  const { isPinned, togglePin, isMaxReached } = usePinnedEvents();

  // Pinned futures
  const {
    isPinned: isFuturesPinned,
    togglePin: toggleFuturesPin,
    isMaxReached: isFuturesMaxReached
  } = usePinnedFutures();

  // Fetch search results
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
      })
      .catch((err) => {
        setError(err.message);
        setIsLoading(false);
      });
  }, [query, sportFilter, currentPage]);

  // Fetch suggestions when no query
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

  // Update URL when changing filters
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

  // Zero-state: no query or too short
  if (!query || query.length < 2) {
    return (
      <div className="max-w-xl mx-auto">
        <div className="mb-6">
          <SearchBar initialQuery={query} />
        </div>
        {suggestionsLoading ? (
          <div className="text-center py-8">
            <p className="text-sm text-text-secondary">Loading suggestions...</p>
          </div>
        ) : (
          <SuggestionChips suggestions={suggestions} />
        )}
      </div>
    );
  }

  if (isLoading) {
    return (
      <div>
        <div className="max-w-xl mx-auto mb-6">
          <SearchBar initialQuery={query} />
        </div>
        <div className="text-center py-12">
          <div className="text-4xl mb-4 animate-pulse">🔍</div>
          <p className="text-text-secondary">Searching for &quot;{query}&quot;...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <div className="max-w-xl mx-auto mb-6">
          <SearchBar initialQuery={query} />
        </div>
        <div className="text-center py-12">
          <div className="text-4xl mb-4">⚠️</div>
          <h1 className="text-title-2 text-text-primary mb-2">Search Error</h1>
          <p className="text-text-secondary">{error}</p>
        </div>
      </div>
    );
  }

  const hasFutures = results?.futures && results.futures.length > 0;
  const hasEvents = results?.results && results.results.length > 0;

  if (!results || (!hasEvents && !hasFutures)) {
    return (
      <div>
        <div className="max-w-xl mx-auto mb-6">
          <SearchBar initialQuery={query} />
        </div>
        <div className="text-center py-12">
          <div className="text-4xl mb-4">🤷</div>
          <h1 className="text-title-2 text-text-primary mb-2">No Results</h1>
          <p className="text-text-secondary">
            No games or futures found for &quot;{query}&quot;
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

  return (
    <div>
      {/* Search bar */}
      <div className="max-w-xl mx-auto mb-6">
        <SearchBar initialQuery={query} />
      </div>

      {/* Header */}
      <div className="mb-6">
        <Link
          href="/"
          className="text-sm text-text-secondary hover:text-text-primary mb-2 inline-block"
        >
          ← Back to all games
        </Link>
        <h1 className="text-title-1 text-text-primary">
          Search results for &quot;{query}&quot;
        </h1>
        <p className="text-text-secondary mt-1">
          {results.pagination.total_results} game{results.pagination.total_results !== 1 ? "s" : ""}
          {hasFutures && ` and ${results.futures.length} futures market${results.futures.length !== 1 ? "s" : ""}`} found
        </p>
      </div>

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
            All ({results.pagination.total_results})
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

      {/* Futures results */}
      {hasFutures && (
        <div className="mb-8">
          <h2 className="text-title-3 text-text-primary mb-4 flex items-center gap-2">
            <span>Futures & Championships</span>
            <span className="text-sm font-normal text-text-secondary">
              ({results.futures.length})
            </span>
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {results.futures.map((market) => (
              <FuturesCard
                key={market.id}
                market={market}
                showSport={!sportFilter}
                isPinned={isFuturesPinned(market.id)}
                onPinToggle={toggleFuturesPin}
                pinDisabled={isFuturesMaxReached}
              />
            ))}
          </div>
        </div>
      )}

      {/* Events results grid */}
      {hasEvents && (
        <>
          {hasFutures && (
            <h2 className="text-title-3 text-text-primary mb-4 flex items-center gap-2">
              <span>Games</span>
              <span className="text-sm font-normal text-text-secondary">
                ({results.pagination.total_results})
              </span>
            </h2>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {results.results.map((event, index) => (
              <EventCard
                key={event.id}
                event={event}
                showSport={!sportFilter}
                sourceSection="search_results"
                positionIndex={index}
                isPinned={isPinned(event.id)}
                onPinToggle={togglePin}
                pinDisabled={isMaxReached}
              />
            ))}
          </div>
        </>
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
