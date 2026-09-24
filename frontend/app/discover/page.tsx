"use client";

import { useState, useCallback, useEffect, useRef, useMemo, type ReactNode } from "react";
import ErrorBoundary from "@/components/ErrorBoundary";
import Link from "next/link";
import useSWR from "swr";
import { fetchFeed, fetchResolutions } from "@/lib/api";
import { useAuthContext } from "@/components/AuthProvider";
import type { FeedItem, FeedEventData, FeedFuturesData, FeedBundleData, FeedConceptData } from "@/lib/types";
import DiscoverCard, { type DiscoverGroupedItem, GuessCard, DailyChallengeCard, ResolutionCard, ResolutionGroup } from "@/components/DiscoverCard";
import EndOfFeedCard from "@/components/discover/EndOfFeedCard";
import FeedUnavailableNotice, { type FeedFailureReason } from "@/components/discover/FeedUnavailableNotice";
import DiscoverSkeletonGrid from "@/components/discover/DiscoverSkeletonGrid";
import { Button } from "@/components/ui/button";
import { usePageTracking, useScrollDepth, useEngagementTime, usePinnedFutures } from "@/hooks";
import { trackEvent } from "@/lib/analytics";
import {
  getDiscoverItemAnalytics,
  conceptDomainToCategory,
  getDiscoverPersonalizationTrace,
  readDiscoverInteractionProfile,
  recordDiscoverInteraction,
  sendDiscoverInteraction,
  type DiscoverProfile,
} from "@/lib/discoverInteractions";
import { SHAPE_UNSHAPED } from "@/lib/marketShape";
import {
  FEED_EVENT_PCT,
  initialFeedRequest,
  nextFeedRequest,
  dedupeById,
  reconcilePage1,
  shouldLoadNextPage,
  shouldAdvanceWindow,
} from "@/lib/discover/feedPaging";
import {
  FEED_RESTORE_LANDING_TIMEOUT_MS,
  clearFeedRestore,
  landingTarget,
  markAndDetectClientTransition,
  readFeedSnapshot,
  readScrollMark,
  shouldRestoreOnMount,
  writeFeedSnapshot,
  writeScrollMark,
} from "@/lib/discover/feedRestore";
import FeedBootScript from "@/components/discover/FeedBootScript";
import { deriveGroupDisplayTitle } from "@/lib/discover/groupTitle";
import { futuresGroupKey } from "@/lib/discover/groupKey";
import { decideFeedPage } from "@/lib/discover/feedAvailability";
import { isStale } from "@/lib/discover/feedFreshness";
import { applyLocalPersonalization, recordEditionScores } from "@/lib/discover/editionOrder";
import { feedItemHasRenderableContent, collectSuppressedEnvelopes, feedItemCanBeGuessed } from "@/components/discover/utils";
import FirstRunOrientation from "@/components/discover/FirstRunOrientation";
import {
  areGamesUnlocked,
  isFirstRunAnonymous,
  markFirstRunEngaged,
  markGamesUnlocked,
  readFirstRunStorage,
  GAMES_UNLOCK_CARDS_SEEN,
  type FirstRunStorage,
} from "@/lib/discoverFirstRun";
import { CHALLENGE_SURFACES_ENABLED } from "@/lib/launchSurfaces";

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

/**
 * Group related futures by their stated colon subject
 * (e.g. "Valero Texas Open: Winner" + "Valero Texas Open: Top 10" → one card).
 *
 * #4804: a market with no colon subject is NOT grouped. See
 * `lib/discover/groupKey.ts` for why the old first-three-words fallback had to go.
 */
