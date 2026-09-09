/**
 * #4425 — THE LEADERBOARD TITLE IS A LINK, LIKE ITS THREE SIBLINGS.
 *
 * Alex, reading Discover on 2026-09-09: expanding a grouped card gave him rows
 * ("2028 Democratic presidential nominee") that could not be opened.
 *
 * ═══ THE DEFECT ═══
 *
 * `FuturesCard.tsx` has four render branches. Three wrap the title in
 * `<Link href={detailHref}>` — the ladder, variant B, variant A — and so does
 * `FuturesCompactRow`, which is what the COLLAPSED peek uses. The
 * `outcome_distribution` leaderboard branch rendered a bare `<h3>`. It was the
 * one variant of the four with no link, which is why a bundle row was clickable
 * until you expanded it and dead afterwards.
 *
 * Measured on production page one: 11 of 11 `leaderboard` bundle members had no
 * anchor, while 4 of 4 `A`/`B`/`heatmap` members did. Expanding "Who wins in
 * 2028?" took its anchor count from 2 to 0.
 *
 * ═══ WHY IT ONLY BIT INSIDE A BUNDLE ═══
 *
 * Standalone, `DiscoverCard` wraps every card in `useSwipe(..., handleTap)` and
 * `handleTap` does `router.push(detailHref)` on a genuine click (L2-175 Item 1)
 * — the whole-card tap hid the missing anchor. `ThemeBundleCard`'s
 * `ThemeBundleMember` renders `<FuturesCard>` RAW: no `DiscoverCard`, no swipe
 * wrapper, no tap handler. So inside a bundle the row had neither a link nor a
 * tap and was completely inert.
 *
 * L2-175 fixed exactly this class for standalone cards and never swept the
 * bundle sibling — a ruling that landed in one component is not landed.
 *
 * ═══ WHY A LEAF RENDER PLUS A SOURCE GUARD ═══
 *
 * The harm is in the EXPANDED bundle, and `ThemeBundleCard`'s `expanded` is
 * `useState(false)` with no prop override, while this suite renders through
 * `renderToStaticMarkup`, which never runs effects or clicks. The expanded
 * branch is therefore unreachable from a render test, and `ThemeBundleMember`
 * is not exported.
 *
 * So the leaf is rendered exactly as the bundle renders it — `FuturesCard`
 * raw, same props — and a source guard pins the two facts that make that leaf
 * render stand in for the bundle path: the expanded branch renders
 * `ThemeBundleMember`, and `ThemeBundleMember` renders `FuturesCard` with no
 * `DiscoverCard` wrapper. If either changes, the coverage claim changes and the
 * guard says so.
 *
 * ⚠️ EVERY ASSERTION OF ABSENCE IS PAIRED WITH A POSITIVE (this suite's
 * standing rule — an empty render reads exactly like a clean pass). The render
 * path is proved by its `data-card-format="leaderboard"` marker (the CERT-678
 * repair, which exists so a render-path test can prove which of the four
 * `<article>` roots it reached) before any claim is made about the title.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
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

const BUNDLE_SOURCE = readFileSync(
  join(__dirname, "..", "..", "components", "discover", "ThemeBundleCard.tsx"),
  "utf8"
);

type Row = { label: string; probability: number; movement: number | null };

/** The specimen from the issue: a member of the "Who wins in 2028?" bundle. */
const NOMINEE_ROWS: Row[] = [
  { label: "Gavin Newsom", probability: 0.31, movement: 0.004 },
  { label: "Jon Ossoff", probability: 0.17, movement: 0.002 },
  { label: "Pete Buttigieg", probability: 0.09, movement: null },
  { label: "Josh Shapiro", probability: 0.07, movement: -0.001 },
  { label: "Wes Moore", probability: 0.04, movement: null },
];

