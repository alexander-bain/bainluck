/**
 * UX-P190 — the category chip, through the REAL components, on the REAL payload.
 *
 * The sibling unit file (`__tests__/lib/marketCategoryLabel.test.ts`) grades the
 * formatter. This one grades what reaches the reader, because a correct helper
 * that no call site calls fixes nothing — and three of the seven call sites
 * held the same open-coded expression character for character.
 *
 * The payload is not hand-written: `fixtures/uxp190_search_kikawada.json` is the
 * verbatim body of `GET /api/events/search?q=Kikawada`, captured 2026-08-30.
 * Nine of its ten futures rows carry `llm_sport_category: "table_tennis"` with
 * `sport_name: null` — the population that made `/search` print "TABLE_TENNIS".
 *
 * ⚠️ Scope, stated rather than implied: four of the seven fixed call sites are
 * NOT rendered here. `/discover/stats` gets its rows from a `useEffect` fetch
 * (this suite is `testEnvironment: node`, so effects do not run), the market
 * page is an SWR client page, and the OpenGraph route returns an `ImageResponse`
 * from satori (it also owns the market page's "More <category>" heading).
 * Those four are covered by the source scan in the sibling file plus the
 * anchors at the bottom of this one, which are source assertions and not
 * render proofs. Said plainly so nobody reads this file as covering seven.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

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

import SearchFuturesCard from "../../components/FuturesCard";
import { ComparisonCard } from "../../components/discover/ComparisonCard";
import type { FuturesMarket, FeedItem, FeedFuturesData } from "@/lib/types";

const FRONTEND = path.join(__dirname, "..", "..");

type SearchRow = FuturesMarket & { llm_sport_category: string | null; sport_name: string | null };

function searchRows(): SearchRow[] {
  const raw = fs.readFileSync(
    path.join(FRONTEND, "__tests__", "fixtures", "uxp190_search_kikawada.json"),
    "utf8",
  );
  return JSON.parse(raw).futures as SearchRow[];
}

/** Strip tags so assertions read the TEXT a person sees, not the markup. */
function visibleText(html: string): string {
  return html.replace(/<[^>]*>/g, " ").replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();
}

describe("the fixture is the population this ship is about", () => {
  // Vacuity companion. Every assertion below is worthless if the captured
  // payload happens to hold no underscored category, so pin that it does.
  const rows = searchRows();

  it("holds real rows whose category key is underscored and whose sport_name is null", () => {
    const affected = rows.filter(
      (r) => (r.llm_sport_category ?? "").includes("_") && !r.sport_name,
    );
    expect(rows.length).toBe(10);
    expect(affected.length).toBe(9);
    expect(affected.every((r) => r.llm_sport_category === "table_tennis")).toBe(true);
  });
});

describe("the search card (/search, /my-stuff, /preferences)", () => {
  const rows = searchRows();
  const tableTennis = rows.find((r) => r.llm_sport_category === "table_tennis")!;

  it("renders the eyebrow as words, not as the payload key", () => {
    const html = renderToStaticMarkup(<SearchFuturesCard market={tableTennis} showSport />);
    const text = visibleText(html);

    // The words, not the shape (UX-P189: a shape check passes on mangled words).
    expect(text).toContain("Table Tennis");
    expect(text).not.toContain("table_tennis");

    // The eyebrow's `uppercase` is a CSS CLASS, so the rendered TEXT is
    // "Table Tennis" and the reader sees "TABLE TENNIS". The class is pinned
    // here because it is the design treatment and is deliberately kept — and
    // because it is why the old bug read as "TABLE_TENNIS" rather than
    // "table_tennis". Whatever the transform does, it cannot introduce or
    // remove an underscore, which is what the assertions above turn on.
    expect(html).toContain("uppercase tracking-widest");
    expect("Table Tennis".toUpperCase()).toBe("TABLE TENNIS");
  });

  it("shows no underscored category token on any fixture row", () => {
    for (const row of rows) {
      const text = visibleText(
        renderToStaticMarkup(<SearchFuturesCard market={row} showSport />),
      );
      // Market NAMES may legitimately contain anything, so scope the assertion
      // to the category token rather than to the whole card. Both casings,
      // because the eyebrow is uppercased downstream by CSS.
      const key = row.llm_sport_category ?? "___no_category___";
      expect(text).not.toContain(key);
      expect(text).not.toContain(key.toUpperCase());
    }
  });

  it("still prints the linked sport's curated name when there is one", () => {
    // Control: the preference order at this call site is deliberately unchanged,
    // and a market with no LLM category must still fall through to the sport.
    const noCategory = { ...tableTennis, llm_sport_category: null, sport_name: "MLB" };
    const text = visibleText(
      renderToStaticMarkup(<SearchFuturesCard market={noCategory} showSport />),
    );
    expect(text).toContain("MLB");
  });
});

