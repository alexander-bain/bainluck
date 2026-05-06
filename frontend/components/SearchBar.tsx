"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { fetchTypeahead } from "@/lib/api";
import type { TypeaheadSuggestion } from "@/lib/api";
import { useAnalyticsContext } from "@/components/Analytics";
import { buildTeamPageUrl } from "@/lib/teamUrls";

const RECENT_SEARCHES_KEY = "bainluck_recent_searches";
const MAX_RECENT = 5;

function getRecentSearches(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(RECENT_SEARCHES_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveRecentSearch(q: string) {
  const cleaned = q.trim();
  if (!cleaned || cleaned.length < 2) return;
  const recent = getRecentSearches().filter((s) => s !== cleaned);
  recent.unshift(cleaned);
  try {
    localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(recent.slice(0, MAX_RECENT)));
  } catch {}
}

interface SearchBarProps {
  initialQuery?: string;
  placeholder?: string;
  compact?: boolean;
}

export default function SearchBar({
  initialQuery = "",
  placeholder = "Search teams, games, futures...",
  compact = false,
}: SearchBarProps) {
  const router = useRouter();
  const { track } = useAnalyticsContext();
  const [query, setQuery] = useState(initialQuery);
  const [suggestions, setSuggestions] = useState<TypeaheadSuggestion[]>([]);
  const [didYouMean, setDidYouMean] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [showRecent, setShowRecent] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [recentSearches, setRecentSearches] = useState<string[]>([]);

  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Load recent searches on mount
  useEffect(() => {
    setRecentSearches(getRecentSearches());
  }, []);

  // Cmd+K / Ctrl+K global shortcut
  useEffect(() => {
    function handleGlobalKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    }
    document.addEventListener("keydown", handleGlobalKey);
    return () => document.removeEventListener("keydown", handleGlobalKey);
  }, []);

  const fetchSuggestions = useCallback(async (q: string) => {
    if (q.length < 2) {
      setSuggestions([]);
      setIsOpen(false);
      return;
    }

    setLoading(true);
    setShowRecent(false);
    try {
      const data = await fetchTypeahead(q);
      setSuggestions(data.suggestions);
      setDidYouMean(data.did_you_mean ?? null);
      setIsOpen(data.suggestions.length > 0);
    } catch {
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchSuggestions(query);
    }, 200);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, fetchSuggestions]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
        setShowRecent(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const navigateToSearch = (q: string) => {
    saveRecentSearch(q);
    setRecentSearches(getRecentSearches());
    router.push(`/search?q=${encodeURIComponent(q)}`);
    setIsOpen(false);
    setShowRecent(false);
  };

  const selectSuggestion = (suggestion: TypeaheadSuggestion) => {
    setIsOpen(false);
    setShowRecent(false);
    setQuery("");

    saveRecentSearch(suggestion.text);
    setRecentSearches(getRecentSearches());

    const teamUrl = suggestion.team_slug
      ? buildTeamPageUrl(suggestion.text, suggestion.sport_key)
      : null;
    track('navigation_click', {
      click_type: 'search_typeahead' as const,
      from_page: 'search',
      to_page: suggestion.type === 'event' ? `/events/${suggestion.event_id}`
        : suggestion.type === 'futures' ? `/futures/${suggestion.market_id}`
        : teamUrl || `/search?q=${suggestion.text}`,
    });

    switch (suggestion.type) {
      case "team":
        if (teamUrl) {
          router.push(teamUrl);
        } else {
          router.push(`/search?q=${encodeURIComponent(suggestion.text)}`);
        }
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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (showRecent && recentSearches.length > 0) {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setSelectedIndex((prev) =>
            prev < recentSearches.length - 1 ? prev + 1 : prev
          );
          return;
        case "ArrowUp":
          e.preventDefault();
          setSelectedIndex((prev) => (prev > 0 ? prev - 1 : -1));
          return;
        case "Enter":
          e.preventDefault();
          if (selectedIndex >= 0 && recentSearches[selectedIndex]) {
            setQuery(recentSearches[selectedIndex]);
            setShowRecent(false);
          }
          return;
        case "Escape":
          setShowRecent(false);
          setSelectedIndex(-1);
          return;
      }
    }

    if (!isOpen) {
      if (e.key === "Enter" && query.length >= 2) {
        navigateToSearch(query);
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
          navigateToSearch(query);
        }
        break;
      case "Escape":
        setIsOpen(false);
        setSelectedIndex(-1);
        break;
    }
  };

  const handleFocus = () => {
    if (suggestions.length > 0) {
      setIsOpen(true);
    } else if (!query && recentSearches.length > 0) {
      setShowRecent(true);
      setSelectedIndex(-1);
    }
  };

  return (
    <div className="relative">
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSelectedIndex(-1);
            if (!e.target.value) setShowRecent(recentSearches.length > 0);
          }}
          onFocus={handleFocus}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className={`w-full bg-surface-elevated border border-surface-border rounded-full text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/30 focus:border-accent-brand/40 transition-colors ${
            compact ? "px-4 py-1.5 text-sm pr-16" : "px-5 py-2.5 text-base pr-20"
          }`}
        />
        <div
          className={`absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5 text-text-muted ${
            compact ? "text-sm" : "text-base"
          }`}
        >
          {loading ? (
            <span className="animate-pulse">...</span>
          ) : (
            <>
              <kbd className="hidden lg:inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-mono text-text-muted/60 bg-surface-card border border-surface-border rounded">
                <span className="text-[9px]">{"⌘"}</span>K
              </kbd>
              <span className="text-sm">{"\u{1F50D}"}</span>
            </>
          )}
        </div>
      </div>

      {/* Recent searches dropdown */}
      {showRecent && !isOpen && recentSearches.length > 0 && (
        <div
          ref={dropdownRef}
          className="absolute z-50 w-full min-w-[360px] sm:min-w-[480px] right-0 mt-1 bg-surface-card rounded-xl shadow-lg border border-surface-border overflow-hidden"
        >
          <div className="px-4 py-2 text-xs text-text-muted font-medium uppercase tracking-wide">
            Recent
          </div>
          {recentSearches.map((s, idx) => (
            <button
              key={s}
              onClick={() => {
                setQuery(s);
                setShowRecent(false);
              }}
              onMouseEnter={() => setSelectedIndex(idx)}
              className={`w-full text-left px-4 py-2 flex items-center gap-3 text-sm transition-colors ${
                idx === selectedIndex ? "bg-surface-elevated" : "hover:bg-surface-elevated/50"
              }`}
            >
              <span className="text-text-muted text-xs">{"\u{1F552}"}</span>
              <span className="text-text-primary">{s}</span>
            </button>
          ))}
        </div>
      )}

      {/* Typeahead dropdown */}
      {isOpen && suggestions.length > 0 && (
        <div
          ref={dropdownRef}
          className="absolute z-50 w-full min-w-[360px] sm:min-w-[480px] right-0 mt-1 bg-surface-card rounded-xl shadow-lg border border-surface-border overflow-hidden"
        >
          {didYouMean && (
            <button
              onClick={() => {
                setQuery(didYouMean);
                setDidYouMean(null);
              }}
              className="w-full text-left px-4 py-2 text-xs text-text-secondary border-b border-surface-border hover:bg-surface-elevated/50"
            >
              Showing results for <span className="font-medium text-text-primary">{didYouMean}</span>
            </button>
          )}
          {suggestions.map((suggestion, idx) => (
            <button
              key={`${suggestion.type}-${suggestion.text}-${idx}`}
              onClick={() => selectSuggestion(suggestion)}
              onMouseEnter={() => setSelectedIndex(idx)}
              className={`w-full text-left px-4 py-2.5 flex items-center gap-3 transition-colors ${
                idx === selectedIndex ? "bg-surface-elevated" : "hover:bg-surface-elevated/50"
              }`}
            >
              <span className="text-sm flex-shrink-0 w-5 text-center">
                {suggestion.type === "team" && (
                  suggestion.logo ? (
                    <img
                      src={suggestion.logo}
                      alt=""
                      className="w-5 h-5 rounded-sm"
                    />
                  ) : (
                    <span>{"\u{1F3C0}"}</span>
                  )
                )}
                {suggestion.type === "event" && (
                  suggestion.status === "live" ? (
                    <span className="text-red-500">{"\u{1F534}"}</span>
                  ) : (
                    <span>{"\u{1F4C5}"}</span>
                  )
                )}
                {suggestion.type === "futures" && <span>{"\u{1F4C8}"}</span>}
              </span>

              <div className="flex-1 min-w-0">
                <div className="text-sm text-text-primary truncate">
                  {suggestion.type === "futures"
                    ? formatFuturesName(suggestion.text)
                    : suggestion.text}
                </div>
                {suggestion.type === "event" && suggestion.commence_time && (
                  <div className="text-xs text-slate">
                    {suggestion.status === "live"
                      ? "Live now"
                      : formatEventTime(suggestion.commence_time)}
                  </div>
                )}
                {suggestion.type === "futures" && suggestion.market_type_label && (
                  <div className="text-xs text-accent-brand">{suggestion.market_type_label}</div>
                )}
              </div>

              <span className="text-xs text-text-muted flex-shrink-0">
                {suggestion.type === "team"
                  ? "Team"
                  : suggestion.type === "event"
                  ? "Game"
                  : "Futures"}
              </span>
            </button>
          ))}

          {query.length >= 2 && (
            <button
              onClick={() => navigateToSearch(query)}
              className="w-full text-left px-4 py-2 bg-surface-elevated/50 text-sm text-text-secondary hover:bg-surface-elevated border-t border-surface-border"
            >
              See all results for &ldquo;{query}&rdquo;
            </button>
          )}
        </div>
      )}
    </div>
  );
}


function formatFuturesName(name: string): string {
  return name
    .replace(/^(?:NBA|NHL|MLB|NFL|MLS|WNBA|PGA)\s+Playoffs?:\s*/i, "")
    .replace(/\s*\d{4}(-\d{2,4})?\s*$/, "")
    .trim();
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
