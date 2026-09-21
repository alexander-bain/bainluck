"use client";

import Link from "next/link";
import type { TeamFutureItem } from "@/lib/api";
import {
  formatMovementPoints,
  formatProbabilityPercent,
  isRenderedMove,
  NO_READING,
} from "@/lib/probabilityDisplay";

// ---------------------------------------------------------------------------
// One row of the team page's "Season Futures" column.
//
// LIFTED VERBATIM out of `app/sport/[sport]/[league]/team/[team]/page.tsx`
// (#7710), for the reason `lib/teamHeadline` was lifted before it: the page is
// a client component that fills itself from three `useEffect` fetches, so the
// row it draws is "the one place a test cannot reach" — this repo renders
// guards with `renderToStaticMarkup`, which never runs an effect. Every branch
// below is the page's, in its order, with its comments; the only edits are the
// `export` and the imports. If this file and the page ever disagree about a
// row, the bug is that somebody edited one of them.
// ---------------------------------------------------------------------------

export function TeamFutureRow({ item }: { item: TeamFutureItem }) {
  const tierLabels: Record<number, string> = {
    1: "Championship",
    2: "Conference",
    3: "Award",
    4: "Division",
    5: "Prop",
  };
  const tierLabel = item.market_tier
    ? tierLabels[item.market_tier] || "Market"
    : "Market";
  // L2-174 Item 3d — settled-means-settled. A graded winner (is_winner=True)
  // surfaces here at ~100% because Kalshi settled markets stay status='open'
  // (gotcha #33). Frame it as a RESULT (the L2-147 "What hit" grammar), not a
  // live 100% probability: settled eyebrow, a Won badge, and no 24h movement.
  const settledWon = item.is_winner === true;

  return (
    <Link
      href={`/futures/${item.market_id}`}
      className="bg-surface-card border border-surface-border rounded-card p-4 hover:shadow-md transition-shadow flex items-center justify-between"
    >
      <div className="min-w-0 flex-1">
        <div className={`text-xs mb-0.5 ${settledWon ? "text-text-muted" : "text-accent-brand"}`}>
          {settledWon ? "What hit" : tierLabel}
        </div>
        <div className="flex items-center gap-1.5 min-w-0">
          <div className="text-sm font-medium text-text-primary truncate">
            {item.outcome_name}
          </div>
          {settledWon && (
            <span className="flex-shrink-0 rounded-full bg-accent-live/10 px-1.5 py-0.5 text-[10px] font-semibold text-accent-live">
              ✓ Won
            </span>
          )}
        </div>
        <div className="text-xs text-text-secondary truncate">
          {item.market_name}
        </div>
      </div>
      <div className="text-right flex-shrink-0 ml-4">
        {/* #7710 — UX-P046's boundary rule, which the rest of this page already
            obeys. This was a bare `Math.round(item.probability * 100)`, and it
            lied at BOTH ends on live rows, measured on production 2026-09-21
            across 12 MLB teams (356 rows, 9 of them strictly inside (0, 1)):

              Munetaka Murakami, AL Rookie of the Year, `0.004`, ranked #3 of
              46 by the line directly below — printed `0%`. Three more Chicago
              rows the same, one of them with a `-0.1 pts` move beside its `0%`.

              Milwaukee Brewers, "Team to advance to NLDS", `0.9955`,
              `is_winner: false` — printed `100%`, in the same column and the
              same card shape as the two settled `✓ Won` rows above it, for a
              series nobody has played. Settled things do not move; that row
              moved `-0.3 pts` today.

            The settled path is untouched: all 15 settled-won rows measured
            carry exactly `1.0`, so `✓ Won` still prints `100%`. */}
        <div className={`text-lg font-mono font-bold ${settledWon ? "text-accent-live" : "text-text-primary"}`}>
          {item.probability !== null
            ? formatProbabilityPercent(item.probability)
            : NO_READING}
        </div>
        {!settledWon && item.rank && item.total_outcomes && (
          <div className="text-xs text-text-muted">
            #{item.rank} of {item.total_outcomes}
          </div>
        )}
        {/* UX-P275, same class as the headline above: the specimen for #5652 was
            this row — Boston Red Sox / MLB World Series Winner at
            `probability_change_24h = 0.000034`, printed as a green "+0.0%". */}
        {!settledWon && isRenderedMove(item.probability_change_24h) && (
          <div
            className={`text-xs ${
              item.probability_change_24h! > 0
                ? "text-accent-live"
                : "text-accent-danger"
            }`}
          >
            {item.probability_change_24h! > 0 ? "+" : "-"}
            {formatMovementPoints(item.probability_change_24h)} pts
          </div>
        )}
      </div>
    </Link>
  );
}
