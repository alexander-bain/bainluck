/**
 * #2622 — /sports Top Markets must not weld two questions into one card.
 *
 * The card that shipped: "2026 Women's US Open Winner (Tennis)", badged
 * `1 sources`, with **Carlos Alcaraz #1 at 36%** and Alexander Zverev third.
 * Two distinct Polymarket markets (114159 men's, 114160 women's), distinct
 * `group_id`s, disjoint outcome sets, one identical `canonical_market_key`
 * `tennis::championship:2026` — and `groupTopMarkets` bundled on that key alone.
 *
 * RED-FIRST: `theWomensCardNeverCarriesAMan` and the two `bundleIsOneQuestion`
 * refusals fail on master, where any two items sharing a key are bundled.
 * `theRealCrossSourceCardStillBundles` is the control and is green on BOTH
 * trees — without it this file could be satisfied by never bundling anything,
 * which would delete the feature instead of fixing it.
 *
 * `groupTopMarkets` and `CombinedFeedCard` had no jest coverage at all before
 * this file, which is why the defect reached production on the one surface that
 * imports `feedSections` — `frontend/app/sports/page.tsx`.
 */
import { groupTopMarkets, isGroupedMarket } from "@/lib/feedSections";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

/**
 * Resolved lazily so this file COLLECTS on a tree without the fix. A red-first
 * run that dies on a missing named export reports a suite-level failure, which
 * cannot be told apart from a broken test file — and that is the one thing a
 * red-first proof has to rule out.
 */
function bundleIsOneQuestion(items: FeedItem[]): boolean {
  const mod = require("@/lib/feedSections") as Record<string, unknown>;
  const fn = mod.bundleIsOneQuestion as ((i: FeedItem[]) => boolean) | undefined;
  if (typeof fn !== "function") {
    throw new Error(
      "bundleIsOneQuestion is not exported from lib/feedSections — #2622 is not applied",
    );
  }
  return fn(items);
}

function market(
  id: number,
  name: string,
  source: string,
  canonical_market_key: string | null,
  outcomes: Array<[string, number]>,
  score = 50,
): FeedItem {
  const data: Partial<FeedFuturesData> = {
    id,
    name,
    source,
    canonical_market_key,
    top_outcomes: outcomes.map(([oname, probability]) => ({
      name: oname,
      probability,
    })) as FeedFuturesData["top_outcomes"],
  };
  return {
    type: "futures",
    score,
    reason: "",
    headline: null,
    data: data as FeedFuturesData,
  };
}

// The two rows exactly as production served them on 2026-09-01.
const MENS_US_OPEN = market(
  114159,
  "2026 Men’s US Open Winner (Tennis)",
  "polymarket",
  "tennis::championship:2026",
  [
    ["Carlos Alcaraz", 0.355],
    ["Alexander Zverev", 0.23],
  ],
  61,
);
const WOMENS_US_OPEN = market(
  114160,
  "2026 Women’s US Open Winner (Tennis)",
  "polymarket",
  "tennis::championship:2026",
  [
    ["Aryna Sabalenka", 0.235],
    ["Coco Gauff", 0.192],
    ["Iga Swiatek", 0.145],
  ],
  59,
);

