// #3892 — the chart's edge callout prints the same whole percent as the hero.
//
// ═══ THE DEFECT, READ ON PRODUCTION ═══
//
// `/events/15307463` (Khachanov v Blockx, a US Open quarter-final) on
// 2026-09-08 at ~09:20Z: the hero read **58%** and the chart's right-edge
// callout, sitting directly underneath it, read **57%**. The wire value is
// `0.575` and both were describing it — since #3898 pinned the pre-match edge to
// the blend, that callout IS the hero's number, drawn a second time.
//
// The cause is one multiplication. The chart plots on a 0–100 axis, so it held
// `homeProbToChartAxis(0.575)` = `57.49999999999999`, and `Math.round` of that
// is 57. `renderedPercent(0.575)` scales by `1000/10` precisely to recover the
// decimal the venue quoted, and gives 58.
//
// ═══ WHY THE EXISTING INVARIANT SUITE DID NOT CATCH IT ═══
//
// `probabilityInvariant.test.ts` guards "hero == readout == chart == tooltip"
// and was green throughout. It computed the displayed integer with its own
// `Math.round(frac * 100)` rather than calling `renderedPercent`, so after #3867
// changed the rule in the contract, the model and the chart were both wrong in
// the same direction and agreed with each other — which is all that file could
// ever check. It now calls the contract, and carries a 0.575 case, because a
// suite whose every input rounds the same way under both rules cannot tell them
// apart no matter how many assertions it makes.
//
// ═══ WHY THIS FILE DRIVES `chartAxisPercents` AND ALSO READS THE SOURCE ═══
//
// The first draft of this suite mirrored the component's arithmetic instead of
// calling it, and a mutation putting `Math.round(homeProb)` back into the
// callout left all of it GREEN. That is the same defect being diagnosed one
// paragraph up, reproduced in its own fix. So the rule moved into
// `chartAxisPercents` (a real exported function, driven below), and the call
// site is held by a source assertion — the only cheap thing that fails when
// someone re-inlines the rounding, which is exactly how this bug arrived.

import { readFileSync } from "fs";
import { join } from "path";

import {
  chartAxisPercents,
  chartAxisToHomeProb,
  homeProbToChartAxis,
} from "../lib/eventKeyStats";
import {
  renderedDuelPercents,
  renderedPercent,
} from "../lib/renderedPercent";

/** What the callout used to do: round the 0–100 axis value. */
const roundTheAxis = (probability: number): number =>
  Math.round(homeProbToChartAxis(probability));

/** What it does now, through the real shipped function. */
const shipped = (probability: number): number | null =>
  chartAxisPercents(homeProbToChartAxis(probability)).home;

// ═══ #4154 — WHAT THIS SUITE COMPARES THE CHART AGAINST, AND WHY IT MOVED ═══
//
// This file's subject is "the callout prints the same whole percent as the
// hero", and it asserted that as `shipped(p) === renderedPercent(p)`. That is a
// PROXY, and it is only the hero's answer when `p` is the LARGER side of the
// duel — `renderedDuelPercents` rounds the larger side and derives the smaller,
// so on `0.275` the hero prints a derived 27 while `renderedPercent(0.275)` is
// 28. Both of #3892's own moved values above 0.5 (0.565, 0.575) sit on the side
// where the proxy holds, so the suite could not tell the two rules apart — and
// #4154 shipped underneath it: hero 27%, callout 28%, on a quarter-final page.
//
// So the comparison is now the hero's ACTUAL function rather than a stand-in
// that agrees with it half the time. Where the two coincide the assertions are
// unchanged; where they do not, this is the one that describes the screen.
const heroHome = (probability: number): number | null =>
  renderedDuelPercents(1 - probability, probability)[1];

// The four three-decimal wire values on which `Math.round(p * 100)` and the
// contract disagree. Named in #3892 and re-derived here rather than trusted:
// the positive control below fails if the contract stops moving them.
const MOVED = [0.145, 0.285, 0.565, 0.575] as const;