describe("the Discover comparison card", () => {
  function feedItem(overrides: Partial<FeedFuturesData>): { item: FeedItem; data: FeedFuturesData } {
    const data = {
      id: 42,
      name: "Who will win the 2026 World Series?",
      llm_sport_category: "table_tennis",
      sport_name: null,
      resolution_date: "2026-11-01T00:00:00Z",
      top_outcomes: [
        { id: 1, name: "Kikawada", probability: 0.48, movement: null },
        { id: 2, name: "Blomqvist", probability: 0.52, movement: null },
      ],
      outcome_count: 2,
      confidence_tier: "high",
      ...overrides,
    } as unknown as FeedFuturesData;
    return { item: { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem, data };
  }

  function render(overrides: Partial<FeedFuturesData>): string {
    const { item, data } = feedItem(overrides);
    return visibleText(
      renderToStaticMarkup(
        <ComparisonCard
          item={item}
          data={data}
          liked={false}
          setLiked={() => {}}
          trending={false}
        />,
      ),
    );
  }

  it("labels an underscored category key", () => {
    const text = render({});
    expect(text).toContain("Table Tennis");
    expect(text).not.toContain("table_tennis");
  });

  it("prefers the curated Sport.name when the market has a linked sport", () => {
    expect(render({ sport_name: "MLB", llm_sport_category: "baseball" })).toContain("MLB");
  });

  it("falls back to its own word when the market has neither", () => {
    // The fallback string belongs to the CALLER, which is why the helper
    // returns undefined rather than inventing one.
    const text = render({ sport_name: null, llm_sport_category: null });
    expect(text).toContain("Markets");
  });
});

describe("the call sites this file cannot render", () => {
  // Source anchors, NOT render proofs — see the header. Each fails if its fix
  // is reverted, which is the whole job they are here to do.
  const ANCHORED: Array<[string, string]> = [
    ["app/discover/stats/page.tsx", "getNameForCategory(cat)"],
    ["app/futures/[id]/page.tsx", "getMarketCategoryLabel(market.sport_name, market.llm_sport_category)"],
    // The SAME page's "More <category>" heading. It read toTitleCaseAcronymSafe,
    // which de-underscores but skips the curated table — so the page called one
    // category two names ("Tech & Science" in the chip, "More Tech" here).
    ["app/futures/[id]/page.tsx", "`More ${getNameForCategory(market.llm_sport_category)}`"],
    ["app/futures/[id]/opengraph-image.tsx", "getMarketCategoryLabel(market?.sport_name, market?.llm_sport_category)"],
  ];

  it.each(ANCHORED)("%s routes its category through the labeller", (file, anchor) => {
    const src = fs.readFileSync(path.join(FRONTEND, file), "utf8");
    expect(src).toContain(anchor);
  });

  it("no longer applies a text-transform that the labeller does not own", () => {
    // Both files carried a CSS `capitalize` that was compensating for the raw
    // key and could not reach its underscore. Now that the labeller cases its
    // own output, re-adding it would corrupt "Track and Field" — so its absence
    // is asserted, not just its removal assumed.
    const stats = fs.readFileSync(path.join(FRONTEND, "app/discover/stats/page.tsx"), "utf8");
    const catRow = stats.split("\n").find((l) => l.includes("getNameForCategory(cat)"))!;
    expect(catRow).not.toContain("capitalize");

    const og = fs.readFileSync(path.join(FRONTEND, "app/futures/[id]/opengraph-image.tsx"), "utf8");
    expect(og).not.toContain('textTransform: "capitalize"');
  });
});
