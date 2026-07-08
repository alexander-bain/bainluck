// #999 slice 1: event-concept display helpers.

import {
  statusLabel,
  fieldOrder,
  childLeader,
  eventDateRange,
  splitChildren,
  marketsTracked,
  competitorMovement,
  formatMovement,
  seriesForName,
} from "../../lib/eventConceptDisplay";

describe("statusLabel", () => {
  test("maps statuses", () => {
    expect(statusLabel("live")).toBe("Live");
    expect(statusLabel("settled")).toBe("Settled");
    expect(statusLabel("upcoming")).toBe("Upcoming");
    expect(statusLabel("")).toBe("Upcoming");
  });
});

describe("fieldOrder", () => {
  test("sorts competitors by probability desc; nulls last", () => {
    const out = fieldOrder([
      { name: "A", probability: 0.1 },
      { name: "B", probability: 0.3 },
      { name: "C", probability: null },
      { name: "D", probability: 0.2 },
    ]);
    expect(out.map((c) => c.name)).toEqual(["B", "D", "A", "C"]);
  });
  test("empty is safe", () => {
    expect(fieldOrder([])).toEqual([]);
  });
});

describe("childLeader", () => {
  test("picks the top outcome", () => {
    const lead = childLeader({
      market_id: 1,
      market_name: "A vs B",
      outcomes: [
        { name: "A", probability: 0.4 },
        { name: "B", probability: 0.6 },
      ],
    });
    expect(lead).toEqual({ name: "B", probability: 0.6 });
  });
  test("falls back to child name/probability with no outcomes", () => {
    expect(childLeader({ market_id: 2, name: "Yes", probability: 0.3 })).toEqual({
      name: "Yes",
      probability: 0.3,
    });
  });
  test("null when nothing to show", () => {
    expect(childLeader({ market_id: 3 })).toBeNull();
  });
});

describe("splitChildren (L2-63: settled vs live)", () => {
  test("settled flag + extreme leader go to settled; live stays live", () => {
    const { live, settled } = splitChildren([
      { market_id: 1, market_name: "Sabalenka vs Osaka", probability: 0.62 },      // live
      { market_id: 2, market_name: "Eala vs Swiatek: Set 1", probability: 0.99 },  // decided (extreme)
      { market_id: 3, market_name: "Gauff vs X", probability: 0.55, settled: true },// flagged
      { market_id: 4, market_name: "Kostyuk vs Y", probability: 0.02 },            // decided (low)
    ]);
    expect(live.map((c) => c.market_id)).toEqual([1]);
    expect(settled.map((c) => c.market_id).sort()).toEqual([2, 3, 4]);
  });

  test("empty is safe", () => {
    expect(splitChildren([])).toEqual({ live: [], settled: [] });
  });
});

describe("eventDateRange", () => {
  test("range, single, none", () => {
    expect(eventDateRange("2026-04-09", "2026-04-12")).toMatch(/–/);
    expect(eventDateRange("2026-04-09", null)).not.toMatch(/–/);
    expect(eventDateRange(null, null)).toBeNull();
  });
});

describe("marketsTracked (L2-64 header count)", () => {
  const base = {
    event: { key: "k", domain: "golf", name: "T", status: "live" as const },
    primary: { kind: "winner_field" as const, label: "Winner", competitors: [], evolution_market_id: 5 },
    sections: [{ type: "winner", label: "Winner", market_ids: [1, 2] }],
    children: [{ market_id: 2 }, { market_id: 9 }],
    movers: [],
  };
  test("unions section + child + evolution market ids (distinct)", () => {
    // {1,2} ∪ {2,9} ∪ {5} = {1,2,5,9}
    expect(marketsTracked(base)).toBe(4);
  });
  test("no evolution / no sections is safe", () => {
    expect(
      marketsTracked({
        ...base,
        primary: { ...base.primary, evolution_market_id: null },
        sections: [],
        children: [],
      }),
    ).toBe(0);
  });
});

describe("competitorMovement", () => {
  test("reads golf movement_24h fraction", () => {
    expect(competitorMovement({ name: "A", probability: 0.2, movement_24h: 0.03 })).toBeCloseTo(0.03);
  });
  test("reads generic probability_change_24h", () => {
    expect(
      competitorMovement({ name: "A", probability: 0.2, probability_change_24h: -0.05 }),
    ).toBeCloseTo(-0.05);
  });
  test("normalizes an abs>1 points value to a fraction", () => {
    expect(competitorMovement({ name: "A", probability: 0.2, movement_24h: 3.2 })).toBeCloseTo(0.032);
  });
  test("null when absent", () => {
    expect(competitorMovement({ name: "A", probability: 0.2 })).toBeNull();
  });
});

describe("formatMovement", () => {
  test("signs and points", () => {
    expect(formatMovement(0.032)).toEqual({ text: "+3.2", dir: "up" });
    expect(formatMovement(-0.01)).toEqual({ text: "−1.0", dir: "down" });
  });
  test("omits negligible / null", () => {
    expect(formatMovement(0)).toBeNull();
    expect(formatMovement(0.0001)).toBeNull();
    expect(formatMovement(null)).toBeNull();
  });
});

describe("seriesForName", () => {
  const outcomes = [
    {
      outcome_id: 1,
      name: "Scottie Scheffler",
      history: [
        { timestamp: "2026-07-01T00:00:00Z", probability: 0.2, american_odds: null, bookmaker: "" },
        { timestamp: "2026-07-02T00:00:00Z", probability: null, american_odds: null, bookmaker: "" },
        { timestamp: "2026-07-03T00:00:00Z", probability: 0.24, american_odds: null, bookmaker: "" },
      ],
    },
  ];
  test("returns the time-ordered series with nulls dropped, name-insensitive", () => {
    expect(seriesForName(outcomes, "scottie scheffler ")).toEqual([0.2, 0.24]);
  });
  test("empty when no match or no data", () => {
    expect(seriesForName(outcomes, "Rory McIlroy")).toEqual([]);
    expect(seriesForName(undefined, "x")).toEqual([]);
  });
});
