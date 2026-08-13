import {
  providerOf,
  providerLabel,
  groupSourcesByProvider,
  shapeBreakdownIsSymmetric,
  SHAPE_BREAKDOWN_MIN_N,
} from "@/lib/calibrationProviders";

// The five source keys the live 2026-08-13 payload publishes, with their real
// outcome counts. Pinned so a change to the grouping rule has to argue with
// production numbers rather than with a convenient example.
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

describe("providerOf", () => {
  it("maps every Odds API shape onto one provider", () => {
    expect(providerOf("odds_api")).toBe("odds_api_family");
    expect(providerOf("odds_api_spreads")).toBe("odds_api_family");
    expect(providerOf("odds_api_totals")).toBe("odds_api_family");
    // Not in today's payload, but the producer still knows how to emit it.
    expect(providerOf("odds_api_bookmaker")).toBe("odds_api_family");
  });

  it("leaves single-shape providers as themselves — they are not special cases", () => {
    expect(providerOf("kalshi")).toBe("kalshi");
    expect(providerOf("polymarket")).toBe("polymarket");
  });

  it("is total: an unknown key becomes its own provider rather than vanishing", () => {
    // A source key we have never seen must still get a row. Dropping it would
    // silently shrink the table's population below the page's own headline.
    expect(providerOf("some_future_source")).toBe("some_future_source");
  });
});

describe("providerLabel", () => {
  it("names the Odds API family for a reader, not for a schema", () => {
    expect(providerLabel("odds_api_family")).toBe("Sportsbooks (Odds API)");
  });

  it("falls back to the raw provider rather than rendering undefined", () => {
    expect(providerLabel("some_future_source")).toBe("some_future_source");
  });
});

describe("groupSourcesByProvider", () => {
  it("collapses the live five source keys into three provider rows", () => {
    const groups = groupSourcesByProvider(LIVE_SOURCES);
    expect(groups.map(g => g.provider)).toEqual([
      "kalshi",
      "polymarket",
      "odds_api_family",
    ]);
    expect(groups[2].sources).toEqual([
      "odds_api",
      "odds_api_totals",
      "odds_api_spreads",
    ]);
  });

  it("preserves every source key — the parent rows partition the input", () => {
    const groups = groupSourcesByProvider(LIVE_SOURCES);
    const regrouped = groups.flatMap(g => g.sources).sort();
    expect(regrouped).toEqual([...LIVE_SOURCES].sort());
  });

  it("preserves first-seen order instead of imposing its own", () => {
    const groups = groupSourcesByProvider(["odds_api_totals", "kalshi", "odds_api"]);
    expect(groups.map(g => g.provider)).toEqual(["odds_api_family", "kalshi"]);
  });

  it("does not double-count a duplicated source key into the parent", () => {
    const groups = groupSourcesByProvider(["odds_api", "odds_api", "odds_api_spreads"]);
    expect(groups).toHaveLength(1);
    expect(groups[0].sources).toEqual(["odds_api", "odds_api_spreads"]);
  });

  it("returns nothing for an empty payload rather than a phantom row", () => {
    expect(groupSourcesByProvider([])).toEqual([]);
  });
});

describe("shapeBreakdownIsSymmetric", () => {
  it("is FALSE on the live payload — Kalshi and Polymarket have one shape each", () => {
    // This is the measurement that sends the shape breakdown to the annex.
    // If it ever flips to true, the breakdown belongs inline and this test is
    // the thing that should fail and say so.
    const groups = groupSourcesByProvider(LIVE_SOURCES);
    expect(shapeBreakdownIsSymmetric(groups, LIVE_N)).toBe(false);
  });

  it("is TRUE only when EVERY provider clears the floor on 2+ shapes", () => {
    const groups = groupSourcesByProvider([
      "kalshi", "kalshi_spreads", "odds_api", "odds_api_totals",
    ]);
    const n = {
      kalshi: 5000, kalshi_spreads: 5000, odds_api: 5000, odds_api_totals: 5000,
    };
    // `kalshi_spreads` groups under kalshi only if providerOf says so; it does
    // not, so this asserts the honest thing: two single-shape providers stay
    // asymmetric no matter how large they are.
    expect(shapeBreakdownIsSymmetric(groups, n)).toBe(false);
  });

  it("holds one provider back when its second shape is below the floor", () => {
    const groups = groupSourcesByProvider(["odds_api", "odds_api_totals"]);
    const justUnder = {
      odds_api: 50000,
      odds_api_totals: SHAPE_BREAKDOWN_MIN_N - 1,
    };
    expect(shapeBreakdownIsSymmetric(groups, justUnder)).toBe(false);

    const justOver = {
      odds_api: 50000,
      odds_api_totals: SHAPE_BREAKDOWN_MIN_N,
    };
    expect(shapeBreakdownIsSymmetric(groups, justOver)).toBe(true);
  });

  it("treats a missing count as zero rather than throwing the table away", () => {
    const groups = groupSourcesByProvider(["odds_api", "odds_api_totals"]);
    expect(shapeBreakdownIsSymmetric(groups, { odds_api: 50000 })).toBe(false);
  });

  it("is FALSE on an empty payload — nothing symmetric about nothing", () => {
    expect(shapeBreakdownIsSymmetric([], {})).toBe(false);
  });
});
