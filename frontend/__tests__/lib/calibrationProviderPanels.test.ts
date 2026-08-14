import {
  buildProviderPanels,
  shapeBreakdownNote,
  type ProviderPanelInput,
} from "@/lib/calibrationProviderPanels";
import { groupSourcesByProvider } from "@/lib/calibrationProviders";
import { ece } from "@/lib/calibrationMath";

// The five source keys the live 2026-08-13 payload publishes, with their real
// outcome counts — the same corpus `calibrationProviders.test.ts` pins, for the
// same reason: a change to the grouping has to argue with production numbers
// rather than with a convenient example.
const LIVE_SOURCES = [
  "kalshi",
  "polymarket",
  "odds_api",
  "odds_api_totals",
  "odds_api_spreads",
];
const LIVE_N: Record<string, number> = {
  kalshi: 424127,
  polymarket: 241372,
  odds_api: 15674,
  odds_api_totals: 12704,
  odds_api_spreads: 12409,
};

/** One bucket carrying the source's whole n, so `n` sums to the live figure. */
const bucketsFor = (src: string, error = 2) => [{ n: LIVE_N[src], error }];

function liveInputs(overrides: Partial<Record<string, Partial<ProviderPanelInput>>> = {}) {
  return groupSourcesByProvider(LIVE_SOURCES).map(g => {
    const base: ProviderPanelInput = {
      provider: g.provider,
      label: g.label,
      sources: g.sources,
      buckets: g.sources.flatMap(s => bucketsFor(s)),
      publishedEce: g.sources.length === 1 ? 3.1 : null,
      pooledEce: g.sources.length > 1 ? 4.2 : null,
    };
    return { ...base, ...(overrides[g.provider] ?? {}) };
  });
}

describe("buildProviderPanels — the shape of By Source", () => {
  it("returns one panel per PROVIDER, not per source key", () => {
    const panels = buildProviderPanels(liveInputs());
    // Five keys in, three panels out. This is Alex's item (d) as an assertion.
    expect(panels).toHaveLength(3);
    expect(panels.map(p => p.provider).sort()).toEqual(
      ["kalshi", "odds_api_family", "polymarket"].sort()
    );
  });

  it("orders largest-first, matching buildSourcePanels", () => {
    const panels = buildProviderPanels(liveInputs());
    expect(panels.map(p => p.provider)).toEqual([
      "kalshi", // 424,127
      "polymarket", // 241,372
      "odds_api_family", // 15,674 + 12,704 + 12,409 = 40,787
    ]);
  });

  it("sums the provider's n across every shape it pooled", () => {
    const sportsbooks = buildProviderPanels(liveInputs()).find(
      p => p.provider === "odds_api_family"
    )!;
    expect(sportsbooks.n).toBe(
      LIVE_N.odds_api + LIVE_N.odds_api_totals + LIVE_N.odds_api_spreads
    );
  });

  it("shares sum to 1 across the panelled population", () => {
    const panels = buildProviderPanels(liveInputs());
    const total = panels.reduce((s, p) => s + p.share, 0);
    expect(total).toBeCloseTo(1, 10);
  });

  it("flags exactly the providers that owe a shape breakdown", () => {
    const panels = buildProviderPanels(liveInputs());
    const withBreakdown = panels.filter(p => p.hasShapeBreakdown).map(p => p.provider);
    // Kalshi and Polymarket publish one shape each, so a disclosure under them
    // would open onto a copy of the panel it is inside.
    expect(withBreakdown).toEqual(["odds_api_family"]);
  });

  it("drops a provider with no outcomes rather than framing an empty panel", () => {
    // An empty panel asserts "we measured this provider and found nothing".
    const panels = buildProviderPanels(
      liveInputs({ polymarket: { buckets: [] } })
    );
    expect(panels.map(p => p.provider)).not.toContain("polymarket");
    expect(panels).toHaveLength(2);
  });

  it("drops a provider whose buckets are all empty, not just one with no buckets", () => {
    // The drop rule is `n`, not `buckets.length` — both states mean absent and
    // both must fall out in the same place.
    const panels = buildProviderPanels(
      liveInputs({ polymarket: { buckets: [{ n: 0, error: 4 }] } })
    );
    expect(panels.map(p => p.provider)).not.toContain("polymarket");
  });

  it("survives an empty or nullish input without throwing", () => {
    expect(buildProviderPanels([])).toEqual([]);
    expect(buildProviderPanels(null)).toEqual([]);
    expect(buildProviderPanels(undefined)).toEqual([]);
  });
});

