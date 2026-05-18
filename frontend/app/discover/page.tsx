"use client";

import { useState, useCallback, useEffect, useRef, useMemo, type ReactNode } from "react";
import Link from "next/link";
import useSWR, { useSWRConfig } from "swr";
import { fetchFeed, fetchResolutions } from "@/lib/api";
import type { FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";
import DiscoverCard, { type DiscoverGroupedItem, GuessCard, DailyChallengeCard, ResolutionCard } from "@/components/DiscoverCard";
import { Button } from "@/components/ui/button";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { trackEvent } from "@/lib/analytics";
import {
  getDiscoverCategoryAdjustment,
  getDiscoverItemAnalytics,
  getDiscoverPersonalizationTrace,
  readDiscoverInteractionProfile,
  recordDiscoverInteraction,
  sendDiscoverInteraction,
  type DiscoverProfile,
} from "@/lib/discoverInteractions";
import { useCategoryInterests } from "@/hooks/useCategoryInterests";

const DISMISSED_KEY = "discover_dismissed";
const PAGE_SIZE = 20;
const DISMISS_TTL_MS = 6 * 60 * 60 * 1000;
const MAX_LOCAL_DISMISSES = 40;
const MIN_ITEMS_AFTER_LOCAL_DISMISS = 20;

function getDismissed(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = localStorage.getItem(DISMISSED_KEY);
    if (!raw) return new Set();

    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      // Legacy storage had no timestamp and could suppress the feed forever.
      localStorage.removeItem(DISMISSED_KEY);
      return new Set();
    }

    const now = Date.now();
    const entries = Array.isArray(parsed?.items) ? parsed.items : [];
    const fresh = entries
      .filter((entry: { id?: string; ts?: number }) => {
        return entry.id && entry.ts && now - entry.ts < DISMISS_TTL_MS;
      })
      .slice(-MAX_LOCAL_DISMISSES);
    localStorage.setItem(DISMISSED_KEY, JSON.stringify({ items: fresh }));
    return new Set(fresh.map((entry: { id: string }) => entry.id));
  } catch {
    localStorage.removeItem(DISMISSED_KEY);
    return new Set();
  }
}

