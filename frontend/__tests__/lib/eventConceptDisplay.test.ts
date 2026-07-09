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
  seriesFromCompetitor,
  competitorsToOutcomeHistory,
  daysUntilStart,
  countdownLabel,
} from "../../lib/eventConceptDisplay";

describe("daysUntilStart / countdownLabel (L2-78 pre-tournament countdown)", () => {
  const now = new Date("2026-07-09T21:44:00Z").getTime();

  test("The Open (Jul 15 00:00Z) reads 6 days out from Jul 9", () => {
    expect(daysUntilStart("2026-07-15T00:00:00Z", now)).toBe(6);
    expect(countdownLabel("upcoming", "2026-07-15T00:00:00Z", now)).toBe(
      "Starts in 6 days",
    );
  });

  test("same calendar date → 0 → 'Starts today'", () => {
    expect(daysUntilStart("2026-07-09T23:30:00Z", now)).toBe(0);
    expect(countdownLabel("upcoming", "2026-07-09T23:30:00Z", now)).toBe(
      "Starts today",
    );
  });

  test("next calendar day is singular ('in 1 day')", () => {
    expect(daysUntilStart("2026-07-10T09:00:00Z", now)).toBe(1);
    expect(countdownLabel("scheduled", "2026-07-10T09:00:00Z", now)).toBe(
      "Starts in 1 day",
    );
    expect(countdownLabel("scheduled", "2026-07-11T09:00:00Z", now)).toBe(
      "Starts in 2 days",
    );
  });

  test("past start / live / settled / missing → null (nothing to count down)", () => {
    expect(daysUntilStart("2026-07-01T00:00:00Z", now)).toBeNull();
    expect(countdownLabel("live", "2026-07-15T00:00:00Z", now)).toBeNull();
    expect(countdownLabel("settled", "2026-07-15T00:00:00Z", now)).toBeNull();
    expect(countdownLabel("upcoming", null, now)).toBeNull();
    expect(countdownLabel("upcoming", "not-a-date", now)).toBeNull();
  });
});

describe("seriesFromCompetitor (L2-71 envelope history)", () => {
  test("extracts the competitor's own probability series", () => {
    expect(
      seriesFromCompetitor({
        name: "A",
        probability: 0.3,
        history: [
          { timestamp: "2026-07-09T10:00:00Z", probability: 0.2 },
          { timestamp: "2026-07-09T12:00:00Z", probability: 0.3 },
        ],
      }),
    ).toEqual([0.2, 0.3]);
  });
  test("empty when no history", () => {
    expect(seriesFromCompetitor({ name: "A", probability: 0.3 })).toEqual([]);
  });
});

describe("competitorsToOutcomeHistory (L2-71)", () => {
  const comps = [
    {
      name: "Rory",
      probability: 0.3,
      outcome_id: 11,
      history: [
        { timestamp: "2026-07-01T00:00:00Z", probability: 0.1 },
        { timestamp: "2026-07-09T00:00:00Z", probability: 0.3 },
      ],
    },
    { name: "No History", probability: 0.05 }, // skipped (no outcome_id/history)
  ];
  test("builds FuturesOutcomeHistory only for competitors with history+outcome_id", () => {
    const out = competitorsToOutcomeHistory(comps);
    expect(out).toHaveLength(1);
    expect(out[0].outcome_id).toBe(11);
    expect(out[0].name).toBe("Rory");
    expect(out[0].history.map((p) => p.probability)).toEqual([0.1, 0.3]);
  });
  test("hours filters points client-side (range switch)", () => {
    // Only the very recent point survives a 24h window from a far-future 'now'.
    const recent = [
      { name: "X", probability: 0.5, outcome_id: 1, history: [
        { timestamp: "1999-01-01T00:00:00Z", probability: 0.2 },
      ]},
    ];
    const out = competitorsToOutcomeHistory(recent, 24);
    expect(out[0].history).toHaveLength(0); // ancient point filtered out
  });
});

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
