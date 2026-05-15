"use client";

import { useState } from "react";
import { trackEvent } from "@/lib/analytics";
import { getDiscoverItemAnalytics, recordDiscoverInteraction, sendDiscoverInteraction } from "@/lib/discoverInteractions";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import { getCat } from "./constants";
import { FuturesCompactRow } from "./FuturesCard";

interface GroupCardProps {
  items: FeedItem[];
  title: string;
  positionIndex?: number;
}

export function GroupCard({ items, title, positionIndex }: GroupCardProps) {
  const [expanded, setExpanded] = useState(false);
  const primary = items[0];
  const rest = items.slice(1);
  const cat = primary.type === "futures" ? (primary.data as FeedFuturesData).llm_sport_category : null;
  const catStyle = getCat(cat);
  const analytics = getDiscoverItemAnalytics(primary);

  const setExpandedWithTracking = (next: boolean) => {
    setExpanded(next);
    if (next) {
      trackEvent("feed_card_action", {
        action: "group_expand",
        ...analytics,
        position: positionIndex,
        surface: "discover",
      });
      recordDiscoverInteraction(analytics.category, "group_expand");
      sendDiscoverInteraction(analytics, "group_expand", positionIndex);
    }
  };

  return (
    <div className="rounded-2xl border border-surface-border bg-surface-card shadow-lg overflow-hidden">
      {/* Group header */}
      <button
        onClick={() => setExpandedWithTracking(!expanded)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-surface-elevated/50 hover:bg-surface-elevated transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className={`${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full`}>
            {catStyle.emoji} {title}
          </span>
          <span className="text-xs text-text-muted">{items.length} markets</span>
        </div>
        <svg className={`w-4 h-4 text-text-muted transition-transform ${expanded ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Primary item always visible */}
      <div className="px-4 py-3 border-b border-surface-border">
        <FuturesCompactRow item={primary} data={primary.data as FeedFuturesData} />
      </div>

      {/* Rest shown on expand */}
      {expanded && rest.map((item, i) => (
        <div key={i} className="px-4 py-3 border-b border-surface-border last:border-0">
          <FuturesCompactRow item={item} data={item.data as FeedFuturesData} />
        </div>
      ))}

      {!expanded && rest.length > 0 && (
        <button
          onClick={() => setExpandedWithTracking(true)}
          className="w-full text-center py-2 text-xs text-blue-600 hover:text-blue-700 font-medium"
        >
          Show {rest.length} more
        </button>
      )}
    </div>
  );
}