describe("the ECE a panel renders states which KIND of number it is (ruling 003)", () => {
  it("a single-shape provider renders the SERVER's published number", () => {
    const kalshi = buildProviderPanels(liveInputs()).find(p => p.provider === "kalshi")!;
    expect(kalshi.ece).toBe(3.1);
    expect(kalshi.eceBasis).toBe("published");
  });

  it("a multi-shape provider renders the POOLED number and says so", () => {
    const sportsbooks = buildProviderPanels(liveInputs()).find(
      p => p.provider === "odds_api_family"
    )!;
    expect(sportsbooks.ece).toBe(4.2);
    expect(sportsbooks.eceBasis).toBe("pooled");
  });

  it("NEVER passes off one shape's published ECE as the provider's", () => {
    // The failure this forbids is subtle and would look right: the Sportsbooks
    // panel showing moneyline's ECE, which measures a strict subset of the
    // outcomes the panel's own `n` counts.
    const sportsbooks = buildProviderPanels(
      liveInputs({ odds_api_family: { publishedEce: 9.9, pooledEce: 4.2 } })
    ).find(p => p.provider === "odds_api_family")!;
    expect(sportsbooks.ece).toBe(4.2);
    expect(sportsbooks.ece).not.toBe(9.9);
  });

  it("NEVER passes off a pooled figure as a single-shape provider's published one", () => {
    // The inverse, which would quietly downgrade a server number to a client one.
    const kalshi = buildProviderPanels(
      liveInputs({ kalshi: { publishedEce: null, pooledEce: 7.7 } })
    ).find(p => p.provider === "kalshi")!;
    expect(kalshi.ece).toBeNull();
    expect(kalshi.eceBasis).toBe("none");
  });

  it("renders nothing, and says 'none', when there is honestly no number", () => {
    const panels = buildProviderPanels(
      liveInputs({
        kalshi: { publishedEce: null },
        odds_api_family: { pooledEce: null },
      })
    );
    for (const p of panels.filter(x => x.provider !== "polymarket")) {
      expect(p.ece).toBeNull();
      expect(p.eceBasis).toBe("none");
    }
  });

  it("refuses NaN and Infinity rather than rendering them", () => {
    const panels = buildProviderPanels(
      liveInputs({
        kalshi: { publishedEce: NaN },
        odds_api_family: { pooledEce: Infinity },
      })
    );
    expect(panels.find(p => p.provider === "kalshi")!.ece).toBeNull();
    expect(panels.find(p => p.provider === "odds_api_family")!.ece).toBeNull();
  });

  it("rounds to the page's display precision — formatting, not deriving", () => {
    const kalshi = buildProviderPanels(
      liveInputs({ kalshi: { publishedEce: 3.14159 } })
    ).find(p => p.provider === "kalshi")!;
    expect(kalshi.ece).toBe(3.1);
  });
});

// ── THE PAIRING ASSERTION ───────────────────────────────────────────────────
// Ruling 003's failure mode is DRIFT between two independent derivations of the
// same calibration number. The Sportsbooks panel and the Sportsbooks row both
// show a pooled ECE, so the only thing that makes them safe is that there is
// ONE derivation rendered twice.
//
// A ban ("the panel must not call `ece()`") would be satisfied by deleting the
// call and hard-coding a number. A pairing is only satisfied by the thing we
// actually wanted — UX-P075 proved that twice in one cycle, when a footnote
// derived from a *condition* was wrong twice and the same footnote derived from
// the *emitted strings* could not be.
describe("the panel's pooled ECE cannot disagree with the table's", () => {
  it("is the identical value, because it is the identical computation", () => {
    // Stand in for `providerMetrics`: pool the provider's buckets and run the
    // page's own metric, exactly as Source Comparison does.
    const group = groupSourcesByProvider(LIVE_SOURCES).find(
      g => g.provider === "odds_api_family"
    )!;
    const pooledBuckets = [
      { n: LIVE_N.odds_api, error: 6 },
      { n: LIVE_N.odds_api_totals, error: 2 },
      { n: LIVE_N.odds_api_spreads, error: -4 },
    ];
    const tableEce = ece(pooledBuckets);

    const panel = buildProviderPanels([
      {
        provider: group.provider,
        label: group.label,
        sources: group.sources,
        buckets: pooledBuckets,
        pooledEce: tableEce, // the page passes the SAME memo's value
      },
    ])[0];

    // Equal at the precision both are rendered with. If a future edit
    // recomputes the panel's number independently, this is what goes red.
    expect(panel.ece).toBe(Math.round(tableEce * 10) / 10);
    expect(panel.eceBasis).toBe("pooled");
  });

  it("a pooled ECE is NOT the mean of the shapes' ECEs — the forbidden blend", () => {
    // Pooling buckets and averaging summaries give different answers whenever
    // the shapes differ in n, which they do by 26% here. If someone ever
    // "simplifies" the page to average the three published figures, the two
    // numbers separate and this states by how much.
    const pooled = ece([
      { n: LIVE_N.odds_api, error: 6 },
      { n: LIVE_N.odds_api_totals, error: 2 },
      { n: LIVE_N.odds_api_spreads, error: -4 },
    ]);
    const meanOfSummaries = (6 + 2 + 4) / 3;
    expect(pooled).not.toBeCloseTo(meanOfSummaries, 1);
  });
});

describe("shapeBreakdownNote — derived from the panels, not from a condition", () => {
  it("names the provider whose disclosure actually exists", () => {
    const note = shapeBreakdownNote(buildProviderPanels(liveInputs()));
    expect(note).toContain("Sportsbooks (Odds API)");
    expect(note).toContain("Break out the shapes");
  });

  it("says NOTHING when no panel has a breakdown to announce", () => {
    // The UX-P075 lesson in its exact shape: a sentence that describes a
    // disclosure the page is not rendering is the defect, and the only way to
    // make it unrepresentable is to read the panels rather than guess a
    // condition that implies them.
    const singleShapeOnly = buildProviderPanels(
      groupSourcesByProvider(["kalshi", "polymarket"]).map(g => ({
        provider: g.provider,
        label: g.label,
        sources: g.sources,
        buckets: bucketsFor(g.sources[0]),
        publishedEce: 2.0,
      }))
    );
    expect(singleShapeOnly.every(p => !p.hasShapeBreakdown)).toBe(true);
    expect(shapeBreakdownNote(singleShapeOnly)).toBeNull();
  });

  it("says nothing for an empty panel set", () => {
    expect(shapeBreakdownNote([])).toBeNull();
  });
});
