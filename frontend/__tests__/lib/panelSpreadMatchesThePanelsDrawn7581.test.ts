/**
 * #7581 — the panels-key fold may not quote a size spread the panels contradict.
 *
 * THE DEFECT, AS A READER MET IT
 *
 * `/calibration` at 390px, production 2026-09-20 ~19:20Z, the `How these panels
 * are drawn` fold in By Source:
 *
 *     "Each panel states its own sample size, and the providers differ by more
 *      than 28x in how much of the curve they carry."
 *
 * Directly beneath it, in the DEFAULT cohort, three panels stating 214,622 /
 * 155,127 / 79,278 outcomes — a 2.7x spread. The reader can falsify the
 * sentence with the numbers the same screen hands them.
 *
 * `28` was a literal in the JSX, measured when the section overlaid FIVE source
 * curves on one axis (~420K against ~15K, per its own code comment). Both ends
 * moved; the string did not.
 *
 * It was wrong in BOTH directions, which is why a "just update the number" fix
 * would not have held: in the all-markets cohort the panels run 326,909 down to
 * DataGolf's 36 — 9,081x — so the frozen figure understated the spread 325x in
 * the one view where the warning is load-bearing, because that is the view
 * drawing a 36-outcome panel at the same size as a 326,909-outcome one.
 *
 * WHAT THESE TESTS PIN
 *
 * Not the wording. The DERIVATION: the sentence's figure is a function of the
 * panels actually built, so it cannot be true in one cohort and false in the
 * other, and it cannot go stale when the populations move. A future edit may
 * reword the sentence freely; it cannot reintroduce a constant.
 *
 * Both cohorts are exercised, because the page can only render the default one
 * in a static test — and, exactly as #7422 found in this same file, the
 * untestable half is the half that ships wrong.
 */
import {
  buildProviderPanels,
  panelSpreadNote,
  type ProviderPanel,
} from "@/lib/calibrationProviderPanels";
import type { PanelBucket } from "@/lib/calibrationMath";

/**
 * A panel at a given size. Only `n` is load-bearing here; the rest is the
 * minimum a `ProviderPanel` has to carry to be one.
 */
const panel = (provider: string, n: number): ProviderPanel => ({
  provider,
  label: provider,
  sources: [provider],
  n,
  share: 0,
  ece: 1,
  eceBasis: "published",
  winners: null,
  hasShapeBreakdown: false,
});

/** Production, 2026-09-20, default (traded) cohort — the three panels drawn. */
const TRADED = [
  panel("kalshi", 214_622),
  panel("odds_api_group", 155_127),
  panel("polymarket", 79_278),
];

/** Production, same payload, `Include untraded (+298,001)` — four panels. */
const ALL_MARKETS = [
  panel("kalshi", 326_909),
  panel("polymarket", 264_956),
  panel("odds_api_group", 155_127),
  panel("datagolf", 36),
];

