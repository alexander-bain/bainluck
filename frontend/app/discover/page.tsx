"use client";

import { useState, useCallback, useEffect, useRef, useMemo, type ReactNode } from "react";
import ErrorBoundary from "@/components/ErrorBoundary";
import Link from "next/link";
import useSWR from "swr";
import { fetchFeed, fetchResolutions } from "@/lib/api";
import type { FeedItem, FeedEventData, FeedFuturesData, FeedBundleData, FeedConceptData } from "@/lib/types";
import DiscoverCard, { type DiscoverGroupedItem, GuessCard, DailyChallengeCard, ResolutionCard, ResolutionGroup } from "@/components/DiscoverCard";
import EndOfFeedCard from "@/components/discover/EndOfFeedCard";
import DiscoverSkeletonGrid from "@/components/discover/DiscoverSkeletonGrid";
import { Button } from "@/components/ui/button";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { trackEvent } from "@/lib/analytics";
import {
  getDiscoverCategoryAdjustment,
  getDiscoverItemAnalytics,
  conceptDomainToCategory,
  getDiscoverPersonalizationTrace,
  readDiscoverInteractionProfile,
  recordDiscoverInteraction,
  sendDiscoverInteraction,
  type DiscoverProfile,
} from "@/lib/discoverInteractions";
import { initialFeedRequest, nextFeedRequest, dedupeById } from "@/lib/discover/feedPaging";
import { isStale } from "@/lib/discover/feedFreshness";
import { feedItemHasRenderableContent, collectSuppressedEnvelopes } from "@/components/discover/utils";

const DISMISSED_KEY = "discover_dismissed";
const PAGE_SIZE = 20;
const DISMISS_TTL_MS = 6 * 60 * 60 * 1000;
const MAX_LOCAL_DISMISSES = 40;
const MIN_ITEMS_AFTER_LOCAL_DISMISS = 20;
const CATEGORY_COOLDOWN_DISMISSES = 3;
const CATEGORY_COOLDOWN_SCORE = -3;

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
  // Theme/comparison bundles carry a stable unique `id` (story_key/group_id +
  // member ids). Without this case bundles fell through to `tournament-undefined`,
  // collided, and got dropped by the dedup pass (Queue #62 / OPS-88).
  if (item.type === "bundle") return `bundle-${(item.data as FeedBundleData).id}`;
  // Concept cards (UFC/F1/cycling) carry their own `event:<domain>:<slug>` key —
  // give them a concept-specific id so they no longer share the `tournament-`
  // namespace (avoids a prefix collision in the dedup pass). (L2-167 Item 3.)
  if (item.type === "concept") return `concept-${(item.data as FeedConceptData).key}`;
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
  // Bundle: use the first ranked member's category (never the "golf"
  // fallthrough, which mis-suppressed bundles via the category cooldown).
  if (item.type === "bundle") {
    const first = (item.data as FeedBundleData).items?.[0];
    return first ? getItemCategory(first) : "other";
  }
  // Concept cards derive category from `domain` (ufc→mma, f1→motorsports,
  // cycling→cycling) instead of the "golf" fallthrough, so they attribute to the
  // right sport and are no longer mis-suppressed by a golf category-cooldown.
  if (item.type === "concept") {
    return conceptDomainToCategory((item.data as FeedConceptData).domain);
  }
  return "golf";
}

function getGroupedAnalytics(groupedItem: DiscoverGroupedItem) {
  const item = groupedItem.type === "single" ? groupedItem.item : groupedItem.items?.[0];
  return item ? getDiscoverItemAnalytics(item) : null;
}

