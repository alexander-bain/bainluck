"use client";

import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import ErrorBoundary from "@/components/ErrorBoundary";
import useSWR from "swr";
import { motion } from "framer-motion";
import { fetchFeed, fetchGroupedFeed } from "@/lib/api";
import { useAuthContext } from "@/components/AuthProvider";
import type { FeedEventData, FeedFuturesData, FeedTournamentData, FeedConceptData, GroupedFeedResponse } from "@/lib/types";
import GroupedFeedRenderer from "@/components/GroupedFeedRenderer";
import FeedCard from "@/components/FeedCard";
import LeagueChips from "@/components/LeagueChips";
import OnboardingBanner from "@/components/OnboardingBanner";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import SportsEmptySlate from "@/components/SportsEmptySlate";
import { getCategoryForLeague } from "@/lib/sportCategories";
import { groupFeedIntoSections, groupTopMarkets, isGroupedMarket } from "@/lib/feedSections";
import { feedItemHasRenderableContent, collectSuppressedEnvelopes } from "@/components/discover/utils";
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

export default function SportsPage() {
  usePageTracking({ pageType: 'sports', pageTitle: 'Sports' });
  useScrollDepth({ pageType: 'sports' });
  useEngagementTime({ pageType: 'sports' });

  // Auth state — used to key SWR so the feed re-fetches when auth loads
  const { user, isLoading: authLoading } = useAuthContext();

  const { track } = useAnalytics();

  // Pinning lives on My Stuff, not /sports (#960) — no pinned wiring here.

  // =========================================================================
  // Data fetching — single feed call
  // =========================================================================

  const {
    data: feedData,
    error: feedError,
    isLoading: feedLoading,
    mutate: refreshFeed,
  } = useSWR(
    // Don't fetch until auth state is resolved — avoids caching the anonymous
    // feed when the user is actually signed in (race condition).
    // Key includes user UID so SWR re-fetches when auth state changes.
    authLoading
      ? null
      : user
        ? ["feed-sports", user.uid]
        : ["feed-sports-anon"],
    () => fetchFeed({ limit: 200, mode: "sports" }),
    { refreshInterval: 30000 }
  );

  // Grouped futures feed (player props, playoff progressions, etc.)
  const {
    data: groupedData,
    error: groupedError,
    isLoading: groupedLoading,
  } = useSWR<GroupedFeedResponse>(
    authLoading ? null : "grouped-feed",
    () => fetchGroupedFeed({ limit: 20, sportsOnly: true }),
    { refreshInterval: 120000 }
  );

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
    const current = interests[category] ?? 0;
    const next = stepUp(current);
    if (next !== current) {
      setInterest(category, next);
      showToast(`Showing more ${category}`);
    }
  }, [interests, setInterest, showToast]);

  const handleThumbsDown = useCallback((category: string) => {
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
    if (!feedData) return { events: 0, futures: 0, live: 0 };
    const events = feedData.items.filter(i => i.type === "event").length;
    const futures = feedData.items.filter(i => i.type === "futures").length;
    const live = feedData.items.filter(i =>
      i.type === "event" && (i.data as FeedEventData).status === "live"
    ).length;
    return { events, futures, live };
  }, [feedData]);

  // =========================================================================
  // Group feed items into visual sections
  // =========================================================================

  const feedSections = useMemo(() => {
    if (!feedData || feedData.items.length === 0) return [];
    // L2-215 Item 1 — fail closed on empty predictive envelopes (#1486): the Sports
    // dispatcher (FeedCard) has no per-card empty guard, so drop any card with
    // neither a renderable probability nor an authoritative result before sectioning.
    const renderable = feedData.items.filter((item) => feedItemHasRenderableContent(item));
    return groupFeedIntoSections(renderable);
  }, [feedData]);

  // L2-215 Item 1 — suppression telemetry (identity-free: type + machine reason
  // only), fired once per distinct suppression signature.
  const suppressedSigRef = useRef("");
  useEffect(() => {
    if (!feedData) return;
    const suppressed = collectSuppressedEnvelopes(feedData.items);
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
  }, [feedData]);

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

      {/* Loading State */}
      {feedLoading && !feedData && <SkeletonGrid count={6} />}

      {/* Main Content */}
      {feedData && (
        <>
          {feedData.items.length === 0 ? (
            <div className="flex justify-center py-10">
              <SportsEmptySlate mode="empty" hasMarketsBelow={false} onRefresh={() => refreshFeed()} />
            </div>
          ) : (
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
          )}

          {feedData.items.length > 0 && (
            <p className="text-center text-micro text-text-muted pt-4">
              {feedStats.events > 0 && (
                <>{feedStats.events} event{feedStats.events !== 1 ? "s" : ""}</>
              )}
              {feedStats.events > 0 && feedStats.futures > 0 && " · "}
              {feedStats.futures > 0 && (
                <>{feedStats.futures} futures market{feedStats.futures !== 1 ? "s" : ""}</>
              )}
              {feedData.personalized && (
                <> · Personalized</>
              )}
            </p>
          )}
        </>
      )}
    </div>
    </ErrorBoundary>
  );
}
