"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import useSWR from "swr";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
  usePinnedEvents,
  usePinnedFutures,
} from "@/hooks";
import EventCard from "@/components/EventCard";
import FuturesCard from "@/components/FuturesCard";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────

interface FacetTag {
  tag: string;
  count: number;
}

interface FacetedEventsResponse {
  total: number;
  page: number;
  per_page: number;
  filters: string[];
  events: Record<string, unknown>[];
  facets: Record<string, FacetTag[]>;
}

interface FacetedFuturesResponse {
  total: number;
  page: number;
  per_page: number;
  filters: string[];
  markets: Record<string, unknown>[];
  facets: Record<string, FacetTag[]>;
}

// ── Namespace display ────────────────────────────────────────────────

const NS_LABELS: Record<string, string> = {
  sport: "Sport",
  importance: "Importance",
  signal: "Signal",
  timing: "Timing",
  stakes: "Stakes",
  narrative: "Narrative",
  audience: "Audience",
  tier: "Tier",
  competitive_structure: "Structure",
  league: "League",
  status: "Status",
  ei: "EI",
  source: "Source",
};

const NS_COLORS: Record<string, string> = {
  sport: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  importance: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  signal: "bg-green-500/15 text-green-400 border-green-500/30",
  timing: "bg-sky-500/15 text-sky-400 border-sky-500/30",
  stakes: "bg-red-500/15 text-red-400 border-red-500/30",
  narrative: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  audience: "bg-cyan-500/15 text-cyan-400 border-cyan-500/30",
  tier: "bg-indigo-500/15 text-indigo-400 border-indigo-500/30",
  competitive_structure: "bg-indigo-500/15 text-indigo-400 border-indigo-500/30",
};

