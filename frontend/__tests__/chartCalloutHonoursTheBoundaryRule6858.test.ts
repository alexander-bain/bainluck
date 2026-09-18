// #6858 — THE CHART'S CALLOUT PRINTS THE HERO'S BOUNDARY RULE, NOT A BARE INTEGER
//
// Seen on production 2026-09-18 03:50Z, `/events/15298678` at 390px — Las Vegas
// Aces at Seattle Storm, LIVE, ten minutes left in the fourth, served
// `home_probability: 0.001`. Inside one phone screenful:
//
//     hero                      <1%
//     Win Probability callout    0%
//
// The chart told a reader that a team still playing had exactly no chance.
//
// ═══ WHY #4154's SUITE COULD NOT SEE THIS ═══
//
// #3892 fixed HOW the chart rounds; #4154 fixed WHICH END it rounds. After both,
// the hero and the callout agree on the INTEGER everywhere. They disagreed on
// what is PRINTED, because the boundary rule lives one layer above the integer,
// in `probabilityParts`, and is guarded on the raw probability:
//
//     if (rounded <= 0   && prob > 0) -> "<1%"
//     if (rounded >= 100 && prob < 1) -> ">99%"
//
// `chartAxisPercents` returned `number | null`, and `<1%` is not a number. So
// both arms were individually obeying their own contract and the screen still
// carried two answers — the same shape as #4154, one floor up.
//
// ═══ THE CONTROL THAT MATTERS MOST IS THE ONE THAT MUST NOT MOVE ═══
//
// A settled game's chart legitimately ends at a literal `100%` / `0%` — the
// completed journey, `prob` exactly 1 and 0. Both clauses above are STRICT on
// the probability, so those fall through untouched. A fix that "handles the
// edges" with a `<= 0` / `>= 100` check on the rounded integer instead would
// convert every finished game on the site to `>99%`, which is a far wider
// regression than the defect. That case is pinned below and is load-bearing.

import { readFileSync } from "fs";
import { join } from "path";

import {
  chartAxisPercents,
  homeProbToChartAxis,
} from "../lib/eventKeyStats";
import { formatProbabilityPercent } from "../lib/probabilityDisplay";
import { renderedDuelPercents } from "../lib/renderedPercent";

/** The label the chart actually prints for a home probability. */
const chartHomeLabel = (probability: number): string | null =>
  chartAxisPercents(homeProbToChartAxis(probability)).homeLabel;

const chartAwayLabel = (probability: number): string | null =>
  chartAxisPercents(homeProbToChartAxis(probability)).awayLabel;

/**
 * What the HERO prints for the same probability: the duel's own integer, put
 * through the shared formatter. Agreement is defined against this rather than
 * against a literal, so the day the hero's rule changes this suite moves with
 * it instead of pinning a stale string.
 */
const heroLabel = (probability: number): string =>
  formatProbabilityPercent(probability, {
    rendered: renderedDuelPercents(1 - probability, probability)[1] as number,
  });

describe("#6858 — the live specimen, and the boundary rule the callout was missing", () => {
  test("0.001 (the filed frame): the callout says <1%, not 0%", () => {
    // POSITIVE CONTROL: the integer really is 0, so this is not a value where
    // the defect never existed. That is exactly why a number cannot carry it.
    expect(chartAxisPercents(homeProbToChartAxis(0.001)).home).toBe(0);
    expect(chartHomeLabel(0.001)).toBe("<1%");
    expect(chartHomeLabel(0.001)).not.toBe("0%");
  });

  test("0.999 (the other end of the same served pair): >99%, not 100%", () => {
    expect(chartAxisPercents(homeProbToChartAxis(0.999)).home).toBe(100);
    expect(chartHomeLabel(0.999)).toBe(">99%");
    expect(chartHomeLabel(0.999)).not.toBe("100%");
  });

  test("the away end carries the rule too — the Aces' 0.999 off the Storm's axis", () => {
    // The frame's axis is the STORM's 0.001; the Aces' >99% is the derived end.
    // Without this the tooltip's second column could keep printing 100%.
    expect(chartAwayLabel(0.001)).toBe(">99%");
    expect(chartAwayLabel(0.999)).toBe("<1%");
  });

  test("callout and hero print the SAME STRING across the whole range", () => {
    for (const p of [
      0.001, 0.004, 0.006, 0.01, 0.145, 0.275, 0.5, 0.565, 0.575, 0.99, 0.994,
      0.996, 0.999,
    ]) {
      expect(chartHomeLabel(p)).toBe(heroLabel(p));
    }
  });
});

