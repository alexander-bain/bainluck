"use client";

import { useState, useCallback } from "react";
import { trackEvent } from "@/lib/analytics";
import { getDiscoverItemAnalytics, recordDiscoverInteraction, sendDiscoverInteraction } from "@/lib/discoverInteractions";
import type { FeedItem, FeedBundleData, FeedEventData, FeedFuturesData, FeedTournamentData } from "@/lib/types";
import type { DiscoverGroupedItem } from "./discover/types";
import { isTrending } from "./discover/utils";
import { useSwipe } from "./discover/shared";
import { EventCard } from "./discover/EventCard";
import { FuturesCard } from "./discover/FuturesCard";
import { ComparisonCard } from "./discover/ComparisonCard";
import { TournamentCard } from "./discover/TournamentCard";
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

  return (
    <div ref={swipe.ref} className="relative touch-pan-y select-none" {...swipe.handlers}>
      {/* Swipe hint overlays */}
      {swipe.swipeAction === "like" && (
        <div className="absolute inset-0 z-20 flex items-center justify-start pl-5 pointer-events-none">
          <span className="rounded-full bg-emerald-500 px-3 py-1.5 text-xs font-bold text-white shadow-sm">More like this</span>
        </div>
      )}
      {swipe.swipeAction === "dismiss" && (
        <div className="absolute inset-0 z-20 flex items-center justify-end pr-5 pointer-events-none">
          <span className="rounded-full bg-rose-500 px-3 py-1.5 text-xs font-bold text-white shadow-sm">Less like this</span>
        </div>
      )}

      <div style={cardStyle}>
        {item.type === "event" && <EventCard item={item} data={item.data as FeedEventData} liked={liked} setLiked={setLikedWithTracking} onDismiss={handleLessLike} trending={trending} onDetailClick={() => trackAction("detail_click")} onShare={() => trackAction("share")} onContextExpand={() => trackAction("context_expand")} onContextCollapse={() => trackAction("context_collapse")} />}
        {item.type === "futures" && (item.data as FeedFuturesData).discover_card?.suggested_format === "outcome_distribution" && (item.data as FeedFuturesData).top_outcomes?.length >= 4 ? (
          <ComparisonCard item={item} data={item.data as FeedFuturesData} liked={liked} setLiked={setLikedWithTracking} onDismiss={handleLessLike} trending={trending} onDetailClick={() => trackAction("detail_click")} onShare={() => trackAction("share")} onContextExpand={() => trackAction("context_expand")} onContextCollapse={() => trackAction("context_collapse")} />
        ) : item.type === "futures" ? (
          <FuturesCard item={item} data={item.data as FeedFuturesData} liked={liked} setLiked={setLikedWithTracking} onDismiss={handleLessLike} trending={trending} onDetailClick={() => trackAction("detail_click")} onShare={() => trackAction("share")} onContextExpand={() => trackAction("context_expand")} onContextCollapse={() => trackAction("context_collapse")} />
        ) : null}
        {item.type === "tournament" && <TournamentCard data={item.data as FeedTournamentData} liked={liked} setLiked={setLikedWithTracking} onDismiss={handleLessLike} onDetailClick={() => trackAction("detail_click")} onShare={() => trackAction("share")} />}
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
