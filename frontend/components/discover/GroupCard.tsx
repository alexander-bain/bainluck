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
  /**
   * The one sentence saying why these members belong together (D1 clause c,
   * #4066) — "Which of these companies is priced highest to list?", not
   * "4 markets". The backend serves it as `data.shared_question` on every
   * bundle it folds; it is absent only on the client-side groups the Discover
   * page builds for itself and on a cached payload built before the backend
   * carried it, and the header then falls back to the old count rather than
   * rendering a blank line.
   */
  sharedQuestion?: string | null;
  positionIndex?: number;
}

/**
 * Comparison bundle (`type:bundle`, `kind:"comparison"`) and the Discover
 * page's own client-side groups.
 *
 * D1 clause c (#4066): the header's second slot used to read "N markets"
 * unconditionally — a count of the rows WE hold, which is inventory, not a
 * reason to read. CERT-2291 caught it: the theme sibling had been wired to the
 * served question while this one, which draws every non-theme bundle, had not,
 * so the US-Netflix / global-Netflix pair Alex read on his phone still said
 * "2 markets". It now carries the question the members are all answers to, on
 * its own line for the same reason ThemeBundleCard does — a question is a
 * sentence and does not fit beside the chip at 390px. The count is not lost:
 * the member rows are underneath and "Show N more" still prints it.
 */
export function GroupCard({ items, title, sharedQuestion, positionIndex }: GroupCardProps) {
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
        className="w-full flex items-center justify-between gap-3 px-4 py-2.5 bg-surface-elevated/50 hover:bg-surface-elevated transition-colors text-left"
      >
        <div className="flex flex-col gap-1 min-w-0">
          <span className="flex items-center gap-2 min-w-0">
            <span className={`${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full whitespace-nowrap`}>
              {catStyle.emoji} {title}
            </span>
            {!sharedQuestion && (
              <span className="text-xs text-text-muted whitespace-nowrap">{items.length} markets</span>
            )}
          </span>
          {sharedQuestion && (
            <span className="text-sm font-semibold text-text-primary leading-snug">{sharedQuestion}</span>
          )}
        </div>
        <svg className={`w-4 h-4 text-text-muted shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
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