function getSuppressedCategories(profile: DiscoverProfile | null): Set<string> {
  const suppressed = new Set<string>();
  if (!profile?.categories) return suppressed;

  for (const [category, bucket] of Object.entries(profile.categories)) {
    if (
      bucket.dismisses >= CATEGORY_COOLDOWN_DISMISSES &&
      bucket.score <= CATEGORY_COOLDOWN_SCORE &&
      bucket.likes === 0 &&
      bucket.shares === 0
    ) {
      suppressed.add(category.toLowerCase());
    }
  }
  return suppressed;
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

/** Interleave items so the default feed does not cluster into one sport or topic. */
function interleave(items: FeedItem[]): FeedItem[] {
  if (items.length <= 2) return items;

  // Separate sports from non-sports
  const SPORTS = new Set(["basketball", "football", "baseball", "hockey", "soccer", "golf", "mma", "boxing", "tennis", "cricket", "motorsports", "americanfootball", "icehockey", "cycling"]);
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

  const SPORTS = new Set(["basketball", "football", "baseball", "hockey", "soccer", "golf", "mma", "boxing", "tennis", "cricket", "motorsports", "americanfootball", "icehockey", "cycling"]);
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

const SPORTS_CATS = new Set(["basketball", "football", "baseball", "hockey", "soccer", "golf", "mma", "boxing", "tennis", "cricket", "motorsports", "americanfootball", "icehockey", "cycling", "olympics"]);

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




  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [showSwipeHint, setShowSwipeHint] = useState(false);
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
    if (typeof window !== "undefined" && !localStorage.getItem("discover_has_swiped")) {
      setShowSwipeHint(true);
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

  useEffect(() => {
    if (!showSwipeHint) return;
    const dismissHint = () => {
      setShowSwipeHint(false);
      localStorage.setItem("discover_has_swiped", "1");
    };
    window.addEventListener("discover-profile-updated", dismissHint);
    const timer = window.setTimeout(dismissHint, 5000);
    return () => {
      window.removeEventListener("discover-profile-updated", dismissHint);
      window.clearTimeout(timer);
    };
  }, [showSwipeHint]);

  const { data, isLoading, error: feedError, mutate: mutateFeed } = useSWR(
    "discover-feed",
    () => {
      // One bounded initial (offset-zero) request. SWR owns this single fetch;
      // background revalidation reuses the same key/shape (no duplicate initial).
      const { limit, offset } = initialFeedRequest();
      return fetchFeed({ limit, offset, event_pct: 0.15 });
    },
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

  // Load the next page from the API when client-side items run out. Exactly one
  // request, advancing monotonically from the returned page boundary — it never
  // re-requests offset zero (that is the SWR-owned initial fetch's job).
  const loadNextPage = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const loadedItems = [...(data?.items ?? []), ...allItems];
      const loadedIds = new Set(loadedItems.map(getItemId));
      const { limit, offset } = nextFeedRequest(loadedItems.length);
      const resp = await fetchFeed({ limit, offset, event_pct: 0.15 });
      const freshItems = resp.items.filter((item) => !loadedIds.has(getItemId(item)));

      if (freshItems.length > 0) {
        setAllItems((prev) => {
          const prevIds = new Set([...(data?.items ?? []), ...prev].map(getItemId));
          return [
            ...prev,
            ...freshItems.filter((item) => !prevIds.has(getItemId(item))),
          ];
        });
      }

      if (!resp.has_more) {
        setHasMore(false);
      }
    } catch { }
    setLoadingMore(false);
  }, [allItems, data, loadingMore, hasMore]);

  // Graceful end-of-feed refresh: reset paging state, scroll to top, revalidate
  // page 1. This is the web reload affordance (web has no pull-to-refresh).
  const handleRefreshFeed = useCallback(() => {
    trackEvent("feed_refresh", { trigger: "manual", new_items_count: 0 });
    setAllItems([]);
    setVisibleCount(PAGE_SIZE);
    setHasMore(true);
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    mutateFeed();
  }, [mutateFeed]);

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
    // Deduplicate by stable item ID across pages (defense in depth — a paging
    // hiccup can never render the same card twice).
    const unique = dedupeById(raw, getItemId);
    // L2-215 Item 1 — fail closed on empty predictive envelopes (#1486): drop any
    // card that carries neither a renderable probability nor an authoritative result
    // (empty concept/bundle/tournament/futures) BEFORE grouping, so no bare tile,
    // group slot, or bundle member ever reaches render. The auto-pager (below) keeps
    // fetching when this shortens a page, so it can never leave a blank tab.
    const renderable = unique.filter((item) => feedItemHasRenderableContent(item));
    const fresh = renderable.filter((item) => !isStale(item));
    const dismissFiltered = fresh.filter((item) => !dismissed.has(getItemId(item)));
    const filtered = dismissFiltered.length >= MIN_ITEMS_AFTER_LOCAL_DISMISS
      || fresh.length < MIN_ITEMS_AFTER_LOCAL_DISMISS
      ? dismissFiltered
      : fresh;
    const suppressedCategories = getSuppressedCategories(interactionProfile);
    const cooldownFiltered = suppressedCategories.size
      ? filtered.filter((item) => !suppressedCategories.has(getItemCategory(item).toLowerCase()))
      : filtered;
    const cooldownSafe = cooldownFiltered.length > 0 ? cooldownFiltered : filtered;
    const grouped = groupRelatedMarkets(interleave(cooldownSafe));
    return interleaveGrouped(applyLocalPersonalization(grouped, interactionProfile));
  }, [data, allItems, dismissed, interactionProfile]);

  // L2-215 Item 1 — suppression telemetry. Count the empty predictive envelopes
  // dropped by the fail-closed filter, by card type + machine reason, with NO
  // identity data (no ids, names, sessions, or market text). Fired once per distinct
  // suppression signature so a stable feed does not re-emit on every render.
  const suppressedEnvelopes = useMemo(
    () => collectSuppressedEnvelopes(dedupeById([...(data?.items ?? []), ...allItems], getItemId)),
    [data, allItems],
  );
  const suppressedSigRef = useRef("");
  useEffect(() => {
    if (suppressedEnvelopes.length === 0) return;
    const counts = new Map<string, number>();
    for (const e of suppressedEnvelopes) {
      const key = `${e.type}:${e.reason}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const sig = [...counts.entries()].sort().map(([k, v]) => `${k}=${v}`).join(",");
    if (sig === suppressedSigRef.current) return;
    suppressedSigRef.current = sig;
    for (const [key, count] of counts) {
      const [card_type, suppression_reason] = key.split(":");
      trackEvent("feed_card_suppressed", { card_type, suppression_reason, count, surface: "discover" });
    }
  }, [suppressedEnvelopes]);

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

  return (
    <ErrorBoundary fallback={<div className="p-8 text-center"><h2>Something went wrong</h2><button onClick={() => window.location.reload()} className="mt-2 text-sm text-accent-brand hover:underline">Reload page</button></div>}>
    <div className="min-h-screen bg-surface-deep">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-surface-card/80 backdrop-blur-lg border-b border-surface-border">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <h1 className="text-lg font-black tracking-tight">Discover</h1>
            <div className="flex items-center gap-3">
              {/* L2-119: killed the "{N} markets" count — on an infinite feed it
                  was the loaded-so-far tally, which reads as a (wrong) total and
                  ticks up as you scroll. The stats link stays. */}
              <Link
                href="/discover/stats"
                aria-label="Prediction stats"
                className="text-text-muted hover:text-text-primary transition-colors"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 20V10" /><path d="M18 20V4" /><path d="M6 20v-4" />
                </svg>
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* Swipe hint toast for first-time visitors */}
      {showSwipeHint && (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-40 animate-fade-in">
          <div className="bg-gray-900 text-white px-5 py-3 rounded-2xl shadow-2xl flex items-center gap-3 text-sm">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500 text-xs font-bold">→</span>
            <span>Swipe right for more like this</span>
          </div>
        </div>
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
        {isLoading && <DiscoverSkeletonGrid />}

        {!isLoading && feedError && !data && (
          <div className="text-center py-20 text-text-muted" data-testid="discover-feed-error" role="alert">
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
          <div className="py-16 flex justify-center">
            <EndOfFeedCard count={0} onRefresh={handleRefreshFeed} />
          </div>
        )}

        {/* Your settled Higher/Lower guesses (L2-119). 3+ collapse into one
            "Your results" group; 1–2 render as individual clickable cards. */}
        {resolutionsData && resolutionsData.resolutions.length > 0 && (
          resolutionsData.resolutions.length >= 3 ? (
            <div className="mb-4">
              <ResolutionGroup resolutions={resolutionsData.resolutions.slice(0, 8)} />
            </div>
          ) : (
            <div className="mb-4 columns-1 sm:columns-2 lg:columns-3 xl:columns-4 gap-4">
              {resolutionsData.resolutions.map((r, idx) => (
                <div key={`${r.market_id}-${idx}`} className="break-inside-avoid mb-4">
                  <ResolutionCard
                    marketId={r.market_id}
                    marketName={r.market_name}
                    guess={r.guess}
                    threshold={r.threshold}
                    actual={r.actual}
                    correct={r.correct}
                  />
                </div>
              ))}
            </div>
          )
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

            const isFirstCard = idx === 0 && showSwipeHint;

            return (
              // `data-testid="discover-card"` is the browser-audit rail's
              // proof that REAL content rendered (L2-223). The audit used to
              // match `main div.break-inside-avoid`, which the loading
              // skeleton also carries — so a Discover stuck on skeletons
              // satisfied "a real card was visible", recorded a first-card
              // latency, and reported green. This hook exists only on a
              // mounted feed item, so that false green cannot recur.
              <div
                key={key}
                data-testid="discover-card"
                className={`break-inside-avoid mb-4${isFirstCard ? " animate-peek-right" : ""}`}
              >
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
          <div className="mt-6 mb-2 flex justify-center">
            <EndOfFeedCard count={processedItems.length} onRefresh={handleRefreshFeed} />
          </div>
        )}
      </main>
    </div>
    </ErrorBoundary>
  );
}