function groupRelatedMarkets(items: FeedItem[]): DiscoverGroupedItem[] {
  const result: DiscoverGroupedItem[] = [];
  const futuresGroups = new Map<string, FeedItem[]>();
  const futuresOrder: string[] = [];

  for (const item of items) {
    if (item.type === "futures") {
      // #4804 — the key is the colon subject or nothing. The old "otherwise
      // first 3 words" arm folded any two questions that merely opened the
      // same way into one card ("Who will be ... Sweden?" + "Who will be
      // Trump's next Press Secretary?"). See lib/discover/groupKey.ts.
      const key = futuresGroupKey((item.data as FeedFuturesData).name);
      if (key === null) continue;

      if (!futuresGroups.has(key)) {
        futuresGroups.set(key, []);
        futuresOrder.push(key);
      }
      futuresGroups.get(key)!.push(item);
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
    const key = futuresGroupKey(name);
    // #4804 — a market whose name states no shared subject is not groupable.
    // It renders as its own card, in place, which is what it is.
    if (key === null) {
      result.push({ type: "single", item });
      continue;
    }

    if (usedPrefixes.has(key)) continue;
    usedPrefixes.add(key);

    const group = futuresGroups.get(key)!;
    if (group.length >= 2) {
      // L2-243 Item 1 — the grouping KEY (`key`) and the DISPLAYED title are
      // decided separately, so the pill never shows a truncated question
      // fragment ("Will the U.S.").
      //
      // #4804 — since a group now only forms on a colon subject,
      // `deriveGroupDisplayTitle` always takes its colon branch here and returns
      // that subject. Its category / "Related markets" fallbacks are no longer
      // reachable from this call site; they are kept because the helper is
      // exported and must stay honest for any caller that has no subject.
      const groupCategory = (group[0].data as FeedFuturesData).llm_sport_category;
      result.push({
        type: "group",
        items: group,
        groupTitle: deriveGroupDisplayTitle(name, groupCategory),
      });
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
  onSeen,
  children,
}: {
  groupedItem: DiscoverGroupedItem;
  positionIndex: number;
  personalizationTrace?: string;
  /**
   * Queue 309 Item 3 — fires once, the first time this card is genuinely in
   * view. The page counts distinct positions to decide when a first-run reader
   * has met enough content to unlock the games. Reusing the impression observer
   * rather than a pixel offset is deliberate: the feed is a CSS multi-column
   * masonry, so on a wide screen 8 cards can be above the fold with no
   * scrolling at all, and a scroll-distance threshold would never fire.
   */
  onSeen?: (positionIndex: number) => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const tracked = useRef(false);
  const analytics = useMemo(() => getGroupedAnalytics(groupedItem), [groupedItem]);

  useEffect(() => {
    if (tracked.current) return;
    const node = ref.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting || tracked.current) return;
        tracked.current = true;
        // Analytics is absent for a few grouped shapes; the "seen" signal is
        // not, because a card without analytics is still content the reader met.
        if (analytics) {
          trackEvent("feed_card_impression", {
            ...analytics,
            position: positionIndex,
            surface: "discover",
          });
          recordDiscoverInteraction(analytics.category, "impression");
          sendDiscoverInteraction(analytics, "impression", positionIndex, "viewport");
        }
        onSeen?.(positionIndex);
        observer.disconnect();
      },
      { threshold: 0.55 }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [analytics, positionIndex, onSeen]);

  return (
    <div ref={ref} data-personalization-trace={personalizationTrace}>
      {children}
    </div>
  );
}

// Exported for `__tests__/capture/emptyStatesRenderTheirOwnBranch.test.tsx`,
// which renders the no-cards branch. Three certs blocked a source-only anchor on
// this empty state; a render needs the component to be reachable.
export function ChallengeModal({
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
            <div
              className="rounded-2xl border border-surface-border bg-surface-card p-6 text-center shadow-md"
              data-empty-state-name="challenge-no-cards"
            >
              <h2 className="text-lg font-black text-text-primary">No challenge cards right now</h2>
              {/* Ruling 142: say where the challenge gets its questions, not
                  when more will arrive. */}
              <p className="mt-2 text-sm text-text-secondary">
                The daily challenge draws its questions from the live feed.
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

  // UX-P234 (board item 16) — Alex: "on the web Discover feed there is no
  // indication a card can be pinned at all." It could not be: the Discover card
  // had no pin of any kind, while the SAME market was pinnable from search,
  // my-stuff and preferences.
  //
  // The PAGE owns the store and hands each card its binding, matching how
  // search/my-stuff/preferences already drive `components/FuturesCard`. A first
  // draft called this hook inside the leaf card instead; it reaches
  // `useAuthContext`, which throws outside an `AuthProvider`, and it took down ten
  // suites that render that card in isolation. `DiscoverCard`'s own docblock
  // already said why: cards stay presentational, never a storage read in there.
  const { isPinned: isFuturePinned, togglePin: toggleFuturePin, isMaxReached: futurePinsFull } =
    usePinnedFutures();
  const pinForFutures = useCallback(
    (futuresId: number) => ({
      pinned: isFuturePinned(futuresId),
      onToggle: () => toggleFuturePin(futuresId),
      atMax: futurePinsFull,
      noun: "market",
    }),
    [isFuturePinned, toggleFuturePin, futurePinsFull],
  );

  // Auth state only feeds the L2-242 shared-anon decision below (feed reads still
  // attach the bearer via apiFetch's module-level getter). Signed-in users are
  // never served the shared feed — the backend keys authenticated requests to
  // `u:<id>` regardless of x-session-id — but passing `authenticated` here keeps
  // the client decision honest.
  const { user } = useAuthContext();

  // L2-242 / C133 — only the PROVEN first request of a fresh, signed-out,
  // zero-interaction visitor may reuse the shared `anon` warm feed. Flips false
  // on the first seen/dismiss THIS mount; the resolver also fails closed on any
  // durable session / prior interaction / unreadable storage.
  const sharedAnonEligibleRef = useRef(true);

  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  // #8176 — whether the infinite-scroll sentinel is inside the observer's band
  // right now. A LEVEL, deliberately: the advance that reads it must be
  // re-askable on every commit, because the transition that used to drive it
  // cannot be produced once the document stops growing.
  const [sentinelVisible, setSentinelVisible] = useState(false);
  const [showSwipeHint, setShowSwipeHint] = useState(false);
  const [dailyGuesses, setDailyGuesses] = useState(0);
  const [allItems, setAllItems] = useState<FeedItem[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  // L2-238: the last page-1 payload the availability decision ACCEPTED. SWR's
  // `data` is whatever came back last, including a typed-unavailable empty body;
  // rendering off `data.items` directly is what let an unavailable revalidation
  // blank a populated feed and then show "all caught up".
  const [page1Items, setPage1Items] = useState<FeedItem[]>([]);
  // L2-238: the backend typed the last response `cache.status = "unavailable"`.
  // A transient no-data terminal, not an empty feed — surfaces this page's own
  // retry state and freezes auto-pagination until the reader retries.
  const [feedUnavailable, setFeedUnavailable] = useState(false);
  const [interactionProfile, setInteractionProfile] = useState<DiscoverProfile | null>(null);
  // #2603 — the ORDER of the edition is decided once: the profile as it stood
  // when the edition opened, and each card's score when it first arrived. The
  // live profile still drives the category cooldown (a removal the reader
  // asked for); it no longer re-sorts cards already on screen. Both reset on a
  // manual refresh. See `lib/discover/editionOrder.ts`.
  const [orderingProfile, setOrderingProfile] = useState<DiscoverProfile | null>(null);
  const editionScoresRef = useRef<Map<string, number>>(new Map());
  const [challengeOpen, setChallengeOpen] = useState(false);
  const [challengeIndex, setChallengeIndex] = useState(0);
  const [challengeComplete, setChallengeComplete] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);
  // #7417 — restore state.
  //
  // `initialVisibleCount` is a STATE value rather than the `PAGE_SIZE` literal
  // it used to be, because `shouldLoadNextPage` reads it as "the window the
  // reader was handed on arrival". A restore hands them a window of, say, 60;
  // comparing that against 20 says the reader advanced it themselves, and the
  // auto-pager fires a page nobody asked for on the first commit after Back.
  const [initialVisibleCount, setInitialVisibleCount] = useState(PAGE_SIZE);
  // The offset a restore is still trying to land on, or `null` when there is
  // nothing pending. Held as a ref as well as state because the sentinel
  // observer and the snapshot writer both have to see it synchronously.
  const [pendingScrollY, setPendingScrollY] = useState<number | null>(null);
  const restorePendingRef = useRef(false);
  // Until the mount effect has looked, nothing may be written: the first commit
  // has empty item state, and saving that over a good edition is how a restore
  // destroys the thing it is restoring.
  const restoreCheckedRef = useRef(false);
  // Queue 309 — first-run orientation state. `null` means "storage not read
  // yet": the pre-mount render is deliberately today's Discover exactly, so no
  // first-run UI can appear in SSR markup and diverge from first hydration.
  const [firstRunStorage, setFirstRunStorage] = useState<FirstRunStorage | null>(null);
  const [engagedThisSession, setEngagedThisSession] = useState(false);
  const [cardsSeen, setCardsSeen] = useState(0);
  const [hasScrolled, setHasScrolled] = useState(false);
  const seenPositionsRef = useRef<Set<number>>(new Set());
  // Queue 310 Item 2 — `feed_exit` state. Declared here, above the action
  // handlers that write them, so the handlers reference initialized bindings
  // rather than relying on closure/TDZ ordering.
  const feedExitFiredRef = useRef(false);
  const feedEnteredAtRef = useRef<number | null>(null);
  const maxScrollDepthRef = useRef(0);
  const lastActionWasDismissRef = useRef(false);
  const exitSnapshotRef = useRef({ itemCount: 0, hasError: false, isLoading: true });

  useEffect(() => {
    setDismissed(getDismissed());
    const profile = readDiscoverInteractionProfile();
    setInteractionProfile(profile);
    setOrderingProfile(profile);
    if (typeof window !== "undefined" && !localStorage.getItem("discover_has_swiped")) {
      setShowSwipeHint(true);
    }
    // Queue 309: every first-run storage read happens HERE, in the one mount
    // effect that already reads `discover_has_swiped` — a second storage-reading
    // mount effect would invite an ordering bug between the two flags.
    setFirstRunStorage(readFirstRunStorage());
    const today = new Date().toISOString().slice(0, 10);
    const stored = localStorage.getItem(`daily_guesses_${today}`);
    if (stored) setDailyGuesses(parseInt(stored, 10));
  }, []);

  useEffect(() => {
    const refreshProfile = () => {
      setInteractionProfile(readDiscoverInteractionProfile());
      // Queue 309 Items 1-3: `discover-profile-updated` is dispatched for every
      // non-impression interaction — tap (detail_click), like, unlike, dismiss,
      // share. That is exactly the "first engagement" this orientation UI is
      // spent on, and exactly the tap that unlocks the games, so it is wired
      // once here rather than through a second invented signal path.
      setEngagedThisSession(true);
      markFirstRunEngaged();
    };
    window.addEventListener("discover-profile-updated", refreshProfile);
    return () => window.removeEventListener("discover-profile-updated", refreshProfile);
  }, []);

  // Queue 309 Item 3 — "the reader has moved at all". Not a distance threshold:
  // the card count is what measures how much content was met, and this only
  // stops a wide desktop masonry from satisfying that count on first paint
  // without the reader doing anything.
  useEffect(() => {
    if (hasScrolled) return;
    const onScroll = () => {
      if (window.scrollY > 0) setHasScrolled(true);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [hasScrolled]);

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

  /**
   * #7417 — put the reader's edition back before anything else touches state.
   *
   * 🔴 DECLARED ABOVE THE PAGE-1 PAYLOAD EFFECT ON PURPOSE. SWR's cache is
   * global and survives a client-side navigation, so on a Back the
   * `discover-feed` key resolves from cache on the very first commit and that
   * effect runs in the same batch as this one. React runs effects in
   * declaration order, so this seeds `page1Items` first and `reconcilePage1`
   * folds the cached page into the restored edition. Declared below it, the
   * order inverts: the cached 20-item page lands first, this overwrites it, and
   * the fold that protects the reader's order never happens.
   *
   * 🔴 AN EFFECT, NOT A LAZY `useState` INITIALIZER. `sessionStorage` does not
   * exist on the server, so a lazy initializer renders an empty feed on the
   * server and a restored one on the client — a hydration mismatch. This is the
   * same reason `dismissed` and the first-run storage are read in mount effects
   * a few lines up, and not a style choice.
   */
  useEffect(() => {
    restoreCheckedRef.current = true;
    const clientTransition = markAndDetectClientTransition(window);
    const navigationType =
      (performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined)
        ?.type ?? null;

    if (!shouldRestoreOnMount({ clientTransition, navigationType })) {
      // A reload or a fresh arrival. The reader asked for a fresh feed, so the
      // stale edition is dropped rather than left to be restored by the NEXT
      // Back — where its scroll mark would point past a document that has only
      // just been rebuilt from page one.
      clearFeedRestore();
      return;
    }

    const snapshot = readFeedSnapshot<FeedItem>();
    if (!snapshot) return;

    setPage1Items(snapshot.page1);
    setAllItems(snapshot.rest);
    setVisibleCount(snapshot.visibleCount);
    setInitialVisibleCount(snapshot.visibleCount);
    setHasMore(snapshot.hasMore);

    const mark = readScrollMark(Date.now());
    if (mark && mark.scrollY > 0) {
      restorePendingRef.current = true;
      setPendingScrollY(mark.scrollY);
    }
  }, []);

  const { data, isLoading, error: feedError, mutate: mutateFeed } = useSWR(
    "discover-feed",
    () => {
      // One bounded initial (offset-zero) request. SWR owns this single fetch;
      // background revalidation reuses the same key/shape (no duplicate initial).
      const { limit, offset } = initialFeedRequest();
      return fetchFeed(
        { limit, offset, event_pct: FEED_EVENT_PCT },
        { sharedAnonEligible: sharedAnonEligibleRef.current, authenticated: !!user }
      );
    },
    { refreshInterval: 120000, revalidateOnFocus: false, keepPreviousData: true }
  );

  // #6445 — a null key is SWR's "do not fetch". The banner is hidden for the
  // initial release, so the page stops asking the backend for settled guesses
  // as well as stops drawing them; a request whose only consumer is hidden is
  // a request nobody can read. Read history is untouched — this is a read we
  // are not making, not a row we are deleting.
  const { data: resolutionsData } = useSWR(
    CHALLENGE_SURFACES_ENABLED ? "discover-resolutions" : null,
    fetchResolutions,
    { revalidateOnFocus: false }
  );

  // L2-238: what the availability decision needs to know about the state that
  // existed BEFORE the payload landed. Declared ahead of the decision effect so
  // React runs these syncs first on any commit that changes both.
  const hasMoreRef = useRef(hasMore);
  useEffect(() => { hasMoreRef.current = hasMore; }, [hasMore]);
  const renderedCountRef = useRef(0);
  useEffect(() => {
    renderedCountRef.current = page1Items.length + allItems.length;
  }, [page1Items, allItems]);

  // L2-238: run every page-1 payload (initial load AND background revalidation)
  // through the availability decision before it touches rendered state. An
  // unavailable payload contributes no items, does not close pagination, and
  // raises the retry state; a genuinely empty, genuinely exhausted feed still
  // applies exactly as before.
  useEffect(() => {
    if (!data) return;
    const decision = decideFeedPage({
      payload: data,
      previousHasMore: hasMoreRef.current,
      hasRenderedItems: renderedCountRef.current > 0,
    });
    setFeedUnavailable(decision.showUnavailable);
    // #4430: fold the payload into the edition the reader is holding instead of
    // assigning over the top. A background tick updates cards in place and
    // appends what is new; it never removes or reorders one under the reader.
    // Cold load still takes the served page wholesale. See `reconcilePage1`.
    if (decision.acceptItems) {
      const incoming = data.items ?? [];
      setPage1Items((prev) => reconcilePage1(prev, incoming, getItemId));
    }
    setHasMore(decision.hasMore);
  }, [data]);

  // Load the next page from the API when client-side items run out. Exactly one
  // request, advancing monotonically from the returned page boundary — it never
  // re-requests offset zero (that is the SWR-owned initial fetch's job).
  const loadNextPage = useCallback(async () => {
    // L2-238: an unavailable page freezes the auto-pager. Without this the
    // sentinel would re-fire against a backend that just said it has nothing,
    // spinning forever instead of terminating on an actionable retry.
    if (loadingMore || !hasMore || feedUnavailable) return;
    setLoadingMore(true);
    try {
      const loadedItems = [...page1Items, ...allItems];
      const loadedIds = new Set(loadedItems.map(getItemId));
      const { limit, offset } = nextFeedRequest(loadedItems.length);
      const resp = await fetchFeed({ limit, offset, event_pct: FEED_EVENT_PCT });
      const decision = decideFeedPage({
        payload: resp,
        previousHasMore: true,
        hasRenderedItems: loadedItems.length > 0,
      });

      if (decision.showUnavailable) {
        // Keep every loaded card, keep `hasMore` exactly where it was, and let
        // the reader retry. An unavailable page never ends the feed.
        setFeedUnavailable(true);
        setLoadingMore(false);
        return;
      }

      if (decision.acceptItems) {
        const freshItems = resp.items.filter((item) => !loadedIds.has(getItemId(item)));
        if (freshItems.length > 0) {
          setAllItems((prev) => {
            const prevIds = new Set([...page1Items, ...prev].map(getItemId));
            return [
              ...prev,
              ...freshItems.filter((item) => !prevIds.has(getItemId(item))),
            ];
          });
        }
      }

      if (!decision.hasMore) {
        setHasMore(false);
      }
    } catch {
      // L2-243 Item 2 — a thrown/hung pagination fetch must not silently spin
      // forever. Surface the established unavailable/retry terminal (which also
      // freezes the auto-pager) instead of swallowing the error and leaving the
      // bottom spinner running. Already-rendered cards are preserved; the reader
      // gets an actionable retry via FeedUnavailableNotice.
      setFeedUnavailable(true);
    }
    setLoadingMore(false);
  }, [allItems, page1Items, loadingMore, hasMore, feedUnavailable]);

  // L2-238: the reader's way out of an unavailable feed. Clears the state and
  // revalidates page 1 — already-rendered cards stay exactly where they are.
  const handleRetryUnavailable = useCallback(() => {
    setFeedUnavailable(false);
    mutateFeed();
  }, [mutateFeed]);

  /**
   * UX-P087 (#1909) — retry a FAILED load without reloading the document.
   *
   * This control used to be `window.location.reload()`. On the failure that
   * actually happens — several people or several tabs behind one address burning
   * the 60/min anonymous budget — a full reload re-fires every request on the
   * page and is rate-limited again, so the only affordance offered was the one
   * action guaranteed not to work. `mutateFeed()` re-requests the feed alone,
   * which is both the cheapest retry and the only one with a chance of landing
   * inside the same minute.
   */
  const handleRetryFailedLoad = useCallback(() => {
    mutateFeed();
  }, [mutateFeed]);

  /**
   * Which honest state a failed load earns. A rate limit and an outage want
   * different sentences from the reader's point of view: one is "wait a moment",
   * the other is "this is not your fault and nothing here is stale".
   *
   * `ApiError.status` is set by `apiFetch` for every non-OK response; a thrown
   * timeout or a dead network carries no status and lands on `error`, which is
   * the honest reading — we do not know which side failed.
   */
  const feedFailureReason: FeedFailureReason =
    (feedError as { status?: number } | undefined)?.status === 429 ? "rate_limited" : "error";

  // Graceful end-of-feed refresh: reset paging state, scroll to top, revalidate
  // page 1. This is the web reload affordance (web has no pull-to-refresh).
  const handleRefreshFeed = useCallback(() => {
    trackEvent("feed_refresh", { trigger: "manual", new_items_count: 0 });
    setAllItems([]);
    // #2603 — a manual refresh opens a new edition: re-read the order inputs.
    editionScoresRef.current = new Map();
    setOrderingProfile(readDiscoverInteractionProfile());
    setVisibleCount(PAGE_SIZE);
    // 🔴 #7417 — THE SEED MOVES WITH THE WINDOW OR THE AUTO-PAGER STALLS. After
    // a Back the seed is the restored window (say 60). Resetting `visibleCount`
    // to 20 and leaving the seed at 60 makes `visibleCount <= initialVisibleCount`
    // true, which `shouldLoadNextPage` reads as "the reader has not touched the
    // window" — so pagination sits out the next three sentinel fires while the
    // reader scrolls a 20-card feed. Reachable by anyone who presses Back and
    // then taps refresh.
    setInitialVisibleCount(PAGE_SIZE);
    setHasMore(true);
    setFeedUnavailable(false);
    // A manual refresh is the reader asking for a fresh feed, exactly as a
    // reload is. Keeping the old edition would let the NEXT Back restore the
    // feed they just chose to discard.
    clearFeedRestore();
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    mutateFeed();
  }, [mutateFeed]);

  // Infinite scroll observer. Re-armed whenever the sentinel unmounts and
  // remounts (L2-238: an unavailable page swaps the spinner for a retry, so the
  // node this observes is destroyed and rebuilt — an observer left watching the
  // detached node would silently kill infinite scroll after a successful retry).
  //
  // 🔴 LAT-P172: `isLoading` is a REQUIRED dependency, not a completeness tidy.
  // The sentinel is now gated on `!isLoading`, so on a cold load the node does
  // not exist when this effect first runs. Without `isLoading` here the effect
  // would never re-run, `sentinelRef.current` would stay null, and infinite
  // scroll would be dead on every cold load — the fix would trade one uninvited
  // fetch for no pagination at all.
  // 🔴 #8176 — THIS OBSERVER RECORDS A LEVEL AND ADVANCES NOTHING. It used to
  // call `setVisibleCount` directly from the intersection callback, which made
  // the window advance EDGE-triggered. Because rendering is capped at
  // `visibleCount` (`processedItems.slice(0, visibleCount)`), the window is the
  // only thing that makes the document taller — so a window that stopped
  // advancing froze the document, which kept the sentinel inside the 400px
  // band, which meant no further transition was ever delivered to re-start it.
  // Measured on production: the feed died at 40 of 115 cards behind a spinner
  // that could never resolve. See `shouldAdvanceWindow` for the full account.
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      ([entry]) => setSentinelVisible(entry.isIntersecting),
      { rootMargin: "400px" }
    );
    observer.observe(sentinel);
    return () => {
      observer.disconnect();
      // 🔴 The sentinel is conditionally rendered (LAT-P172 gates it on
      // `!isLoading`, L2-238 swaps it for a retry). A disconnected observer
      // delivers no exit event, so without this the level would stay stuck
      // `true` after the node it describes has gone and the advance effect
      // would keep firing against a sentinel nobody can see.
      setSentinelVisible(false);
    };
  }, [feedUnavailable, isLoading]);

  /**
   * #7417 — land the reader on the offset they left from, once the restored
   * document is actually tall enough to hold it.
   *
   * 🔴 THE HEIGHT CHECK IS THE POINT. Scrolling to a saved offset in a document
   * that has not finished laying out is precisely the defect: the browser
   * clamps to the short document's maximum and the reader ends up at the
   * bottom. `landingTarget` only reports `reached` when the offset fits, so
   * this waits frame by frame instead of scrolling into a document that is not
   * there yet.
   *
   * On timeout it lands on the best available offset rather than abandoning the
   * restore. That case is a reader who was deeper than `FEED_SNAPSHOT_MAX_ITEMS`
   * can hold: as close as the cap reaches is still their part of the feed,
   * where doing nothing would leave them at the top.
   */
  useEffect(() => {
    if (pendingScrollY === null) return;
    const deadline = Date.now() + FEED_RESTORE_LANDING_TIMEOUT_MS;
    let frame = 0;
    const attempt = () => {
      const { y, reached } = landingTarget(
        pendingScrollY,
        document.documentElement.scrollHeight,
        window.innerHeight,
      );
      if (!reached && Date.now() < deadline) {
        frame = requestAnimationFrame(attempt);
        return;
      }
      window.scrollTo(0, y);
      restorePendingRef.current = false;
      setPendingScrollY(null);
    };
    frame = requestAnimationFrame(attempt);
    return () => cancelAnimationFrame(frame);
  }, [pendingScrollY]);

  /**
   * #7417 — keep the stored edition current.
   *
   * Written on state change rather than on the way out: a card tap is a
   * client-side route change, so there is no unload event to hang this on, and
   * `pagehide` never fires for the navigation that actually loses the feed.
   *
   * `restoreCheckedRef` is the guard that matters. The first commit of a Back
   * has empty item state — the restore effect has not run yet — and writing
   * that would blank the edition this whole module exists to preserve.
   */
  useEffect(() => {
    if (!restoreCheckedRef.current) return;
    if (page1Items.length === 0) return;
    writeFeedSnapshot({ page1: page1Items, rest: allItems, visibleCount, hasMore });
  }, [page1Items, allItems, visibleCount, hasMore]);

  /**
   * #7417 — keep the scroll mark current, throttled.
   *
   * 🔴 `restorePendingRef` IS LOAD-BEARING HERE, NOT DEFENSIVE. A restore in
   * flight generates scroll events at the clamped bottom of a half-built
   * document. Recording one overwrites the reader's real offset with the
   * artefact the restore is in the middle of correcting, and the next Back
   * would faithfully return them to the footer — the defect, now persisted.
   */
  useEffect(() => {
    let timer = 0;
    const onScroll = () => {
      if (timer) return;
      timer = window.setTimeout(() => {
        timer = 0;
        if (!restoreCheckedRef.current || restorePendingRef.current) return;
        writeScrollMark({ scrollY: window.scrollY, savedAt: Date.now() });
      }, 250);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  const handleDismiss = useCallback((itemId: string) => {
    // L2-242 — a dismiss is seen/dismiss evidence: never share the warm feed on
    // a later request this mount (the durable dismiss set also proves this on
    // reload).
    sharedAnonEligibleRef.current = false;
    // Queue 310 Item 2 — the reader's most recent act was a dismiss. Cleared by
    // any subsequent card open, so this reflects the FINAL action, not "a
    // dismiss happened at some point".
    lastActionWasDismissRef.current = true;
    // Persist local dismissals so anonymous users do not see the same card
    // again after refresh while the server downrank catches up.
    setDismissed((prev) => {
      const next = new Set([...prev, itemId]);
      saveDismissed(next);
      return next;
    });
  }, []);

  // Queue 309 Item 3 — one card genuinely in view. Distinct positions only, so a
  // card scrolled past twice cannot inflate the count toward the unlock.
  const handleCardSeen = useCallback((position: number) => {
    if (seenPositionsRef.current.has(position)) return;
    // Queue 310 Item 2 — meeting a NEW card means the reader kept going, so a
    // dismiss is no longer their last act. This is what makes `dismissed_last`
    // mean "dismissed, then stopped" rather than "dismissed at some point",
    // which would swallow most of the mid_scroll bucket.
    lastActionWasDismissRef.current = false;
    seenPositionsRef.current.add(position);
    setCardsSeen(seenPositionsRef.current.size);
  }, []);

  const startChallenge = useCallback(() => {
    // Queue 309 Item 1 — playing the challenge is engagement: it spends the
    // orientation UI permanently, exactly as a tap or a like does.
    setEngagedThisSession(true);
    markFirstRunEngaged();
    // Queue 310 Item 2 — playing the challenge is a later act than any dismiss.
    lastActionWasDismissRef.current = false;
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
      // The daily challenge is a synthetic card, not a market — it has no shape.
      market_type: SHAPE_UNSHAPED,
    }, "challenge_start", undefined, "challenge");
  }, []);

  const processedItems = useMemo((): DiscoverGroupedItem[] => {
    // L2-238: the last ACCEPTED page-1 items, not `data.items` — an unavailable
    // revalidation must never blank the generation already on screen.
    const raw = [...page1Items, ...allItems];
    // Deduplicate by stable item ID across pages (defense in depth — a paging
    // hiccup can never render the same card twice).
    const unique = dedupeById(raw, getItemId);
    // #2603 — first sight fixes a card's ranking score for this edition.
    const editionScores = editionScoresRef.current;
    recordEditionScores(editionScores, unique, getItemId);
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
    return interleaveGrouped(
      applyLocalPersonalization(grouped, orderingProfile, (groupedItem) => {
        const item = groupedItem.type === "single" ? groupedItem.item : groupedItem.items?.[0];
        if (!item) return null;
        return {
          score: editionScores.get(getItemId(item)) ?? item.score ?? 0,
          category: getDiscoverItemAnalytics(item).category,
        };
      }),
    );
  }, [page1Items, allItems, dismissed, interactionProfile, orderingProfile]);

  // L2-215 Item 1 — suppression telemetry. Count the empty predictive envelopes
  // dropped by the fail-closed filter, by card type + machine reason, with NO
  // identity data (no ids, names, sessions, or market text). Fired once per distinct
  // suppression signature so a stable feed does not re-emit on every render.
  const suppressedEnvelopes = useMemo(
    () => collectSuppressedEnvelopes(dedupeById([...page1Items, ...allItems], getItemId)),
    [page1Items, allItems],
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

  // Queue 309 — the whole first-run decision, in two lines. Both delegate to
  // pure functions that take no time input, so neither can expire on a timer
  // the way the swipe hint does (that 5s dismissal is the trap this copies the
  // persistence of, and not the timing of).
  const isFirstRunAnon = isFirstRunAnonymous({
    authenticated: !!user,
    storage: firstRunStorage,
    engagedThisSession,
  });
  const gamesUnlocked = areGamesUnlocked({
    firstRun: isFirstRunAnon,
    storage: firstRunStorage,
    cardsSeen,
    hasScrolled,
    engagedThisSession,
  });

  // Persist the unlock the moment it is earned, so games do not re-lock on a
  // remount mid-session. Only for the cohort that was ever locked — nobody
  // else's storage is touched.
  useEffect(() => {
    if (isFirstRunAnon && gamesUnlocked) markGamesUnlocked();
  }, [isFirstRunAnon, gamesUnlocked]);

  // ==========================================================================
  // Queue 310 Item 2 — `feed_exit`, the session-death event.
  //
  // Content-free by construction: positions, counts, a duration, one enum. No
  // item id, market text or category may be added here.
  //
  // Everything the handler reads comes from a REF, never from state captured in
  // the listener's closure — a listener registered once would otherwise report
  // the counts as they were at mount (0 cards seen, still loading) for every
  // session. The snapshot ref is refreshed by its own effect each render.
  // ==========================================================================
  useEffect(() => {
    exitSnapshotRef.current = {
      itemCount: processedItems.length,
      hasError: !!feedError,
      isLoading,
    };
  }, [processedItems.length, feedError, isLoading]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    feedEnteredAtRef.current = Date.now();

    const trackScroll = () => {
      const doc = document.documentElement;
      const scrollable = doc.scrollHeight - window.innerHeight;
      // A feed shorter than the viewport is fully seen, not 0% seen. The feed is
      // a CSS multi-column masonry, so on a wide screen this is the common case.
      const pct =
        scrollable <= 0
          ? 100
          : Math.min(100, Math.round(((window.scrollY || doc.scrollTop) / scrollable) * 100));
      if (pct > maxScrollDepthRef.current) maxScrollDepthRef.current = pct;
    };
    trackScroll();

    const fireFeedExit = () => {
      // Fires at most once per page life. `visibilitychange` and `beforeunload`
      // both fire on a real tab close, and mobile Safari commonly fires only the
      // former — so both are registered and the guard is what keeps it to one.
      // Without it, every tab-switch would re-report the session as dead.
      if (feedExitFiredRef.current) return;
      feedExitFiredRef.current = true;

      const seen = seenPositionsRef.current;
      const { itemCount, hasError, isLoading: loading } = exitSnapshotRef.current;
      const lastPosition = seen.size > 0 ? Math.max(...seen) : -1;

      let terminalState: "end_of_feed" | "unavailable" | "mid_scroll" | "dismissed_last";
      if (hasError || (!loading && itemCount === 0)) {
        // The reader was shown nothing — an empty or failed feed. Checked first:
        // "they left without reaching the end" is technically true here too, and
        // would hide the outage inside the ordinary mid_scroll bucket.
        terminalState = "unavailable";
      } else if (lastActionWasDismissRef.current) {
        // Their FINAL act was a dismiss (not necessarily on the final card).
        terminalState = "dismissed_last";
      } else if (itemCount > 0 && lastPosition >= itemCount - 1) {
        terminalState = "end_of_feed";
      } else {
        terminalState = "mid_scroll";
      }

      trackEvent(
        "feed_exit",
        {
          last_position: lastPosition,
          visible_count: seen.size,
          max_scroll_depth: maxScrollDepthRef.current,
          dwell_ms: feedEnteredAtRef.current ? Date.now() - feedEnteredAtRef.current : 0,
          terminal_state: terminalState,
        },
        // MANDATORY. `trackEvent` defers to requestIdleCallback by default, and
        // an idle callback never runs during unload — the default-options form
        // of this event would fire exactly zero times in production.
        { immediate: true }
      );
    };

    const onVisibility = () => {
      if (document.visibilityState === "hidden") fireFeedExit();
    };

    window.addEventListener("scroll", trackScroll, { passive: true });
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("beforeunload", fireFeedExit);

    return () => {
      window.removeEventListener("scroll", trackScroll);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("beforeunload", fireFeedExit);
    };
  }, []);

  const challengeItems = useMemo(() => {
    // #5763 — the same predicate the in-feed quiz slot uses. This filter used
    // to state the probability half privately, which is how the two sites came
    // to disagree about who may be asked a question at all.
    return processedItems
      .filter((gi): gi is { type: "single"; item: FeedItem } => {
        if (gi.type !== "single" || !gi.item) return false;
        return feedItemCanBeGuessed(gi.item);
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
      // The daily challenge is a synthetic card, not a market — it has no shape.
      market_type: SHAPE_UNSHAPED,
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

  // Load more from API when client-side items run out. The predicate lives in
  // `lib/discover/feedPaging` (LAT-P171) — inline it fired on the FIRST commit,
  // racing a duplicate `offset=1` feed build against the `offset=0` request that
  // gates the first card. See `shouldLoadNextPage` for the full account.
  //
  // LAT-P172: `initialVisibleCount` is what keeps the SECOND uninvited build off
  // the cold path. Without it the predicate is true the moment page one lands
  // (`visibleCount` is seeded to PAGE_SIZE, which is the page size), so a cold
  // load fetched page two before the reader had scrolled at all.
  //
  // 🔴 CERT-603: `loadedCount` is the RAW pre-filter count and it is a SEPARATE
  // argument from `renderedCount` on purpose. `processedItems` is downstream of
  // the L2-215 renderability filter, staleness, dismissal and suppression, so a
  // good non-empty page can render zero rows. Passing only `processedItems`
  // made "no page has landed" and "every row was filtered" the same state, and
  // the auto-pager stopped for good — a blank tab that L2-215 (see the comment
  // above `processedItems`) exists to prevent.
  // #8176 — the level-triggered half of infinite scroll. Declared here, below
  // `processedItems`, because the dependency array is evaluated during render:
  // referencing it from the observer effect above would be a TDZ error.
  //
  // `pendingScrollY` is a dependency because `restorePendingRef` is a ref and
  // cannot re-trigger anything. Without it a window suppressed during a restore
  // would stay suppressed after the restore RESOLVED, until something else
  // happened to move — the same class of freeze this fix is removing.
  useEffect(() => {
    if (
      shouldAdvanceWindow({
        sentinelVisible,
        visibleCount,
        renderedCount: processedItems.length,
        restorePending: restorePendingRef.current,
        pageSize: PAGE_SIZE,
      })
    ) {
      setVisibleCount((c) => c + PAGE_SIZE);
    }
  }, [sentinelVisible, visibleCount, processedItems.length, pendingScrollY]);

  const loadedCount = page1Items.length + allItems.length;
  useEffect(() => {
    if (
      shouldLoadNextPage({
        visibleCount,
        loadedCount,
        renderedCount: processedItems.length,
        // #7417: the window the reader ARRIVED with, which after a Back is the
        // restored one, not `PAGE_SIZE`. Hard-coding the literal here told the
        // predicate that a restored reader had already advanced their window by
        // two pages, so the auto-pager fetched on the first commit after Back.
        initialVisibleCount,
        hasMore,
        loadingMore,
      })
    ) {
      loadNextPage();
    }
  }, [visibleCount, loadedCount, processedItems.length, initialVisibleCount, hasMore, loadingMore, loadNextPage]);

  return (
    <ErrorBoundary fallback={<div className="p-8 text-center"><h2>Something went wrong</h2><button onClick={() => window.location.reload()} className="mt-2 text-sm text-accent-brand hover:underline">Reload page</button></div>}>
    <div className="min-h-screen bg-surface-deep">
      {/* LAT-P184 (D-C, staged loading). FIRST node in the Discover tree so the
          parser reaches it — and puts the first screen's request on the wire —
          before the header, the skeleton grid and the footer are even parsed,
          let alone before any entry chunk has executed. */}
      <FeedBootScript />
      {/* Header */}
      <header className="sticky top-0 z-20 bg-surface-card/80 backdrop-blur-lg border-b border-surface-border">
        {/* #8254 — ONE WIDTH TOKEN, THE SAME ONE THE SITE SHELL USES.
            This inner box and the feed's `<main>` below MUST carry identical width classes: the
            header's painted background spans the shell (`max-w-content`, 1600px, in
            `app/layout.tsx`) while this box decided where the word "Discover" sat, so the two
            widths were free to disagree — and did. Measured on production 2026-09-23 in Chromium:
            at a 1920px window the slab's background was 1552px and the feed 1248px, so the white
            band overhung the cards by 152px on EACH side. Alex photographed exactly that on an
            iPad in Safari on an external monitor.
            `max-w-7xl` (1280px) also capped the feed 320px below the shell it lives in, so a wide
            window bought nothing: the feed used 65% of a 1920px window and 49% of a 2560px one.
            Sharing the shell's token fixes both with one number — and it binds only above ~1328px,
            so 390px and iPad-portrait geometry are byte-identical to before (measured). */}
        <div className="max-w-content mx-auto px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <h1 className="text-lg font-black tracking-tight">Discover</h1>
            <div className="flex items-center gap-3">
              {/* L2-119: killed the "{N} markets" count — on an infinite feed it
                  was the loaded-so-far tally, which reads as a (wrong) total and
                  ticks up as you scroll.
                  #8187 — and the stats link no longer "stays". It was the FOURTH
                  render site of the surface the three below already gate, and the
                  only one on the first screen: an 18px unlabelled icon opening
                  `/discover/stats`, which told the reader to go and play cards
                  that #6445 had switched off everywhere. Same flag as the other
                  three, so the door and the rooms behind it move together. */}
              {CHALLENGE_SURFACES_ENABLED && (
                <Link
                  href="/discover/stats"
                  aria-label="Prediction stats"
                  className="text-text-muted hover:text-text-primary transition-colors"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 20V10" /><path d="M18 20V4" /><path d="M6 20v-4" />
                  </svg>
                </Link>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Queue 309 Item 1 — one quiet line between the header and the feed, so a
          first-time reader learns what the numbers ARE inside one viewport. It
          can coexist with the swipe-hint toast below: they say different things
          and sit in different places. */}
      <FirstRunOrientation visible={isFirstRunAnon} />

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

      {/* Feed — responsive: 1 col mobile, 2 col tablet, 3 col desktop.
          #8254: width classes here are the HEADER's, character for character (see the note on it).
          The extra width becomes WIDER cards, not more of them — four columns in 1520px are ~368px
          each against ~300px before, which is the "comfortably readable" half of the ask. A fifth
          column at this width would take them back down to ~291px, narrower than the defect, so
          the column ladder is deliberately untouched. */}
      <main className="max-w-content mx-auto px-4 py-4">
        {isLoading && <DiscoverSkeletonGrid />}

        {/* UX-P087 (#1909): the same component the typed-UNAVAILABLE case uses,
            told by REASON. It was an inline copy of that markup with different
            words and a document reload; two renderings of "the feed is not here"
            drifting apart is how one of them ends up saying something untrue.
            No latch: this branch is derived from SWR's error on every render, so
            a successful revalidation clears it without any reset of its own. */}
        {!isLoading && feedError && !data && (
          <FeedUnavailableNotice
            onRetry={handleRetryFailedLoad}
            variant="empty"
            reason={feedFailureReason}
          />
        )}

        {/* L2-238: the backend typed this response `unavailable`. It knows
            nothing about the feed, so this page must not claim the feed ended.
            With nothing on screen it takes the same retry state a transport
            failure does — this surface's existing words, no new copy — and with
            last-good cards on screen it keeps them and hangs the same retry
            below them (rendered after the grid). */}
        {!isLoading && !feedError && feedUnavailable && processedItems.length === 0 && (
          <FeedUnavailableNotice onRetry={handleRetryUnavailable} variant="empty" />
        )}

        {!isLoading && !feedError && !feedUnavailable && visibleItems.length === 0 && (
          <div className="py-16 flex justify-center">
            <EndOfFeedCard count={0} onRefresh={handleRefreshFeed} />
          </div>
        )}

        {/* Your settled Higher/Lower guesses (L2-119). 3+ collapse into one
            "Your results" group; 1–2 render as individual clickable cards.
            #6445 — hidden for the initial release. Stated here as well as on
            the SWR key above because this is the line a reader's screen is
            decided by: a future restore that revives the fetch alone must
            still not paint the banner without saying so. */}
        {CHALLENGE_SURFACES_ENABLED && resolutionsData && resolutionsData.resolutions.length > 0 && (
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

        {/* Daily Challenge — passive progress tracker, counts guesses from feed.
            Queue 309 Item 3: content before the game. A first-run anonymous
            reader meets ~8 cards (or taps one) before this appears; everyone
            else — signed in, returning, previously engaged — sees it exactly as
            before, on the first paint.
            #6445 — hidden for the initial release: `gamesUnlocked` is false for
            every reader while `CHALLENGE_SURFACES_ENABLED` is off, which is also
            what closes the quiz slots below. One gate, deliberately, so the
            tracker and the questions it counts cannot come back separately. */}
        {!isLoading && gamesUnlocked && processedItems.length > 0 && (
          <div className="mb-4">
            <DailyChallengeCard guessesToday={dailyGuesses} onStart={startChallenge} />
          </div>
        )}

        <div className="columns-1 sm:columns-2 lg:columns-3 xl:columns-4 gap-4">
          {visibleItems.map((gi, idx) => {
            const key = gi.type === "single" ? getItemId(gi.item!) : `group-${gi.groupTitle}-${idx}`;
            // Queue 309 Item 3: a locked slot falls through to the normal
            // DiscoverCard rather than rendering nothing — suppressing the quiz
            // must never leave a hole in the masonry grid.
            // #5763 — `feedItemCanBeGuessed` replaces the bare type test here.
            // Every fifth card was offered as a "higher or lower?" question on
            // nothing but its type, so a finished game seated on page one by the
            // marquee-final arm (#4681/#5100) was asked as a live question, and
            // graded against an in-game probability frozen at the whistle. A
            // rejected slot falls through to the ordinary card below, exactly as
            // a locked one does — the masonry grid never gains a hole.
            const isGuessSlot = gamesUnlocked && gi.type === "single" && (idx + 1) % 5 === 0 && feedItemCanBeGuessed(gi.item);
            const analytics = getGroupedAnalytics(gi);
            const personalizationTrace = analytics
              ? getDiscoverPersonalizationTrace(interactionProfile, analytics.category)
              : undefined;

            const handleLessLike = gi.type === "single"
              ? () => {
                  handleDismiss(getItemId(gi.item!));
                }
              : undefined;

            // One first-card concept, two consumers: the existing peek animation
            // (swipe-hint cohort) and Queue 309's hero label (first-run cohort).
            const isFirstPosition = idx === 0;
            const isFirstCard = isFirstPosition && showSwipeHint;

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
                <FeedItemShell groupedItem={gi} positionIndex={idx} personalizationTrace={personalizationTrace} onSeen={handleCardSeen}>
                  {isGuessSlot ? (
                    <GuessCard item={gi.item!} onGuessCompleted={incrementDailyGuesses} />
                  ) : (
                    <DiscoverCard
                      groupedItem={gi}
                      positionIndex={idx}
                      onDismiss={handleLessLike}
                      showProbabilityHint={isFirstPosition && isFirstRunAnon}
                      pinFor={pinForFutures}
                    />
                  )}
                </FeedItemShell>
              </div>
            );
          })}
        </div>

        {/* L2-238: unavailable-with-last-good. The cards above stay usable; the
            spinner is replaced by a terminating, actionable retry so the reader
            is never left watching an indefinite loader after a backend that has
            already said it has nothing. */}
        {!isLoading && feedUnavailable && processedItems.length > 0 && (
          <FeedUnavailableNotice onRetry={handleRetryUnavailable} variant="inline" />
        )}

        {/* LAT-P172 — the sentinel must not be observed against the SKELETON.
            `hasMore` is optimistically true from the first commit, so this node
            rendered underneath `DiscoverSkeletonGrid`'s nine placeholders while
            page one was still in flight. Nine placeholders are ~870 px in the
            three-column desktop layout, well inside the observer's 400 px
            rootMargin, so on a desktop viewport the observer intersected an
            empty page and advanced `visibleCount` before a single card existed.
            That is the signal `shouldLoadNextPage` now reads as "the reader
            scrolled", and it was being forged by a loading state. Gated on
            `!isLoading`, which SWR holds true only until the first payload —
            background revalidation keeps `data`, so the sentinel does not
            flicker out from under an infinite scroll already in progress. */}
        {!isLoading && !feedUnavailable && (visibleCount < processedItems.length || hasMore) && (
          <div ref={sentinelRef} className="h-10 flex items-center justify-center mt-4">
            <div className="w-5 h-5 border-2 border-text-muted/30 border-t-text-muted rounded-full animate-spin" />
          </div>
        )}

        {!feedUnavailable && visibleCount >= processedItems.length && !hasMore && processedItems.length > 0 && (
          <div className="mt-6 mb-2 flex justify-center">
            <EndOfFeedCard count={processedItems.length} onRefresh={handleRefreshFeed} />
          </div>
        )}
      </main>
    </div>
    </ErrorBoundary>
  );
}

