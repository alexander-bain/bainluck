// UX-P257 / #2622 — a man is not the favourite in the women's draw.
//
// The defect, as shopped on 2026-09-01 during the US Open: /sports "Top Markets"
// printed a card titled "2026 Women's US Open Winner (Tennis)" whose #1 row was
// **Carlos Alcaraz at 36%**, with Alexander Zverev at #3. Both men came from the
// MEN'S market, welded in by `groupTopMarkets`.
//
// Why it welded: `compute_canonical_market_key` has no gender axis and
// `LEAGUE_PATTERNS` has no "us open" entry, so futures_markets 114159 (Men's) and
// 114160 (Women's) BOTH carry `canonical_market_key = "tennis::championship:2026"`
// — a key shared by 1,341 open markets. The backend's own dedupe
// (`_dedupe_futures_by_canonical`) sees disjoint outcome names and correctly
// refuses to collapse them, but that verdict never reaches the client, and
// `groupTopMarkets` re-grouped on the shared key ALONE. `CombinedFeedCard` then
// unions the outcomes, re-sorts by probability, and takes the title and link from
// `items[0]` — so the men's names got relabelled with the women's question.
//
// The rule this locks: a combined card is a CROSS-SOURCE comparison of ONE
// question. Bundling requires two different sources AND overlapping outcomes.
// A shared canonical key proves neither.

import { groupTopMarkets, isGroupedMarket } from "@/lib/feedSections";
import type { FeedItem } from "@/lib/types";

const TENNIS_2026 = "tennis::championship:2026";

function outcome(name: string, probability: number) {
  return { id: 0, name, probability, rank: null, movement: null };
}

/** A Top Markets futures item, shaped like the real /api/feed payload. */
function futures(opts: {
  id: number;
  name: string;
  source: string;
  score: number;
  canonicalKey?: string | null;
  groupId?: string;
  outcomes: { name: string; probability: number }[];
}): FeedItem {
  return {
    type: "futures",
    score: opts.score,
    reason: null,
    data: {
      id: opts.id,
      name: opts.name,
      sport: "tennis",
      sport_name: "Tennis",
      llm_sport_category: "tennis",
      source: opts.source,
      source_count: 1,
      market_tier: 2,
      status: "open",
      resolution_date: null,
      group_id: opts.groupId ?? `${opts.source}:${opts.id}`,
      top_outcomes: opts.outcomes.map((o) => outcome(o.name, o.probability)),
      outcome_count: opts.outcomes.length,
      canonical_market_key:
        opts.canonicalKey === undefined ? TENNIS_2026 : opts.canonicalKey,
    },
  } as unknown as FeedItem;
}

// ---------------------------------------------------------------------------
// The production specimen: futures_markets 114159 + 114160, verbatim prices.
// ---------------------------------------------------------------------------

const MENS_US_OPEN = futures({
  id: 114159,
  name: "2026 Men's US Open Winner (Tennis)",
  source: "polymarket",
  score: 72,
  groupId: "polymarket:139236",
  outcomes: [
    { name: "Carlos Alcaraz", probability: 0.355 },
    { name: "Alexander Zverev", probability: 0.23 },
  ],
});

const WOMENS_US_OPEN = futures({
  id: 114160,
  name: "2026 Women's US Open Winner (Tennis)",
  source: "polymarket",
  score: 70,
  groupId: "polymarket:139255",
  outcomes: [
    { name: "Aryna Sabalenka", probability: 0.235 },
    { name: "Coco Gauff", probability: 0.192 },
    { name: "Iga Swiatek", probability: 0.145 },
  ],
});

/** Every outcome name printed by whichever entry the women's market landed in. */
function namesRenderedWith(
  ordered: ReturnType<typeof groupTopMarkets>["ordered"],
  marketId: number
): string[] {
  for (const entry of ordered) {
    const items = isGroupedMarket(entry) ? entry.items : [entry];
    if (!items.some((i) => (i.data as { id: number }).id === marketId)) continue;
    return items.flatMap((i) =>
      ((i.data as { top_outcomes: { name: string }[] }).top_outcomes ?? []).map(
        (o) => o.name
      )
    );
  }
  throw new Error(`market ${marketId} vanished from Top Markets`);
}

describe("#2622 — the men's and women's US Open draws are two questions", () => {
  // G1 (red-first): this is the failing arm on clean master.
  it("does not weld two same-source markets that merely share a canonical key", () => {
    const { ordered } = groupTopMarkets([MENS_US_OPEN, WOMENS_US_OPEN]);

    expect(ordered).toHaveLength(2);
    expect(ordered.filter(isGroupedMarket)).toHaveLength(0);
  });

  // G1b: the user-visible claim, stated as the shopper stated it.
  it("keeps Carlos Alcaraz out of the women's card", () => {
    const { ordered } = groupTopMarkets([MENS_US_OPEN, WOMENS_US_OPEN]);

    const womens = namesRenderedWith(ordered, 114160);
    expect(womens).toContain("Aryna Sabalenka");
    expect(womens).not.toContain("Carlos Alcaraz");
    expect(womens).not.toContain("Alexander Zverev");
  });

  // G1c: neither market loses its own identity — no card is dropped.
  it("keeps both markets on the page", () => {
    const { ordered } = groupTopMarkets([MENS_US_OPEN, WOMENS_US_OPEN]);

    expect(namesRenderedWith(ordered, 114159)).toContain("Carlos Alcaraz");
    expect(namesRenderedWith(ordered, 114160)).toContain("Coco Gauff");
  });

  // G3: cross-source is not sufficient either — disjoint outcomes still refuse.
  // This is the same pair waiting to happen at Wimbledon, where LEAGUE_PATTERNS
  // maps both draws to ATP regardless of gender.
  it("refuses a cross-source pair whose outcome sets are disjoint", () => {
    const mensOnKalshi = futures({
      id: 114161,
      name: "2026 Men's US Open Winner (Tennis)",
      source: "kalshi",
      score: 71,
      outcomes: [{ name: "Carlos Alcaraz", probability: 0.36 }],
    });

    const { ordered } = groupTopMarkets([mensOnKalshi, WOMENS_US_OPEN]);

    expect(ordered.filter(isGroupedMarket)).toHaveLength(0);
    expect(namesRenderedWith(ordered, 114160)).not.toContain("Carlos Alcaraz");
  });
});

