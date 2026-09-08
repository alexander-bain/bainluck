/**
 * #3999 — the leaderboard card drew its closing rule twice.
 *
 * The outcome-list container was `border-y`, and `ActionBar` directly beneath
 * it carries an unconditional `border-t`. Measured on production at 390px
 * (`NFL Super Bowl Winner`, card height 361.5px, every bordered element's rect
 * read from the browser):
 *
 *   y=89.5   rows container `border-y` — top edge     (legitimate: opens the list)
 *   y=291.5  rows container `border-y` — bottom edge  (the duplicate)
 *   y=303.5  ActionBar      `border-t` — top edge
 *
 * so a reader saw two hairlines 12px apart with nothing between them. The fix
 * is `border-y` → `border-t`: the list keeps the rule that opens it and lets
 * ActionBar's own rule close it.
 *
 * ⚠️ WHAT THIS FILE CAN AND CANNOT PROVE. `jest.config.js` sets
 * `testEnvironment: 'node'` and this renders through `renderToStaticMarkup`,
 * so there is no layout engine here and NOTHING below measures a pixel gap.
 * What it does measure is the thing that produced the gap: how many horizontal
 * rules the card's markup asks for. That is a real invariant — `border-y` is
 * two rules and `border-t` is one — and it fails the moment either class comes
 * back.
 *
 * The counting arm is the one that matters. A plain `not.toContain("border-y")`
 * would also pass on a card that rendered nothing at all, so every absence
 * below is paired with a positive, and the rule count is asserted as an exact
 * number rather than a bound.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { FuturesCard } from "../../components/discover/FuturesCard";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

// ── fixtures (same shapes as dismissCornerReserve3777) ───────────────────────

function itemFor(data: FeedFuturesData): FeedItem {
  return { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
}

function leaderboardData(): FeedFuturesData {
  const rows = [
    { label: "Chiefs", probability: 0.31, movement: null },
    { label: "Eagles", probability: 0.24, movement: null },
    { label: "Ravens", probability: 0.13, movement: null },
    { label: "49ers", probability: 0.09, movement: null },
  ];
  return {
    id: 78,
    name: "NFL Super Bowl Winner",
    llm_sport_category: "americanfootball_nfl",
    sport_name: "NFL",
    resolution_date: "2027-02-14T00:00:00Z",
    top_outcomes: rows.map((r, i) => ({ id: i + 1, name: r.label, probability: r.probability, movement: null })),
    outcome_count: rows.length,
    confidence_tier: "moderate",
    discover_card: {
      suggested_format: "outcome_distribution",
      distribution_outcomes: rows,
      remaining_outcome_count: 28,
    },
  } as unknown as FeedFuturesData;
}

/** Variant A — the control format: it never carried the second rule. */
function variantAData(): FeedFuturesData {
  return {
    id: 79,
    name: "Who will win the 2027 Masters?",
    llm_sport_category: "golf",
    sport_name: "Golf",
    resolution_date: "2027-04-11T00:00:00Z",
    top_outcomes: [
      { id: 1, name: "Scottie Scheffler", probability: 0.22, movement: null },
      { id: 2, name: "Rory McIlroy", probability: 0.11, movement: null },
    ],
    outcome_count: 2,
    confidence_tier: "moderate",
  } as unknown as FeedFuturesData;
}

// ── rule counting ────────────────────────────────────────────────────────────

/**
 * Count the horizontal rules the markup asks for. `border-y` is deliberately
 * weighted 2 — it is one class that paints two lines, which is the entire
 * mechanism of this bug. Weighting it 1 would let the regression back in.
 *
 * Only edge-specific classes count. A plain `border` (a box, e.g. the
 * `<article>` outline) is not a horizontal rule between stacked blocks.
 */
function countRules(markup: string): number {
  let total = 0;
  for (const m of markup.matchAll(/class="([^"]*)"/g)) {
    for (const token of m[1].split(/\s+/)) {
      if (token === "border-y") total += 2;
      else if (token === "border-t" || token === "border-b") total += 1;
    }
  }
  return total;
}

function render(data: FeedFuturesData): string {
  return renderToStaticMarkup(
    <FuturesCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
}

describe("#3999 — the leaderboard card draws one closing rule, not two", () => {
  it("the outcome list opens with a rule and does not draw its own bottom edge", () => {
    const markup = render(leaderboardData());

    // Positive: we are on the leaderboard path and it actually rendered rows.
    // Without these, every absence below would pass on an empty render.
    expect(markup).toContain('data-card-format="leaderboard"');
    expect(markup).toContain("Chiefs");
    expect(markup).toContain("49ers");

    // The container keeps the rule that OPENS the list …
    expect(markup).toContain("space-y-1.5 border-t border-surface-border py-2");
    // … and no longer paints one at the bottom.
    expect(markup).not.toContain("space-y-1.5 border-y border-surface-border py-2");

    // The rule that CLOSES the list is ActionBar's, and it is still there —
    // otherwise this fix would have left the list hanging open.
    expect(markup).toContain("mt-3 pt-3 border-t border-surface-border");
  });

  it("exactly two horizontal rules on the card: one opens the list, one is the action bar", () => {
    const markup = render(leaderboardData());
    // Pre-fix this read 3 (border-y = 2, ActionBar = 1). An exact number, not a
    // bound: a bound is satisfied by deleting rules as happily as by fixing one.
    expect(countRules(markup)).toBe(2);
  });

  it("no element anywhere on the leaderboard card asks for border-y", () => {
    const markup = render(leaderboardData());
    expect(markup).toContain("NFL Super Bowl Winner"); // positive control
    expect(markup).not.toContain("border-y");
  });

  it("CONTROL — variant A is untouched: it never stacked rules and still closes on the action bar", () => {
    const markup = render(variantAData());
    expect(markup).toContain("Who will win the 2027 Masters?"); // it rendered
    expect(markup).not.toContain('data-card-format="leaderboard"'); // a different path
    expect(markup).toContain("mt-3 pt-3 border-t border-surface-border"); // still closed
    expect(markup).not.toContain("border-y");
    // One rule: the action bar's. This arm passes before AND after the fix by
    // design — it is what proves the change was scoped to the leaderboard.
    expect(countRules(markup)).toBe(1);
  });
});
