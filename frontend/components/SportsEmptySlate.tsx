"use client";

import Link from "next/link";
import { trackEvent } from "@/lib/analytics";
import { END_OF_FEED_CATEGORIES } from "@/components/discover/EndOfFeedCard";

// #217 — the no-games UX. On an off-brand sports lull (mid-July: no Tier-1
// slate) the Sports tab used to render either a bare "Nothing interesting"
// shell (whole feed empty) or a headerless Top-Markets list with no framing
// (games empty, futures present). Neither is honest OR helpful. This is the
// graceful replacement: it names the situation and points at what IS on —
// Top Markets below (when present), the Discover feed's live movers, and the
// category surfaces — instead of an empty room.
//
// Two modes:
//  - "no-games": games are quiet but markets/props still render below this panel.
//  - "empty": the entire sports feed is empty (rare — even futures returned none).

interface SportsEmptySlateProps {
  mode: "no-games" | "empty";
  /** True when Top Markets / props render below this panel (no-games mode). */
  hasMarketsBelow: boolean;
  onRefresh: () => void;
}

export default function SportsEmptySlate({
  mode,
  hasMarketsBelow,
  onRefresh,
}: SportsEmptySlateProps) {
  const headline =
    mode === "empty"
      ? "The slate is quiet right now"
      : "No live or upcoming games right now";
  const subline =
    mode === "empty"
      ? "No games and no markets are surfacing at the moment. New games and markets open throughout the day."
      : hasMarketsBelow
      ? "It's a light day for games — but the markets below are still moving. Here's what else is worth a look."
      : "It's a light day for games. Here's what else is worth a look.";

  return (
    <div className="w-full rounded-2xl bg-surface-card border border-surface-border px-6 py-8 text-center">
      <p className="text-lg font-medium text-text-primary">{headline}</p>
      <p className="text-sm text-text-secondary mt-1 max-w-md mx-auto">{subline}</p>

      <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
        <Link
          href="/discover"
          onClick={() =>
            trackEvent("navigation_click", {
              click_type: "nav_tab",
              from_page: "sports",
              to_page: "/discover",
            })
          }
          className="inline-flex items-center justify-center rounded-full bg-accent-brand/10 text-accent-brand text-sm font-medium px-4 py-2 hover:bg-accent-brand/20 transition-colors"
        >
          See what&apos;s moving
        </Link>
        <button
          onClick={onRefresh}
          className="inline-flex items-center justify-center rounded-full bg-surface-elevated text-text-secondary text-sm font-medium px-4 py-2 hover:text-text-primary hover:bg-surface-border transition-colors"
        >
          Refresh
        </button>
      </div>

      {mode === "no-games" && hasMarketsBelow && (
        <p className="mt-4 text-xs text-text-muted">Top markets are below ↓</p>
      )}

      <div className="mt-5 pt-4 border-t border-surface-border">
        <p className="text-xs text-text-muted mb-3">Explore by category</p>
        <div className="flex flex-wrap justify-center gap-2">
          {END_OF_FEED_CATEGORIES.map((c) => (
            <Link
              key={c.href}
              href={c.href}
              onClick={() =>
                trackEvent("navigation_click", {
                  click_type: "nav_tab",
                  from_page: "sports",
                  to_page: c.href,
                })
              }
              className="rounded-full bg-surface-elevated text-text-secondary text-xs px-3 py-1.5 hover:text-text-primary hover:bg-surface-border transition-colors"
            >
              {c.label}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
