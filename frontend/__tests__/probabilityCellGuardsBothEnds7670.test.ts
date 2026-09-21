// #7670 — A GRID CELL STOPS PRINTING `100%` FOR A CLUB THAT CAN STILL MISS,
// AND `0%` FOR ONE THAT CAN STILL GET IN.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// The MLB playoff grid printed **`100%`** in Boston's `Make Playoffs` cell.
// Boston's served probability was **`0.9972`** — and two rows above, the Yankees
// and Rays rendered **✓** for having actually clinched. So the grid used its
// certainty glyph and its certainty number on two different states, one row
// apart, and a reader had no way to tell the decided club from the nearly
// decided one. Filed by authority/928 from a LOOK plus `GET /api/playoffs/mlb`
// read in the same minute, 2026-09-21 03:29Z.
//
// Re-read on production at 04:22Z while building this, still live:
//
//     teams[5]  make_playoffs  merged_probability = 0.9972   -> printed "100%"
//     teams[7]  make_playoffs  merged_probability = 0.9948   -> printed "99%"
//     teams[16] championship   merged_probability = 0.0005   -> printed "0%"
//
// The Cubs at `0.9948` are five thousandths from the same lie, which is what
// makes this a rounding rule and not a one-club anomaly.
//
// ── THE SHAPE: ONE GUARDED END OUT OF TWO ────────────────────────────────────
//
// `TournamentProgressionTable.formatProb` already refused `0%` for a
// small-but-possible outcome, degrading to `<0.1%` — because `0%` claims
// impossibility. Six lines later it rounded the top with `Math.round`, which
// claims certainty for the mirror-image reason. One end defended, one not, in
// the same function.
//
// `lib/playoffGrid.formatGridCell` had NEITHER guard, so it told both lies.
//
// `ChampionshipGrid` is the third renderer of this quantity and is the one that
// already guards both ends (`<1` and `99+`). It is deliberately NOT routed
// through the shared helper: 10px cells, bare numbers, no `%`. Asserted below,
// because "make them all consistent" is the obvious wrong fix here.

import { probabilityCellText } from "@/lib/probabilityCellText";
import { formatGridCell } from "@/lib/playoffGrid";
import { readFileSync } from "fs";
import { join } from "path";

const CHAMPIONSHIP_GRID_SOURCE = readFileSync(
  join(__dirname, "../components/ChampionshipGrid.tsx"),
  "utf8"
);
const PROGRESSION_SOURCE = readFileSync(
  join(__dirname, "../components/TournamentProgressionTable.tsx"),
  "utf8"
);

/** `formatGridCell` takes a cell; only `probability` is read. */
const cell = (probability: number | null) =>
  ({ probability } as Parameters<typeof formatGridCell>[0]);

describe("#7670 — the production specimens", () => {
  it("THE SHIP: 0.9972 no longer prints an absolute", () => {
    expect(probabilityCellText(0.9972)).toBe("99.7%");
    expect(formatGridCell(cell(0.9972))).toBe("99.7%");
    // The claim, stated as the reader's question: is this cell telling me the
    // season is decided?
    expect(probabilityCellText(0.9972)).not.toBe("100%");
  });

  it("the Cubs at 0.9948, five thousandths away, were already fine and stay fine", () => {
    // A fix that moved the rounding boundary instead of guarding the absolute
    // would change this one too, and it has nothing wrong with it.
    expect(probabilityCellText(0.9948)).toBe("99.5%");
  });

  it("and 0.0005 no longer prints an absolute at the other end", () => {
    expect(formatGridCell(cell(0.0005))).toBe("<0.1%");
    expect(formatGridCell(cell(0.0005))).not.toBe("0%");
  });
});

