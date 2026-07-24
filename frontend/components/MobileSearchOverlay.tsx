"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { fetchTypeahead } from "@/lib/api";
import type { TypeaheadSuggestion } from "@/lib/api";
import { buildTeamPageUrl } from "@/lib/teamUrls";
import { eventPath } from "@/lib/eventKey";
import { matchCuratedConcepts } from "@/lib/curatedConcepts";
import { getRecentSearches, saveRecentSearch } from "@/lib/recentSearches";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export default function MobileSearchOverlay({ isOpen, onClose }: Props) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<TypeaheadSuggestion[]>([]);
  const [didYouMean, setDidYouMean] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);
  // Aborts the previous in-flight typeahead so a slow earlier keystroke can't
  // clobber the results of a newer one (the mobile stale-response race — the
  // desktop SearchBar was already guarded, mobile was not). L2-178.
  const typeaheadAbortRef = useRef<AbortController | null>(null);
  const recentSearches = getRecentSearches();

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
      setQuery("");
      setSuggestions([]);
    }
    return () => { document.body.style.overflow = ""; };
  }, [isOpen]);

  const fetchSuggestions = useCallback(async (q: string) => {
    if (q.length < 2) {
      setSuggestions([]);
      return;
    }
    // Cancel any in-flight typeahead so stale results can't overwrite fresh ones.
    typeaheadAbortRef.current?.abort();
    const controller = new AbortController();
    typeaheadAbortRef.current = controller;

    setLoading(true);
    // L2-96: curated concept hubs (e.g. "midterms") not derivable from market names.
    const curated = matchCuratedConcepts(q);
    try {
      const data = await fetchTypeahead(q, controller.signal);
      const backendKeys = new Set(
        data.suggestions.filter((s) => s.event_key).map((s) => s.event_key)
      );
      setSuggestions([
        ...curated.filter((c) => !backendKeys.has(c.event_key)),
        ...data.suggestions,
      ]);
      setDidYouMean(data.did_you_mean ?? null);
    } catch (err) {
      // A newer keystroke aborted this request — a fresher one owns the state.
      if (err instanceof DOMException && err.name === "AbortError") return;
      setSuggestions(curated);
    } finally {
      // Only the latest request clears the spinner; a superseded (aborted)
      // request must not turn it off out from under the fresh one.
      if (typeaheadAbortRef.current === controller) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(query), 200);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, fetchSuggestions]);

  const navigate = (url: string, searchText?: string) => {
    if (searchText) saveRecentSearch(searchText);
    onClose();
    router.push(url);
  };

  const selectSuggestion = (s: TypeaheadSuggestion) => {
    saveRecentSearch(s.text);
    onClose();
    switch (s.type) {
      case "team": {
        const url = s.team_slug ? buildTeamPageUrl(s.text, s.sport_key) : null;
        router.push(url || `/search?q=${encodeURIComponent(s.text)}`);
        break;
      }
      case "event":
        if (s.event_id) router.push(`/events/${s.event_id}`);
        break;
      case "futures":
        if (s.market_id) router.push(`/futures/${s.market_id}`);
        break;
      case "event_concept":
        // L2-96: event-concept hub page (/event/[key]) — was previously a no-op
        // on mobile, so concept suggestions (tournaments, elections) dead-clicked.
        if (s.event_key) router.push(eventPath(s.event_key));
        break;
      case "hub":
        // L2-88 parity with desktop: competition-hub landing shortcut.
        router.push(s.href || `/hub/${s.competition ?? ""}`);
        break;
    }
  };

  if (!isOpen) return null;

  const showRecent = !query && recentSearches.length > 0;

  return (
    <div className="fixed inset-0 z-[100] bg-surface-deep flex flex-col" role="dialog" aria-label="Search" aria-modal="true">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 pt-safe-top pb-3 border-b border-surface-border bg-surface-card" role="search">
        <div className="flex-1 relative">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && query.length >= 2) {
                navigate(`/search?q=${encodeURIComponent(query)}`, query);
              }
            }}
            placeholder="Search teams, games, futures..."
            aria-label="Search teams, games, and futures"
            className="w-full bg-surface-elevated border border-surface-border rounded-full px-4 py-2.5 text-base text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/30"
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
          />
          {loading && (
            <span className="absolute right-4 top-1/2 -translate-y-1/2 text-text-muted animate-pulse">...</span>
          )}
        </div>
        <button
          onClick={onClose}
          aria-label="Close search"
          className="text-sm font-medium text-text-secondary hover:text-text-primary px-1"
        >
          Cancel
        </button>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto">
        {/* Did you mean */}
        {didYouMean && (
          <button
            onClick={() => { setQuery(didYouMean); setDidYouMean(null); }}
            className="w-full text-left px-5 py-3 text-sm text-text-secondary border-b border-surface-border"
          >
            Showing results for <span className="font-medium text-text-primary">{didYouMean}</span>
          </button>
        )}

        {/* Recent searches */}
        {showRecent && (
          <div>
            <div className="px-5 pt-4 pb-2 text-xs text-text-muted font-medium uppercase tracking-wide">
              Recent
            </div>
            {recentSearches.map((s) => (
              <button
                key={s}
                onClick={() => setQuery(s)}
                className="w-full text-left px-5 py-3 flex items-center gap-3 hover:bg-surface-elevated/50 active:bg-surface-elevated"
              >
                <span className="text-text-muted text-sm">{"\u{1F552}"}</span>
                <span className="text-text-primary text-base">{s}</span>
              </button>
            ))}
          </div>
        )}

        {/* Suggestions */}
        {suggestions.map((s, idx) => (
          <button
            key={`${s.type}-${s.text}-${idx}`}
            onClick={() => selectSuggestion(s)}
            className="w-full text-left px-5 py-3 flex items-center gap-3 hover:bg-surface-elevated/50 active:bg-surface-elevated"
          >
            <span className="text-base flex-shrink-0 w-6 text-center">
              {s.type === "team" && (s.logo ? <img src={s.logo} alt="" className="w-6 h-6 rounded-sm" /> : "\u{1F3C0}")}
              {s.type === "event" && (s.status === "live" ? <span className="text-red-500">{"\u{1F534}"}</span> : "\u{1F4C5}")}
              {s.type === "futures" && "\u{1F4C8}"}
              {s.type === "event_concept" && "\u{1F3C6}"}
              {s.type === "hub" && (s.emoji || "\u{1F3DF}")}
            </span>
            <div className="flex-1 min-w-0">
              <div className="text-base text-text-primary truncate">{s.text}</div>
              {s.type === "event" && s.commence_time && (
                <div className="text-xs text-text-muted mt-0.5">
                  {s.status === "live" ? "Live now" : new Date(s.commence_time).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}
                </div>
              )}
              {s.type === "futures" && s.market_type_label && (
                <div className="text-xs text-accent-brand mt-0.5">{s.market_type_label}</div>
              )}
            </div>
            <span className="text-xs text-text-muted flex-shrink-0">
              {s.type === "team"
                ? "Team"
                : s.type === "event"
                ? "Game"
                : s.type === "event_concept"
                ? "Event"
                : s.type === "hub"
                ? "Hub"
                : "Futures"}
            </span>
          </button>
        ))}

        {/* Full search link */}
        {query.length >= 2 && (
          <button
            onClick={() => navigate(`/search?q=${encodeURIComponent(query)}`, query)}
            className="w-full text-left px-5 py-3 text-base text-text-secondary hover:bg-surface-elevated/50 border-t border-surface-border"
          >
            See all results for &ldquo;{query}&rdquo;
          </button>
        )}
      </div>
    </div>
  );
}