function tagLabel(tag: string): string {
  const val = tag.split(":")[1] || tag;
  return val.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Fetchers ─────────────────────────────────────────────────────────

async function fetchFacetedEvents(
  tags: string[],
  page: number
): Promise<FacetedEventsResponse> {
  const params = new URLSearchParams();
  if (tags.length > 0) params.set("tags", JSON.stringify(tags));
  params.set("page", String(page));
  params.set("per_page", "20");
  params.set("days", "14");
  const res = await fetch(`${API_URL}/api/events/faceted?${params}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function fetchFacetedFutures(
  tags: string[],
  page: number
): Promise<FacetedFuturesResponse> {
  const params = new URLSearchParams();
  if (tags.length > 0) params.set("tags", JSON.stringify(tags));
  params.set("page", String(page));
  params.set("per_page", "20");
  const res = await fetch(`${API_URL}/api/futures/faceted?${params}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// ── Component ────────────────────────────────────────────────────────

export default function ExplorePage() {
  usePageTracking({ pageType: "explore", pageTitle: "Explore" });
  useScrollDepth({ pageType: "explore" });
  useEngagementTime({ pageType: "explore" });

  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tab, setTab] = useState<"events" | "futures">("events");
  const [page, setPage] = useState(1);

  const { isPinned: isEventPinned, togglePin: toggleEventPin, isMaxReached: eventMaxReached } =
    usePinnedEvents();
  const { isPinned: isFuturesPinned, togglePin: toggleFuturesPin, isMaxReached: futuresMaxReached } =
    usePinnedFutures();

  const toggleTag = useCallback(
    (tag: string) => {
      setSelectedTags((prev) =>
        prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
      );
      setPage(1);
    },
    []
  );

  const clearTags = useCallback(() => {
    setSelectedTags([]);
    setPage(1);
  }, []);

  // Fetch data
  const eventsKey =
    tab === "events"
      ? ["faceted-events", JSON.stringify(selectedTags), page]
      : null;
  const futuresKey =
    tab === "futures"
      ? ["faceted-futures", JSON.stringify(selectedTags), page]
      : null;

  const { data: eventsData, isLoading: eventsLoading } = useSWR(
    eventsKey,
    () => fetchFacetedEvents(selectedTags, page),
    { keepPreviousData: true }
  );

  const { data: futuresData, isLoading: futuresLoading } = useSWR(
    futuresKey,
    () => fetchFacetedFutures(selectedTags, page),
    { keepPreviousData: true }
  );

  const data = tab === "events" ? eventsData : futuresData;
  const loading = tab === "events" ? eventsLoading : futuresLoading;
  const facets = data?.facets || {};

  // Prioritized namespace order
  const nsOrder = [
    "stakes",
    "narrative",
    "audience",
    "importance",
    "signal",
    "sport",
    "timing",
    "competitive_structure",
  ];
  const sortedNamespaces = Object.keys(facets).sort(
    (a, b) => (nsOrder.indexOf(a) === -1 ? 99 : nsOrder.indexOf(a)) -
              (nsOrder.indexOf(b) === -1 ? 99 : nsOrder.indexOf(b))
  );

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-text-primary">Explore</h1>
        <p className="text-sm text-text-muted mt-1">
          Browse events and futures by tag — filter by stakes, narratives, and more.
        </p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-surface-card rounded-lg p-1 border border-surface-border w-fit">
        {(["events", "futures"] as const).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
              setPage(1);
            }}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === t
                ? "bg-surface-elevated text-text-primary"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            {t === "events" ? "Events" : "Futures"}
          </button>
        ))}
      </div>

      {/* Active filters */}
      {selectedTags.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-text-muted font-medium">Filtering:</span>
          {selectedTags.map((tag) => {
            const ns = tag.split(":")[0];
            const colors = NS_COLORS[ns] || "bg-text-muted/15 text-text-secondary border-text-muted/30";
            return (
              <button
                key={tag}
                onClick={() => toggleTag(tag)}
                className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border ${colors}`}
              >
                {tagLabel(tag)}
                <span className="opacity-60">×</span>
              </button>
            );
          })}
          <button
            onClick={clearTags}
            className="text-xs text-text-muted hover:text-text-secondary underline"
          >
            Clear all
          </button>
        </div>
      )}

      <div className="grid lg:grid-cols-[240px_1fr] gap-6">
        {/* Facet sidebar */}
        <aside className="space-y-4">
          {sortedNamespaces.length === 0 && !loading && (
            <p className="text-xs text-text-muted">No facets available.</p>
          )}
          {sortedNamespaces.map((ns) => {
            const tags = facets[ns] || [];
            if (tags.length === 0) return null;
            return (
              <div key={ns}>
                <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
                  {NS_LABELS[ns] || ns}
                </h3>
                <div className="space-y-0.5">
                  {tags.slice(0, 12).map(({ tag, count }) => {
                    const active = selectedTags.includes(tag);
                    return (
                      <button
                        key={tag}
                        onClick={() => toggleTag(tag)}
                        className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-md text-xs transition-colors ${
                          active
                            ? "bg-accent-futures/15 text-accent-futures font-medium"
                            : "text-text-secondary hover:bg-surface-elevated hover:text-text-primary"
                        }`}
                      >
                        <span className="truncate">{tagLabel(tag)}</span>
                        <span className="text-text-muted ml-2 shrink-0">{count}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </aside>

        {/* Results */}
        <div className="space-y-4">
          {/* Count */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-muted">
              {loading ? (
                <span className="animate-pulse">Loading...</span>
              ) : (
                `${data?.total ?? 0} ${tab === "events" ? "events" : "markets"}`
              )}
            </span>
            {data && data.total > 20 && (
              <div className="flex items-center gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="px-2 py-1 rounded text-xs text-text-secondary hover:bg-surface-elevated disabled:opacity-30"
                >
                  ← Prev
                </button>
                <span className="text-xs text-text-muted">
                  Page {page} / {Math.ceil(data.total / 20)}
                </span>
                <button
                  disabled={page * 20 >= data.total}
                  onClick={() => setPage((p) => p + 1)}
                  className="px-2 py-1 rounded text-xs text-text-secondary hover:bg-surface-elevated disabled:opacity-30"
                >
                  Next →
                </button>
              </div>
            )}
          </div>

          {/* Event cards */}
          {tab === "events" && eventsData && (
            <div className="space-y-3">
              {eventsData.events.length === 0 && !eventsLoading && (
                <div className="text-center py-12 text-text-muted">
                  No events match these filters.
                </div>
              )}
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
              {eventsData.events.map((event: any) => (
                <Link href={`/events/${event.id}`} key={event.id}>
                  <EventCard
                    event={event}
                    isPinned={isEventPinned(event.id)}
                    onPinToggle={() => toggleEventPin(event.id)}
                    pinDisabled={eventMaxReached}
                  />
                </Link>
              ))}
            </div>
          )}

          {/* Futures cards */}
          {tab === "futures" && futuresData && (
            <div className="space-y-3">
              {futuresData.markets.length === 0 && !futuresLoading && (
                <div className="text-center py-12 text-text-muted">
                  No futures markets match these filters.
                </div>
              )}
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
              {futuresData.markets.map((market: any) => (
                <Link href={`/futures/${market.id}`} key={market.id}>
                  <FuturesCard
                    market={market}
                    isPinned={isFuturesPinned(market.id)}
                    onPinToggle={() => toggleFuturesPin(market.id)}
                    pinDisabled={futuresMaxReached}
                  />
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
