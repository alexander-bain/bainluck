"use client";

import { Suspense, useState, useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { searchEvents } from "@/lib/api";
import { getLeagueDisplay, getEmojiForLeague } from "@/lib/sportCategories";
import EventCard from "@/components/EventCard";
import type { SearchResponse } from "@/lib/types";

function SearchLoading() {
  return (
    <div className="text-center py-12">
      <div className="text-4xl mb-4 animate-pulse">🔍</div>
      <p className="text-slate">Loading search...</p>
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

  if (!query || query.length < 2) {
    return (
      <div className="text-center py-12">
        <div className="text-4xl mb-4">🔍</div>
        <h1 className="text-title-2 text-graphite mb-2">Search for Teams</h1>
        <p className="text-slate">
          Enter at least 2 characters to search for games by team name
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="text-center py-12">
        <div className="text-4xl mb-4 animate-pulse">🔍</div>
        <p className="text-slate">Searching for &quot;{query}&quot;...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <div className="text-4xl mb-4">⚠️</div>
        <h1 className="text-title-2 text-graphite mb-2">Search Error</h1>
        <p className="text-slate">{error}</p>
      </div>
    );
  }

  if (!results || results.results.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="text-4xl mb-4">🤷</div>
        <h1 className="text-title-2 text-graphite mb-2">No Results</h1>
        <p className="text-slate">
          No games found for &quot;{query}&quot;
          {sportFilter && ` in ${getLeagueDisplay(sportFilter)}`}
        </p>
        {sportFilter && (
          <button
            onClick={() => setFilter(undefined)}
            className="mt-4 text-sm text-graphite underline hover:no-underline"
          >
            Clear sport filter
          </button>
        )}
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <Link
          href="/"
          className="text-sm text-slate hover:text-graphite mb-2 inline-block"
        >
          ← Back to all games
        </Link>
        <h1 className="text-title-1 text-graphite">
          Search results for &quot;{query}&quot;
        </h1>
        <p className="text-slate mt-1">
          {results.pagination.total_results} games found
        </p>
      </div>

      {/* Sport filters */}
      {results.sports.length > 1 && (
        <div className="mb-6 flex flex-wrap gap-2">
          <button
            onClick={() => setFilter(undefined)}
            className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
              !sportFilter
                ? "bg-graphite text-white"
                : "bg-white border border-mist text-slate hover:border-graphite"
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
                  ? "bg-graphite text-white"
                  : "bg-white border border-mist text-slate hover:border-graphite"
              }`}
            >
              <span>{getEmojiForLeague(sport.key)}</span>
              <span>{sport.name}</span>
              <span className="text-xs opacity-75">({sport.count})</span>
            </button>
          ))}
        </div>
      )}

      {/* Results grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {results.results.map((event, index) => (
          <EventCard
            key={event.id}
            event={event}
            showSport={!sportFilter}
            sourceSection="search_results"
            positionIndex={index}
          />
        ))}
      </div>

      {/* Pagination */}
      {results.pagination.total_pages > 1 && (
        <div className="mt-8 flex justify-center gap-2">
          <button
            onClick={() => goToPage(currentPage - 1)}
            disabled={!results.pagination.has_prev}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              results.pagination.has_prev
                ? "bg-white border border-mist text-graphite hover:bg-snow"
                : "bg-snow text-silver cursor-not-allowed"
            }`}
          >
            ← Previous
          </button>
          <span className="px-4 py-2 text-sm text-slate">
            Page {currentPage} of {results.pagination.total_pages}
          </span>
          <button
            onClick={() => goToPage(currentPage + 1)}
            disabled={!results.pagination.has_next}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              results.pagination.has_next
                ? "bg-white border border-mist text-graphite hover:bg-snow"
                : "bg-snow text-silver cursor-not-allowed"
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
