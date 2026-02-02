"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { searchEvents, formatProbability } from "@/lib/api";
import { getLeagueDisplay, getEmojiForLeague } from "@/lib/sportCategories";
import type { Event, SearchResponse } from "@/lib/types";

/**
 * SearchBox component for the header
 * - Debounced search as user types
 * - Dropdown with quick results
 * - Click result to go to event detail
 * - Press Enter or click "View all" to go to full search page
 */
export default function SearchBox() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  // Debounced search
  useEffect(() => {
    if (query.length < 2) {
      setResults(null);
      setIsOpen(false);
      return;
    }

    const timer = setTimeout(async () => {
      setIsLoading(true);
      try {
        const data = await searchEvents({ q: query, per_page: 5 });
        setResults(data);
        setIsOpen(true);
      } catch (error) {
        console.error("Search failed:", error);
        setResults(null);
      } finally {
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && query.length >= 2) {
      setIsOpen(false);
      router.push(`/search?q=${encodeURIComponent(query)}`);
    } else if (e.key === "Escape") {
      setIsOpen(false);
      inputRef.current?.blur();
    }
  }, [query, router]);

  // Format game time compactly
  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();

    if (isToday) {
      return date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    }
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  return (
    <div ref={containerRef} className="relative">
      {/* Search Input */}
      <div className={`flex items-center gap-2 bg-snow border rounded-full px-3 py-1.5 transition-all ${
        isFocused ? "border-graphite shadow-sm" : "border-mist"
      }`}>
        <span className="text-slate text-sm">
          {isLoading ? "..." : "🔍"}
        </span>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            setIsFocused(true);
            if (results && query.length >= 2) setIsOpen(true);
          }}
          onBlur={() => setIsFocused(false)}
          onKeyDown={handleKeyDown}
          placeholder="Search teams..."
          className="bg-transparent outline-none text-body text-graphite placeholder:text-silver w-32 sm:w-48 lg:w-56"
        />
        {query && (
          <button
            onClick={() => {
              setQuery("");
              setResults(null);
              setIsOpen(false);
              inputRef.current?.focus();
            }}
            className="text-slate hover:text-graphite transition-colors"
          >
            ✕
          </button>
        )}
      </div>

      {/* Dropdown Results */}
      {isOpen && results && (
        <div className="absolute top-full right-0 mt-2 w-80 sm:w-96 bg-white border border-mist rounded-lg shadow-lg overflow-hidden z-50">
          {results.results.length === 0 ? (
            <div className="p-4 text-center text-slate">
              No results for &quot;{query}&quot;
            </div>
          ) : (
            <>
              {/* Sport filter pills if multiple sports */}
              {results.sports.length > 1 && (
                <div className="px-3 py-2 border-b border-mist bg-snow flex gap-2 flex-wrap">
                  {results.sports.map((sport) => (
                    <span
                      key={sport.key}
                      className="text-xs bg-white border border-mist px-2 py-0.5 rounded-full text-slate"
                    >
                      {getEmojiForLeague(sport.key)} {sport.name} ({sport.count})
                    </span>
                  ))}
                </div>
              )}

              {/* Results list */}
              <div className="max-h-80 overflow-y-auto">
                {results.results.map((event) => (
                  <SearchResultItem key={event.id} event={event} formatTime={formatTime} onClick={() => setIsOpen(false)} />
                ))}
              </div>

              {/* Footer with "View all" link */}
              {results.pagination.total_results > 5 && (
                <Link
                  href={`/search?q=${encodeURIComponent(query)}`}
                  className="block px-4 py-3 bg-snow border-t border-mist text-center text-sm font-medium text-graphite hover:bg-mist/30 transition-colors"
                  onClick={() => setIsOpen(false)}
                >
                  View all {results.pagination.total_results} results →
                </Link>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Individual search result item
 */
function SearchResultItem({
  event,
  formatTime,
  onClick,
}: {
  event: Event;
  formatTime: (iso: string) => string;
  onClick: () => void;
}) {
  const isLive = event.status === "live";
  const isFinished = event.status === "completed" || event.status === "closed";
  const homeProb = event.current_odds?.home_probability;
  const awayProb = event.current_odds?.away_probability;

  return (
    <Link
      href={`/events/${event.id}`}
      className="block px-4 py-3 hover:bg-snow border-b border-mist/50 last:border-b-0 transition-colors"
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-3">
        {/* Teams and status */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            {event.sport && (
              <span className="text-xs text-slate">
                {getEmojiForLeague(event.sport)} {getLeagueDisplay(event.sport)}
              </span>
            )}
            {isLive && (
              <span className="flex items-center gap-1 bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded text-xs font-semibold">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                LIVE
              </span>
            )}
            {isFinished && (
              <span className="text-xs text-slate">Final</span>
            )}
          </div>
          <div className="text-sm font-medium text-graphite truncate">
            {event.home_team} vs {event.away_team}
          </div>
          <div className="text-xs text-slate mt-0.5">
            {isFinished && event.home_score !== null
              ? `${event.home_score} - ${event.away_score}`
              : formatTime(event.commence_time)}
          </div>
        </div>

        {/* Probabilities */}
        {homeProb !== null && homeProb !== undefined && (
          <div className="text-right shrink-0">
            <div className="text-sm font-mono font-semibold text-graphite">
              {formatProbability(homeProb)}
            </div>
            <div className="text-sm font-mono text-slate">
              {formatProbability(awayProb)}
            </div>
          </div>
        )}
      </div>
    </Link>
  );
}
