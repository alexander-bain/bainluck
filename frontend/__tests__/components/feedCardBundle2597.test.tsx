// #2597 — A BUNDLE MUST NOT TAKE THE PAGE DOWN.
//
// What a reader saw, measured on production 2026-09-01 (second day of the US Open):
// `/categories/tennis`, `/categories/soccer` and `/categories/politics` each rendered
// the error boundary — "Something went wrong" — and nothing else. `/categories/golf`,
// shot in the same run, rendered normally.
//
// The differentiator was measured, not guessed: of nine category feeds pulled at the
// same minute, exactly the three carrying a `type: "bundle"` item crashed
// (tennis 1, soccer 2, politics 6) and the six carrying none did not. The served
// bundle in `/api/feed?category=tennis` folded 114159 and 114160 — the men's and
// women's US Open winner markets, the most-wanted questions on the site that week.
//
// The mechanism, read off the bytes production served
// (`_next/static/chunks/7225-487cb64f15c5d0c3.js` col 17133, exact offset of the
// thrown `TypeError: Cannot read properties of undefined (reading 'length')`):
// `data.top_outcomes.length > 1` inside the futures card. `FeedCard`'s dispatcher
// ends in a DEFAULT arm, not a `futures` branch, so a bundle — which has no
// `top_outcomes` — was rendered as a futures card.
//
// Two things had to be true for this to be invisible: `FeedFuturesData.top_outcomes`
// is a REQUIRED field, so `npm run typecheck` could not see the mismatch; and every
// OTHER read of that field on the card (`heroOutcome`, `leaderFirstSlice(... ?? [])`,
// `renderedLeaderPercent`) already tolerated a missing list. One read did not.
//
// This file renders. A lib-only guard over `flattenFeedBundles` would stay green if
// the dispatcher never called it, which is exactly the state that shipped.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem, FeedBundleData, FeedFuturesData } from "@/lib/types";

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

import FeedCard from "../../components/FeedCard";
import {
  groupFeedIntoSections,
  groupTopMarkets,
  isGroupedMarket,
  flattenFeedBundles,
} from "@/lib/feedSections";

// ── Fixtures: the payload production actually served, not an invented shape ──

function member(
  id: number,
  name: string,
  outcomes: { id: number; name: string; probability: number; rendered_percent: number }[],
): FeedItem {
  return {
    type: "futures",
    score: 78,
    reason: `${outcomes[0].name} leads`,
    headline: null,
    data: {
      id,
      name,
      llm_sport_category: "tennis",
      source: "polymarket",
      source_count: 2,
      status: "open",
      resolution_date: "2026-09-13T00:00:00+00:00",
      outcome_count: outcomes.length,
      card_sum_reason: null,
      canonical_market_key: `tennis::market:${id}`,
      top_outcomes: outcomes.map((o, i) => ({ rank: i + 1, movement: null, ...o })),
    } as unknown as FeedFuturesData,
  } as FeedItem;
}

const MENS_US_OPEN = member(114159, "2026 Men’s US Open Winner (Tennis)", [
  { id: 1632728, name: "Carlos Alcaraz", probability: 0.355, rendered_percent: 36 },
  { id: 1632731, name: "Alexander Zverev", probability: 0.2315, rendered_percent: 23 },
  { id: 1632735, name: "Taylor Fritz", probability: 0.086, rendered_percent: 9 },
]);

const RYBAKINA_QF = member(
  59559170,
  "Will Elena Rybakina advance to the Quarterfinals in Women's Singles at the 2026 US Open?",
  [
    { id: 221667240, name: "Not Elena Rybakina", probability: 0.71, rendered_percent: 71 },
    { id: 221667239, name: "Elena Rybakina", probability: 0.29, rendered_percent: 29 },
  ],
);

/** The `type: "bundle"` item exactly as `/api/feed?category=tennis` served it. */
function tennisBundle(members: FeedItem[] = [MENS_US_OPEN, RYBAKINA_QF]): FeedItem {
  return {
    type: "bundle",
    score: 78,
    reason: `${members.length} related markets`,
    headline: "Grand Slam Tennis",
    data: {
      id: "theme:story:grand_slam_tennis:114159-114160-59559170-59556831",
      title: "Grand Slam Tennis",
      kind: "theme",
      story_key: "story:grand_slam_tennis",
      item_count: members.length,
      member_ids: members.map((m) => (m.data as FeedFuturesData).id),
      items: members,
    } as unknown as FeedBundleData,
  } as FeedItem;
}

