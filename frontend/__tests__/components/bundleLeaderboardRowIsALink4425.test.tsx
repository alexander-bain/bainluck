/**
 * #4425 — `4425-LEADERBOARD-TITLE-IS-A-LINK`
 *
 * EVERY MEMBER OF AN EXPANDED DISCOVER BUNDLE CAN BE OPENED.
 *
 * ── WHAT ALEX HIT ───────────────────────────────────────────────────────────
 *
 * Reading Discover on the web the morning of 2026-09-09 he expanded "Who wins
 * in 2028?" and found its rows — "2028 Democratic presidential nominee" — were
 * not clickable. Measured on production page one at 1440px, every bundle told
 * the same story:
 *
 *     11 of 11 `leaderboard` members    title is NOT inside an <a>
 *      4 of  4 `A` / `B` / `heatmap`    title IS inside an <a>
 *
 * and expanding the 2028 card took its anchor count from 2 to 0 — the collapsed
 * peek uses `FuturesCompactRow`, which is a <Link>, so the rows are clickable
 * right up until the reader asks to see more of them.
 *
 * ── THE DECISION SITE ───────────────────────────────────────────────────────
 *
 * `FuturesCard` has four render branches. Variant A (line ~665), variant B
 * (~547) and the ladder (~230) all wrap the title in `<Link href={detailHref}>`.
 * The `outcome_distribution` leaderboard branch rendered a bare `<h3>`.
 *
 * Standalone that was survivable: `DiscoverCard` wraps every card in
 * `useSwipe(..., handleTap)` and `handleTap` does `router.push(detailHref)`
 * (L2-175 Item 1), so the whole-card tap navigated for it. `ThemeBundleCard`'s
 * `ThemeBundleMember` renders `<FuturesCard>` RAW — no `DiscoverCard`, no swipe
 * wrapper, no tap — so inside a bundle the row had neither a link nor a tap and
 * was completely inert. L2-175 fixed this class for standalone cards and never
 * swept the bundle sibling.
 *
 * ── WHY THIS ASSERTS `data-card-format` TOO ─────────────────────────────────
 *
 * This file's subject carries its own warning (the CERT-678 note above the
 * leaderboard `<article>`): it was once the only one of the four roots with no
 * marker, "so a render-path test could not prove it had reached the leaderboard
 * rather than falling through to Variant A — the exact way a guard passes while
 * the path it claims to cover stays dark". Variant A's title is linked, so a
 * fixture that quietly missed the leaderboard branch would satisfy every
 * assertion below for the wrong reason. Each arm pins the marker first.
 *
 * ── THE ARMS ────────────────────────────────────────────────────────────────
 *
 *  1. THE PROBE CAN FAIL. `titleAnchorHref` is run over hand-written markup in
 *     both shapes before it is trusted on a render — a regex over rendered
 *     output that only ever sees the fixed shape cannot tell "linked" from
 *     "matched nothing";
 *  2. the leaderboard specimen reaches its own branch AND its title is an
 *     anchor to the market;
 *  3. the href is DERIVED, not hard-coded — a concept-keyed specimen anchors to
 *     the concept path instead of `/futures/{id}`;
 *  4. CONTROL. The variant-A sibling keeps its linked title, so a future edit
 *     cannot repair the leaderboard by breaking a branch that was already right.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedFuturesData, FeedItem } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import { FuturesCard } from "../../components/discover/FuturesCard";

/**
 * The href of the anchor DIRECTLY wrapping the <h3> that carries `title`, or
 * null when that <h3> is bare. `testEnvironment` is `node`, so there is no
 * document to walk — arm 1 exercises this both ways before any render is
 * judged by it.
 */
function titleAnchorHref(html: string, title: string): string | null {
  const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = html.match(new RegExp(`<a href="([^"]+)"[^>]*>\\s*<h3[^>]*>${escaped}</h3>`));
  return m ? m[1] : null;
}

/** The production specimen Alex named, from the "Who wins in 2028?" bundle. */
const NOMINEE = "2028 Democratic presidential nominee";

