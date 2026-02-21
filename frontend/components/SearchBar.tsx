"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { fetchTypeahead } from "@/lib/api";
import type { TypeaheadSuggestion } from "@/lib/api";

interface SearchBarProps {
  /** Initial query value */
  initialQuery?: string;
  /** Placeholder text */
  placeholder?: string;
  /** Compact mode for header */
  compact?: boolean;
}

/**
 * SearchBar with typeahead suggestions.
 *
 * Shows matching teams, live/upcoming events, and futures markets
 * as the user types. Navigates to the appropriate page on selection.
 */
export default function SearchBar({
  initialQuery = "",
  placeholder = "Search teams, games, futures...",
  compact = false,
}: SearchBarProps) {
  const router = useRouter();
  const [query, setQuery] = useState(initialQuery);
  const [suggestions, setSuggestions] = useState<TypeaheadSuggestion[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [loading, setLoading] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Debounced fetch
  const fetchSuggestions = useCallback(async (q: string) => {
    if (q.length < 2) {
      setSuggestions([]);
      setIsOpen(false);
      return;
    }

    setLoading(true);
    try {
      const data = await fetchTypeahead(q);
      setSuggestions(data.suggestions);
      setIsOpen(data.suggestions.length > 0);
    } catch {
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounce input
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    debounceRef.current = setTimeout(() => {
      fetchSuggestions(query);
    }, 200);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, fetchSuggestions]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Navigate to a suggestion
  const selectSuggestion = (suggestion: TypeaheadSuggestion) => {
    setIsOpen(false);
    setQuery("");

    switch (suggestion.type) {
      case "team":
        router.push(`/search?q=${encodeURIComponent(suggestion.text)}`);
        break;
      case "event":
        if (suggestion.event_id) {
          router.push(`/events/${suggestion.event_id}`);
        }
        break;
      case "futures":
        if (suggestion.market_id) {
          router.push(`/futures/${suggestion.market_id}`);
        }
        break;
    }
  };

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === "Enter" && query.length >= 2) {
        router.push(`/search?q=${encodeURIComponent(query)}`);
        setIsOpen(false);
      }
      return;
    }

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setSelectedIndex((prev) =>
          prev < suggestions.length - 1 ? prev + 1 : prev
        );
        break;
      case "ArrowUp":
        e.preventDefault();
        setSelectedIndex((prev) => (prev > 0 ? prev - 1 : -1));
        break;
      case "Enter":
        e.preventDefault();
        if (selectedIndex >= 0 && suggestions[selectedIndex]) {
          selectSuggestion(suggestions[selectedIndex]);
        } else if (query.length >= 2) {
          router.push(`/search?q=${encodeURIComponent(query)}`);
          setIsOpen(false);
        }
        break;
      case "Escape":
        setIsOpen(false);
        setSelectedIndex(-1);
        break;
    }
  };

  return (
    <div className="relative">
      {/* Input */}
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSelectedIndex(-1);
          }}
          onFocus={() => {
            if (suggestions.length > 0) setIsOpen(true);
          }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className={`w-full bg-white border border-mist rounded-full text-graphite placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-graphite/20 focus:border-graphite/40 transition-colors ${
            compact ? "px-4 py-1.5 text-sm" : "px-5 py-2.5 text-base"
          }`}
        />
        {/* Search icon */}
        <div
          className={`absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 ${
            compact ? "text-sm" : "text-base"
          }`}
        >
          {loading ? (
            <span className="animate-pulse">...</span>
          ) : (
            <span>&#x1f50d;</span>
          )}
        </div>
      </div>

      {/* Dropdown */}
      {isOpen && suggestions.length > 0 && (
        <div
          ref={dropdownRef}
          className="absolute z-50 w-full mt-1 bg-white rounded-xl shadow-lg border border-mist overflow-hidden"
        >
          {suggestions.map((suggestion, idx) => (
            <button
              key={`${suggestion.type}-${suggestion.text}-${idx}`}
              onClick={() => selectSuggestion(suggestion)}
              onMouseEnter={() => setSelectedIndex(idx)}
              className={`w-full text-left px-4 py-2.5 flex items-center gap-3 transition-colors ${
                idx === selectedIndex ? "bg-snow" : "hover:bg-snow/50"
              }`}
            >
              {/* Type icon */}
              <span className="text-sm flex-shrink-0 w-5 text-center">
                {suggestion.type === "team" && (
                  suggestion.logo ? (
                    <img
                      src={suggestion.logo}
                      alt=""
                      className="w-5 h-5 rounded-sm"
                    />
                  ) : (
                    "&#x1f3c0;"
                  )
                )}
                {suggestion.type === "event" && (
                  suggestion.status === "live" ? (
                    <span className="text-red-500">&#x1f534;</span>
                  ) : (
                    "&#x1f4c5;"
                  )
                )}
                {suggestion.type === "futures" && "&#x1f4c8;"}
              </span>

              {/* Text */}
              <div className="flex-1 min-w-0">
                <div className="text-sm text-graphite truncate">
                  {suggestion.text}
                </div>
                {/* Subtitle */}
                {suggestion.type === "event" && suggestion.commence_time && (
                  <div className="text-xs text-slate">
                    {suggestion.status === "live"
                      ? "Live now"
                      : formatEventTime(suggestion.commence_time)}
                  </div>
                )}
                {suggestion.type === "futures" && suggestion.market_tier === 1 && (
                  <div className="text-xs text-purple-500">Championship</div>
                )}
              </div>

              {/* Type badge */}
              <span className="text-xs text-gray-400 flex-shrink-0">
                {suggestion.type === "team"
                  ? "Team"
                  : suggestion.type === "event"
                  ? "Game"
                  : "Futures"}
              </span>
            </button>
          ))}

          {/* Footer: full search link */}
          {query.length >= 2 && (
            <button
              onClick={() => {
                router.push(`/search?q=${encodeURIComponent(query)}`);
                setIsOpen(false);
              }}
              className="w-full text-left px-4 py-2 bg-snow/50 text-sm text-slate hover:bg-snow border-t border-mist"
            >
              See all results for &ldquo;{query}&rdquo;
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function formatEventTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffHours = diffMs / (1000 * 60 * 60);

  if (diffHours < 0) return "Recently";
  if (diffHours < 1) return `In ${Math.round(diffHours * 60)} min`;
  if (diffHours < 24) {
    return date.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
    });
  }

  return date.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
