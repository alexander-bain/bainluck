"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetchFeed } from "@/lib/api";
import type { FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";
import DiscoverCard, { type DiscoverGroupedItem, GuessCard, DailyChallengeCard, ResolutionCard } from "@/components/DiscoverCard";
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
  { key: "geopolitics", label: "Geopolitics", emoji: "🌍" },
  { key: "politics", label: "Politics", emoji: "🏛" },
  { key: "economics", label: "Economics", emoji: "📈" },
  { key: "tech", label: "Tech", emoji: "💻" },
  { key: "entertainment", label: "Entertainment", emoji: "🎬" },
  { key: "culture", label: "Culture", emoji: "🎭" },
  { key: "health", label: "Health", emoji: "🏥" },
  { key: "weather", label: "Weather", emoji: "🌤" },
];

const SPORTS_CATS = new Set(["basketball", "football", "baseball", "hockey", "soccer", "golf", "mma", "boxing", "tennis", "cricket", "motorsports", "americanfootball", "icehockey", "olympics"]);

export default function DiscoverPage() {
  usePageTracking({ pageType: "discover", pageTitle: "Discover" });
  useScrollDepth({ pageType: "discover" });
  useEngagementTime({ pageType: "discover" });

  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [dailyGuesses, setDailyGuesses] = useState(0);
  const [allItems, setAllItems] = useState<FeedItem[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [pagesLoaded, setPagesLoaded] = useState(0);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setDismissed(getDismissed());
    if (typeof window !== "undefined" && !localStorage.getItem("discover_onboarded")) {
      setShowOnboarding(true);
    }
    const today = new Date().toISOString().slice(0, 10);
    const stored = localStorage.getItem(`daily_guesses_${today}`);
    if (stored) setDailyGuesses(parseInt(stored, 10));
  }, []);

  // Load more pages from the API when client-side items run out
  const loadNextPage = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const nextOffset = (pagesLoaded + 1) * 200;
      const resp = await fetchFeed({ limit: 200, offset: nextOffset, event_pct: 0.15 });
      if (resp.items.length === 0 || !resp.has_more) {
        setHasMore(false);
      }
      if (resp.items.length > 0) {
        setAllItems((prev) => [...prev, ...resp.items]);
        setPagesLoaded((p) => p + 1);
      }
    } catch { }
    setLoadingMore(false);
  }, [loadingMore, hasMore, pagesLoaded]);

  // Infinite scroll observer
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisibleCount((c) => c + PAGE_SIZE);
        }
      },
      { rootMargin: "400px" }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, []);

  const { data, isLoading } = useSWR(
    "discover-feed",
    () => fetchFeed({ limit: 200, event_pct: 0.15 }),
    { refreshInterval: 60000 }
  );

  const handleDismiss = useCallback((itemId: string) => {
    addDismissed(itemId);
    setDismissed((prev) => new Set([...prev, itemId]));
  }, []);

  const processedItems = useMemo((): DiscoverGroupedItem[] => {
    const firstPage = data?.items ?? [];
    const raw = [...firstPage, ...allItems];
    // Deduplicate by item ID across pages
    const seen = new Set<string>();
    const unique = raw.filter((item) => {
      const id = getItemId(item);
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    });
    const filtered = unique.filter((item) => !dismissed.has(getItemId(item)) && !isStale(item));
    const catFiltered = categoryFilter === "all"
      ? filtered
      : categoryFilter === "sports"
      ? filtered.filter((i) => SPORTS_CATS.has(getItemCategory(i)))
      : filtered.filter((i) => getItemCategory(i) === categoryFilter);
    return groupRelatedMarkets(catFiltered);
  }, [data, allItems, dismissed, categoryFilter]);

  const visibleItems = processedItems.slice(0, visibleCount);

  // Load more from API when client-side items run out
  useEffect(() => {
    if (visibleCount >= processedItems.length - 5 && hasMore && !loadingMore) {
      loadNextPage();
    }
  }, [visibleCount, processedItems.length, hasMore, loadingMore, loadNextPage]);

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
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <h1 className="text-lg font-black tracking-tight">Discover</h1>
            <div className="flex items-center gap-3">
              <Link href="/discover/stats" className="text-text-muted hover:text-text-primary transition-colors">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 20V10" /><path d="M18 20V4" /><path d="M6 20v-4" />
                </svg>
              </Link>
              <span className="text-text-muted text-xs font-medium">{processedItems.length} markets</span>
            </div>
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

      {/* Onboarding overlay */}
      {showOnboarding && (
        <OnboardingFlow onComplete={(cats) => {
          setShowOnboarding(false);
          localStorage.setItem("discover_onboarded", "1");
          if (cats.length > 0 && !SPORTS_CATS.has(cats[0])) setCategoryFilter(cats[0]);
        }} />
      )}

      {/* Feed — responsive: 1 col mobile, 2 col tablet, 3 col desktop */}
      <main className="max-w-7xl mx-auto px-4 py-4">
        {isLoading && (
          <div className="columns-1 sm:columns-2 lg:columns-3 gap-4 space-y-4">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="break-inside-avoid rounded-2xl bg-surface-card border border-surface-border animate-pulse mb-4">
                <div className="h-44 bg-surface-elevated rounded-t-2xl" />
                <div className="p-4 space-y-3">
                  <div className="h-5 bg-surface-elevated rounded w-3/4" />
                  <div className="h-3 bg-surface-elevated rounded w-full" />
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

        {/* Daily Challenge — expands to show a guess card inline */}
        {!isLoading && processedItems.length > 0 && (() => {
          const guessCandidate = processedItems.find(
            (gi) => gi.type === "single" && gi.item?.type === "futures"
          );
          return (
            <div className="mb-4">
              <DailyChallengeCard
                guessesToday={dailyGuesses}
                guessItem={guessCandidate?.item ?? undefined}
                onGuessCompleted={() => {
                  const today = new Date().toISOString().slice(0, 10);
                  const next = dailyGuesses + 1;
                  setDailyGuesses(next);
                  localStorage.setItem(`daily_guesses_${today}`, next.toString());
                }}
              />
            </div>
          );
        })()}

        <div className="columns-1 sm:columns-2 lg:columns-3 gap-4">
          {visibleItems.map((gi, idx) => {
            const key = gi.type === "single" ? getItemId(gi.item!) : `group-${gi.groupTitle}-${idx}`;
            const isGuessSlot = gi.type === "single" && (idx + 1) % 5 === 0 && gi.item!.type === "futures";

            return (
              <div key={key} className="break-inside-avoid mb-4">
                {isGuessSlot ? (
                  <GuessCard item={gi.item!} />
                ) : (
                  <DiscoverCard
                    groupedItem={gi}
                    onDismiss={gi.type === "single" ? () => handleDismiss(getItemId(gi.item!)) : undefined}
                  />
                )}
              </div>
            );
          })}
        </div>

        {(visibleCount < processedItems.length || hasMore) && (
          <div ref={sentinelRef} className="h-10 flex items-center justify-center mt-4">
            <div className="w-5 h-5 border-2 border-text-muted/30 border-t-text-muted rounded-full animate-spin" />
          </div>
        )}

        {visibleCount >= processedItems.length && !hasMore && processedItems.length > 0 && (
          <div className="text-center py-8 text-text-muted text-sm">
            {processedItems.length} markets explored
          </div>
        )}
      </main>
    </div>
  );
}

