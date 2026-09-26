// #8955 — "How We Measure This" is open by default on /calibration, and three of
// its exclusion notes were written for a reviewer: "A skeptical auditor can
// re-include them", raw payload keys (`kalshi/economics 108,704`), "the Gamma
// synthetic-placeholder band", "the residual asymmetry", and "if this sentence
// outlives the fix, the exclusion is the thing that is wrong". The two Kalshi
// bullets also said "1,144,458 included" under a page total of 942,284 — they
// count every Kalshi outcome checked, BEFORE the other rules, so "included"
// read as more Kalshi rows in the curve than the whole curve holds.
//
// The ruled clauses (CAL-P114/P117/P119, CERT-647) keep their own suite in
// `calibrationNonexclusiveBundleDisclosure.test.tsx`; this one pins the words.

import * as fs from "fs";
import * as path from "path";
import { exclusionCellLabel, temporaryCellCondition } from "@/lib/calibrationExclusionCopy";
import { makeSourceLabeller } from "@/lib/calibrationProviders";

const PAGE = path.join(__dirname, "..", "..", "app", "calibration", "page.tsx");
const SOURCE = fs.readFileSync(PAGE, "utf8");

/** The copy as a reader meets it: JSX comments gone, whitespace collapsed. */
const READER = SOURCE.replace(/\{\/\*[\s\S]*?\*\/\}/g, " ").replace(/\s+/g, " ");

const sourceLabel = makeSourceLabeller(undefined);

describe("#8955 — exclusion cells are named, never printed as payload keys", () => {
  test.each([
    ["kalshi/economics", "Kalshi"],
    ["polymarket/baseball", "Polymarket"],
    ["kalshi/crypto", "Kalshi"],
  ])("%s reads as a source and a category", (cell, source) => {
    const label = exclusionCellLabel(cell, sourceLabel);
    expect(label.startsWith(`${source} `)).toBe(true);
    expect(label).not.toContain("/");
    expect(label).not.toBe(cell);
  });

  test("a bare category key is a category label", () => {
    const label = exclusionCellLabel("esports", sourceLabel);
    expect(label).not.toContain("/");
    expect(label[0]).toBe(label[0].toUpperCase());
  });

  test("the page routes both per-cell maps through the labeller", () => {
    expect(SOURCE).toContain("`${exclusionCellLabel(cell, sourceLabel)} ${n.toLocaleString()}`");
    expect(SOURCE).toContain(
      "`${exclusionCellLabel(cell, sourceLabel)} — returns when ${temporaryCellCondition(cell)}`",
    );
    // The raw forms this replaced.
    expect(SOURCE).not.toContain("`${cell} ${n.toLocaleString()}`");
    expect(SOURCE).not.toContain("`${cell} — returns when ${condition}`");
  });
});

describe("#8955 — the revert condition is the page's own sentence", () => {
  test("the one ruled temporary cell has plain words, not the server's", () => {
    const condition = temporaryCellCondition("polymarket/baseball");
    expect(condition).not.toMatch(/writer|placeholder|0\.50|quote/i);
    expect(condition).toMatch(/player-prop/);
  });

  test("an unknown temporary cell still gets a clause (CAL-P119 disclosure survives)", () => {
    expect(temporaryCellCondition("kalshi/somethingnew").length).toBeGreaterThan(0);
  });
});

describe("#8955 — no reviewer prose on the reader's screen", () => {
  test.each([
    "skeptical auditor",
    "synthetic-placeholder",
    "Gamma",
    "residual asymmetry",
    "poly never-traded",
    "outlives the fix",
    "placeholder band",
    "Non-partition",
    "of the Kalshi set",
    "and we say so",
  ])("%s is gone from the rendered copy", phrase => {
    expect(READER).not.toContain(phrase);
  });
});

describe("#8955 — the Kalshi counts say what population they are over", () => {
  test("they read 'passed', not 'included', beside the page total", () => {
    expect(SOURCE).toContain("{data.liquidity_filter.kalshi_included.toLocaleString()} passed");
    expect(SOURCE).toContain("{data.writer_bar_filter.included.toLocaleString()} passed");
    expect(SOURCE).not.toContain("{data.liquidity_filter.kalshi_included.toLocaleString()} included");
    expect(SOURCE).not.toContain("{data.writer_bar_filter.included.toLocaleString()} included");
  });

  test("the page says they are taken before the other rules", () => {
    expect(READER).toMatch(/taken before the other rules, so they can be larger than the page.{1,8}s total/);
  });
});
