"use client";

import { useState, useCallback } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { trackEvent } from "@/lib/analytics";
import { getDiscoverItemAnalytics, recordDiscoverInteraction, sendDiscoverInteraction } from "@/lib/discoverInteractions";
import type { FeedItem, FeedBundleData, FeedConceptData, FeedEventData, FeedFuturesData, FeedTournamentData } from "@/lib/types";
import type { DiscoverGroupedItem } from "./discover/types";
import { isTrending, suppressBareZeroFuturesCard } from "./discover/utils";
import { useSwipe } from "./discover/shared";
import { EventCard } from "./discover/EventCard";
import { FuturesCard } from "./discover/FuturesCard";
import { ComparisonCard } from "./discover/ComparisonCard";
import { TournamentCard } from "./discover/TournamentCard";
import { ConceptCard } from "./discover/ConceptCard";
import { GroupCard } from "./discover/GroupCard";
import { ThemeBundleCard } from "./discover/ThemeBundleCard";

// ── Re-exports (public API) ──
// Consumer code (discover/page.tsx) imports these from this file for backward compat.

export type { DiscoverGroupedItem } from "./discover/types";
export { GuessCard } from "./discover/GuessCard";
export { DailyChallengeCard } from "./discover/DailyChallengeCard";
export { ResolutionCard } from "./discover/ResolutionCard";
export { ResolutionGroup } from "./discover/ResolutionGroup";

interface DiscoverCardProps {
  groupedItem: DiscoverGroupedItem;
  onDismiss?: () => void;
  positionIndex?: number;
}

// ── Main Export ──

export default function DiscoverCard({ groupedItem, onDismiss, positionIndex }: DiscoverCardProps) {
  if (groupedItem.type === "group" && groupedItem.items) {
    return (
      <GroupCard
        items={groupedItem.items}
        title={groupedItem.groupTitle || ""}
        kind={groupedItem.groupKind}
        theme={groupedItem.groupTheme}
        positionIndex={positionIndex}
      />
    );
  }
  const item = groupedItem.item!;
  return <SingleCard item={item} onDismiss={onDismiss} positionIndex={positionIndex} />;
}

// ── Single Card Wrapper (handles swipe + analytics delegation) ──

