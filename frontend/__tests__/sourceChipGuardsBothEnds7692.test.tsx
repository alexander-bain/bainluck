// #7692 — THE PER-SOURCE CHIPS STOP CONTRADICTING THE CELL ABOVE THEM.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/playoffs/mlb`, National League, row 5, photographed at 2026-09-21 05:3xZ
// (`artifacts/ux-7692/before-desktop-grid-cubs.png`):
//
//     Chicago Cubs  87-69      99.5%       <- #7670's fix, correct and live
//                             P99 K100     <- the chips, unguarded
//
// `GET /api/playoffs/mlb` read in the same minute:
//
//     teams[].cells.make_playoffs  merged 0.9948
//                                  polymarket 0.9945   -> printed `P99`
//                                  kalshi     0.995    -> printed `K100`
//
// So the grid corrected the number and then un-corrected it in smaller type,
// about a club that can still miss. The legend above the table reads
// "Sources: K=Kalshi, S=Sportsbooks, P=Poly", so `K100` is read as "Kalshi says
// 100%" — the certainty claim #7670 removed from the line directly above.
//
// ── THE SHAPE: ONE GUARDED END OUT OF TWO, ONE LEVEL DOWN ────────────────────
//
//     pct >= 10 ? `${Math.round(pct)}` : … : pct < 0.1 ? "<.1" : pct.toFixed(1)
//
// The floor was defended (`<.1` never claims impossibility); the ceiling was a
// bare `Math.round`, so everything from 99.5 up printed `100`. This is #7670's
// own defect, eleven lines from the function #7670 fixed, and #7670 did not
// look down.
//
// ── WHY A SIBLING FUNCTION AND NOT A REROUTE ─────────────────────────────────
//
// The obvious fix — call `probabilityCellText` and drop the `%` — is wrong
// twice: the chips print no unit by design (the legend carries it), and the
// suffix-stripped floor becomes `<0.1`, widening a 9px cell for no reader
// benefit while changing an end that was already right. So the chips get
// `probabilityChipText`, which SHARES THE BANDS and keeps the vocabulary. The
// two functions sit in one file; the bands are one edit, not two.
//
// ── AND THE TOOLTIP, WHICH #7692 CITED AS THE MITIGATION ─────────────────────
//
// The issue said the hover text "already spells it out (`Polymarket: 99.95%`)".
// It did not: `pct.toFixed(1)` above 99 rounds into the absolute, so a served
// `0.9995` hovered as `Poly: 100.0%` — the same lie in the place named as the
// reason the chip's lie was tolerable. Both are fixed here.

import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";
import React from "react";

jest.mock("@/hooks/useAnalytics", () => ({
  useAnalytics: () => ({ track: () => {} }),
}));

import { probabilityCellText, probabilityChipText } from "../lib/probabilityCellText";
import TournamentProgressionTable from "../components/TournamentProgressionTable";
import type { ProgressionResponse } from "../lib/types";

const PROGRESSION_SOURCE = readFileSync(
  join(__dirname, "../components/TournamentProgressionTable.tsx"),
  "utf8"
);

/** One row, one column, with the per-source values a cell was actually served. */
function gridWith(
  rows: { name: string; merged: number; sources: [string, number][] }[]
): ProgressionResponse {
  return {
    stages: [
      { key: "make_playoffs", label: "Make Playoffs", order: 0, market_id: null, market_name: null, resolved: false },
    ],
    participants: rows.map((r) => ({
      name: r.name,
      team_id: null,
      logo_url: null,
      primary_color: null,
      conference: null,
      region: null,
      seed: null,
      record: null,
      probabilities: { make_playoffs: r.merged },
      changes_24h: {},
      status: {},
      sources_data: {
        make_playoffs: r.sources.map(([source, probability]) => ({ source, probability })),
      },
    })),
  } as unknown as ProgressionResponse;
}

/** Every chip's text, in render order — the 9px spans, not the cell numbers. */
function renderedChips(data: ProgressionResponse): string[] {
  const html = renderToStaticMarkup(<TournamentProgressionTable data={data} showLogos={false} />);
  return Array.from(
    html.matchAll(/text-\[9px\][^>]*>(?:<span[^>]*>)?([A-Za-z])(?:<\/span>)?([^<]*)</g)
  ).map((m) => `${m[1]}${m[2]}`);
}