describe("#7670 — an absolute is printed only when the payload states one", () => {
  it("prints 100% for exactly 1 and 0% for exactly 0", () => {
    // The guard must not swallow the real thing. A club that HAS clinched, and
    // one that IS eliminated, are the two cases where an absolute is the truth.
    expect(probabilityCellText(1)).toBe("100%");
    expect(probabilityCellText(0)).toBe("0%");
  });

  it("prints a bound when it is too close to an absolute to render", () => {
    expect(probabilityCellText(0.99995)).toBe(">99.9%");
    expect(probabilityCellText(0.00005)).toBe("<0.1%");
  });

  it("nothing below 1 prints 100%, and nothing above 0 prints 0%", () => {
    // The rule as a sweep rather than as three examples. This is the assertion
    // that cannot be satisfied by special-casing the specimen.
    for (const p of [
      0.99, 0.995, 0.9949, 0.9972, 0.999, 0.9999, 0.99999, 0.999999,
    ]) {
      expect(probabilityCellText(p)).not.toBe("100%");
      expect(formatGridCell(cell(p))).not.toBe("100%");
    }
    for (const p of [
      0.01, 0.005, 0.001, 0.0005, 0.0001, 0.00001, 0.000001,
    ]) {
      expect(probabilityCellText(p)).not.toBe("0%");
      expect(formatGridCell(cell(p))).not.toBe("0%");
    }
  });
});

describe("#7670 — what must not have moved", () => {
  it("the ordinary middle of the range still rounds to whole points", () => {
    // The overwhelming majority of cells. If this drifted to one decimal the
    // grid would grow a column of noise on every page that renders it.
    expect(probabilityCellText(0.65)).toBe("65%");
    expect(probabilityCellText(0.444)).toBe("44%");
    expect(probabilityCellText(0.895)).toBe("90%");
    expect(probabilityCellText(0.10)).toBe("10%");
  });

  it("`formatProb`'s long-standing sub-10% decimals are unchanged", () => {
    // The band this function has always kept a decimal in: 0.1–10.
    expect(probabilityCellText(0.047)).toBe("4.7%");
    expect(probabilityCellText(0.012)).toBe("1.2%");
    expect(probabilityCellText(0.004)).toBe("0.4%");
    expect(probabilityCellText(0.001)).toBe("0.1%");
    // …and its floor word, which is where the ceiling guard was modelled from.
    expect(probabilityCellText(0.0009)).toBe("<0.1%");
  });

  it("a missing number is still each surface's own decision, not the helper's", () => {
    // The helper takes a number. `formatGridCell` returns null for a hole so the
    // grid can draw one of its named states, and `formatProb` prints an em dash.
    // Folding those into the helper would have made one of them wrong.
    expect(formatGridCell(cell(null))).toBeNull();
    expect(formatGridCell(cell(NaN))).toBeNull();
    expect(PROGRESSION_SOURCE).toContain('return "—"');
  });

  it("both renderers ask the one helper — no second copy of the rule", () => {
    // Strawman guard first: the names have to exist, or the greps below pass by
    // looking for something that was renamed away.
    expect(PROGRESSION_SOURCE).toContain("probabilityCellText(p)");
    expect(PROGRESSION_SOURCE).toContain("function formatProb");
    // And the arithmetic that WAS the bug has not survived beside the call.
    const formatProbBody = PROGRESSION_SOURCE.slice(
      PROGRESSION_SOURCE.indexOf("function formatProb")
    ).slice(0, 600);
    expect(formatProbBody).not.toContain("Math.round(pct)");
  });

  it("CONTROL: ChampionshipGrid keeps its own compact vocabulary", () => {
    // It is 10px, prints no `%`, and already guards both ends. Routing it
    // through this helper would be a regression dressed as consistency — so the
    // decision is asserted, not left to the next reader's judgement.
    expect(CHAMPIONSHIP_GRID_SOURCE).toContain('prob >= 0.995 ? "99+"');
    expect(CHAMPIONSHIP_GRID_SOURCE).toContain('if (p > 0 && p <= 0.01) return "<1";');
    expect(CHAMPIONSHIP_GRID_SOURCE).not.toContain("probabilityCellText");
  });
});
