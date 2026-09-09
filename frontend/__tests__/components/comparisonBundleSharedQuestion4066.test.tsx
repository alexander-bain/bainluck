/**
 * #4066 D1 clause c / CERT-2291 repair
 * `4066-COMPARISON-BUNDLE-RENDERS-SHARED-QUESTION`
 *
 * A BUNDLE ON PAGE ONE SAYS WHY ITS MEMBERS BELONG TOGETHER — ON BOTH BRANCHES.
 *
 * ── WHAT WAS SHIPPED, AND THE HALF IT MISSED ────────────────────────────────
 *
 * D1 clause c made the backend author a `shared_question` for every bundle it
 * folds (`app/utils/discover_bundles.py`), so a card could stop printing a
 * count of the rows WE hold and start printing the question its members are
 * all answers to. `DiscoverCard` routes a bundle two ways:
 *
 *     kind === "theme"  -> ThemeBundleCard   <- was wired to the question
 *     everything else   -> GroupCard         <- WAS NOT
 *
 * and "everything else" is `kind: "comparison"`, which is the branch Alex read
 * on his phone at 3:15pm PT on 2026-09-08. The sentence travelled all the way
 * to the client on the wire and the card still rendered `${items.length}
 * markets`. CERT-2291 blocked D1 on exactly this, with a server-render
 * falsifier that reproduced `2 markets` with the question absent.
 *
 * ── THE SPECIMENS ARE REAL, READ OFF PRODUCTION ─────────────────────────────
 *
 * `GET https://api.bainluck.com/api/feed?limit=60&offset=0`, 2026-09-08:
 * items 16 and 59 are `kind:"comparison"` bundles —
 *
 *     "Commodity price ranges"        3 members, reason "3 commodity markets
 *                                     compared by price range"
 *     "Rotten Tomatoes score ranges"  2 members, reason "2 score markets
 *                                     compared by threshold"
 *
 * — so this is not a hypothetical branch: two of the sixty items served that
 * afternoon were comparison bundles whose header read "3 markets" / "2
 * markets". The fixture below is the Rotten Tomatoes pair with its real member
 * names and real prices; `SHARED_QUESTION` is the string
 * `_bundle_subtitle("rotten_tomatoes_scores", 2)` authors for it.
 *
 * ── WHY THIS RENDERS `DiscoverCard` AND NOT `GroupCard` ─────────────────────
 *
 * The defect was never inside GroupCard's markup — it was a prop that was
 * never passed. A test that hands `sharedQuestion` straight to GroupCard would
 * have been green on the blocked commit. The wiring is the claim, so the test
 * enters where the payload does: `DiscoverCard` with an untouched
 * `type:"bundle"` item, the same object shape `/api/feed` serves.
 *
 * ── THE ARMS ────────────────────────────────────────────────────────────────
 *
 *  1. the served comparison bundle prints the question AND no longer prints
 *     "N markets";
 *  2. the question is read from the payload, not baked in — a second question
 *     on the same fixture changes the rendered sentence (a `toContain` on one
 *     string cannot tell a wired prop from a hard-coded one);
 *  3. OLD-CACHE FALLBACK. A payload with no `shared_question` — what a reader
 *     holding a response cached before this shipped has — keeps the count
 *     rather than rendering a blank header line;
 *  4. CONTROL. The `kind:"theme"` sibling still carries its question, so a
 *     future edit cannot fix one branch by breaking the other.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedBundleData, FeedFuturesData, FeedItem } from "@/lib/types";

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

import DiscoverCard from "../../components/DiscoverCard";

// `_bundle_subtitle("rotten_tomatoes_scores", 2)`.
const SHARED_QUESTION = "Which of these lands best with the critics?";

function member(id: number, name: string, probability: number): FeedItem {
  return {
    type: "futures",
    score: 70,
    reason: "",
    headline: null,
    data: {
      id,
      name,
      llm_sport_category: "entertainment",
      top_outcomes: [{ id, name: "Above 50", probability, movement: null }],
      outcome_count: 3,
    } as unknown as FeedFuturesData,
  } as unknown as FeedItem;
}

/** The production specimen: `comparison:rotten_tomatoes_scores:60481964-58728437`. */
const MEMBERS = [
  member(60481964, "Runner · Rotten Tomatoes score", 0.925),
  member(58728437, "The Uprising · Rotten Tomatoes score", 0.525),
];

function bundleItem(overrides: Partial<FeedBundleData>): FeedItem {
  return {
    type: "bundle",
    score: 70,
    reason: "",
    headline: null,
    data: {
      id: "comparison:rotten_tomatoes_scores:60481964-58728437",
      title: "Rotten Tomatoes score ranges",
      kind: "comparison",
      comparison_theme: "rotten_tomatoes_scores",
      shared_question: SHARED_QUESTION,
      item_count: MEMBERS.length,
      member_ids: MEMBERS.map((m) => (m.data as FeedFuturesData).id),
      items: MEMBERS,
      ...overrides,
    } as unknown as FeedBundleData,
  } as unknown as FeedItem;
}

function render(overrides: Partial<FeedBundleData> = {}): string {
  return renderToStaticMarkup(
    <DiscoverCard groupedItem={{ type: "single", item: bundleItem(overrides) }} positionIndex={0} />,
  );
}

describe("#4066 — a comparison bundle's header is its shared question, not our row count", () => {
  it("prints the served question and stops printing the member count", () => {
    const html = render();

    expect(html).toContain(SHARED_QUESTION);
    // The exact string the blocked commit rendered. `item_count` is 2 here, so
    // this is the literal header text a reader saw.
    expect(html).not.toContain("2 markets");
  });

  it("reads the question off the payload rather than holding one of its own", () => {
    // The commodity specimen from the same feed response, whose authored
    // question is a different sentence about a different thing.
    const html = render({
      shared_question: "Where do these commodity prices land?",
      title: "Commodity price ranges",
    });

    expect(html).toContain("Where do these commodity prices land?");
    expect(html).not.toContain(SHARED_QUESTION);
  });

  it("falls back to the count for a payload cached before the question existed", () => {
    const html = render({ shared_question: null });

    expect(html).toContain("2 markets");
    expect(html).not.toContain(SHARED_QUESTION);
  });

  it("leaves the theme branch carrying its own question", () => {
    const html = render({
      kind: "theme",
      title: "Awards Season",
      comparison_theme: null,
      story_key: "awards-season",
      shared_question: "Who wins Best Picture?",
    });

    expect(html).toContain("Who wins Best Picture?");
    expect(html).not.toContain("· 2 related");
  });
});