/** The Cubs row exactly as production served it, plus a floor row for the mirror. */
const CUBS_GRID = gridWith([
  { name: "Chicago Cubs", merged: 0.9948, sources: [["polymarket", 0.9945], ["kalshi", 0.995]] },
  { name: "Seattle Mariners", merged: 0.0085, sources: [["polymarket", 0.0007], ["kalshi", 0.01]] },
]);

describe("#7692 — the production specimen, rendered", () => {
  it("THE SHIP: the Cubs' chips no longer say a source is certain", () => {
    const chips = renderedChips(CUBS_GRID);
    // Strawman guard first: the chips must actually be on the screen, or the
    // assertion below passes by reading nothing at all.
    expect(chips.length).toBe(4);
    // Polymarket 0.9945 and Kalshi 0.995 both land on 99.5 — which is the
    // merged cell's own number, so the three lines finally agree.
    expect(chips.slice(0, 2)).toEqual(["P99.5", "K99.5"]);
    // The reader's question: does anything under this cell claim 100?
    expect(chips).not.toContain("K100");
    expect(chips.join(" ")).not.toMatch(/\b100\b/);
  });

  it("the cell and its chips now tell the same story", () => {
    // The defect was not "a wrong number" — it was two numbers one line apart
    // disagreeing about whether the season is decided.
    const cell = probabilityCellText(0.9948); // "99.5%"
    const chip = probabilityChipText(0.995); // was "100"
    expect(cell.replace("%", "")).toBe("99.5");
    expect(chip).toBe("99.5");
  });

  it("the floor row is untouched — this fix only moved the ceiling", () => {
    const chips = renderedChips(CUBS_GRID);
    // polymarket 0.0007 -> 0.07% -> the chip's long-standing elided floor.
    expect(chips).toContain("P&lt;.1");
    // kalshi 0.01 -> 1.0% -> the decimal band below 10, unchanged.
    expect(chips).toContain("K1.0");
  });
});

describe("#7692 — the rule, as a sweep", () => {
  it("nothing below 1 prints `100`", () => {
    // The assertion that cannot be satisfied by special-casing 0.995.
    for (const p of [0.99, 0.995, 0.9945, 0.9948, 0.999, 0.9999, 0.99999, 0.999999]) {
      expect(probabilityChipText(p)).not.toBe("100");
    }
  });

  it("`100` survives for a source that really does state the absolute", () => {
    // The guard must not swallow the real thing, and must agree with the cell
    // above it — which prints `100%` at exactly 1 for the same reason.
    expect(probabilityChipText(1)).toBe("100");
    expect(probabilityCellText(1)).toBe("100%");
  });

  it("prints a bound where a decimal cannot express the distance", () => {
    expect(probabilityChipText(0.9995)).toBe(">99.9");
    expect(probabilityChipText(0.00005)).toBe("<.1");
  });

  it("the ordinary middle still rounds to whole points", () => {
    // Two chips per cell at 9px: a column of decimals across the whole grid
    // would be the regression this fix is one edit away from.
    expect(probabilityChipText(0.65)).toBe("65");
    expect(probabilityChipText(0.444)).toBe("44");
    expect(probabilityChipText(0.1)).toBe("10");
  });

  it("the sub-10% decimals the chip has always kept are unchanged", () => {
    expect(probabilityChipText(0.047)).toBe("4.7");
    expect(probabilityChipText(0.012)).toBe("1.2");
    expect(probabilityChipText(0.007)).toBe("0.7");
    expect(probabilityChipText(0.001)).toBe("0.1");
  });

  it("a served 0 keeps the chip's conservative floor, not a bare `0`", () => {
    // Deliberately NOT the cell's `0%`. A chip printing `0` would make the
    // impossibility claim #7670 removed; `<.1` is the safe side of that and
    // has been the chip's answer since it was written.
    expect(probabilityChipText(0)).toBe("<.1");
  });
});