function SingleCard({ item, onDismiss, positionIndex }: { item: FeedItem; onDismiss?: () => void; positionIndex?: number }) {
  const [liked, setLiked] = useState(false);
  const trending = isTrending(item);
  const analytics = getDiscoverItemAnalytics(item);

  const trackAction = useCallback((action: "detail_click" | "like" | "unlike" | "share" | "context_expand" | "context_collapse") => {
    trackEvent("feed_card_action", {
      action,
      ...analytics,
      position: positionIndex,
      surface: "discover",
    });
    recordDiscoverInteraction(analytics.category, action);
    sendDiscoverInteraction(analytics, action, positionIndex);
  }, [analytics, positionIndex]);

  const setLikedWithTracking = useCallback((next: boolean) => {
    setLiked(next);
    trackAction(next ? "like" : "unlike");
  }, [trackAction]);

  const handleLike = useCallback(() => setLikedWithTracking(true), [setLikedWithTracking]);
  const handleSwipeLike = useCallback(() => {
    setLikedWithTracking(true);
    onDismiss?.();
  }, [onDismiss, setLikedWithTracking]);
  const handleLessLike = useCallback(() => {
    trackAction("unlike");
    onDismiss?.();
  }, [onDismiss, trackAction]);
  const swipe = useSwipe(handleLessLike, handleSwipeLike);

  const cardStyle = {
    transform: `translateX(${swipe.offset}px) rotate(${swipe.offset * 0.02}deg)`,
    transition: swipe.offset === 0 ? "transform 0.3s ease" : "none",
  };

  // L2-164 Item 3: belt-and-suspenders 0% guard — never render a bare live-looking
  // sub-1% futures hero (the stale post-Open golf-card class). Suppress the whole
  // card here (not just the number) so no empty swipe wrapper is left behind; the
  // authoritative ranking-side suppression is #240's backend job.
  if (suppressBareZeroFuturesCard(item)) return null;

  return (
    <div ref={swipe.ref} className="relative touch-pan-y select-none" {...swipe.handlers}>
      {/* Swipe-reveal backdrop (L2-160 — the handoff's "swipe & tap coexistence"
          treatment). The colored action panel sits BEHIND the card and is revealed
          as the whole card translates, so the horizontal drag never competes with
          in-card tap targets on game cards. Right = more like this, left = less. */}
      {swipe.swipeAction === "like" && (
        <div className="absolute inset-0 z-0 flex items-center justify-start gap-2.5 rounded-[10px] bg-emerald-500/10 pl-5 pointer-events-none">
          <ThumbsUp size={20} strokeWidth={2} className="text-accent-brand" aria-hidden="true" />
          <span className="text-sm font-semibold text-accent-brand">More like this</span>
        </div>
      )}
      {swipe.swipeAction === "dismiss" && (
        <div className="absolute inset-0 z-0 flex items-center justify-end gap-2.5 rounded-[10px] bg-rose-500/10 pr-5 pointer-events-none">
          <span className="text-sm font-semibold text-accent-danger">Less like this</span>
          <ThumbsDown size={20} strokeWidth={2} className="text-accent-danger" aria-hidden="true" />
        </div>
      )}

      <div className="relative z-10" style={cardStyle}>
        {item.type === "event" && <EventCard item={item} data={item.data as FeedEventData} liked={liked} setLiked={setLikedWithTracking} onDismiss={handleLessLike} trending={trending} onDetailClick={() => trackAction("detail_click")} onShare={() => trackAction("share")} onContextExpand={() => trackAction("context_expand")} onContextCollapse={() => trackAction("context_collapse")} />}
        {item.type === "futures" && (item.data as FeedFuturesData).discover_card?.suggested_format === "outcome_distribution" && (item.data as FeedFuturesData).top_outcomes?.length >= 4 ? (
          <ComparisonCard item={item} data={item.data as FeedFuturesData} liked={liked} setLiked={setLikedWithTracking} onDismiss={handleLessLike} trending={trending} onDetailClick={() => trackAction("detail_click")} onShare={() => trackAction("share")} onContextExpand={() => trackAction("context_expand")} onContextCollapse={() => trackAction("context_collapse")} />
        ) : item.type === "futures" ? (
          <FuturesCard item={item} data={item.data as FeedFuturesData} liked={liked} setLiked={setLikedWithTracking} onDismiss={handleLessLike} trending={trending} onDetailClick={() => trackAction("detail_click")} onShare={() => trackAction("share")} onContextExpand={() => trackAction("context_expand")} onContextCollapse={() => trackAction("context_collapse")} />
        ) : null}
        {item.type === "tournament" && <TournamentCard data={item.data as FeedTournamentData} liked={liked} setLiked={setLikedWithTracking} onDismiss={handleLessLike} onDetailClick={() => trackAction("detail_click")} onShare={() => trackAction("share")} />}
        {/* L2-166: a `concept` item (UFC card / F1 GP / cycling grand tour) reaches
            the Discover feed too — without this branch it rendered an EMPTY card
            (the settled Tour de France WHAT-HIT marquee vanished on the landing
            page). Result-first settled grammar handled inside ConceptCard. */}
        {item.type === "concept" && <ConceptCard data={item.data as FeedConceptData} liked={liked} setLiked={setLikedWithTracking} onDismiss={handleLessLike} onDetailClick={() => trackAction("detail_click")} onShare={() => trackAction("share")} />}
        {item.type === "bundle" && (item.data as FeedBundleData).kind === "theme" ? (
          <ThemeBundleCard
            items={(item.data as FeedBundleData).items}
            title={(item.data as FeedBundleData).title}
            storyKey={(item.data as FeedBundleData).story_key ?? (item.data as FeedBundleData).group_id}
            positionIndex={positionIndex}
          />
        ) : item.type === "bundle" ? (
          <GroupCard
            items={(item.data as FeedBundleData).items}
            title={(item.data as FeedBundleData).title}
            positionIndex={positionIndex}
          />
        ) : null}
      </div>
    </div>
  );
}