// ── 1. THE CRASH ─────────────────────────────────────────────────────────────

describe("a bundle reaching FeedCard does not throw", () => {
  it("renders the served tennis bundle instead of throwing the production TypeError", () => {
    // Pre-fix this call threw `Cannot read properties of undefined (reading 'length')`
    // — the same error the deployed bundle threw — and React's boundary turned it
    // into the full-page "Something went wrong".
    expect(() =>
      renderToStaticMarkup(<FeedCard item={tennisBundle()} />),
    ).not.toThrow();
  });

  it("prints the folded members' markets, not an empty shell", () => {
    // An element that renders NOTHING also does not throw, so "did not crash" is
    // not the ship. The ship is that the two markets the bundle was hiding are on
    // the page.
    const html = renderToStaticMarkup(<FeedCard item={tennisBundle()} />);
    expect(html).toContain("2026 Men’s US Open Winner (Tennis)");
    expect(html).toContain("Carlos Alcaraz");
    expect(html).toContain("36%");
    expect(html).toContain("Elena Rybakina");
    expect(html).toContain("71%");
    // Both members link to their own market pages — the point of unfolding.
    expect(html).toContain("/futures/114159");
    expect(html).toContain("/futures/59559170");
  });

  it("an empty bundle renders nothing rather than a bare tile (#1486 class)", () => {
    expect(renderToStaticMarkup(<FeedCard item={tennisBundle([])} />)).toBe("");
  });
});

// ── 2. THE SECTION THE BUNDLE LANDED IN ──────────────────────────────────────

describe("a bundle sections as the markets it holds", () => {
  it("files it under Top Markets, not Upcoming", () => {
    // A bundle carries no `status`, so it fell through the sectioning ladder's
    // events `else` arm and filed a cluster of OPEN markets under "Upcoming".
    const sections = groupFeedIntoSections([tennisBundle()]);
    expect(sections.map((s) => s.key)).toEqual(["markets"]);
  });

  it("stays FOLDED through the sectioner, so its members skip cross-source grouping", () => {
    // The load-bearing half of the #2597 fix's shape. `groupTopMarkets` merges
    // same-`canonical_market_key` items into one `CombinedFeedCard`, which averages
    // outcomes BY NAME on the premise that the group is one question asked of
    // several sources. On the committed 2026-09-01 tennis payload three unrelated
    // markets share `tennis::championship:2026`, so flattening before that pass
    // built a card mixing the men's draw, the women's draw and a set-winner market.
    // Unfolding therefore happens at the LEAF, after grouping — assert the order,
    // because it is invisible in the rendered output until it is wrong.
    const sections = groupFeedIntoSections([tennisBundle()]);
    // Read the section BY KEY. Indexing `sections[0]` would also be satisfied by
    // the pre-fix behaviour, where the lone section was "upcoming" and happened to
    // hold the same one bundle — a pass that proves nothing.
    const markets = sections.find((s) => s.key === "markets");
    expect(markets).toBeDefined();
    expect(markets!.items).toHaveLength(1);
    expect(markets!.items[0].type).toBe("bundle");

    const { ordered } = groupTopMarkets(markets!.items);
    expect(ordered).toHaveLength(1);
    expect(isGroupedMarket(ordered[0])).toBe(false);
  });

  it("two same-key members do not form a group when they arrive inside a bundle", () => {
    const collidingKey = "tennis::championship:2026";
    const mens = member(114159, "2026 Men’s US Open Winner (Tennis)", [
      { id: 1, name: "Carlos Alcaraz", probability: 0.355, rendered_percent: 36 },
      { id: 2, name: "Alexander Zverev", probability: 0.2315, rendered_percent: 23 },
    ]);
    const womens = member(114160, "2026 Women’s US Open Winner (Tennis)", [
      { id: 3, name: "Aryna Sabalenka", probability: 0.33, rendered_percent: 33 },
      { id: 4, name: "Iga Swiatek", probability: 0.22, rendered_percent: 22 },
    ]);
    (mens.data as FeedFuturesData).canonical_market_key = collidingKey;
    (womens.data as FeedFuturesData).canonical_market_key = collidingKey;

    const sections = groupFeedIntoSections([tennisBundle([mens, womens])]);
    const { ordered } = groupTopMarkets(sections.find((s) => s.key === "markets")!.items);
    expect(ordered.some(isGroupedMarket)).toBe(false);

    // …and both questions still reach the reader, each as its own card.
    const html = renderToStaticMarkup(<FeedCard item={tennisBundle([mens, womens])} />);
    expect(html).toContain("2026 Men’s US Open Winner (Tennis)");
    expect(html).toContain("2026 Women’s US Open Winner (Tennis)");
  });
});