describe("#7692 — the chip keeps its own vocabulary", () => {
  it("prints no `%` — the table legend carries the unit", () => {
    // A reroute through `probabilityCellText` would put a percent sign in a
    // 9px cell twice per column. This is the assertion that stops the next
    // "make them consistent" pass.
    for (const p of [1, 0.9995, 0.9948, 0.65, 0.007, 0]) {
      expect(probabilityChipText(p)).not.toContain("%");
    }
  });

  it("keeps the elided floor rather than the cell's wider one", () => {
    expect(probabilityChipText(0.0004)).toBe("<.1");
    expect(probabilityCellText(0.0004)).toBe("<0.1%");
  });

  it("both functions share one set of bands", () => {
    // The drift this fix exists to prevent: the chip and the cell agreeing on
    // WHERE the decimal bands are, differing only in how they spell them.
    for (const p of [0.9948, 0.995, 0.65, 0.444, 0.047, 0.0012]) {
      expect(probabilityCellText(p)).toBe(`${probabilityChipText(p)}%`);
    }
  });
});

describe("#7692 — the tooltip, which the issue named as the mitigation", () => {
  it("a served 0.9995 no longer hovers as `100.0%`", () => {
    // Boston's own numbers from the morning #7687 was filed — 0.9995 is the
    // value the issue asserted already hovered honestly.
    const html = renderToStaticMarkup(
      <TournamentProgressionTable
        data={gridWith([
          {
            name: "Boston Red Sox",
            merged: 0.9972,
            sources: [["polymarket", 0.9995], ["kalshi", 0.995]],
          },
        ])}
        showLogos={false}
      />
    );
    expect(html).toContain('title="Poly: 99.95%"');
    expect(html).not.toContain("100.0%");
    // …and the cell-wide tooltip, the second copy of the same expression.
    expect(html).toContain("Poly: 99.95% · Kalshi: 99.50%");
  });

  it("neither end rounds into an absolute even at two decimals", () => {
    // `99.995` renders as `100.00` and `0.004` as `0.00`; the extra decimal is
    // a resolution, not a guard, so the bound is still needed underneath it.
    expect(PROGRESSION_SOURCE).toContain('return `${label}: >99.99%`');
    expect(PROGRESSION_SOURCE).toContain('return `${label}: <0.01%`');
  });
});

describe("#7692 — what must not have come back", () => {
  it("the bare ceiling round is gone from the chip", () => {
    // Strawman guard first: the component has to still be the thing being read.
    expect(PROGRESSION_SOURCE).toContain("function SourceBreakdown");
    expect(PROGRESSION_SOURCE).toContain("probabilityChipText(s.probability)");
    const breakdown = PROGRESSION_SOURCE.slice(
      PROGRESSION_SOURCE.indexOf("function SourceBreakdown")
    ).slice(0, 900);
    expect(breakdown).not.toContain("Math.round(pct)");
  });

  it("the duplicated tooltip expression is gone from both call sites", () => {
    // It existed twice — once per chip, once per cell — and both copies told
    // the same lie. One function now, so the next fix lands on both.
    expect(PROGRESSION_SOURCE).not.toContain("pct.toFixed(1)}%` : `${pct.toFixed(2)}");
    expect(PROGRESSION_SOURCE).not.toMatch(/pct >= 1 \? pct\.toFixed\(1\) : pct\.toFixed\(2\)/);
    expect(PROGRESSION_SOURCE).toContain("function sourceTooltipText");
  });

  it("a non-finite source probability prints a dash, never `NaN`", () => {
    const html = renderToStaticMarkup(
      <TournamentProgressionTable
        data={gridWith([
          {
            name: "Poison Row",
            merged: 0.5,
            sources: [["polymarket", NaN], ["kalshi", 0.5]],
          },
        ])}
        showLogos={false}
      />
    );
    expect(html).not.toContain("NaN");
    // The healthy sibling still renders beside it (gotcha #42).
    expect(renderedChips(gridWith([
      { name: "Poison Row", merged: 0.5, sources: [["polymarket", NaN], ["kalshi", 0.5]] },
    ]))).toContain("K50");
  });
});
