"use client";

import { useState } from "react";
import { trackEvent } from "@/lib/analytics";
import { getDiscoverItemAnalytics, recordDiscoverInteraction, sendDiscoverInteraction } from "@/lib/discoverInteractions";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import { BundleActionBar } from "./BundleActionBar";
import { BundleHeader } from "./BundleHeader";
import { bundleSeatCount } from "./constants";
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
 * the member rows are underneath and "All N questions" still prints it whenever
 * there is more behind the chevron than the card already seats.
 *
 * #7492: it used to seat `items[0]` and nothing else, so a card whose own
 * header asked "Which of these companies is priced highest to list?" drew ONE
 * company under a `Show 1 more` — a control that cost a row to reveal a row,
 * and a comparison the reader could not make without a tap. The theme sibling
 * has seated five since it was written. Both now read `BUNDLE_PEEK_COUNT`, and
 * the footer takes the sibling's label, accent token and top border: two bundle
 * cards side by side in one scroll are one card family (notice 35), and these
 * two differed in seat count, label, colour and border at once.
 */
export function GroupCard({ items, title, sharedQuestion, positionIndex }: GroupCardProps) {
  const [expanded, setExpanded] = useState(false);
  const primary = items[0];
  const peek = items.slice(0, bundleSeatCount(items.length));
  // Every row this card draws is a `FuturesCompactRow` in BOTH states — unlike
  // the theme sibling, which swaps compact rows for full member cards — so
  // expanding a bundle that already seats all of its members changes nothing on
  // screen. The chevron and the header's click target are therefore conditional
  // on there being something behind them; a control that does nothing is the
  // same lie as the `Show 1 more` this fix removes.
  const canExpand = items.length > peek.length;
  const shown = expanded ? items : peek;
  const cat = primary.type === "futures" ? (primary.data as FeedFuturesData).llm_sport_category : null;
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
      <BundleHeader
        title={title}
        sharedQuestion={sharedQuestion}
        fallbackCount={`${items.length} markets`}
        category={cat}
        expanded={expanded}
        canExpand={canExpand}
        onToggle={() => setExpandedWithTracking(!expanded)}
      />

      {/* The members: the first `bundleSeatCount` of them collapsed, all of them
          expanded. Both are the same compact row — the header's question is
          answered by the rows, so the rows are what the card is for. */}
      <div className="divide-y divide-surface-border border-t border-surface-border">
        {shown.map((item, i) => (
          <div key={i} className="px-4 py-3">
            <FuturesCompactRow item={item} data={item.data as FeedFuturesData} />
          </div>
        ))}
      </div>

      {!expanded && canExpand && (
        <button
          type="button"
          onClick={() => setExpandedWithTracking(true)}
          className="w-full text-center py-2.5 text-xs font-medium text-accent-brand hover:text-accent-brand/80 border-t border-surface-border"
        >
          All {items.length} questions
        </button>
      )}

      {/* #4428 — the same footer the theme sibling grows, from the same component.
          This card renders NO member card in either state (every row is a
          `FuturesCompactRow`), so before this it had no action bar anywhere at
          all, expanded or not. Wiring one sibling and not the other is the
          failure #4425 was: four branches, three linked. */}
      <BundleActionBar
        items={items}
        title={title}
        sharedQuestion={sharedQuestion}
        positionIndex={positionIndex}
      />
    </div>
  );
}