// ── Build Your Feed Onboarding ──

function OnboardingFlow({ onComplete }: { onComplete: (selectedCategories: string[]) => void }) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const categories = [
    { key: "basketball", emoji: "🏀", label: "Basketball" },
    { key: "football", emoji: "🏈", label: "Football" },
    { key: "baseball", emoji: "⚾", label: "Baseball" },
    { key: "hockey", emoji: "🏒", label: "Hockey" },
    { key: "soccer", emoji: "⚽", label: "Soccer" },
    { key: "golf", emoji: "⛳", label: "Golf" },
    { key: "politics", emoji: "🏛", label: "Politics" },
    { key: "economics", emoji: "📈", label: "Economics" },
    { key: "tech", emoji: "💻", label: "Tech" },
    { key: "culture", emoji: "🎭", label: "Culture" },
    { key: "weather", emoji: "🌤", label: "Weather" },
    { key: "mma", emoji: "🥊", label: "MMA / Boxing" },
  ];

  const toggle = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl">
        <div className="text-center mb-6">
          <div className="text-3xl mb-2">🎯</div>
          <h2 className="text-xl font-black">Build Your Feed</h2>
          <p className="text-sm text-text-secondary mt-1">Pick topics you&apos;re interested in. You can change these anytime.</p>
        </div>

        <div className="grid grid-cols-3 gap-2 mb-6">
          {categories.map((cat) => (
            <button
              key={cat.key}
              onClick={() => toggle(cat.key)}
              className={`flex flex-col items-center gap-1 py-3 px-2 rounded-xl border-2 transition-all ${
                selected.has(cat.key)
                  ? "border-blue-500 bg-blue-50 scale-105"
                  : "border-surface-border bg-surface-card hover:border-text-muted"
              }`}
            >
              <span className="text-xl">{cat.emoji}</span>
              <span className="text-xs font-medium">{cat.label}</span>
            </button>
          ))}
        </div>

        <button
          onClick={() => onComplete([...selected])}
          className="w-full py-3 rounded-xl bg-[#111827] text-white font-bold text-sm hover:bg-[#1f2937] transition-colors"
        >
          {selected.size === 0 ? "Show me everything" : `Start with ${selected.size} topic${selected.size > 1 ? "s" : ""}`}
        </button>
      </div>
    </div>
  );
}
