"use client";

import { useState } from "react";
import { trackEvent } from "@/lib/analytics";
import { getDiscoverItemAnalytics, recordDiscoverInteraction, sendDiscoverInteraction } from "@/lib/discoverInteractions";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import { getCat } from "./constants";
import { FuturesCard, FuturesCompactRow } from "./FuturesCard";

interface ThemeBundleCardProps {
  items: FeedItem[];
  title: string;
  storyKey?: string | null;
  positionIndex?: number;
}

// Number of members shown in the collapsed mini-ranked-peek before "show all".
const PEEK_COUNT = 5;

/**
 * Theme bundle (geopolitics archetype — Phase 1, slice 1).
 *
 * Collapsed: a header (theme label + "· N related") over a tight mini-ranked
 * peek of the top members. Expanded: the real member market cards (reuses
 * FuturesCard — no reinvented card). Folds same-conflict scatter into one slot.
 */
export function ThemeBundleCard({ items, title, storyKey, positionIndex }: ThemeBundleCardProps) {
  const [expanded, setExpanded] = useState(false);
  const primary = items[0];
  const cat = primary?.type === "futures" ? (primary.data as FeedFuturesData).llm_sport_category : null;
  const catStyle = getCat(cat);
  const analytics = primary ? getDiscoverItemAnalytics(primary) : { category: "geopolitics" };
  const peek = items.slice(0, PEEK_COUNT);

  const toggleExpanded = () => {
    const next = !expanded;
    setExpanded(next);
    if (next) {
      trackEvent("theme_bundle_expand", {
        ...analytics,
        story_key: storyKey,
        member_count: items.length,
        position: positionIndex,
        surface: "discover",
      });
      recordDiscoverInteraction(analytics.category, "group_expand");
      sendDiscoverInteraction(analytics, "group_expand", positionIndex);
    }
  };

  return (
    <div className="rounded-2xl border border-surface-border bg-surface-card shadow-lg overflow-hidden">
      {/* Theme header */}
      <button
        onClick={toggleExpanded}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-surface-elevated/50 hover:bg-surface-elevated transition-colors"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className={`${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full whitespace-nowrap`}>
            {catStyle.emoji} {title}
          </span>
          <span className="text-xs text-text-muted whitespace-nowrap">· {items.length} related</span>
        </div>
        <svg className={`w-4 h-4 text-text-muted shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Collapsed: mini-ranked-peek */}
      {!expanded && (
        <>
          <div className="divide-y divide-surface-border">
            {peek.map((member, i) => (
              <div key={i} className="px-4 py-3">
                {member.type === "futures" ? (
                  <FuturesCompactRow item={member} data={member.data as FeedFuturesData} />
                ) : (
                  <div className="text-sm font-semibold text-text-primary line-clamp-2">{member.headline || "Market"}</div>
                )}
              </div>
            ))}
          </div>
          <button
            onClick={toggleExpanded}
            className="w-full text-center py-2.5 text-xs font-medium text-accent-brand hover:text-accent-brand/80 border-t border-surface-border"
          >
            {items.length > PEEK_COUNT ? `Show all ${items.length}` : "Expand"}
          </button>
        </>
      )}

      {/* Expanded: the real member cards */}
      {expanded && (
        <div className="p-3 space-y-3 bg-surface-elevated/30">
          {items.map((member, i) => (
            <ThemeBundleMember key={i} member={member} />
          ))}
        </div>
      )}
    </div>
  );
}

// Renders a single member as its real market card (reuses FuturesCard with local
// like state; non-futures members fall back to a compact row).
function ThemeBundleMember({ member }: { member: FeedItem }) {
  const [liked, setLiked] = useState(false);
  if (member.type === "futures") {
    return (
      <FuturesCard
        item={member}
        data={member.data as FeedFuturesData}
        liked={liked}
        setLiked={setLiked}
        trending={false}
      />
    );
  }
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card px-4 py-3">
      <div className="text-sm font-semibold text-text-primary line-clamp-2">{member.headline || "Market"}</div>
    </div>
  );
}
