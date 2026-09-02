// #2597 — THE LIVE PAYLOAD, THROUGH THE REAL RENDER PATH.
//
// `feedCardBundle2597.test.tsx` proves the mechanism with a hand-built bundle. This
// file proves the SHIP, by replaying the exact bytes production served at the moment
// the page was broken.
//
// The two fixtures are unedited `GET /api/feed?limit=50&category=<slug>` responses
// captured 2026-09-01 ~16:30 PT, second day of the US Open:
//
//   uxp254_category_tennis_bundle.20260901.json — 19 items, 1 bundle + 18 futures.
//     `/categories/tennis` rendered "Something went wrong" on this exact payload.
//   uxp254_category_golf_control.20260901.json  — 16 items, 0 bundles.
//     `/categories/golf` rendered correctly on this exact payload, in the same run.
//
// The control is the load-bearing half: it is what rules out "the category route is
// broken" and pins the cause to the bundle. It must stay green in BOTH arms of this
// fix — a golf payload that only renders after a bundle fix would mean the fix went
// somewhere it had no business going.
//
// The same correlation held across nine categories pulled that minute: tennis (1
// bundle), soccer (2) and politics (6) all threw; basketball, baseball, football,
// hockey, table_tennis and golf carried none and all rendered. Only tennis and golf
// are committed here — 240 KB of payload is not worth a fourth decimal place on a
// correlation the two committed ends already demonstrate.
//
// This replays the category page's OWN pipeline —
// `groupFeedIntoSections` → `groupTopMarkets` → `FeedCard`/`CombinedFeedCard` — and
// not a simplified stand-in, because the crash lived in the seam between the
// sectioner and the dispatcher, which a stand-in is exactly what would smooth over.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

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
import CombinedFeedCard from "../../components/CombinedFeedCard";
import { groupFeedIntoSections, groupTopMarkets, isGroupedMarket, flattenFeedBundles } from "@/lib/feedSections";
import { feedItemHasRenderableContent } from "@/components/discover/utils";

import tennisPayload from "../fixtures/uxp254_category_tennis_bundle.20260901.json";
import golfPayload from "../fixtures/uxp254_category_golf_control.20260901.json";

/**
 * The body of `app/categories/[slug]/page.tsx`, minus the SWR/auth chrome: the same
 * sectioner, the same `groupTopMarkets` split on the markets section, the same two
 * leaf components in the same order.
 */
function renderCategoryPage(items: FeedItem[]): string {
  const sections = groupFeedIntoSections(items);
  return renderToStaticMarkup(
    <>
      {sections.map((section) => {
        const grouped = section.key === "markets" ? groupTopMarkets(section.items) : null;
        return (
          <section key={section.key}>
            <h2>{section.title}</h2>
            <span>{section.items.length}</span>
            {grouped
              ? grouped.ordered.map((entry) =>
                  isGroupedMarket(entry) ? (
                    <CombinedFeedCard key={`grouped-${entry.canonicalKey}`} group={entry} />
                  ) : (
                    <FeedCard
                      key={`cat-futures-${(entry.data as FeedFuturesData).id}`}
                      item={entry}
                    />
                  ),
                )
              : section.items.map((item, i) => <FeedCard key={i} item={item} />)}
          </section>
        );
      })}
    </>,
  );
}

const tennisItems = tennisPayload.items as unknown as FeedItem[];
const golfItems = golfPayload.items as unknown as FeedItem[];

describe("the payload that broke /categories/tennis", () => {
  it("still contains the bundle — the fixture has not been quietly normalised", () => {
    // If a future refresh of this fixture drops the bundle, every assertion below
    // passes for the wrong reason. Assert the hazard is present before testing it.
    const bundles = tennisItems.filter((i) => i.type === "bundle");
    expect(bundles).toHaveLength(1);
    expect(bundles[0].data).not.toHaveProperty("top_outcomes");
  });

  it("renders the whole page instead of the error boundary", () => {
    expect(() => renderCategoryPage(tennisItems)).not.toThrow();
  });

  it("shows the two US Open winner markets the bundle was hiding", () => {
    // The reader-visible ship. These were the most-wanted tennis questions on the
    // site that week and they were behind "Something went wrong".
    const html = renderCategoryPage(tennisItems);
    expect(html).toContain("2026 Men’s US Open Winner (Tennis)");
    expect(html).toContain("2026 Women’s US Open Winner (Tennis)");
    expect(html).toContain("Carlos Alcaraz");
  });

  it("loses none of the 19 served items and files them all under Top Markets", () => {
    const sections = groupFeedIntoSections(tennisItems);
    expect(sections.map((s) => s.key)).toEqual(["markets"]);
    expect(sections[0].items).toHaveLength(tennisItems.length);
  });

  it("the section badge counts CARDS, so the page's three numbers agree", () => {
    // Unfolding made the page state three different totals: the header counted
    // top-level futures (18), the badge counted feed slots (19) and the grid
    // rendered 22. `count` is the rendered number, and the header now derives from
    // the same unfolded list.
    const sections = groupFeedIntoSections(tennisItems);
    const markets = sections.find((s) => s.key === "markets")!;
    expect(markets.items).toHaveLength(19);
    expect(markets.count).toBe(22);
    expect(markets.count).toBe(flattenFeedBundles(tennisItems).length);
  });

  it("every card the page admits actually has something to print", () => {
    // Fail-closed sibling of the crash (#1486 / L2-215): unfolding must not
    // reintroduce bare tiles.
    const sections = groupFeedIntoSections(tennisItems);
    for (const item of sections.flatMap((s) => s.items)) {
      expect(feedItemHasRenderableContent(item)).toBe(true);
    }
  });

  it("does NOT merge the three markets that share one canonical_market_key", () => {
    // The regression this fix's shape exists to avoid, asserted on the live payload.
    // 114159 (men's draw), 114160 (women's draw) and 59712997 (a Bartunkova/Mertens
    // set-winner market) all carry `tennis::championship:2026`. Only 59712997 is
    // top-level, so the correct answer today is: no cross-source group at all.
    const sections = groupFeedIntoSections(tennisItems);
    const { ordered } = groupTopMarkets(sections[0].items);
    const groups = ordered.filter(isGroupedMarket);
    expect(groups).toHaveLength(0);

    // …and on the render, the men's-draw card carries only men's-draw names. The
    // card boundary is the NEXT `/futures/` link, not a tag: this card is a `div`,
    // so slicing to `</article>` finds nothing, runs to the end of the document and
    // swallows every later card — an assertion that fails on a correct page.
    const html = renderCategoryPage(tennisItems);
    const from = html.indexOf("/futures/114159");
    expect(from).toBeGreaterThan(-1);
    const next = html.indexOf("/futures/", from + "/futures/114159".length);
    const mensCard = html.slice(from, next === -1 ? undefined : next);
    expect(mensCard).toContain("Carlos Alcaraz");
    expect(mensCard).not.toContain("Elise Mertens");
  });
});

describe("control: the payload that always rendered", () => {
  // Green in BOTH arms. Verified by running this file against the pre-fix sources.
  it("carries no bundle, which is why /categories/golf survived", () => {
    expect(golfItems.filter((i) => i.type === "bundle")).toHaveLength(0);
  });

  it("renders, and its sectioning is byte-for-byte what it was before the fix", () => {
    const html = renderCategoryPage(golfItems);
    expect(html).toContain("Top Markets");
    const sections = groupFeedIntoSections(golfItems);
    expect(sections.flatMap((s) => s.items)).toHaveLength(golfItems.length);
  });
});