describe("#3892 — the chart callout rounds the probability, not the axis value", () => {
  test.each(MOVED)(
    "%p: rounding the axis disagrees with the contract, the shipped path agrees",
    (p) => {
      // POSITIVE CONTROL. Without this the suite could pass on a value where
      // both rules already agree, which is almost all of them.
      expect(roundTheAxis(p)).not.toBe(renderedPercent(p));
      expect(roundTheAxis(p)).toBe(renderedPercent(p)! - 1);

      // The hero's answer, not `renderedPercent` — see the #4154 note above.
      // On 0.565/0.575 these are the same number; on 0.145/0.285 they are not,
      // and the hero is what the reader is comparing the callout to.
      expect(shipped(p)).toBe(heroHome(p));
    },
  );

  test("the exemplar: 0.575 is a 58% hero, and the callout no longer says 57", () => {
    expect(renderedPercent(0.575)).toBe(58);
    expect(roundTheAxis(0.575)).toBe(57); // what production printed
    expect(shipped(0.575)).toBe(58);
  });

  test.each([0, 0.01, 0.2, 0.5, 0.62, 0.81, 0.99, 1])(
    "%p: values that were never affected are unchanged — this is not a re-round",
    (p) => {
      expect(shipped(p)).toBe(roundTheAxis(p));
      expect(shipped(p)).toBe(renderedPercent(p));
    },
  );

  test("the away end is DERIVED, so a complement pair cannot print 101", () => {
    // On the half-percent grid both ends can land on `.5` at once: 0.565 and
    // 0.435 rounded independently under the contract is 57 + 44 = 101.
    expect(renderedPercent(0.565)! + renderedPercent(0.435)!).toBe(101);

    const pair = chartAxisPercents(homeProbToChartAxis(0.565));
    expect(pair.home).toBe(57);
    expect(pair.home! + pair.away!).toBe(100);
  });

  test("a non-finite axis value yields nulls, not NaN% — the caller must fall back", () => {
    for (const bad of [Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(chartAxisPercents(bad)).toEqual({ home: null, away: null });
      expect(renderedPercent(chartAxisToHomeProb(bad))).toBeNull();
    }
  });
});

// ═══ THE CALL SITE, NOT ONLY THE RULE ═══
//
// A unit test of `chartAxisPercents` proves the function is right. It cannot
// prove `OddsChart` still calls it — and re-inlining the arithmetic is precisely
// how the divergence got there. Rendering the chart in jsdom to find out is
// heavy and fragile (Recharts needs layout), so the call site is held by reading
// the file: cheap, and it fails on the actual regression.
describe("#3892 — OddsChart prints whole percents through the shared rule", () => {
  const raw = readFileSync(
    join(__dirname, "..", "components", "OddsChart.tsx"),
    "utf8",
  );

  // COMMENTS ARE STRIPPED BEFORE MATCHING, and this is not tidiness.
  //
  // The banned patterns below are the old code, and the fix DOCUMENTS the old
  // code — the comment beside the callout quotes `?? Math.round(homeProb)` to
  // explain why the fallback was removed. Matched against the raw file, the
  // explanation of the fix reads as the defect and the guard fails on a correct
  // file. (It did, on the first run.) A source guard has to read code, or the
  // only way to keep it green is to stop writing down what was wrong.
  //
  // `//` is not stripped when preceded by `:`, so a `https://` inside a comment
  // does not swallow the rest of the line.
  const source = raw
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1");

  test("the comment stripper leaves code and removes prose", () => {
    // A control on the instrument itself: if this over-stripped, every
    // `not.toMatch` below would pass vacuously.
    expect(source).toContain("chartAxisPercents");
    expect(source).not.toContain("ROUND THE PROBABILITY, NOT THE AXIS VALUE");
  });

  test("it calls chartAxisPercents at both print sites", () => {
    expect(source).toContain("chartAxisPercents");
    // The edge callout and the sportsbook tooltip. Two, so removing either one
    // fails here rather than being covered by the survivor.
    expect(source.match(/chartAxisPercents\(/g)?.length).toBe(2);
  });

  test("no whole percent is taken off the 0–100 axis value directly", () => {
    // `Math.round(homeProb)` and `homeProb.toFixed(0)` are the two forms this
    // bug took. `.toFixed(1)` is deliberately still allowed — the hover tooltip
    // prints one decimal, which is a different (and more honest) claim than a
    // whole percent, and is not what the contract governs.
    expect(source).not.toMatch(/Math\.round\(\s*homeProb\s*\)/);
    expect(source).not.toMatch(/Math\.round\(\s*100 - homeProb\s*\)/);
    expect(source).not.toMatch(/homeProb\.toFixed\(0\)/);
    expect(source).not.toMatch(/awayProb\.toFixed\(0\)/);

    // A control: the assertions above are not passing because the names
    // vanished from the file entirely.
    expect(source).toContain("homeProb");
  });
});