describe("#6858 — settled means settled: a true 100% / 0% is NOT a boundary case", () => {
  test("prob exactly 1 still prints the literal 100%", () => {
    expect(chartHomeLabel(1)).toBe("100%");
    expect(chartAwayLabel(1)).toBe("0%");
  });

  test("prob exactly 0 still prints the literal 0%", () => {
    expect(chartHomeLabel(0)).toBe("0%");
    expect(chartAwayLabel(0)).toBe("100%");
  });

  test("the strictness is the whole difference: 0 vs 0.001, 1 vs 0.999", () => {
    // Stated as a pair so the distinction cannot be read as an accident of two
    // separate cases. A `<= 0` check on the integer collapses both columns.
    expect([chartHomeLabel(0), chartHomeLabel(0.001)]).toEqual(["0%", "<1%"]);
    expect([chartHomeLabel(1), chartHomeLabel(0.999)]).toEqual([
      "100%",
      ">99%",
    ]);
  });
});

describe("#6858 — the pair still cannot print 101, and nulls still propagate", () => {
  test("a complement pair on the half-percent grid sums to 100", () => {
    // #4154's invariant, re-asserted through the LABELS: the boundary rule is
    // applied on top of the derived integer, never by re-rounding, so deriving
    // still does its job.
    const pair = chartAxisPercents(homeProbToChartAxis(0.565));
    expect(pair.home! + pair.away!).toBe(100);
    expect(pair.homeLabel).toBe("57%");
    expect(pair.awayLabel).toBe("43%");
  });

  test("a non-finite axis value yields null labels, never the string 'null%'", () => {
    for (const bad of [Number.NaN, Number.POSITIVE_INFINITY]) {
      const pair = chartAxisPercents(bad);
      expect(pair.homeLabel).toBeNull();
      expect(pair.awayLabel).toBeNull();
    }
  });
});

// ═══ THE CALL SITES, NOT ONLY THE RULE ═══
//
// Same argument as #3892's source guard: a unit test proves the function is
// right and cannot prove `OddsChart` prints its answer. Re-interpolating the
// integer is exactly how this defect existed, and it is one character of diff.
describe("#6858 — OddsChart prints the LABEL at both sites", () => {
  const raw = readFileSync(
    join(__dirname, "..", "components", "OddsChart.tsx"),
    "utf8",
  );
  const source = raw
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1");

  test("the comment stripper leaves code and removes prose", () => {
    // Anti-vacuity control on the instrument: every assertion below that can
    // pass by absence is worthless if this over-stripped.
    expect(source).toContain("chartAxisPercents");
    expect(source).not.toContain("the boundary rule's answer");
  });

  test("the edge callout interpolates homeLabel, not the bare integer", () => {
    expect(source).toContain("currentCallout.homeLabel");
    // The exact defect: `${currentCallout.homeProb}%`.
    expect(source).not.toMatch(/\$\{\s*currentCallout\.homeProb\s*\}%/);
  });

  test("the sportsbook tooltip prints the labels, not the bare integers", () => {
    expect(source).toContain("percents.homeLabel");
    expect(source).toContain("percents.awayLabel");
    expect(source).not.toMatch(/\{\s*percents\.home\s*\}%/);
    expect(source).not.toMatch(/\{\s*percents\.away\s*\}%/);
  });
});
