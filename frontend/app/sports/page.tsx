"use client";

import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import ErrorBoundary from "@/components/ErrorBoundary";
import useSWR from "swr";
import { motion } from "framer-motion";
import { fetchFeed, fetchGroupedFeed } from "@/lib/api";
import { useAuthContext } from "@/components/AuthProvider";
import type { FeedItem, FeedEventData, FeedFuturesData, FeedTournamentData, FeedConceptData, GroupedFeedResponse } from "@/lib/types";
import GroupedFeedRenderer from "@/components/GroupedFeedRenderer";
import FeedCard from "@/components/FeedCard";
import LeagueChips from "@/components/LeagueChips";
import OnboardingBanner from "@/components/OnboardingBanner";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import SportsEmptySlate from "@/components/SportsEmptySlate";
import EndOfFeedCard from "@/components/discover/EndOfFeedCard";
import FeedUnavailableNotice from "@/components/discover/FeedUnavailableNotice";
import { getCategoryForLeague } from "@/lib/sportCategories";
import { groupFeedIntoSections, groupTopMarkets, isGroupedMarket } from "@/lib/feedSections";
import { feedItemHasRenderableContent, collectSuppressedEnvelopes } from "@/components/discover/utils";
import { initialFeedRequest, nextFeedRequest, dedupeById } from "@/lib/discover/feedPaging";
import { decideFeedPage } from "@/lib/discover/feedAvailability";
import { decideForegroundTerminal, FOREGROUND_FEED_BUDGET_MS } from "@/lib/discover/foregroundTerminal";
import { sportsFeedKey, groupedFeedKey, sportsFeedIdentity } from "@/lib/sports/feedKey";
import { trackEvent } from "@/lib/analytics";
import CombinedFeedCard from "@/components/CombinedFeedCard";
import { useCategoryInterests, stepUp, stepDown } from "@/hooks/useCategoryInterests";
import {
  useAnalytics,
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";

// ---------------------------------------------------------------------------
// Sports feed
// ---------------------------------------------------------------------------

// Stable per-item id for cross-page dedup (mirrors app/discover/page.tsx). The
// paginated Sports feed can overlap a card across page boundaries; dedup keeps
// any single question from rendering twice.
function getSportsItemId(item: FeedItem): string {
  if (item.type === "event") return `event-${(item.data as FeedEventData).id}`;
  if (item.type === "futures") return `futures-${(item.data as FeedFuturesData).id}`;
  if (item.type === "concept") return `concept-${(item.data as FeedConceptData).key}`;
  return `tournament-${(item.data as FeedTournamentData).key}`;
}

export default function SportsPage() {
  usePageTracking({ pageType: 'sports', pageTitle: 'Sports' });
  useScrollDepth({ pageType: 'sports' });
  useEngagementTime({ pageType: 'sports' });

  // Auth state — the feed key is derived from `user` only (never gated on
  // loading), so the anonymous request starts immediately and re-keys onto the
  // personalized path once an identity resolves. See lib/sports/feedKey.ts.
  const { user } = useAuthContext();

  const { track } = useAnalytics();

  // Pinning lives on My Stuff, not /sports (#960) — no pinned wiring here.

  // =========================================================================
  // Data fetching — single feed call
  // =========================================================================

  // L2-240 Item 1 — start the anonymous request immediately; do NOT gate the
  // key on `authLoading`. The key never goes null (the fetch must not wait on
  // Firebase); anon and signed-in reads live under distinct keys so a late
  // identity re-keys onto the personalized path without a stale response ever
  // overwriting a newer one. `keepPreviousData` keeps visible cards up across
  // the anon → user transition instead of blanking. See lib/sports/feedKey.ts.
  // L2-242 / C133 — the initial request of a fresh, signed-out, zero-interaction
  // visitor may reuse the shared `anon` warm feed (omit x-session-id). This ref
  // flips false on the first interaction/seen THIS mount so every request after
  // it (and every returning/interacted visitor) stays on the per-session path.
  // The resolver additionally fails closed on any durable session / prior
  // interaction / unreadable storage; authenticated identity always wins.
  const sharedAnonEligibleRef = useRef(true);

  const {
    data: feedData,
    error: feedError,
    isLoading: feedLoading,
    mutate: refreshFeed,
  } = useSWR(
    sportsFeedKey(user?.uid),
    // L2-240 Item 2 — one bounded initial (offset-zero) request, not the old
    // 200-item pull. The rest streams in on scroll via loadNextPage below.
    () => {
      const { limit, offset } = initialFeedRequest();
      return fetchFeed(
        { limit, offset, mode: "sports" },
        { sharedAnonEligible: sharedAnonEligibleRef.current, authenticated: !!user }
      );
    },
    { refreshInterval: 30000, keepPreviousData: true }
  );

  // Grouped futures feed (player props, playoff progressions, etc.). Same auth
  // decoupling: fires immediately, re-keys on a late identity.
  const {
    data: groupedData,
    error: groupedError,
    isLoading: groupedLoading,
  } = useSWR<GroupedFeedResponse>(
    groupedFeedKey(user?.uid),
    () => fetchGroupedFeed({ limit: 20, sportsOnly: true }),
    { refreshInterval: 120000, keepPreviousData: true }
  );

  // =========================================================================
  // L2-240 Item 2 — bounded first paint + monotonic pagination
  // =========================================================================
  // SWR owns the single offset-zero request (feedData above); subsequent pages
  // accumulate here. Mirrors the hardened Discover paging contract
  // (lib/discover/feedPaging + feedAvailability), including the L2-238 rule that
  // an UNAVAILABLE page is inert — it contributes no items and never closes
  // pagination — so a transient no-data terminal is distinct from exhaustion.
  const [pagedItems, setPagedItems] = useState<FeedItem[]>([]);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [feedUnavailable, setFeedUnavailable] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);

  // The page-1 items SWR last returned, kept in a ref for loadNextPage so its
  // callback identity does not churn on every feed refresh.
  const page1Items = useMemo<FeedItem[]>(() => feedData?.items ?? [], [feedData]);

  // Reset the paginated tail whenever the identity behind the feed changes
  // (anon → user, user → logout, user → other user). Without this an anonymous
  // page 2+ would ride under a signed-in identity after a late sign-in.
  const feedIdentity = sportsFeedIdentity(user?.uid);
  const feedIdentityRef = useRef(feedIdentity);
  useEffect(() => {
    if (feedIdentityRef.current === feedIdentity) return;
    feedIdentityRef.current = feedIdentity;
    setPagedItems([]);
    setHasMore(true);
    setFeedUnavailable(false);
  }, [feedIdentity]);

  // Run every page-1 payload (initial load AND background revalidation) through
  // the availability decision before it touches pagination state. An unavailable
  // payload raises the retry state without closing pagination; a genuinely
  // exhausted feed sets hasMore=false.
  const hasMoreRef = useRef(hasMore);
  useEffect(() => { hasMoreRef.current = hasMore; }, [hasMore]);
  const renderedCountRef = useRef(0);
  useEffect(() => {
    renderedCountRef.current = page1Items.length + pagedItems.length;
  }, [page1Items, pagedItems]);

  useEffect(() => {
    if (!feedData) return;
    const decision = decideFeedPage({
      payload: feedData,
      previousHasMore: hasMoreRef.current,
      hasRenderedItems: renderedCountRef.current > 0,
    });
    setFeedUnavailable(decision.showUnavailable);
    setHasMore(decision.hasMore);
  }, [feedData]);

  const loadNextPage = useCallback(async () => {
    if (loadingMore || !hasMore || feedUnavailable) return;
    setLoadingMore(true);
    try {
      const loadedItems = [...page1Items, ...pagedItems];
      const loadedIds = new Set(loadedItems.map(getSportsItemId));
      const { limit, offset } = nextFeedRequest(loadedItems.length);
      const resp = await fetchFeed({ limit, offset, mode: "sports" });
      const decision = decideFeedPage({
        payload: resp,
        previousHasMore: true,
        hasRenderedItems: loadedItems.length > 0,
      });

      if (decision.showUnavailable) {
        // Keep every loaded card, keep hasMore where it was, let the reader
        // retry. An unavailable page never ends the feed.
        setFeedUnavailable(true);
        setLoadingMore(false);
        return;
      }

      if (decision.acceptItems) {
        const freshItems = resp.items.filter((item) => !loadedIds.has(getSportsItemId(item)));
        if (freshItems.length > 0) {
          setPagedItems((prev) => {
            const prevIds = new Set([...page1Items, ...prev].map(getSportsItemId));
            return [
              ...prev,
              ...freshItems.filter((item) => !prevIds.has(getSportsItemId(item))),
            ];
          });
        }
      }

      if (!decision.hasMore) setHasMore(false);
    } catch { /* a failed page never ends the feed; the sentinel retries */ }
    setLoadingMore(false);
  }, [page1Items, pagedItems, loadingMore, hasMore, feedUnavailable]);

  const handleRetryUnavailable = useCallback(() => {
    setFeedUnavailable(false);
    refreshFeed();
  }, [refreshFeed]);

  // Infinite-scroll sentinel. Re-armed on feedUnavailable changes because the
  // node it observes is swapped for the retry notice and back (L2-238 lesson).
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) loadNextPage(); },
      { rootMargin: "600px" }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadNextPage, feedUnavailable]);

  // The accumulated, de-duplicated feed across all loaded pages. Everything
  // downstream (sections, stats) reads this, so pagination is invisible to the
  // rest of the page.
  const mergedItems = useMemo(
    () => dedupeById([...page1Items, ...pagedItems], getSportsItemId),
    [page1Items, pagedItems]
  );

  // =========================================================================
  // L2-241 Item 2 — honest foreground terminal for the INITIAL request
  // =========================================================================
  // The other feed terminals already exist below: an errored request shows the
  // ErrorMessage retry, an unavailable page shows FeedUnavailableNotice,
  // exhaustion shows EndOfFeedCard, and keepPreviousData preserves last-good.
  // The one missing state is a SLOW request that has neither errored nor
  // resolved — today that is skeletons until it finally does one or the other.
  //
  // Reaching an honest terminal for a slow request needs a budget (how long is
  // too long), and that number is Alex's product call, not this code's to
  // invent — C132 refuses a foreground terminal without an approved budget
  // (FOREGROUND_BUDGET_NEEDS_APPROVAL). So the rail is wired and INERT:
  // FOREGROUND_FEED_BUDGET_MS is null, which keeps a slow request on the
  // skeleton exactly as before; setting it to an approved value activates the
  // terminal with no other code change. The decision logic + its C132
  // conformance live in lib/discover/foregroundTerminal.ts.
  const initialPending = feedLoading && !feedData && mergedItems.length === 0;
  const [foregroundBudgetExpired, setForegroundBudgetExpired] = useState(false);

  // Reset the budget clock whenever a new request begins (identity change).
  useEffect(() => {
    setForegroundBudgetExpired(false);
  }, [feedIdentity]);

  // Arm the budget only when one is approved AND the initial request is still
  // pending. With no approved budget this effect is a pure no-op.
  useEffect(() => {
    if (FOREGROUND_FEED_BUDGET_MS == null) return;
    if (!initialPending || foregroundBudgetExpired) return;
    const timer = setTimeout(() => setForegroundBudgetExpired(true), FOREGROUND_FEED_BUDGET_MS);
    return () => clearTimeout(timer);
  }, [initialPending, foregroundBudgetExpired]);

  const foregroundDecision = decideForegroundTerminal({
    elapsedMs:
      foregroundBudgetExpired && FOREGROUND_FEED_BUDGET_MS != null ? FOREGROUND_FEED_BUDGET_MS : 0,
    budgetMs: FOREGROUND_FEED_BUDGET_MS,
    aborted: false,
    failed: !!feedError,
    hasLastGood: mergedItems.length > 0,
  });

  const handleForegroundRetry = useCallback(() => {
    setForegroundBudgetExpired(false);
    refreshFeed();
  }, [refreshFeed]);

  // =========================================================================
  // Interest signals — thumbs up/down step through affinity levels
  // =========================================================================

  const { interests, setInterest } = useCategoryInterests();
  const [toast, setToast] = useState<string | null>(null);
  const toastTimeoutRef = useRef<NodeJS.Timeout>();

  const showToast = useCallback((message: string) => {
    setToast(message);
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    toastTimeoutRef.current = setTimeout(() => setToast(null), 2000);
  }, []);

  const handleThumbsUp = useCallback((category: string) => {
    // L2-242 — an explicit affinity signal is interaction evidence: leave the
    // shared warm feed for the per-session path on any subsequent request.
    sharedAnonEligibleRef.current = false;
    const current = interests[category] ?? 0;
    const next = stepUp(current);
    if (next !== current) {
      setInterest(category, next);
      showToast(`Showing more ${category}`);
    }
  }, [interests, setInterest, showToast]);

  const handleThumbsDown = useCallback((category: string) => {
    sharedAnonEligibleRef.current = false;
    const current = interests[category] ?? 0;
    const next = stepDown(current);
    if (next !== current) {
      setInterest(category, next);
      showToast(`Showing less ${category}`);
    }
  }, [interests, setInterest, showToast]);

  // =========================================================================
  // Summary stats
  // =========================================================================

  const feedStats = useMemo(() => {
    const events = mergedItems.filter(i => i.type === "event").length;
    const futures = mergedItems.filter(i => i.type === "futures").length;
    const live = mergedItems.filter(i =>
      i.type === "event" && (i.data as FeedEventData).status === "live"
    ).length;
    return { events, futures, live };
  }, [mergedItems]);

  // =========================================================================
  // Group feed items into visual sections
  // =========================================================================

  const feedSections = useMemo(() => {
    if (mergedItems.length === 0) return [];
    // L2-215 Item 1 — fail closed on empty predictive envelopes (#1486): the Sports
    // dispatcher (FeedCard) has no per-card empty guard, so drop any card with
    // neither a renderable probability nor an authoritative result before sectioning.
    const renderable = mergedItems.filter((item) => feedItemHasRenderableContent(item));
    return groupFeedIntoSections(renderable);
  }, [mergedItems]);

  // L2-215 Item 1 — suppression telemetry (identity-free: type + machine reason
  // only), fired once per distinct suppression signature.
  const suppressedSigRef = useRef("");
  useEffect(() => {
    if (mergedItems.length === 0) return;
    const suppressed = collectSuppressedEnvelopes(mergedItems);
    if (suppressed.length === 0) return;
    const counts = new Map<string, number>();
    for (const e of suppressed) {
      const key = `${e.type}:${e.reason}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const sig = [...counts.entries()].sort().map(([k, v]) => `${k}=${v}`).join(",");
    if (sig === suppressedSigRef.current) return;
    suppressedSigRef.current = sig;
    for (const [key, count] of counts) {
      const [card_type, suppression_reason] = key.split(":");
      trackEvent("feed_card_suppressed", { card_type, suppression_reason, count, surface: "sports" });
    }
  }, [mergedItems]);

  // #1102 information architecture: games LEAD the page. Split the game sections
  // (Live Now / Just Happened / Upcoming) from the Top Markets futures section so
  // the grouped props strip can slot BELOW the games feed and above Top Markets.
  const gameSections = useMemo(
    () => feedSections.filter((s) => s.key !== "markets"),
    [feedSections]
  );
  const marketsSection = useMemo(
    () => feedSections.find((s) => s.key === "markets") ?? null,
    [feedSections]
  );

  // =========================================================================
  // Section renderer (shared by game sections + Top Markets)
  // =========================================================================

  const renderFeedSection = useCallback(
    (section: (typeof feedSections)[number], sectionIndex: number) => {
      // For "markets" section, group futures by canonical_market_key
      const isMarkets = section.key === "markets";
      const groupedMarkets = isMarkets ? groupTopMarkets(section.items) : null;

      return (
        <section key={section.key}>
          {/* Divider between sections */}
          {sectionIndex > 0 && (
            <div className="border-t border-surface-border/30 -mt-1 mb-5" />
          )}
          <motion.div
            className="flex items-center gap-2 mb-3"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
          >
            <span className="text-sm">{section.emoji}</span>
            <h2 className={`text-sm font-semibold ${section.accent}`}>
              {section.title}
            </h2>
            <span className="text-[11px] text-text-muted bg-surface-elevated px-1.5 py-0.5 rounded-full font-medium">
              {section.items.length}
            </span>
          </motion.div>
          <div
            className="grid gap-3"
            style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))" }}
          >
            {isMarkets && groupedMarkets
              ? /* Top Markets: render grouped cross-source cards + singles */
                groupedMarkets.ordered.map((entry, itemIndex) => {
                  if (isGroupedMarket(entry)) {
                    return (
                      <motion.div
                        key={`grouped-${entry.canonicalKey}`}
                        data-testid="sports-card"
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{
                          duration: 0.3,
                          ease: "easeOut",
                          delay: Math.min(itemIndex, 10) * 0.05 + 0.15,
                        }}
                      >
                        <CombinedFeedCard group={entry} />
                      </motion.div>
                    );
                  }
                  const singleData = entry.data as FeedFuturesData;
                  const category = singleData.llm_sport_category ?? "other";
                  return (
                    <motion.div
                      key={`feed-futures-${singleData.id}`}
                      data-testid="sports-card"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{
                        duration: 0.3,
                        ease: "easeOut",
                        delay: Math.min(itemIndex, 10) * 0.05 + 0.15,
                      }}
                    >
                      <FeedCard
                        item={entry}
                        onThumbsUp={handleThumbsUp}
                        onThumbsDown={handleThumbsDown}
                        category={category}
                      />
                    </motion.div>
                  );
                })
              : /* Other sections: render as before */
                section.items.map((item, itemIndex) => {
                  const key = item.type === "event"
                    ? `feed-event-${(item.data as FeedEventData).id}`
                    : item.type === "tournament"
                    ? `feed-tournament-${(item.data as FeedTournamentData).key}`
                    : item.type === "concept"
                    ? `feed-concept-${(item.data as FeedConceptData).key}`
                    : `feed-futures-${(item.data as FeedFuturesData).id}`;
                  const category = item.type === "event"
                    ? getCategoryForLeague((item.data as FeedEventData).sport ?? "")?.key ?? "other"
                    : item.type === "tournament"
                    ? "golf"
                    : item.type === "concept"
                    ? (item.data as FeedConceptData).domain ?? "other"
                    : (item.data as FeedFuturesData).llm_sport_category ?? "other";
                  return (
                    <motion.div
                      key={key}
                      data-testid="sports-card"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{
                        duration: 0.3,
                        ease: "easeOut",
                        delay: Math.min(itemIndex, 10) * 0.05 + 0.15,
                      }}
                    >
                      <FeedCard
                        item={item}
                        onThumbsUp={handleThumbsUp}
                        onThumbsDown={handleThumbsDown}
                        category={category}
                      />
                    </motion.div>
                  );
                })}
          </div>
        </section>
      );
    },
    [handleThumbsUp, handleThumbsDown]
  );

  // =========================================================================
  // Render
  // =========================================================================

  return (
    <ErrorBoundary fallback={<div className="p-8 text-center"><h2>Something went wrong</h2><button onClick={() => window.location.reload()} className="mt-2 text-sm text-accent-brand hover:underline">Reload page</button></div>}>
    <div className="space-y-5">
      {/* Toast feedback */}
      {toast && (
        <div className="fixed bottom-24 md:bottom-8 left-1/2 -translate-x-1/2 z-50 px-4 py-2 bg-surface-card border border-surface-border rounded-xl shadow-lg text-xs font-medium text-text-primary animate-fade-in">
          {toast}
        </div>
      )}

      {/* Error State */}
      {feedError && (
        <ErrorMessage
          message={feedError.message}
          onRetry={() => refreshFeed()}
        />
      )}

      {/* League Navigation */}
      <LeagueChips />

      {/* Loading State. L2-241: the skeleton is owned by the foreground-terminal
          decision, so a slow initial request past an approved budget flips to an
          honest retry instead of skeletons-forever. Inert (identical to before)
          while FOREGROUND_FEED_BUDGET_MS is null. */}
      {initialPending && foregroundDecision.showSkeleton && <SkeletonGrid count={6} />}

      {/* L2-241 Item 2: a slow initial request that outran the approved
          foreground budget — an honest retry terminal, never a perpetual
          skeleton. Only renders once a budget is approved. */}
      {initialPending && !foregroundDecision.showSkeleton && !feedError && (
        <FeedUnavailableNotice onRetry={handleForegroundRetry} variant="empty" />
      )}

      {/* L2-238/L2-240: a typed-UNAVAILABLE first page with nothing on screen is
          a retryable no-data terminal, NOT an empty feed. */}
      {feedUnavailable && mergedItems.length === 0 && (
        <FeedUnavailableNotice onRetry={handleRetryUnavailable} variant="empty" />
      )}

      {/* Genuine empty feed (backend said available, zero cards). */}
      {feedData && !feedUnavailable && mergedItems.length === 0 && (
        <div className="flex justify-center py-10">
          <SportsEmptySlate mode="empty" hasMarketsBelow={false} onRefresh={() => refreshFeed()} />
        </div>
      )}

      {/* Main Content */}
      {mergedItems.length > 0 && (
        <>
          <div className="space-y-6">
            {/* Onboarding CTA */}
            <OnboardingBanner teamCount={feedData?.personalization?.team_count} />

            {/* #217 no-games UX: games are quiet but the feed isn't empty
                (Top Markets / props still surface). Lead with an honest,
                helpful panel instead of a headerless list of futures. */}
            {gameSections.length === 0 && (
              <SportsEmptySlate
                mode="no-games"
                hasMarketsBelow={
                  !!marketsSection || (!!groupedData && groupedData.feed.length > 0)
                }
                onRefresh={() => refreshFeed()}
              />
            )}

            {/* #1102: Games LEAD — Live Now / Just Happened / Upcoming first */}
            {gameSections.map((section, sectionIndex) =>
              renderFeedSection(section, sectionIndex)
            )}

            {/* Player Props & Progressions strip — BELOW the games feed (#1102).
                Renders the shared Quantity kernel (QuantityGroup) per question,
                never a naked pooled strip without its context. */}
            {groupedData && groupedData.feed.length > 0 && (
              <section>
                {gameSections.length > 0 && (
                  <div className="border-t border-surface-border/30 -mt-1 mb-5" />
                )}
                <motion.div
                  className="flex items-center gap-2 mb-3"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.3, ease: "easeOut" }}
                >
                  <span className="text-sm">🎯</span>
                  <h2 className="text-sm font-semibold text-text-primary">
                    Player Props & Progressions
                  </h2>
                  <span className="text-[11px] text-text-muted bg-surface-elevated px-1.5 py-0.5 rounded-full font-medium">
                    {groupedData.feed.length}
                  </span>
                </motion.div>
                <GroupedFeedRenderer items={groupedData.feed} compact />
              </section>
            )}

            {/* Top Markets (futures) close out the page */}
            {marketsSection &&
              renderFeedSection(marketsSection, gameSections.length)}
          </div>

          <p className="text-center text-micro text-text-muted pt-4">
            {feedStats.events > 0 && (
              <>{feedStats.events} event{feedStats.events !== 1 ? "s" : ""}</>
            )}
            {feedStats.events > 0 && feedStats.futures > 0 && " · "}
            {feedStats.futures > 0 && (
              <>{feedStats.futures} futures market{feedStats.futures !== 1 ? "s" : ""}</>
            )}
            {feedData?.personalized && (
              <> · Personalized</>
            )}
          </p>

          {/* L2-240 Item 2 — pagination tail. The sentinel drives the next page
              on scroll; an unavailable page swaps in a retry (never ends the
              feed); genuine exhaustion shows the caught-up card — a state the
              old limit:200 single-pull page never had. */}
          {feedUnavailable ? (
            <FeedUnavailableNotice onRetry={handleRetryUnavailable} variant="inline" />
          ) : hasMore ? (
            <>
              <div ref={sentinelRef} aria-hidden className="h-1" />
              {loadingMore && <SkeletonGrid count={3} />}
            </>
          ) : (
            <div className="flex justify-center pt-4">
              <EndOfFeedCard count={mergedItems.length} onRefresh={() => refreshFeed()} />
            </div>
          )}
        </>
      )}
    </div>
    </ErrorBoundary>
  );
}