function saveDismissed(items: Set<string>) {
  if (typeof window === "undefined") return;
  try {
    const now = Date.now();
    const existingRaw = localStorage.getItem(DISMISSED_KEY);
    const existing = existingRaw ? JSON.parse(existingRaw) : {};
    const previous = Array.isArray(existing?.items) ? existing.items : [];
    const byId = new Map<string, { id: string; ts: number }>();

    for (const entry of previous) {
      if (entry?.id && entry?.ts && now - entry.ts < DISMISS_TTL_MS) {
        byId.set(entry.id, { id: entry.id, ts: entry.ts });
      }
    }
    for (const id of items) {
      byId.set(id, { id, ts: now });
    }

    const fresh = Array.from(byId.values()).slice(-MAX_LOCAL_DISMISSES);
    localStorage.setItem(DISMISSED_KEY, JSON.stringify({ items: fresh }));
  } catch { }
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

function getGroupedAnalytics(groupedItem: DiscoverGroupedItem) {
  const item = groupedItem.type === "single" ? groupedItem.item : groupedItem.items?.[0];
  return item ? getDiscoverItemAnalytics(item) : null;
}

function applyLocalPersonalization(
  items: DiscoverGroupedItem[],
  profile: DiscoverProfile | null
): DiscoverGroupedItem[] {
  if (!profile || items.length <= 6) return items;

  const pinnedLead = items.slice(0, 3);
  const rest = items.slice(3);
  const result: DiscoverGroupedItem[] = [...pinnedLead];
  const windowSize = 5;

  for (let start = 0; start < rest.length; start += windowSize) {
    const window = rest.slice(start, start + windowSize);
    const ranked = window
      .map((groupedItem, idx) => {
        const analytics = getGroupedAnalytics(groupedItem);
        const adjustment = analytics
          ? getDiscoverCategoryAdjustment(profile, analytics.category)
          : 0;
        return {
          groupedItem,
          idx,
          adjustedScore: (analytics?.score ?? 0) + adjustment,
        };
      })
      .sort((a, b) => {
        const scoreDiff = b.adjustedScore - a.adjustedScore;
        return Math.abs(scoreDiff) > 0.001 ? scoreDiff : a.idx - b.idx;
      })
      .map((entry) => entry.groupedItem);
    result.push(...ranked);
  }

  return result;
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

/** Interleave items so the default feed does not cluster into one sport or topic. */
function interleave(items: FeedItem[]): FeedItem[] {
  if (items.length <= 2) return items;

  // Separate sports from non-sports
  const SPORTS = new Set(["basketball", "football", "baseball", "hockey", "soccer", "golf", "mma", "boxing", "tennis", "cricket", "motorsports", "americanfootball", "icehockey"]);
  const sports = items.filter(i => SPORTS.has(getItemCategory(i)));
  const nonSports = items.filter(i => !SPORTS.has(getItemCategory(i)));

  const result: FeedItem[] = [];
  let si = 0, ni = 0;
  let lastCat = "";
  let sportsSinceNonSport = 0;
  const maxSportsRun = nonSports.length >= 4 ? 2 : 3;

  while (si < sports.length || ni < nonSports.length) {
    if (ni < nonSports.length && (sportsSinceNonSport >= maxSportsRun || si >= sports.length)) {
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
    } else if (ni < nonSports.length) {
      result.push(nonSports[ni++]);
      sportsSinceNonSport = 0;
      lastCat = getItemCategory(result[result.length - 1]);
    } else {
      break;
    }
  }

  return result;
}

function getGroupedCategory(groupedItem: DiscoverGroupedItem): string {
  const item = groupedItem.type === "single" ? groupedItem.item : groupedItem.items?.[0];
  return item ? getItemCategory(item) : "other";
}

function interleaveGrouped(items: DiscoverGroupedItem[]): DiscoverGroupedItem[] {
  if (items.length <= 2) return items;

  const SPORTS = new Set(["basketball", "football", "baseball", "hockey", "soccer", "golf", "mma", "boxing", "tennis", "cricket", "motorsports", "americanfootball", "icehockey"]);
  const sports = items.filter(i => SPORTS.has(getGroupedCategory(i)));
  const nonSports = items.filter(i => !SPORTS.has(getGroupedCategory(i)));
  const result: DiscoverGroupedItem[] = [];
  let si = 0, ni = 0;
  let lastCat = "";
  let sportsSinceNonSport = 0;
  const maxSportsRun = nonSports.length >= 4 ? 2 : 3;

  while (si < sports.length || ni < nonSports.length) {
    if (ni < nonSports.length && (sportsSinceNonSport >= maxSportsRun || si >= sports.length)) {
      result.push(nonSports[ni++]);
      sportsSinceNonSport = 0;
      lastCat = getGroupedCategory(result[result.length - 1]);
      continue;
    }

    if (si < sports.length) {
      const cat = getGroupedCategory(sports[si]);
      if (cat === lastCat && si + 1 < sports.length) {
        let swapIdx = -1;
        for (let j = si + 1; j < Math.min(si + 5, sports.length); j++) {
          if (getGroupedCategory(sports[j]) !== lastCat) {
            swapIdx = j;
            break;
          }
        }
        if (swapIdx !== -1) {
          [sports[si], sports[swapIdx]] = [sports[swapIdx], sports[si]];
        }
      }
      result.push(sports[si++]);
      lastCat = getGroupedCategory(result[result.length - 1]);
      sportsSinceNonSport++;
    } else if (ni < nonSports.length) {
      result.push(nonSports[ni++]);
      sportsSinceNonSport = 0;
      lastCat = getGroupedCategory(result[result.length - 1]);
    } else {
      break;
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

function FeedItemShell({
  groupedItem,
  positionIndex,
  personalizationTrace,
  children,
}: {
  groupedItem: DiscoverGroupedItem;
  positionIndex: number;
  personalizationTrace?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const tracked = useRef(false);
  const analytics = useMemo(() => getGroupedAnalytics(groupedItem), [groupedItem]);

  useEffect(() => {
    if (!analytics || tracked.current) return;
    const node = ref.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting || tracked.current) return;
        tracked.current = true;
        trackEvent("feed_card_impression", {
          ...analytics,
          position: positionIndex,
          surface: "discover",
        });
        recordDiscoverInteraction(analytics.category, "impression");
        sendDiscoverInteraction(analytics, "impression", positionIndex, "viewport");
        observer.disconnect();
      },
      { threshold: 0.55 }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [analytics, positionIndex]);

  return (
    <div ref={ref} data-personalization-trace={personalizationTrace}>
      {children}
    </div>
  );
}

function ChallengeModal({
  items,
  currentIndex,
  completed,
  onClose,
  onGuessCompleted,
  onNextQuestion,
}: {
  items: FeedItem[];
  currentIndex: number;
  completed: boolean;
  onClose: () => void;
  onGuessCompleted: () => void;
  onNextQuestion: () => void;
}) {
  const goal = Math.min(5, Math.max(items.length, 1));
  const progress = completed ? 1 : currentIndex / goal;
  const currentItem = items[currentIndex];
  const isLastQuestion = currentIndex >= goal - 1;

  return (
    <div className="fixed inset-0 z-50 bg-black/55 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-md max-h-[92vh] overflow-y-auto rounded-2xl bg-surface-deep shadow-2xl border border-surface-border">
        <div className="sticky top-0 z-10 bg-surface-card/90 backdrop-blur border-b border-surface-border px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-black text-text-primary">Today’s Challenge</div>
              <div className="text-xs text-text-muted">
                {completed ? "Set complete" : `Question ${Math.min(currentIndex + 1, goal)} of ${goal}`}
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="grid place-items-center w-8 h-8 rounded-full text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors"
              aria-label="Close challenge"
            >
              ×
            </button>
          </div>
          <div className="mt-3 h-2 rounded-full bg-surface-elevated overflow-hidden">
            <div
              className="h-full rounded-full bg-amber-500 transition-all duration-500"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
        </div>

        <div className="p-4">
          {completed ? (
            <div className="rounded-2xl border border-green-400/40 bg-surface-card p-6 text-center shadow-md">
              <div className="text-4xl mb-3">🏆</div>
              <h2 className="text-xl font-black text-text-primary">Challenge complete</h2>
              <p className="mt-2 text-sm text-text-secondary">
                Your predictions are counted. Come back tomorrow for a fresh set.
              </p>
              <Button
                type="button"
                onClick={onClose}
                size="lg"
                className="mt-5 w-full rounded-xl"
              >
                Back to Discover
              </Button>
            </div>
          ) : currentItem ? (
            <GuessCard
              key={getItemId(currentItem)}
              item={currentItem}
              onGuessCompleted={onGuessCompleted}
              nextButtonLabel={isLastQuestion ? "Finish challenge" : "Next question"}
              onNextQuestion={onNextQuestion}
            />
          ) : (
            <div className="rounded-2xl border border-surface-border bg-surface-card p-6 text-center shadow-md">
              <h2 className="text-lg font-black text-text-primary">No challenge cards right now</h2>
              <p className="mt-2 text-sm text-text-secondary">Check back after the feed refreshes.</p>
              <Button
                type="button"
                onClick={onClose}
                size="lg"
                className="mt-5 w-full rounded-xl"
              >
                Back to Discover
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function DiscoverPage() {
  usePageTracking({ pageType: "discover", pageTitle: "Discover" });
  useScrollDepth({ pageType: "discover" });
  useEngagementTime({ pageType: "discover" });

  const { setInterest } = useCategoryInterests();
  const { mutate } = useSWRConfig();

  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [dailyGuesses, setDailyGuesses] = useState(0);
  const [allItems, setAllItems] = useState<FeedItem[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [interactionProfile, setInteractionProfile] = useState<DiscoverProfile | null>(null);
  const [challengeOpen, setChallengeOpen] = useState(false);
  const [challengeIndex, setChallengeIndex] = useState(0);
  const [challengeComplete, setChallengeComplete] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setDismissed(getDismissed());
    setInteractionProfile(readDiscoverInteractionProfile());
    if (typeof window !== "undefined" && !localStorage.getItem("discover_onboarded")) {
      setShowOnboarding(true);
    }
    const today = new Date().toISOString().slice(0, 10);
    const stored = localStorage.getItem(`daily_guesses_${today}`);
    if (stored) setDailyGuesses(parseInt(stored, 10));
  }, []);

  useEffect(() => {
    const refreshProfile = () => setInteractionProfile(readDiscoverInteractionProfile());
    window.addEventListener("discover-profile-updated", refreshProfile);
    return () => window.removeEventListener("discover-profile-updated", refreshProfile);
  }, []);

  const { data, isLoading, error: feedError } = useSWR(
    "discover-feed",
    () => fetchFeed({ limit: 200, event_pct: 0.15 }),
    { refreshInterval: 120000, revalidateOnFocus: false, keepPreviousData: true }
  );

  const { data: resolutionsData } = useSWR(
    "discover-resolutions",
    fetchResolutions,
    { revalidateOnFocus: false }
  );

  useEffect(() => {
    if (data) setHasMore(data.has_more);
  }, [data]);

  // Load more pages from the API when client-side items run out
  const loadNextPage = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const loadedItems = [...(data?.items ?? []), ...allItems];
      const loadedIds = new Set(loadedItems.map(getItemId));
      const offsets = Array.from(new Set([0, loadedItems.length]));
      let sawMore = false;
      let added = false;

      for (const offset of offsets) {
        const resp = await fetchFeed({ limit: 200, offset, event_pct: 0.15 });
        sawMore = sawMore || resp.has_more;
        const freshItems = resp.items.filter((item) => !loadedIds.has(getItemId(item)));
        if (freshItems.length === 0) continue;

        for (const item of freshItems) loadedIds.add(getItemId(item));
        setAllItems((prev) => {
          const prevIds = new Set([...(data?.items ?? []), ...prev].map(getItemId));
          return [
            ...prev,
            ...freshItems.filter((item) => !prevIds.has(getItemId(item))),
          ];
        });
        added = true;
        break;
      }

      if (!added && !sawMore) {
        setHasMore(false);
      }
    } catch { }
    setLoadingMore(false);
  }, [allItems, data, loadingMore, hasMore]);

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

  const handleDismiss = useCallback((itemId: string) => {
    // Persist local dismissals so anonymous users do not see the same card
    // again after refresh while the server downrank catches up.
    setDismissed((prev) => {
      const next = new Set([...prev, itemId]);
      saveDismissed(next);
      return next;
    });
  }, []);

  const startChallenge = useCallback(() => {
    setChallengeIndex(0);
    setChallengeComplete(false);
    setChallengeOpen(true);
    trackEvent("feed_card_action", {
      action: "challenge_start",
      content_type: "grid",
      item_id: "daily_challenge",
      category: "challenge",
      item_name: "Today’s Challenge",
      surface: "discover",
    });
    sendDiscoverInteraction({
      content_type: "grid",
      item_id: "daily_challenge",
      category: "challenge",
      item_name: "Today’s Challenge",
      score: 0,
    }, "challenge_start", undefined, "challenge");
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
    const fresh = unique.filter((item) => !isStale(item));
    const dismissFiltered = fresh.filter((item) => !dismissed.has(getItemId(item)));
    const filtered = dismissFiltered.length >= MIN_ITEMS_AFTER_LOCAL_DISMISS
      || fresh.length < MIN_ITEMS_AFTER_LOCAL_DISMISS
      ? dismissFiltered
      : fresh;
    const catFiltered = categoryFilter === "all"
      ? filtered
      : categoryFilter === "sports"
      ? filtered.filter((i) => SPORTS_CATS.has(getItemCategory(i)))
      : filtered.filter((i) => getItemCategory(i) === categoryFilter);
    const grouped = groupRelatedMarkets(interleave(catFiltered));
    return interleaveGrouped(applyLocalPersonalization(grouped, interactionProfile));
  }, [data, allItems, dismissed, categoryFilter, interactionProfile]);

  const visibleItems = processedItems.slice(0, visibleCount);
  const challengeItems = useMemo(() => {
    return processedItems
      .filter((gi): gi is { type: "single"; item: FeedItem } => {
        if (gi.type !== "single" || !gi.item) return false;
        if (gi.item.type === "futures") {
          const fd = gi.item.data as FeedFuturesData;
          return Boolean(fd.top_outcomes?.[0]?.probability != null);
        }
        if (gi.item.type === "event") {
          const ed = gi.item.data as FeedEventData;
          return Boolean(ed.current_odds?.home_probability != null);
        }
        return false;
      })
      .map((gi) => gi.item)
      .slice(0, 5);
  }, [processedItems]);

  const incrementDailyGuesses = useCallback(() => {
    const today = new Date().toISOString().slice(0, 10);
    setDailyGuesses((current) => {
      const next = current + 1;
      localStorage.setItem(`daily_guesses_${today}`, next.toString());
      return next;
    });
  }, []);

  const handleChallengeGuess = useCallback(() => {
    incrementDailyGuesses();
  }, [incrementDailyGuesses]);

  const completeChallenge = useCallback(() => {
    setChallengeComplete(true);
    trackEvent("feed_card_action", {
      action: "challenge_complete",
      content_type: "grid",
      item_id: "daily_challenge",
      category: "challenge",
      item_name: "Today’s Challenge",
      surface: "discover",
    });
    sendDiscoverInteraction({
      content_type: "grid",
      item_id: "daily_challenge",
      category: "challenge",
      item_name: "Today’s Challenge",
      score: 0,
    }, "challenge_complete", undefined, "challenge");
  }, []);

  const handleChallengeNext = useCallback(() => {
    const next = challengeIndex + 1;
    if (next >= challengeItems.length || next >= 5) {
      completeChallenge();
      return;
    }
    setChallengeIndex(next);
  }, [challengeIndex, challengeItems.length, completeChallenge]);

  // Load more from API when client-side items run out
  useEffect(() => {
    if (visibleCount >= processedItems.length - 5 && hasMore && !loadingMore) {
      loadNextPage();
    }
  }, [visibleCount, processedItems.length, hasMore, loadingMore, loadNextPage]);

  // Count items per category for chip badges
  const catCountsForChips = useMemo(() => {
    const raw = data?.items ?? [];
    const fresh = raw.filter((item) => !isStale(item));
    const dismissFiltered = fresh.filter((item) => !dismissed.has(getItemId(item)));
    const live = dismissFiltered.length >= MIN_ITEMS_AFTER_LOCAL_DISMISS
      || fresh.length < MIN_ITEMS_AFTER_LOCAL_DISMISS
      ? dismissFiltered
      : fresh;
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
    <div className="min-h-screen bg-surface-deep">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-surface-card/80 backdrop-blur-lg border-b border-surface-border">
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
                      ? "bg-text-primary text-white"
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

          // Persist selected categories as sport affinities (1.0 = "Love it").
          // useCategoryInterests handles the dual path: API for auth'd users,
          // localStorage for anonymous (migrated to server on first sign-in
          // via useInterestSync in PinSyncEffect).
          for (const cat of cats) {
            setInterest(cat, 1.0);
          }

          // Revalidate the feed so server-side personalization picks up
          // the freshly saved affinities on the next request.
          if (cats.length > 0) {
            void mutate("discover-feed");
          }

          if (cats.length > 0 && !SPORTS_CATS.has(cats[0])) setCategoryFilter(cats[0]);
        }} />
      )}

      {challengeOpen && (
        <ChallengeModal
          items={challengeItems}
          currentIndex={challengeIndex}
          completed={challengeComplete}
          onClose={() => setChallengeOpen(false)}
          onGuessCompleted={handleChallengeGuess}
          onNextQuestion={handleChallengeNext}
        />
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

        {!isLoading && feedError && !data && (
          <div className="text-center py-20 text-text-muted">
            <p className="text-text-secondary text-sm">Failed to load feed</p>
            <button
              onClick={() => window.location.reload()}
              className="mt-3 text-sm text-accent-brand hover:underline transition-colors"
            >
              Try again
            </button>
          </div>
        )}

        {!isLoading && !feedError && visibleItems.length === 0 && (
          <div className="text-center py-20 text-text-muted">
            <p className="text-lg font-medium">
              {categoryFilter !== "all" ? `No ${categoryFilter} markets right now` : "All caught up!"}
            </p>
            <p className="text-sm mt-1">
              {categoryFilter !== "all"
                ? <Button variant="text" onClick={() => setCategoryFilter("all")}>Show all markets</Button>
                : "Check back later for new markets"}
            </p>
          </div>
        )}

        {/* Resolution notifications */}
        {resolutionsData && resolutionsData.resolutions.length > 0 && (
          <div className="mb-4 columns-1 sm:columns-2 lg:columns-3 xl:columns-4 gap-4">
            {resolutionsData.resolutions.slice(0, 3).map((r, idx) => (
              <div key={idx} className="break-inside-avoid mb-4">
                <ResolutionCard
                  marketName={r.market_name}
                  guess={r.guess}
                  threshold={r.threshold}
                  actual={r.actual}
                  correct={r.correct}
                />
              </div>
            ))}
          </div>
        )}

        {/* Daily Challenge — passive progress tracker, counts guesses from feed */}
        {!isLoading && processedItems.length > 0 && (
          <div className="mb-4">
            <DailyChallengeCard guessesToday={dailyGuesses} onStart={startChallenge} />
          </div>
        )}

        <div className="columns-1 sm:columns-2 lg:columns-3 xl:columns-4 gap-4">
          {visibleItems.map((gi, idx) => {
            const key = gi.type === "single" ? getItemId(gi.item!) : `group-${gi.groupTitle}-${idx}`;
            const isGuessSlot = gi.type === "single" && (idx + 1) % 5 === 0 && (gi.item!.type === "futures" || gi.item!.type === "event");
            const analytics = getGroupedAnalytics(gi);
            const personalizationTrace = analytics
              ? getDiscoverPersonalizationTrace(interactionProfile, analytics.category)
              : undefined;

            const handleLessLike = gi.type === "single"
              ? () => {
                  handleDismiss(getItemId(gi.item!));
                }
              : undefined;

            return (
              <div key={key} className="break-inside-avoid mb-4">
                <FeedItemShell groupedItem={gi} positionIndex={idx} personalizationTrace={personalizationTrace}>
                  {isGuessSlot ? (
                    <GuessCard item={gi.item!} onGuessCompleted={incrementDailyGuesses} />
                  ) : (
                    <DiscoverCard
                      groupedItem={gi}
                      positionIndex={idx}
                      onDismiss={handleLessLike}
                    />
                  )}
                </FeedItemShell>
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
      <div className="bg-surface-card rounded-3xl max-w-md w-full p-6 shadow-2xl">
        <div className="text-center mb-6">
          <div className="text-3xl mb-2">🎯</div>
          <h2 className="text-xl font-black">Build Your Feed</h2>
          <p className="text-sm text-text-secondary mt-1">Pick topics you&apos;re interested in. You can change these anytime.</p>
        </div>

        <div className="mb-5 grid gap-2 rounded-2xl border border-surface-border bg-surface-elevated p-3 text-sm">
          <div className="flex items-center gap-3">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-500 text-white">→</span>
            <span className="text-text-secondary"><strong className="text-text-primary">Swipe right</strong> for more like this</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-rose-500 text-white">←</span>
            <span className="text-text-secondary"><strong className="text-text-primary">Swipe left</strong> for less like this</span>
          </div>
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

        <Button
          onClick={() => onComplete([...selected])}
          size="lg"
          className="w-full rounded-xl"
        >
          {selected.size === 0 ? "Show me everything" : `Start with ${selected.size} topic${selected.size > 1 ? "s" : ""}`}
        </Button>
      </div>
    </div>
  );
}