describe("#2622 — the /sports card that put a man on the women's board", () => {
  it("theWomensCardNeverCarriesAMan: the two US Open boards render separately", () => {
    const { ordered } = groupTopMarkets([MENS_US_OPEN, WOMENS_US_OPEN]);

    expect(ordered.some(isGroupedMarket)).toBe(false);
    expect(ordered).toHaveLength(2);

    const names = ordered.map((e) => (e as FeedItem).data as FeedFuturesData)
      .map((d) => d.name);
    expect(names).toContain("2026 Women’s US Open Winner (Tennis)");
    expect(names).toContain("2026 Men’s US Open Winner (Tennis)");

    // The claim in the issue's title, asserted directly: whatever card the
    // women's market produces, no man is in it.
    const womens = ordered.find(
      (e) => ((e as FeedItem).data as FeedFuturesData).id === 114160,
    ) as FeedItem;
    const outcomeNames = (womens.data as FeedFuturesData).top_outcomes.map((o) => o.name);
    expect(outcomeNames).not.toContain("Carlos Alcaraz");
    expect(outcomeNames).not.toContain("Alexander Zverev");
  });

  it("refuses a group whose members all come from ONE venue", () => {
    // The absurd badge is the tell: a card built by merging two markets said
    // "1 sources", because a cross-source card had no cross source in it.
    expect(bundleIsOneQuestion([MENS_US_OPEN, WOMENS_US_OPEN])).toBe(false);
  });

  it("refuses two venues whose outcome sets are disjoint", () => {
    const kalshiWomens = market(
      9001,
      "US Open Women's Winner",
      "kalshi",
      "tennis::championship:2026",
      [["Aryna Sabalenka", 0.24]],
    );
    const polyMens = market(
      9002,
      "2026 Men’s US Open Winner (Tennis)",
      "polymarket",
      "tennis::championship:2026",
      [["Carlos Alcaraz", 0.355]],
    );
    expect(bundleIsOneQuestion([kalshiWomens, polyMens])).toBe(false);
  });

  it("refuses a member with no outcomes at all", () => {
    // An empty outcome list overlaps nothing, so it cannot be shown to be the
    // same question — and merging it would still contribute its NAME to the
    // group's identity via items[0].
    const empty = market(9003, "Mystery market", "kalshi",
      "tennis::championship:2026", []);
    const real = market(9004, "2026 Women’s US Open Winner", "polymarket",
      "tennis::championship:2026", [["Aryna Sabalenka", 0.235]]);
    expect(bundleIsOneQuestion([empty, real])).toBe(false);
  });
});

describe("#2622 controls — green on master and on this branch", () => {
  const KALSHI_NBA = market(
    201,
    "NBA Championship Winner",
    "kalshi",
    "basketball:NBA:championship:2025-26",
    [
      ["Boston Celtics", 0.22],
      ["Oklahoma City Thunder", 0.31],
    ],
    70,
  );
  const POLY_NBA = market(
    202,
    "NBA Champion 2026",
    "polymarket",
    "basketball:NBA:championship:2025-26",
    [
      ["Oklahoma City Thunder", 0.29],
      ["Boston Celtics", 0.24],
    ],
    68,
  );

  // THE load-bearing control, and it touches only symbols that exist on BOTH
  // trees. Without it this whole file could be satisfied by never bundling
  // anything, which deletes the cross-source card instead of fixing it.
  it("theRealCrossSourceCardStillBundles: two venues, one question", () => {
    const { ordered } = groupTopMarkets([KALSHI_NBA, POLY_NBA]);
    expect(ordered).toHaveLength(1);
    expect(isGroupedMarket(ordered[0])).toBe(true);
    if (isGroupedMarket(ordered[0])) {
      expect(ordered[0].items).toHaveLength(2);
      expect(ordered[0].bestScore).toBe(70);
    }
  });

  it("and bundleIsOneQuestion agrees with it", () => {
    expect(bundleIsOneQuestion([KALSHI_NBA, POLY_NBA])).toBe(true);
  });

  it("a refused group's members keep their own score positions", () => {
    // The refusal must not drop rows — it un-bundles them. Before this branch
    // the `else` arm pushed `items[0]` ONLY, so a two-member group that failed
    // to bundle would have silently deleted its second market.
    const { ordered } = groupTopMarkets([MENS_US_OPEN, WOMENS_US_OPEN, KALSHI_NBA]);
    const ids = ordered.map((e) =>
      isGroupedMarket(e) ? -1 : ((e.data as FeedFuturesData).id),
    );
    expect(ids).toContain(114159);
    expect(ids).toContain(114160);
    expect(ids).toContain(201);
    // Sorted by score descending: NBA 70, men's 61, women's 59.
    expect(ids).toEqual([201, 114159, 114160]);
  });

  it("a single market with a key is untouched", () => {
    const { ordered } = groupTopMarkets([KALSHI_NBA]);
    expect(ordered).toHaveLength(1);
    expect(isGroupedMarket(ordered[0])).toBe(false);
  });

  it("markets without a key are never grouped", () => {
    const a = market(301, "A", "kalshi", null, [["X", 0.5]]);
    const b = market(302, "B", "polymarket", null, [["X", 0.5]]);
    const { ordered } = groupTopMarkets([a, b]);
    expect(ordered).toHaveLength(2);
    expect(ordered.some(isGroupedMarket)).toBe(false);
  });

  it("a lone item is never a bundle", () => {
    expect(bundleIsOneQuestion([KALSHI_NBA])).toBe(false);
    expect(bundleIsOneQuestion([])).toBe(false);
  });
});
