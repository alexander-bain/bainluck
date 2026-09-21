import {
  buildProviderPanels,
  eceInputsForPanel,
  shapeBreakdownNote,
  shapeBreakoutPointer,
  type ProviderPanelInput,
  providerKpiDetail,
  withoutGroupQualifier,
} from "@/lib/calibrationProviderPanels";
import { groupSourcesByProvider, sourceLabel } from "@/lib/calibrationProviders";
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

/**
 * A `winners` that is neither all nor none, so #7411's censoring gate reads
 * these fixtures as MEASURED populations and the panels below are about what
 * they were always about. A fixture that happened to be one-sided would now
 * withhold its ECE, and every assertion here would be failing for a reason
 * that has nothing to do with what it is testing.
 */
const mixedWinners = (n: number) => Math.max(1, Math.round(n / 2));

/** One bucket carrying the source's whole n, so `n` sums to the live figure. */
const bucketsFor = (src: string, error = 2) => [
  { n: LIVE_N[src], error, winners: mixedWinners(LIVE_N[src]) },
];

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
      liveInputs({ polymarket: { buckets: [{ n: 0, error: 4, winners: 0 }] } })
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

  // ── #7422 SPLIT ───────────────────────────────────────────────────────────
  // This was ONE test asserting that a pooled figure on a single-shape provider
  // is dropped to `none`. That conflated two things, and only one of them was
  // the thing worth protecting:
  //
  //   (a) a pooled figure must never be LAUNDERED as `published` — still true,
  //       still asserted, and it is the half that stops a client number being
  //       passed off as the server's;
  //   (b) a pooled figure on a single-shape provider is meaningless — FALSE
  //       since the cohort toggle. Under a filter the server has published no
  //       figure for the panel's population, so the pooled one is the only
  //       honest number there is, and dropping it left the panel free to print
  //       the whole-population figure instead (#7422: Polymarket, 1.6pp over
  //       "79,278 outcomes", against its own row's 2.7pp).
  //
  // Split rather than deleted, per the rule that a test documenting a measured
  // cost is split and made to assert the opposite, never pruned.
  it("renders a single-shape provider's pooled figure, and NEVER as 'published'", () => {
    const kalshi = buildProviderPanels(
      liveInputs({ kalshi: { publishedEce: null, pooledEce: 7.7 } })
    ).find(p => p.provider === "kalshi")!;
    expect(kalshi.ece).toBe(7.7);
    // The half of the old assertion that survives, and the load-bearing half:
    // a client-derived number is never dressed up as the server's.
    expect(kalshi.eceBasis).toBe("pooled");
    expect(kalshi.eceBasis).not.toBe("published");
  });

  it("prefers the pooled figure over a stale published one on a single-shape provider", () => {
    // The #7422 defect in miniature. Both are supplied — as they would be if a
    // call site ever passed the whole-population number through under a cohort
    // filter — and the one measured over the panel's OWN population wins.
    const kalshi = buildProviderPanels(
      liveInputs({ kalshi: { publishedEce: 1.6, pooledEce: 2.7 } })
    ).find(p => p.provider === "kalshi")!;
    expect(kalshi.ece).toBe(2.7);
    expect(kalshi.ece).not.toBe(1.6);
    expect(kalshi.eceBasis).toBe("pooled");
  });

  it("a single-shape provider with neither figure still says 'none'", () => {
    const kalshi = buildProviderPanels(
      liveInputs({ kalshi: { publishedEce: null, pooledEce: null } })
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
      { n: LIVE_N.odds_api, error: 6, winners: mixedWinners(LIVE_N.odds_api) },
      { n: LIVE_N.odds_api_totals, error: 2, winners: mixedWinners(LIVE_N.odds_api_totals) },
      { n: LIVE_N.odds_api_spreads, error: -4, winners: mixedWinners(LIVE_N.odds_api_spreads) },
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
    // No `winners` here: `ece` takes the curve's two fields, and this call is
    // about the metric, not about a panel.
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
    expect(note).toContain("Break out the curves");
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

describe("shapeBreakoutPointer — the count is the PANEL's, never the page's (#7308)", () => {
  it("counts the keys in the panel it names, not the keys on the page", () => {
    // Five source keys on the page; the panel the sentence points at holds
    // three of them. The old call site quoted five. This is the whole defect.
    const panels = buildProviderPanels(liveInputs());
    const pointer = shapeBreakoutPointer(panels)!;
    expect(pointer).not.toBeNull();
    expect(pointer.label).toBe("Sportsbooks (Odds API)");
    expect(pointer.providerCount).toBe(1);
    expect(pointer.keyCount).toBe(3);
    expect(pointer.keyCount).not.toBe(LIVE_SOURCES.length);
  });

  it("returns the very expression the control renders, for any grouping", () => {
    // Stated as an identity rather than a number so it survives a regrouping:
    // `<summary>Break out the curves ({p.sources.length})</summary>` is the
    // control, and this is that same read.
    const panels = buildProviderPanels(liveInputs());
    const breakout = panels.filter(p => p.hasShapeBreakdown);
    expect(breakout).toHaveLength(1);
    expect(shapeBreakoutPointer(panels)!.keyCount).toBe(breakout[0].sources.length);
  });

  it("refuses a number when two controls would each render a different one", () => {
    // Two breakout providers means no single figure is true of either
    // disclosure. Summing them would invent a count neither control shows —
    // the same invention one scope up.
    const twoFamilies = buildProviderPanels([
      {
        provider: "odds_api_family",
        label: "Sportsbooks (Odds API)",
        sources: ["odds_api", "odds_api_totals", "odds_api_spreads"],
        buckets: [{ n: 100, error: 2, winners: 50 }],
        pooledEce: 4.2,
      },
      {
        provider: "kalshi",
        label: "Kalshi",
        sources: ["kalshi", "kalshi_scalar"],
        buckets: [{ n: 90, error: 2, winners: 45 }],
        pooledEce: 3.0,
      },
    ]);
    const pointer = shapeBreakoutPointer(twoFamilies)!;
    expect(pointer.providerCount).toBe(2);
    expect(pointer.keyCount).toBeNull();
    expect(pointer.label).toBe("Sportsbooks (Odds API) and Kalshi");
  });

  it("points nowhere when there is no disclosure to point at", () => {
    // Same UX-P075 rule `shapeBreakdownNote` above is held to: the sentence
    // must be unable to describe a control the page is not rendering. The old
    // call site was gated on `shapeInline`, which is false in this case too —
    // so it sent a reader to a Sportsbooks panel that does not exist.
    const singleShapeOnly = buildProviderPanels(
      groupSourcesByProvider(["kalshi", "polymarket"]).map(g => ({
        provider: g.provider,
        label: g.label,
        sources: g.sources,
        buckets: bucketsFor(g.sources[0]),
        publishedEce: 2.0,
      }))
    );
    expect(shapeBreakoutPointer(singleShapeOnly)).toBeNull();
    expect(shapeBreakoutPointer([])).toBeNull();
  });
});

describe("providerKpiDetail — UX-P080 item 2 (Alex round 2)", () => {
  const label = (s: string) =>
    ({ kalshi: "Kalshi", polymarket: "Polymarket", odds_api: "moneyline",
       odds_api_bookmaker: "moneyline (book)", odds_api_spread: "spread" }[s] ?? s);

  const GROUPS = [
    { label: "Kalshi", sources: ["kalshi"] },
    { label: "Polymarket", sources: ["polymarket"] },
    { label: "Sportsbooks (Odds API)",
      sources: ["odds_api", "odds_api_bookmaker", "odds_api_spread"] },
  ];

  test("single-shape providers are named plainly, with no empty parens", () => {
    const out = providerKpiDetail(GROUPS, label);
    expect(out).toContain("Kalshi");
    expect(out).not.toContain("Kalshi (");
    expect(out).not.toContain("()");
  });

  test("a multi-shape provider names its shapes in the subtext", () => {
    expect(providerKpiDetail(GROUPS, label)).toContain(
      "Sportsbooks (Odds API: moneyline, moneyline (book), spread)",
    );
  });

  // #4214 — THE QUALIFIER, ONCE.
  //
  // Production read "Sportsbooks (Odds API) (Per-sportsbook (Odds API), Odds
  // API, Totals (Odds API), Spreads (Odds API))": "Odds API" five times, three
  // parens deep. The fixture above uses invented short labels, so it could
  // never have caught it — these tests use the REAL strings the page composes,
  // `PROVIDER_DISPLAY_NAMES.odds_api_family` against `SOURCE_DISPLAY_NAMES`.
  describe("the real production labels, which are what #4214 was filed on", () => {
    const REAL_GROUPS = [
      { label: "Kalshi", sources: ["kalshi"] },
      {
        label: "Sportsbooks (Odds API)",
        sources: ["odds_api", "odds_api_bookmaker", "odds_api_totals", "odds_api_spreads"],
      },
    ];
    // #7213: the page's own labeller, not five strings restated here. A copy
    // cannot fail when the page's map moves, which is the one thing a test
    // calling itself "the real production labels" has to be able to do.
    const realLabel = sourceLabel;

    const out = providerKpiDetail(REAL_GROUPS, realLabel);

    test("says the provider qualifier once, not once per member", () => {
      expect(out).toBe(
        "Kalshi · Sportsbooks (Odds API: Moneylines, Per-sportsbook, Totals, Spreads)",
      );
    });

    test("never nests a parenthesis inside a parenthesis", () => {
      // The reader-visible symptom, pinned independently of the exact wording:
      // scan the string and assert the depth never exceeds one.
      let depth = 0;
      for (const ch of out) {
        if (ch === "(") depth += 1;
        if (ch === ")") depth -= 1;
        expect(depth).toBeLessThanOrEqual(1);
        expect(depth).toBeGreaterThanOrEqual(0);
      }
      expect(depth).toBe(0);
    });

    test("still names every source key — UX-P080 collapses the count, not the information", () => {
      for (const src of REAL_GROUPS[1].sources) {
        const shape = realLabel(src).replace(" (Odds API)", "");
        expect(out).toContain(shape);
      }
    });

    test("and the supplier's name is not one of the shapes (#7213)", () => {
      // The loop above asserts each key is REACHABLE, not that it reads a
      // particular way — so it stayed green for months while the moneyline key
      // reached the tile as "Odds API", the supplier's name sitting in a list
      // of market shapes inside a parenthetical that had already said it.
      // #4214 recorded that as a residual; this is the assertion it was owed.
      const inside = /\(Odds API: ([^)]*)\)/.exec(out);
      expect(inside).not.toBeNull();
      const members = inside![1].split(", ");
      expect(members).toHaveLength(4);
      for (const member of members) {
        expect(member.toLowerCase()).not.toBe("odds api");
      }
    });

    // The fallback branch inside `withoutGroupQualifier`, which the render
    // tests cannot reach: no production label is only its own qualifier, so a
    // mutant that deletes the fallback survives every one of them. Reached
    // directly here instead, because an unreachable branch and an unguarded
    // branch look identical from the outside and only one of them is fine.
    test("a member that IS the qualifier keeps its name rather than becoming empty", () => {
      expect(withoutGroupQualifier(" (Odds API)", "Sportsbooks (Odds API)")).toBe(" (Odds API)");
      expect(withoutGroupQualifier("Totals (Odds API)", "Sportsbooks (Odds API)")).toBe("Totals");
      expect(withoutGroupQualifier("Kalshi", "Sportsbooks (Odds API)")).toBe("Kalshi");
      expect(withoutGroupQualifier("Totals (Odds API)", "Kalshi")).toBe("Totals (Odds API)");
    });

    test("a group with no qualifier is composed exactly as before", () => {
      // The strip must be a no-op wherever there is nothing to strip: this is
      // the regression path for every provider that is not the sportsbook
      // family, now and later.
      expect(
        providerKpiDetail([{ label: "Polymarket", sources: ["a", "b"] }], (s) => s.toUpperCase()),
      ).toBe("Polymarket (A, B)");
    });
  });

  test("the shapes are NOT dropped — every source key is still reachable", () => {
    // Alex's ruling collapses the COUNT, not the information. A KPI that says
    // "3" with no way to see what the third is made of trades one confusion for
    // another.
    const out = providerKpiDetail(GROUPS, label);
    for (const src of GROUPS.flatMap(g => g.sources)) {
      expect(out).toContain(label(src));
    }
  });

  test("the detail describes exactly the groups it was given", () => {
    // The pairing that makes the card unable to disagree with the tables: it is
    // a pure function of the same ProviderGroup[] they are built from, so it
    // cannot count a provider they do not show.
    const two = GROUPS.slice(0, 2);
    const out = providerKpiDetail(two, label);
    expect(out).not.toContain("Sportsbooks");
    expect(out.split(" · ")).toHaveLength(2);
  });

  test("an empty provider list yields an empty string, not 'undefined'", () => {
    expect(providerKpiDetail([], label)).toBe("");
  });
});

// ── #7422: WHICH FIGURE A PANEL MAY USE, IN BOTH COHORTS ────────────────────
//
// The defect was never in `buildProviderPanels`. It was at the call site, in
// two ternaries keyed on `sources.length` — which answers "does the server
// publish at this level" when the question the panel needs answered is "did
// the server measure THIS population". Under the cohort toggle those come
// apart, and `by_source[].ece` has no cohort dimension at all.
//
// What it printed: the traded Polymarket panel read "1.6pp ECE" (whole
// population, n=264,956) directly above its own "79,278 outcomes", while the
// Source Comparison row for the same provider in the same cohort read 2.7pp.
//
// This block exists because only ONE of the two cohorts is reachable by the
// static page render the sibling test file uses, and the unreachable one is
// the one that shipped wrong. A rule you cannot test in both states is a rule
// with an untested half.
describe("eceInputsForPanel — the server's figure is used only where it measured", () => {
  const SERVER = 1.6; // by_source[].ece for polymarket — whole population
  const POOLED = 2.7; // what Source Comparison derived for the traded cohort

  it("unfiltered single-shape: the SERVER's number, and no pooled one (ruling 003)", () => {
    expect(eceInputsForPanel(1, false, SERVER, POOLED)).toEqual({
      publishedEce: SERVER,
      pooledEce: null,
    });
  });

  it("FILTERED single-shape: the pooled number, and the server's is withheld", () => {
    // The defect, as an assertion. Pre-#7422 this returned the server's 1.6
    // and the panel rendered it beside a filtered n.
    expect(eceInputsForPanel(1, true, SERVER, POOLED)).toEqual({
      publishedEce: null,
      pooledEce: POOLED,
    });
  });

  it("multi-shape is pooled in BOTH cohorts — the server publishes nothing there", () => {
    for (const filtered of [false, true]) {
      expect(eceInputsForPanel(3, filtered, SERVER, POOLED)).toEqual({
        publishedEce: null,
        pooledEce: POOLED,
      });
    }
  });

  it("the two are never both non-null — a basis is never ambiguous", () => {
    for (const count of [1, 2, 3]) {
      for (const filtered of [false, true]) {
        const out = eceInputsForPanel(count, filtered, SERVER, POOLED);
        expect(out.publishedEce === null || out.pooledEce === null).toBe(true);
      }
    }
  });

  it("a missing figure normalises to null rather than undefined", () => {
    expect(eceInputsForPanel(1, false, undefined, undefined)).toEqual({
      publishedEce: null,
      pooledEce: null,
    });
    expect(eceInputsForPanel(1, true, SERVER, undefined)).toEqual({
      publishedEce: null,
      pooledEce: null,
    });
  });

  it("end to end: a filtered panel renders the COHORT's figure, not the server's", () => {
    // The rule and the builder together, which is what the page does. Without
    // this the two halves could each be right and the composition still wrong.
    const panel = buildProviderPanels([
      {
        provider: "polymarket",
        label: "Polymarket",
        sources: ["polymarket"],
        buckets: [{ n: 79_278, error: 2.7, winners: 27_000 }],
        ...eceInputsForPanel(1, true, SERVER, POOLED),
      },
    ])[0];
    expect(panel.ece).toBe(POOLED);
    expect(panel.ece).not.toBe(SERVER);
    expect(panel.eceBasis).toBe("pooled");
  });

  it("end to end: an UNFILTERED panel still renders the server's figure", () => {
    const panel = buildProviderPanels([
      {
        provider: "polymarket",
        label: "Polymarket",
        sources: ["polymarket"],
        buckets: [{ n: 264_956, error: 1.6, winners: 90_660 }],
        ...eceInputsForPanel(1, false, SERVER, POOLED),
      },
    ])[0];
    expect(panel.ece).toBe(SERVER);
    expect(panel.eceBasis).toBe("published");
  });
});