// ---------------------------------------------------------------------------
// Controls — green in BOTH arms. If one of these ever reddens, the fix has
// stopped being a narrowing and has started deleting the feature.
// ---------------------------------------------------------------------------

describe("the cross-source card the grouping exists for still works", () => {
  it("bundles the same question priced by two different sources", () => {
    const kalshi = futures({
      id: 200,
      name: "2026 Men's US Open Winner (Tennis)",
      source: "kalshi",
      score: 80,
      outcomes: [
        { name: "Carlos Alcaraz", probability: 0.34 },
        { name: "Jannik Sinner", probability: 0.28 },
      ],
    });
    const polymarket = futures({
      id: 201,
      name: "US Open Men's Champion",
      source: "polymarket",
      score: 76,
      outcomes: [
        { name: "Carlos Alcaraz", probability: 0.355 },
        { name: "Jannik Sinner", probability: 0.27 },
      ],
    });

    const { ordered } = groupTopMarkets([kalshi, polymarket]);

    expect(ordered).toHaveLength(1);
    const [group] = ordered;
    expect(isGroupedMarket(group)).toBe(true);
    if (!isGroupedMarket(group)) throw new Error("unreachable");
    expect(group.items.map((i) => (i.data as { id: number }).id).sort()).toEqual([
      200, 201,
    ]);
    // Highest-scoring item seeds the cluster, so it supplies title and link.
    expect((group.items[0].data as { id: number }).id).toBe(200);
    expect(group.bestScore).toBe(80);
  });

  it("bundles a cross-source binary Yes/No pair", () => {
    const kalshi = futures({
      id: 300,
      name: "Will the men's final go five sets?",
      source: "kalshi",
      score: 60,
      outcomes: [
        { name: "Yes", probability: 0.41 },
        { name: "No", probability: 0.59 },
      ],
    });
    const polymarket = futures({
      id: 301,
      name: "Men's final: five sets?",
      source: "polymarket",
      score: 58,
      outcomes: [
        { name: "Yes", probability: 0.44 },
        { name: "No", probability: 0.56 },
      ],
    });

    const { ordered } = groupTopMarkets([kalshi, polymarket]);

    expect(ordered.filter(isGroupedMarket)).toHaveLength(1);
  });

  it("bundles when one side lists no outcomes (benefit of the doubt)", () => {
    const withOutcomes = futures({
      id: 400,
      name: "2026 Men's US Open Winner (Tennis)",
      source: "kalshi",
      score: 55,
      outcomes: [{ name: "Carlos Alcaraz", probability: 0.34 }],
    });
    const bare = futures({
      id: 401,
      name: "US Open Men's Champion",
      source: "polymarket",
      score: 50,
      outcomes: [],
    });

    const { ordered } = groupTopMarkets([withOutcomes, bare]);

    expect(ordered.filter(isGroupedMarket)).toHaveLength(1);
  });

  it("leaves keyless and unique-key markets as singles, sorted by score", () => {
    const keyless = futures({
      id: 500,
      name: "A market with no canonical key",
      source: "kalshi",
      score: 90,
      canonicalKey: null,
      outcomes: [{ name: "Yes", probability: 0.5 }],
    });
    const unique = futures({
      id: 501,
      name: "A market alone on its key",
      source: "polymarket",
      score: 10,
      canonicalKey: "golf::championship:2026",
      outcomes: [{ name: "Scottie Scheffler", probability: 0.2 }],
    });

    const { ordered } = groupTopMarkets([unique, keyless]);

    expect(ordered.filter(isGroupedMarket)).toHaveLength(0);
    expect(ordered.map((e) => (isGroupedMarket(e) ? -1 : e.score))).toEqual([
      90, 10,
    ]);
  });

  it("splits a three-way pile into the cross-source pair plus the odd one out", () => {
    // The realistic mixed case: men's priced by two sources, women's by one.
    // The men's pair combines; the women's market stands alone with its own
    // players — it must not be swept into the men's card as a third 'source'.
    const mensKalshi = futures({
      id: 600,
      name: "2026 Men's US Open Winner (Tennis)",
      source: "kalshi",
      score: 88,
      outcomes: [{ name: "Carlos Alcaraz", probability: 0.34 }],
    });
    const mensPoly = futures({
      id: 601,
      name: "US Open Men's Champion",
      source: "polymarket",
      score: 85,
      outcomes: [{ name: "Carlos Alcaraz", probability: 0.355 }],
    });
    const womensPoly = futures({
      id: 602,
      name: "2026 Women's US Open Winner (Tennis)",
      source: "polymarket",
      score: 84,
      outcomes: [{ name: "Aryna Sabalenka", probability: 0.235 }],
    });

    const { ordered } = groupTopMarkets([mensKalshi, mensPoly, womensPoly]);

    expect(ordered).toHaveLength(2);
    const groups = ordered.filter(isGroupedMarket);
    expect(groups).toHaveLength(1);
    expect(groups[0].items.map((i) => (i.data as { id: number }).id).sort()).toEqual(
      [600, 601]
    );
    expect(namesRenderedWith(ordered, 602)).toEqual(["Aryna Sabalenka"]);
  });
});