describe("#7581 the panels-key spread is derived from the panels drawn", () => {
  it("states the traded cohort's real spread, not the 28x that was frozen there", () => {
    const note = panelSpreadNote(TRADED);
    // 214,622 / 79,278 = 2.707…
    expect(note).toBe(
      "Each panel states its own sample size, and the largest here carries " +
        "2.7x the outcomes of the smallest."
    );
  });

  it("states the all-markets spread, which the frozen figure understated 325x", () => {
    const note = panelSpreadNote(ALL_MARKETS);
    // 326,909 / 36 = 9,080.8 → 9,081
    expect(note).toContain("9,081x the outcomes of the smallest");
  });

  it("never reprints the literal the defect was, in either cohort", () => {
    // The specific regression. `28x` was true of neither cohort measured here:
    // the traded spread is an order of magnitude below it and the all-markets
    // spread is two orders above, so a constant cannot serve both.
    for (const panels of [TRADED, ALL_MARKETS]) {
      expect(panelSpreadNote(panels)).not.toContain("28x");
    }
  });

  it("is a bound-free statement of the ratio (#7573, same page)", () => {
    // The sibling defect on this page was a bound verb over a computed figure.
    // A bound has to be re-argued every time the data moves, which is how the
    // constant survived; the ratio is stated, not capped.
    const note = panelSpreadNote(TRADED);
    expect(note).not.toMatch(/more than|within about|at least|up to/i);
  });

  it("moves when the panels move — the property a constant cannot have", () => {
    // The strawman guard. If the derivation were severed and a literal restored,
    // every assertion above could still be satisfied by that literal; this one
    // cannot be.
    const widened = [panel("kalshi", 214_622), panel("polymarket", 2_146)];
    expect(panelSpreadNote(widened)).toContain("100x");
    expect(panelSpreadNote(widened)).not.toBe(panelSpreadNote(TRADED));
  });

  it("drops the comparison, keeping the sample-size half, when there is nothing to compare", () => {
    // Fewer than two panels: every panel still states its own n, so that half
    // is unconditional — but there is no "largest" and no "smallest".
    expect(panelSpreadNote([panel("kalshi", 214_622)])).toBe(
      "Each panel states its own sample size."
    );
    expect(panelSpreadNote([])).toBe("Each panel states its own sample size.");
  });

  it("drops the comparison when the panels are the same size", () => {
    // A 1.0x "spread" is a sentence with no content. This is the state the
    // clause is supposed to disappear in on its own, the way #7515's clause
    // disappears when no row contradicts the bar.
    const even = [panel("kalshi", 100_000), panel("polymarket", 100_000)];
    expect(panelSpreadNote(even)).toBe("Each panel states its own sample size.");
    // and just inside the rounding boundary
    expect(panelSpreadNote([panel("a", 102_000), panel("b", 100_000)])).toBe(
      "Each panel states its own sample size."
    );
  });

  it("ignores a 0-outcome panel rather than dividing by it", () => {
    // `buildProviderPanels` drops 0-outcome providers (#7446), so this should
    // be unreachable — but a ratio is the one place where "should be" is not
    // good enough: the failure mode is Infinity rendered to a reader.
    const withEmpty = [panel("kalshi", 214_622), panel("polymarket", 79_278), panel("datagolf", 0)];
    expect(panelSpreadNote(withEmpty)).toContain("2.7x");
    expect(panelSpreadNote(withEmpty)).not.toMatch(/Infinity|NaN/);
  });

  it("the page's own builder feeds it: panels built from rows carry usable sizes", () => {
    // Ties the helper to the real call site rather than to hand-made fixtures
    // only — the note the fold renders is `panelSpreadNote(providerPanels)`,
    // and `providerPanels` comes from here.
    // `n` is DERIVED from the buckets, not passed — an empty `buckets` makes a
    // 0-outcome provider, which `buildProviderPanels` correctly drops. So the
    // sizes have to arrive as buckets or this fixture proves nothing.
    const bucketsOf = (n: number): PanelBucket[] => [
      { n, winners: Math.round(n * 0.5), error: 0.5 },
    ];
    const panels = buildProviderPanels([
      {
        provider: "kalshi",
        label: "Kalshi",
        sources: ["kalshi"],
        buckets: bucketsOf(214_622),
        publishedEce: 0.9,
      },
      {
        provider: "polymarket",
        label: "Polymarket",
        sources: ["polymarket"],
        buckets: bucketsOf(79_278),
        publishedEce: 2.7,
      },
    ]);
    expect(panels.length).toBe(2);
    expect(panels.map(p => p.n).sort((a, b) => b - a)).toEqual([214_622, 79_278]);
    // the same 2.7x the fold states in the default cohort, this time end-to-end
    expect(panelSpreadNote(panels)).toContain("2.7x the outcomes of the smallest");
    expect(panelSpreadNote(panels)).toContain("x the outcomes of the smallest");
  });
});