function leaderboardItem(overrides: Partial<FeedFuturesData> = {}): {
  item: FeedItem;
  data: FeedFuturesData;
} {
  const data = {
    id: 60481964,
    name: NOMINEE,
    llm_sport_category: "politics",
    // Below 4, so `DiscoverCard` would not divert this to ComparisonCard and
    // `FuturesCard`'s own leaderboard test (distribution_outcomes >= 4) decides.
    top_outcomes: [{ id: 1, name: "Jon Ossoff", probability: 0.17, movement: null }],
    outcome_count: 12,
    discover_card: {
      suggested_format: "outcome_distribution",
      remaining_outcome_count: 8,
      distribution_outcomes: [
        { label: "Jon Ossoff", probability: 0.17, movement: null },
        { label: "Gavin Newsom", probability: 0.16, movement: null },
        { label: "Pete Buttigieg", probability: 0.11, movement: null },
        { label: "Josh Shapiro", probability: 0.08, movement: null },
      ],
    },
    ...overrides,
  } as unknown as FeedFuturesData;
  return {
    data,
    item: { type: "futures", score: 70, reason: "", headline: null, data } as unknown as FeedItem,
  };
}

/** Renders exactly the way `ThemeBundleMember` does: raw, no DiscoverCard. */
function renderAsBundleMember(fixture: { item: FeedItem; data: FeedFuturesData }): string {
  return renderToStaticMarkup(
    <FuturesCard item={fixture.item} data={fixture.data} liked={false} setLiked={() => {}} trending={false} />,
  );
}

describe("#4425 — an expanded bundle's leaderboard rows can be opened", () => {
  it("the probe itself can fail (both shapes, before it is trusted on a render)", () => {
    const wrapped = `<a href="/futures/1"><h3 class="x">${NOMINEE}</h3></a>`;
    const bare = `<h3 class="x">${NOMINEE}</h3>`;

    expect(titleAnchorHref(wrapped, NOMINEE)).toBe("/futures/1");
    // The exact markup the defect rendered. If this ever returns a string the
    // arms below are meaningless.
    expect(titleAnchorHref(bare, NOMINEE)).toBeNull();
    expect(titleAnchorHref(wrapped, "a title that is not on this card")).toBeNull();
  });

  it("reaches the leaderboard branch and anchors its title to the market", () => {
    const html = renderAsBundleMember(leaderboardItem());

    // CERT-678: prove the branch, not just the outcome — variant A is linked
    // too, so a fixture that fell through would pass the next assertion.
    expect(html).toContain('data-card-format="leaderboard"');
    expect(titleAnchorHref(html, NOMINEE)).toBe("/futures/60481964");
  });

  it("derives the href rather than holding one of its own", () => {
    // A second dead row from the same production sweep — the "Who wins the
    // Slam?" bundle. It is a winner field in a concept domain, so `L2-65` sends
    // it to /event/[key] instead of /futures/{id}; the expected path is the one
    // its own COLLAPSED peek row was measured serving on production, which is
    // the whole point (the two states must agree on where the row goes).
    const MENS = "2026 Men’s US Open Winner (Tennis)";
    const html = renderAsBundleMember(
      leaderboardItem({ id: 59331002, name: MENS, llm_sport_category: "tennis" }),
    );

    expect(html).toContain('data-card-format="leaderboard"');
    expect(titleAnchorHref(html, MENS)).toBe("/event/tennis/2026-men-s-us-open-winner-tennis");
  });

  it("leaves the variant-A sibling's linked title alone", () => {
    // No `discover_card`, so this is the plain variant — the branch that was
    // already correct.
    const data = {
      id: 58728437,
      name: "Will the Iranian regime fall before 2027?",
      llm_sport_category: "geopolitics",
      top_outcomes: [{ id: 1, name: "Yes", probability: 0.12, movement: null }],
      outcome_count: 2,
    } as unknown as FeedFuturesData;
    const html = renderAsBundleMember({
      data,
      item: { type: "futures", score: 70, reason: "", headline: null, data } as unknown as FeedItem,
    });

    expect(html).not.toContain('data-card-format="leaderboard"');
    expect(titleAnchorHref(html, "Will the Iranian regime fall before 2027?")).toBe("/futures/58728437");
  });
});