// ── 3. RECURSION BACKSTOP ────────────────────────────────────────────────────

describe("a malformed deep chain cannot blow the stack", () => {
  it("stops unfolding past the depth cap", () => {
    let nested = tennisBundle();
    for (let i = 0; i < 8; i++) nested = tennisBundle([nested]);
    expect(() => flattenFeedBundles([nested])).not.toThrow();
    expect(() => renderToStaticMarkup(<FeedCard item={nested} />)).not.toThrow();
  });

  it("a bundle whose own members are bundles still yields the real markets", () => {
    const wrapped = tennisBundle([tennisBundle()]);
    const flat = flattenFeedBundles([wrapped]);
    expect(flat).toHaveLength(2);
    expect(flat.every((i) => i.type === "futures")).toBe(true);
  });

  it("leaves a bundle-free list untouched", () => {
    const items = [MENS_US_OPEN, RYBAKINA_QF];
    expect(flattenFeedBundles(items)).toEqual(items);
  });
});

// ── 4. CONTROL — the surface that never broke must not move ──────────────────

describe("control: a bundle-free feed is unchanged", () => {
  // `/categories/golf` carried no bundle on 2026-09-01 and rendered correctly both
  // before and after this fix. Every assertion in this block is green in BOTH arms
  // — verified by running this file against the pre-fix sources — so it can only go
  // red if the fix reaches a surface it had no business touching. Nothing here may
  // name a symbol the fix introduced; that would make it a fix assertion wearing a
  // control's label, which is how a control silently stops being one.
  it("a plain futures item still sections into Top Markets and prints its card", () => {
    const sections = groupFeedIntoSections([MENS_US_OPEN]);
    expect(sections.map((s) => s.key)).toEqual(["markets"]);
    const html = renderToStaticMarkup(<FeedCard item={MENS_US_OPEN} />);
    expect(html).toContain("Carlos Alcaraz");
    expect(html).toContain("36%");
  });

  it("a two-outcome futures card still prints both sides of the pair", () => {
    const html = renderToStaticMarkup(<FeedCard item={RYBAKINA_QF} />);
    expect(html).toContain("71%");
    expect(html).toContain("29%");
  });

  it("an event item still sections by status, not into markets", () => {
    const event = {
      type: "event",
      score: 60,
      reason: "live",
      headline: null,
      data: { id: 15293823, status: "live", home_team: "A", away_team: "B" },
    } as unknown as FeedItem;
    expect(groupFeedIntoSections([event]).map((s) => s.key)).toEqual(["live"]);
  });
});

// ── 5. PLANTS — proof these assertions can fail ──────────────────────────────

describe("plants", () => {
  it("the crash assertion is real: reading `.length` off bundle data DOES throw", () => {
    // The exact expression the deployed card ran, against the exact data it ran on.
    const bundleData = tennisBundle().data as unknown as FeedFuturesData;
    expect(() => {
      // eslint-disable-next-line @typescript-eslint/no-unused-expressions
      (bundleData.top_outcomes as unknown as { length: number }).length > 1;
    }).toThrow(TypeError);
  });

  it("the content assertion is real: a name absent from the bundle is absent from the html", () => {
    const html = renderToStaticMarkup(<FeedCard item={tennisBundle()} />);
    expect(html).not.toContain("Novak Djokovic");
  });
});
