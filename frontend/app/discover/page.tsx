"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import useSWR from "swr";
import { fetchFeed } from "@/lib/api";
import type { FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";
import DiscoverCard, { type DiscoverGroupedItem } from "@/components/DiscoverCard";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

const DISMISSED_KEY = "discover_dismissed";
const PAGE_SIZE = 20;

function getDismissed(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = localStorage.getItem(DISMISSED_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

function addDismissed(id: string) {
  const set = getDismissed();
  set.add(id);
  localStorage.setItem(DISMISSED_KEY, JSON.stringify([...set]));
}

function getItemId(item: FeedItem): string {
  if (item.type === "event") return `event-${(item.data as FeedEventData).id}`;
  if (item.type === "futures") return `futures-${(item.data as FeedFuturesData).id}`;
  return `tournament-${(item.data as any).key}`;
}

function getItemCategory(item: FeedItem): string {
  if (item.type === "event") {
    const ed = item.data as FeedEventData;
    return ed.sport?.split("_")[0] || "sports";
  }
  if (item.type === "futures") {
    return (item.data as FeedFuturesData).llm_sport_category || "other";
  }
  return "golf";
}

function isStale(item: FeedItem): boolean {
  if (item.type === "futures") {
    const fd = item.data as FeedFuturesData;
    const leader = fd.top_outcomes?.[0];
    if (fd.status === "closed" || fd.status === "resolved") return true;
    if (leader && (leader.probability ?? 0) >= 0.95) return true;
    // Leader ≥90% with zero movement = effectively resolved
    if (leader && (leader.probability ?? 0) >= 0.90 && (!leader.movement || Math.abs(leader.movement) < 0.005)) return true;
    // Resolution date in the past
    if (fd.resolution_date && new Date(fd.resolution_date) < new Date()) return true;
  }
  if (item.type === "event") {
    const ed = item.data as FeedEventData;
    if (ed.status === "completed" || ed.status === "closed") {
      const hoursAgo = (Date.now() - new Date(ed.commence_time).getTime()) / (1000 * 60 * 60);
      if (hoursAgo > 8) return true;
    }
  }
  return false;
}

/** Interleave items so no two adjacent share a category. Boost underrepresented categories. */
function interleave(items: FeedItem[]): FeedItem[] {
  if (items.length <= 2) return items;

  // Count by category
  const catCounts = new Map<string, number>();
  for (const item of items) {
    const cat = getItemCategory(item);
    catCounts.set(cat, (catCounts.get(cat) || 0) + 1);
  }

  // Separate sports from non-sports
  const SPORTS = new Set(["basketball", "football", "baseball", "hockey", "soccer", "golf", "mma", "boxing", "tennis", "cricket", "motorsports", "americanfootball", "icehockey"]);
  const sports = items.filter(i => SPORTS.has(getItemCategory(i)));
  const nonSports = items.filter(i => !SPORTS.has(getItemCategory(i)));

  // Interleave: insert non-sports items every 4-5 positions
  const result: FeedItem[] = [];
  let si = 0, ni = 0;
  let lastCat = "";
  let sportsSinceNonSport = 0;

  while (si < sports.length || ni < nonSports.length) {
    // Try to insert non-sports every 4 items (ensures ~20% quota)
    if (ni < nonSports.length && (sportsSinceNonSport >= 4 || si >= sports.length)) {
      result.push(nonSports[ni++]);
      sportsSinceNonSport = 0;
      lastCat = getItemCategory(result[result.length - 1]);
      continue;
    }

    if (si < sports.length) {
      // Skip if same category as last (find next different one)
      const cat = getItemCategory(sports[si]);
      if (cat === lastCat && si + 1 < sports.length) {
        // Look ahead for a different category
        let swapIdx = -1;
        for (let j = si + 1; j < Math.min(si + 5, sports.length); j++) {
          if (getItemCategory(sports[j]) !== lastCat) {
            swapIdx = j;
            break;
          }
        }
        if (swapIdx !== -1) {
          [sports[si], sports[swapIdx]] = [sports[swapIdx], sports[si]];
        }
      }
      result.push(sports[si++]);
      lastCat = getItemCategory(result[result.length - 1]);
      sportsSinceNonSport++;
    }
  }

  return result;
}

/** Group related futures by name prefix (e.g., "Valero Texas Open: ..." → one group card) */
function groupRelatedMarkets(items: FeedItem[]): DiscoverGroupedItem[] {
  const result: DiscoverGroupedItem[] = [];
  const futuresGroups = new Map<string, FeedItem[]>();
  const futuresOrder: string[] = [];

  for (const item of items) {
    if (item.type === "futures") {
      const name = (item.data as FeedFuturesData).name;
      // Group by: text before ":" if present, otherwise first 3 words
      const colonIdx = name.indexOf(":");
      const prefix = colonIdx > 0 && colonIdx < 30
        ? name.slice(0, colonIdx).trim()
        : name.split(/\s+/).slice(0, 3).join(" ");

      if (!futuresGroups.has(prefix)) {
        futuresGroups.set(prefix, []);
        futuresOrder.push(prefix);
      }
      futuresGroups.get(prefix)!.push(item);
    }
  }

  // Build output: non-futures pass through, futures get grouped
  let futuresIdx = 0;
  const usedPrefixes = new Set<string>();

  for (const item of items) {
    if (item.type !== "futures") {
      result.push({ type: "single", item });
      continue;
    }

    const name = (item.data as FeedFuturesData).name;
    const colonIdx = name.indexOf(":");
    const prefix = colonIdx > 0 && colonIdx < 30
      ? name.slice(0, colonIdx).trim()
      : name.split(/\s+/).slice(0, 3).join(" ");

    if (usedPrefixes.has(prefix)) continue;
    usedPrefixes.add(prefix);

    const group = futuresGroups.get(prefix)!;
    if (group.length >= 2) {
      result.push({ type: "group", items: group, groupTitle: prefix });
    } else {
      result.push({ type: "single", item: group[0] });
    }
  }

  return result;
}

const CATEGORY_FILTERS = [
  { key: "all", label: "All", emoji: "✨" },
  { key: "sports", label: "Sports", emoji: "🏆" },
  { key: "politics", label: "Politics", emoji: "🏛" },
  { key: "economics", label: "Economics", emoji: "📈" },
  { key: "tech", label: "Tech", emoji: "💻" },
  { key: "culture", label: "Culture", emoji: "🎭" },
  { key: "weather", label: "Weather", emoji: "🌤" },
  { key: "geopolitics", label: "World", emoji: "🌍" },
];

const SPORTS_CATS = new Set(["basketball", "football", "baseball", "hockey", "soccer", "golf", "mma", "boxing", "tennis", "cricket", "motorsports", "americanfootball", "icehockey", "olympics"]);

export default function DiscoverPage() {
  usePageTracking({ pageType: "discover", pageTitle: "Discover" });
  useScrollDepth({ pageType: "discover" });
  useEngagementTime({ pageType: "discover" });

  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setDismissed(getDismissed()); }, []);

  // Infinite scroll observer
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setVisibleCount((c) => c + PAGE_SIZE); },
      { rootMargin: "200px" }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, []);

  const { data, isLoading } = useSWR(
    "discover-feed",
    () => fetchFeed({ limit: 200 }),
    { refreshInterval: 60000 }
  );

  const handleDismiss = useCallback((itemId: string) => {
    addDismissed(itemId);
    setDismissed((prev) => new Set([...prev, itemId]));
  }, []);

  const processedItems = useMemo((): DiscoverGroupedItem[] => {
    const raw = data?.items ?? [];
    const filtered = raw.filter((item) => !dismissed.has(getItemId(item)) && !isStale(item));
    const catFiltered = categoryFilter === "all"
      ? filtered
      : categoryFilter === "sports"
      ? filtered.filter((i) => SPORTS_CATS.has(getItemCategory(i)))
      : filtered.filter((i) => getItemCategory(i) === categoryFilter);
    const interleaved = categoryFilter === "all" ? interleave(catFiltered) : catFiltered;
    return groupRelatedMarkets(interleaved);
  }, [data, dismissed, categoryFilter]);

  const visibleItems = processedItems.slice(0, visibleCount);

  // Count items per category for chip badges
  const catCountsForChips = useMemo(() => {
    const raw = data?.items ?? [];
    const live = raw.filter((item) => !dismissed.has(getItemId(item)) && !isStale(item));
    const counts = new Map<string, number>();
    for (const item of live) {
      const cat = getItemCategory(item);
      if (SPORTS_CATS.has(cat)) {
        counts.set("sports", (counts.get("sports") || 0) + 1);
      } else {
        counts.set(cat, (counts.get(cat) || 0) + 1);
      }
    }
    counts.set("all", live.length);
    return counts;
  }, [data, dismissed]);

  return (
    <div className="min-h-screen bg-[#fafbfc]">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-white/80 backdrop-blur-lg border-b border-surface-border">
        <div className="max-w-lg mx-auto px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <h1 className="text-lg font-black tracking-tight">Discover</h1>
            <span className="text-text-muted text-xs font-medium">{processedItems.length} markets</span>
          </div>
          {/* Category filter chips */}
          <div className="flex gap-1.5 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-hide">
            {CATEGORY_FILTERS.map((cf) => {
              const count = catCountsForChips.get(cf.key) || 0;
              if (cf.key !== "all" && count === 0) return null;
              const active = categoryFilter === cf.key;
              return (
                <button
                  key={cf.key}
                  onClick={() => { setCategoryFilter(cf.key); setVisibleCount(PAGE_SIZE); }}
                  className={`shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                    active
                      ? "bg-[#111827] text-white"
                      : "bg-surface-elevated text-text-secondary hover:text-text-primary"
                  }`}
                >
                  <span>{cf.emoji}</span>
                  <span>{cf.label}</span>
                  {count > 0 && <span className={`text-[10px] ${active ? "text-white/60" : "text-text-muted"}`}>{count}</span>}
                </button>
              );
            })}
          </div>
        </div>
      </header>

      {/* Feed */}
      <main className="max-w-lg mx-auto px-4 py-4 space-y-4">
        {isLoading && (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="rounded-2xl bg-surface-card border border-surface-border animate-pulse">
                <div className="h-44 bg-surface-elevated rounded-t-2xl" />
                <div className="p-4 space-y-3">
                  <div className="h-5 bg-surface-elevated rounded w-3/4" />
                  <div className="h-3 bg-surface-elevated rounded w-full" />
                  <div className="h-3 bg-surface-elevated rounded w-2/3" />
                </div>
              </div>
            ))}
          </div>
        )}

        {!isLoading && visibleItems.length === 0 && (
          <div className="text-center py-20 text-text-muted">
            <p className="text-lg font-medium">
              {categoryFilter !== "all" ? `No ${categoryFilter} markets right now` : "All caught up!"}
            </p>
            <p className="text-sm mt-1">
              {categoryFilter !== "all"
                ? <button onClick={() => setCategoryFilter("all")} className="text-blue-600 hover:underline">Show all markets</button>
                : "Check back later for new markets"}
            </p>
          </div>
        )}

        {visibleItems.map((gi, idx) => (
          <DiscoverCard
            key={gi.type === "single" ? getItemId(gi.item) : `group-${gi.groupTitle}-${idx}`}
            groupedItem={gi}
            onDismiss={gi.type === "single" ? () => handleDismiss(getItemId(gi.item)) : undefined}
          />
        ))}

        {/* Infinite scroll sentinel */}
        {visibleCount < processedItems.length && (
          <div ref={sentinelRef} className="h-10 flex items-center justify-center">
            <div className="w-5 h-5 border-2 border-text-muted/30 border-t-text-muted rounded-full animate-spin" />
          </div>
        )}

        {visibleCount >= processedItems.length && processedItems.length > 0 && (
          <div className="text-center py-8 text-text-muted text-sm">
            You&apos;ve seen everything · {processedItems.length} markets
          </div>
        )}
      </main>
    </div>
  );
}