function futuresItem(opts: { id: number; name: string; rows: Row[] }): FeedItem {
  return {
    type: "futures",
    score: 90,
    reason: "",
    headline: "",
    data: {
      id: opts.id,
      name: opts.name,
      llm_sport_category: "politics",
      sport_name: "Politics",
      resolution_date: "2028-11-07T00:00:00Z",
      // Production sends 3 top outcomes on every live outcome_distribution
      // card; the leaderboard branch gates on distribution_outcomes, not this.
      top_outcomes: opts.rows.slice(0, 3).map((r, i) => ({
        id: i + 1, name: r.label, probability: r.probability, movement: r.movement,
      })),
      outcome_count: opts.rows.length,
      confidence_tier: "moderate",
      discover_card: {
        suggested_format: "outcome_distribution",
        distribution_outcomes: opts.rows,
        remaining_outcome_count: 12,
      },
    } as unknown as FeedFuturesData,
  } as unknown as FeedItem;
}

/**
 * Render the leaf EXACTLY as `ThemeBundleMember` renders it — raw `FuturesCard`,
 * no `DiscoverCard` wrapper, no tap handler. That absence is the whole point:
 * it is what leaves the row with nothing but its anchor.
 */
function renderAsBundleMember(item: FeedItem): string {
  return renderToStaticMarkup(
    <FuturesCard
      item={item}
      data={item.data as FeedFuturesData}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />
  );
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The href of the anchor wrapping this exact title, or null if it is bare text. */
function titleAnchorHref(markup: string, title: string): string | null {
  const m = markup.match(
    new RegExp(`<a href="([^"]+)"><h3[^>]*>${escapeRe(title)}</h3></a>`)
  );
  return m ? m[1] : null;
}

const NOMINEE = "2028 Democratic presidential nominee";

describe("#4425 — an expanded bundle's leaderboard rows can be opened", () => {
  const item = futuresItem({ id: 60481294, name: NOMINEE, rows: NOMINEE_ROWS });
  const markup = renderAsBundleMember(item);

  it("CONTROL: the render reached the leaderboard branch, not another variant", () => {
    // Asserted BEFORE any claim about the title. Without this, a payload that
    // fell through to variant A would satisfy the link assertion below while
    // saying nothing about the branch this issue is about — and a render that
    // produced nothing at all would pass every absence check in the file.
    expect(markup).toContain('data-card-format="leaderboard"');
    expect(markup).toContain(NOMINEE);
  });

  it("🔴 THE SHIP: the leaderboard title is an anchor to its market", () => {
    expect(titleAnchorHref(markup, NOMINEE)).toBe("/futures/60481294");
  });

  it("🔴 the row is not left inert — a bundle member has no other way to open", () => {
    // The bundle renders this leaf raw, so the anchor is the ONLY affordance.
    // Pre-fix this count was 0 and the row could not be opened at all.
    const detailAnchors = [...markup.matchAll(/<a href="\/futures\/60481294"/g)];
    expect(detailAnchors.length).toBeGreaterThan(0);
  });

  it("the title carries the sibling branches' hover affordance", () => {
    // The three linked siblings all use `className="block group"` on the Link
    // with `group-hover:text-accent-brand` on the heading. A link a reader
    // cannot see is a link they will not try (see the invisible-cue finding on
    // #4171): the row must LOOK clickable, not merely be clickable.
    expect(markup).toMatch(
      new RegExp(`<h3[^>]*group-hover:text-accent-brand[^>]*>${escapeRe(NOMINEE)}</h3>`)
    );
  });
});

describe("#4425 — the bundle path this leaf render stands in for", () => {
  it("the expanded bundle renders ThemeBundleMember", () => {
    expect(BUNDLE_SOURCE).toMatch(/\{expanded && \([\s\S]{0,400}<ThemeBundleMember/);
  });

  it("🔴 ThemeBundleMember renders FuturesCard RAW — no DiscoverCard wrapper", () => {
    // This is what makes the leaf render above cover the reported harm, and it
    // is the reason the missing anchor was fatal here and invisible elsewhere.
    // Paired positive: FuturesCard IS rendered, so this is not passing on an
    // empty file or a renamed component.
    expect(BUNDLE_SOURCE).toContain("<FuturesCard");
    expect(BUNDLE_SOURCE).not.toContain("<DiscoverCard");
  });
});
