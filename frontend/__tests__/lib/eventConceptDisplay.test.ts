// #999 slice 1: event-concept display helpers.

import {
  statusLabel,
  fieldOrder,
  childLeader,
  eventDateRange,
  splitChildren,
  settledChampion,
  marketsTracked,
  renderedFinishColumns,
  finishPositionRows,
  competitorMovement,
  formatMovement,
  seriesForName,
  seriesFromCompetitor,
  competitorsToOutcomeHistory,
  daysUntilStart,
  countdownLabel,
  isMatchupChild,
  childReactKey,
  headlinerMatchup,
  matchupKickoffLabel,
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

describe("settledChampion (L2-81 concluded winner-field)", () => {
  test("prefers the authoritative won flag over probability order", () => {
    // Stale field where the top probability is NOT the actual winner.
    const champ = settledChampion([
      { name: "Runner Up", probability: 0.55 },
      { name: "Champion", probability: 0.45, won: true },
    ]);
    expect(champ?.name).toBe("Champion");
  });

  test("falls back to a confident (>=0.9) top competitor when no won flag", () => {
    const champ = settledChampion([
      { name: "Winner", probability: 0.98 },
      { name: "Loser", probability: 0.02 },
    ]);
    expect(champ?.name).toBe("Winner");
  });

  test("null when no won flag and the field is ambiguous (never falsely crowns)", () => {
    expect(
      settledChampion([
        { name: "A", probability: 0.4 },
        { name: "B", probability: 0.35 },
      ]),
    ).toBeNull();
  });

  test("empty field is safe", () => {
    expect(settledChampion([])).toBeNull();
  });

  test("L2-83: crowns a diluted champion via the backend won flag", () => {
    // The REAL settled women's Wimbledon envelope: the champion's raw ~1.0 price is
    // #23-normalized DOWN to 0.888 (the residual field summed >100%), which is under
    // the >=0.9 confident-leader fallback. The backend L2-83 fix stamps `won` from
    // the raw price so the settled page still names the champion honestly.
    const field = [
      { name: "Linda Nosková", probability: 0.888, won: true },
      { name: "Aryna Sabalenka", probability: 0.018 },
      { name: "Jessica Pegula", probability: 0.01 },
    ];
    expect(settledChampion(field)?.name).toBe("Linda Nosková");
    // Without the backend won flag the diluted 0.888 (<0.9) would crown nobody —
    // proving the flag, not the display probability, is what makes it honest.
    const undiluted = field.map((c) => ({ ...c, won: undefined }));
    expect(settledChampion(undiluted)).toBeNull();
  });
});

describe("eventDateRange", () => {
  test("range, single, none", () => {
    expect(eventDateRange("2026-04-09", "2026-04-12")).toMatch(/–/);
    expect(eventDateRange("2026-04-09", null)).not.toMatch(/–/);
    expect(eventDateRange(null, null)).toBeNull();
  });
});

describe("marketsTracked (L2-116 count only what renders)", () => {
  const base = {
    event: { key: "k", domain: "golf", name: "T", status: "live" as const },
    primary: { kind: "winner_field" as const, label: "Winner", competitors: [], evolution_market_id: 5 },
    sections: [{ type: "winner", label: "Winner", market_ids: [1, 2] }],
    children: [{ market_id: 2 }, { market_id: 9 }],
    movers: [],
  };
  test("counts evolution + rendered children, NOT invisible winner-section extras", () => {
    // Rendered surfaces: evolution {5} ∪ children {2,9} = {2,5,9} = 3.
    // The extra winner-section market (1) renders nowhere — it must not count.
    expect(marketsTracked(base)).toBe(3);
  });
  test("no evolution / no children is safe", () => {
    expect(
      marketsTracked({
        ...base,
        primary: { ...base.primary, evolution_market_id: null },
        sections: [],
        children: [],
      }),
    ).toBe(0);
  });
  test("counts one question per RENDERED finish-position column (both directions)", () => {
    // top_5 + make_cut sections exist AND competitors carry the odds → 2 columns
    // render → +2. top_10 section exists but NO competitor carries top_10_prob →
    // that column does NOT render → not counted.
    const data = {
      ...base,
      primary: {
        ...base.primary,
        competitors: [
          { name: "A", probability: 0.3, top_5_prob: 55, make_cut_prob: 92 },
          { name: "B", probability: 0.1, top_5_prob: 30 },
        ],
      },
      sections: [
        { type: "winner", label: "Winner", market_ids: [1, 2] },
        { type: "top_5", label: "Top 5", market_ids: [11, 12] }, // two source copies → one column
        { type: "top_10", label: "Top 10", market_ids: [13] },
        { type: "make_cut", label: "Make Cut", market_ids: [14] },
      ],
    };
    // evolution {5} ∪ children {2,9} = 3, + top_5 + make_cut columns = 5.
    expect(marketsTracked(data)).toBe(5);
  });
  test("settled field suppresses finish columns from the count (settled-means-settled)", () => {
    const data = {
      ...base,
      event: { ...base.event, status: "settled" as const },
      primary: {
        ...base.primary,
        competitors: [{ name: "A", probability: 1, top_5_prob: 100, make_cut_prob: 100 }],
      },
      sections: [
        { type: "top_5", label: "Top 5", market_ids: [11] },
        { type: "make_cut", label: "Make Cut", market_ids: [14] },
      ],
    };
    // Only evolution {5} ∪ children {2,9} = 3; finish columns don't render.
    expect(marketsTracked(data)).toBe(3);
  });
});

describe("renderedFinishColumns / finishPositionRows (L2-116 ladder)", () => {
  const mk = (
    competitors: Record<string, unknown>[],
    sectionTypes: string[],
    status: "live" | "upcoming" | "settled" = "upcoming",
  ) => ({
    event: { key: "k", domain: "golf", name: "T", status },
    primary: {
      kind: "winner_field" as const,
      label: "Winner",
      competitors: competitors as never,
      evolution_market_id: 5,
    },
    sections: sectionTypes.map((t) => ({ type: t, label: t, market_ids: [1] })),
    children: [],
    movers: [],
  });

  test("a column renders iff its section exists AND a competitor carries a value", () => {
    const cols = renderedFinishColumns(
      mk(
        [{ name: "A", probability: 0.3, top_5_prob: 40, top_20_prob: 80 }],
        ["top_5", "top_10", "top_20", "make_cut"],
      ),
    );
    // top_5 + top_20 have data; top_10/make_cut sections exist but no odds → drop.
    expect(cols.map((c) => c.type)).toEqual(["top_5", "top_20"]);
  });

  test("section present but no odds → no column (never an empty ladder)", () => {
    const cols = renderedFinishColumns(
      mk([{ name: "A", probability: 0.3 }], ["top_5"]),
    );
    expect(cols).toEqual([]);
  });

  test("settled event renders no finish columns", () => {
    const cols = renderedFinishColumns(
      mk([{ name: "A", probability: 1, top_5_prob: 100 }], ["top_5"], "settled"),
    );
    expect(cols).toEqual([]);
  });

  test("L2-123: an all-tied-flat placeholder column is suppressed (never fake flats)", () => {
    // The Open's make-cut showed the whole field at ≈1.1 pts — a wide-spread/no-trade
    // capture placeholder (#199). The column must not render as a wall of fake flats.
    const flat = Array.from({ length: 8 }, (_, i) => ({
      name: `G${i}`,
      probability: 0.5 - i * 0.01,
      make_cut_prob: 1.1, // every golfer identical → degenerate
      top_5_prob: 40 - i * 4, // a genuine spread → keeps rendering
    }));
    const cols = renderedFinishColumns(mk(flat, ["top_5", "make_cut"]));
    expect(cols.map((c) => c.type)).toEqual(["top_5"]); // make_cut dropped
  });

  test("L2-123: a near-flat (not perfectly tied) placeholder column is suppressed", () => {
    // Mirrors the live Open R3 shape: values agree to ~1pp, not exactly. The relative
    // ratio must still catch it.
    const nearFlat = Array.from({ length: 8 }, (_, i) => ({
      name: `G${i}`,
      probability: 0.5 - i * 0.01,
      make_cut_prob: i === 0 ? 1.9 : 2.0, // ~0.1pt spread on a ~2pt field
    }));
    const cols = renderedFinishColumns(mk(nearFlat, ["make_cut"]));
    expect(cols).toEqual([]);
  });

  test("L2-123: a real spread survives even at scale (not over-suppressed)", () => {
    const real = Array.from({ length: 8 }, (_, i) => ({
      name: `G${i}`,
      probability: 0.5 - i * 0.05,
      make_cut_prob: 95 - i * 10, // wide, genuine field
    }));
    const cols = renderedFinishColumns(mk(real, ["make_cut"]));
    expect(cols.map((c) => c.type)).toEqual(["make_cut"]);
  });

  test("L2-123: a thin (<5) tied field is NOT flagged degenerate (too few to judge)", () => {
    const thin = [
      { name: "A", probability: 0.3, make_cut_prob: 1.1 },
      { name: "B", probability: 0.2, make_cut_prob: 1.1 },
    ];
    const cols = renderedFinishColumns(mk(thin, ["make_cut"]));
    expect(cols.map((c) => c.type)).toEqual(["make_cut"]);
  });

  test("rows are win-prob-ordered, drop competitors with no finish odds, keep nulls per cell", () => {
    const data = mk(
      [
        { name: "Low", probability: 0.05, top_5_prob: 10 },
        { name: "High", probability: 0.4, top_5_prob: 60 },
        { name: "NoOdds", probability: 0.2 },
      ],
      ["top_5", "top_10"],
    );
    const cols = renderedFinishColumns(data); // only top_5 has data
    const rows = finishPositionRows(data, cols);
    expect(rows.map((r) => r.competitor.name)).toEqual(["High", "Low"]); // NoOdds dropped
    expect(rows[0].values.top_5_prob).toBe(60);
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

// L2-130 — soccer matchup duels (World Cup bracket games as team duels).
describe("isMatchupChild", () => {
  test("true for explicit matchup kind or home/away presence", () => {
    expect(isMatchupChild({ kind: "matchup", home: { name: "A" }, away: { name: "B" } })).toBe(true);
    expect(isMatchupChild({ home: { name: "A" } })).toBe(true);
    expect(isMatchupChild({ away: { name: "B" } })).toBe(true);
  });
  test("false for combat fight cards and props", () => {
    expect(isMatchupChild({ kind: "fight", outcomes: [{ name: "X", probability: 0.6 }] })).toBe(false);
    expect(isMatchupChild({ kind: "prop", market_id: 5 })).toBe(false);
    expect(isMatchupChild({ market_id: 5, outcomes: [] })).toBe(false);
  });
});

describe("childReactKey", () => {
  test("prefers market_id, then event_id, then name+index — soccer games never collide on undefined", () => {
    expect(childReactKey({ market_id: 42 }, 0)).toBe("m42");
    // The pre-L2-130 bug: matchup children have NO market_id, so every soccer game
    // keyed as `undefined`. event_id keeps them distinct.
    expect(childReactKey({ event_id: 7 }, 0)).toBe("e7");
    expect(childReactKey({ event_id: 8 }, 1)).toBe("e8");
    expect(childReactKey({ market_name: "A vs B" }, 3)).toBe("A vs B-3");
  });
});

describe("headlinerMatchup", () => {
  const live = { kind: "matchup" as const, event_id: 1, status: "live", commence_time: "2026-07-15T19:00:00Z", home: { name: "England" }, away: { name: "Argentina" } };
  const soon = { kind: "matchup" as const, event_id: 2, status: "scheduled", commence_time: "2026-07-16T19:00:00Z", home: { name: "Spain" }, away: { name: "France" } };
  const later = { kind: "matchup" as const, event_id: 3, status: "scheduled", commence_time: "2026-07-19T19:00:00Z", home: { name: "Spain" }, away: { name: "England" } };
  const done = { kind: "matchup" as const, event_id: 4, status: "completed", settled: true, commence_time: "2026-07-14T19:00:00Z", home: { name: "France", score: 0 }, away: { name: "Spain", score: 2 } };
  test("prefers the live game", () => {
    expect(headlinerMatchup([done, later, live, soon])?.event_id).toBe(1);
  });
  test("falls back to the soonest upcoming when nothing is live", () => {
    expect(headlinerMatchup([done, later, soon])?.event_id).toBe(2);
  });
  test("null when only settled games remain (hero suppressed)", () => {
    expect(headlinerMatchup([done])).toBeNull();
  });
  test("ignores non-matchup children", () => {
    expect(headlinerMatchup([{ kind: "prop", market_id: 9 }])).toBeNull();
  });
});

describe("matchupKickoffLabel", () => {
  const now = Date.parse("2026-07-15T18:00:00Z");
  test("live and settled read as status, clock-independent", () => {
    expect(matchupKickoffLabel({ status: "live" }, now)).toBe("Live");
    expect(matchupKickoffLabel({ status: "completed", settled: true }, now)).toBe("Final");
    expect(matchupKickoffLabel({ settled: true }, now)).toBe("Final");
  });
  test("relative countdown for an upcoming game within the hour / day", () => {
    expect(matchupKickoffLabel({ status: "scheduled", commence_time: "2026-07-15T18:45:00Z" }, now)).toBe("Kicks off in 45m");
    expect(matchupKickoffLabel({ status: "scheduled", commence_time: "2026-07-15T20:30:00Z" }, now)).toBe("Kicks off in 2h 30m");
  });
  test("null when an upcoming game has no usable time", () => {
    expect(matchupKickoffLabel({ status: "scheduled" }, now)).toBeNull();
    expect(matchupKickoffLabel({ status: "scheduled", commence_time: "not-a-date" }, now)).toBeNull();
  });
});

describe("marketsTracked counts soccer games by event_id", () => {
  test("winner market + matchup children (event_id) all count, no id collisions", () => {
    const data = {
      event: { key: "event:soccer:world-cup-2026", domain: "soccer", name: "WC", status: "live" as const },
      primary: { kind: "winner_field" as const, label: "Winner", competitors: [], evolution_market_id: 10 },
      sections: [],
      children: [
        { kind: "matchup" as const, event_id: 1, home: { name: "A" }, away: { name: "B" } },
        { kind: "matchup" as const, event_id: 2, home: { name: "C" }, away: { name: "D" } },
      ],
      movers: [],
    };
    // 1 winner market + 2 games = 3.
    expect(marketsTracked(data)).toBe(3);
  });
});
