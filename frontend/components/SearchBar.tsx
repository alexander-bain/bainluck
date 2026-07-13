"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { fetchTypeahead, fetchTrendingSearches } from "@/lib/api";
import type { TypeaheadSuggestion } from "@/lib/api";
import { useAnalyticsContext } from "@/components/Analytics";
import { buildTeamPageUrl } from "@/lib/teamUrls";
import { eventPath } from "@/lib/eventKey";
import { matchCuratedConcepts } from "@/lib/curatedConcepts";

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
  const [trendingSearches, setTrendingSearches] = useState<string[]>([]);

  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Load recent searches on mount; trending cached for 5 min
  useEffect(() => {
    setRecentSearches(getRecentSearches());
    const TRENDING_CACHE_KEY = "bainluck:trending";
    const TRENDING_TTL = 300_000;
    const cached = sessionStorage.getItem(TRENDING_CACHE_KEY);
    if (cached) {
      try {
        const { data, ts } = JSON.parse(cached);
        if (Date.now() - ts < TRENDING_TTL) { setTrendingSearches(data); return; }
      } catch {}
    }
    fetchTrendingSearches()
      .then((res) => {
        const top = res.trending.map((t) => t.query).slice(0, 5);
        setTrendingSearches(top);
        sessionStorage.setItem(TRENDING_CACHE_KEY, JSON.stringify({ data: top, ts: Date.now() }));
      })
      .catch(() => {});
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
    // L2-96: curated concept hubs (e.g. "midterms" → the 2026 elections page)
    // whose phrase no market NAME contains, so the backend won't derive them.
    const curated = matchCuratedConcepts(q);
    try {
      const data = await fetchTypeahead(q);
      const backendKeys = new Set(
        data.suggestions.filter((s) => s.event_key).map((s) => s.event_key)
      );
      const merged = [
        ...curated.filter((c) => !backendKeys.has(c.event_key)),
        ...data.suggestions,
      ];
      setSuggestions(merged);
      setDidYouMean(data.did_you_mean ?? null);
      setIsOpen(merged.length > 0);
      // #993 Slice A: measure real exposure of the answer-in-typeahead so the
      // Alex-test interviews can be cross-checked against it.
      const withAnswer = data.suggestions.filter(
        (s) => s.type === "futures" && (s.top_outcomes ?? []).some((o) => o.probability != null)
      ).length;
      if (withAnswer > 0) {
        track("answer_visible_typeahead", { query: q, answers_shown: withAnswer });
      }
    } catch {
      // Backend down/slow: still surface curated hubs so discovery survives.
      setSuggestions(curated);
      setIsOpen(curated.length > 0);
    } finally {
      setLoading(false);
    }
  }, [track]);

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
        : suggestion.type === 'event_concept' ? (suggestion.event_key ? eventPath(suggestion.event_key) : `/search?q=${suggestion.text}`)
        : suggestion.type === 'hub' ? (suggestion.href || `/hub/${suggestion.competition}`)
        : suggestion.type === 'futures' ? `/futures/${suggestion.market_id}`
        : teamUrl || `/search?q=${suggestion.text}`,
    });

    switch (suggestion.type) {
      case "hub":
        // L2-88: competition-hub landing shortcut (/hub/<slug>).
        router.push(suggestion.href || `/hub/${suggestion.competition ?? ""}`);
        break;
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
      case "event_concept":
        // L2-65: tournament concept page (/event/[key]).
        if (suggestion.event_key) {
          router.push(eventPath(suggestion.event_key));
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
    } else if (!query && (recentSearches.length > 0 || trendingSearches.length > 0)) {
      setShowRecent(true);
      setSelectedIndex(-1);
    }
  };

  return (
    <div className="relative" role="search" aria-label="Site search">
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
          aria-label="Search teams, games, and futures"
          aria-autocomplete="list"
          aria-expanded={isOpen || showRecent}
          role="combobox"
          autoComplete="off"
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

      {/* Recent + trending searches dropdown */}
      {showRecent && !isOpen && (recentSearches.length > 0 || trendingSearches.length > 0) && (
        <div
          ref={dropdownRef}
          className="absolute z-50 w-full min-w-[360px] sm:min-w-[480px] right-0 mt-1 bg-surface-card rounded-xl shadow-lg border border-surface-border overflow-hidden"
          role="listbox"
          aria-label="Search suggestions"
        >
          {recentSearches.length > 0 && (
            <>
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
            </>
          )}
          {trendingSearches.length > 0 && (
            <>
              <div className="px-4 py-2 text-xs text-text-muted font-medium uppercase tracking-wide border-t border-surface-border">
                Trending
              </div>
              <div className="px-4 pb-3 flex flex-wrap gap-1.5">
                {trendingSearches.map((t) => (
                  <button
                    key={t}
                    onClick={() => {
                      setQuery(t);
                      setShowRecent(false);
                    }}
                    className="px-3 py-1 text-xs font-medium rounded-full bg-surface-elevated text-text-secondary hover:text-text-primary hover:bg-surface-border transition-colors"
                  >
                    {t}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Typeahead dropdown */}
      {isOpen && suggestions.length > 0 && (
        <div
          ref={dropdownRef}
          className="absolute z-50 w-full min-w-[360px] sm:min-w-[480px] right-0 mt-1 bg-surface-card rounded-xl shadow-lg border border-surface-border overflow-hidden"
          role="listbox"
          aria-label="Search results"
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
              role="option"
              aria-selected={idx === selectedIndex}
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
                {suggestion.type === "event_concept" && <span>{"\u{1F3C6}"}</span>}
                {suggestion.type === "hub" && <span>{suggestion.emoji || "\u{1F3DF}"}</span>}
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
                {suggestion.type === "event_concept" && (
                  <div className="text-xs text-slate">
                    Event{suggestion.sport_key ? ` · ${suggestion.sport_key}` : ""}
                  </div>
                )}
                {suggestion.type === "hub" && (
                  <div className="text-xs text-slate">Browse all markets</div>
                )}
                {suggestion.type === "futures" && (() => {
                  // #993 Slice A: lead with the answer — leader + probability
                  // (already #23-normalized server-side), then the runner-up as
                  // space allows, with a movement arrow when |Δ24h| ≥ 2pts.
                  const outs = (suggestion.top_outcomes ?? []).filter(
                    (o) => o.probability != null
                  );
                  if (outs.length > 0) {
                    const leader = outs[0];
                    const second = outs[1];
                    const mv = leader.movement ?? 0;
                    return (
                      <div className="text-xs text-text-secondary truncate">
                        <span className="text-text-primary font-medium">
                          {leader.name} {Math.round((leader.probability as number) * 100)}%
                        </span>
                        {Math.abs(mv) >= 0.02 && (
                          <span className={mv > 0 ? "text-accent-live" : "text-accent-danger"}>
                            {" "}{mv > 0 ? "↑" : "↓"}{Math.abs(Math.round(mv * 100))}
                          </span>
                        )}
                        {second && (
                          <span className="text-text-muted">
                            {" · "}{second.name} {Math.round((second.probability as number) * 100)}%
                          </span>
                        )}
                      </div>
                    );
                  }
                  return suggestion.market_type_label ? (
                    <div className="text-xs text-accent-brand">{suggestion.market_type_label}</div>
                  ) : null;
                })()}
              </div>

              <span className="text-xs text-text-muted flex-shrink-0">
                {suggestion.type === "team"
                  ? "Team"
                  : suggestion.type === "event"
                  ? "Game"
                  : suggestion.type === "hub"
                  ? "Hub"
                  : suggestion.type === "event_concept"
                  ? "Event"
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
