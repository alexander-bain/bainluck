// #4530 (D102 = D, Alex 2026-09-09) — THE SCRIPT folds the rows it has no
// opening price for, instead of printing `pregame mark pending` beside each one.
//
// WHAT THIS FILE IS GUARDING, in the reader's terms: on an NFL event page at
// 390px, 89 of 298 script rows printed a grey monospace chip reading "pregame
// mark pending". That is our word for the hole, not a reader's — standing notice
// 34 bans exactly that sentence on a reader's screen, and Alex's D102 says the
// rows go behind a collapsed toggle that names its own count.
//
// THE TWO ASSERTIONS THAT ARE LOAD-BEARING, and why the rest are controls:
//
//   1. The fold exists, names its count, hides nothing and promotes nothing.
//      Eight assertions below, and all eight are red on the parent.
//   2. The fold is scoped to THE SCRIPT. DIVERGENCE and WHAT HIT have their own
//      documented treatments for a missing mark (UX-P036's "N unchanged" and
//      #1650's single settled phrase); a fold that leaked into them would
//      silently hide graded rows.
//
// RED-FIRST, measured rather than asserted. Run against the parent commit
// (`ScriptValue` returning the `pregame mark pending` chip, no `partitionScript`,
// no `ScriptFold`) the file imports and runs — it reaches the fold only through
// rendered output — and scores **8 failed, 6 passed of 14**.
//
// The six that already passed, named exactly, because "6 passed" is only
// evidence if you can say which six:
//   · the four tests marked CONTROL (divergence scoping, graded scoping,
//     pending_label rows, the empty list) — states the old code already got right;
//   · "no fold is rendered when every row carries a mark" — vacuously true before
//     a fold existed, and the other direction of gotcha #43 after;
//   · "a folded row never prints its live price" — ALSO green on the parent, which
//     printed the chip rather than the price. It is not load-bearing for this diff.
//     It guards the alternative fix this ship measured and REFUSED: falling back to
//     `current`. On the live payload, 209 rows carried both fields on an event that
//     had not started and they differed by a median of 4pts, up to 22.5pts, so a
//     fallback would print a live price under a heading reading "What the market
//     expected before the event". Nothing in the code stops a future session doing
//     that; this test does.
// A file where every test reds is a file whose controls are not controls.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";

/** Two rows with a mark, two without — the shape of every real family. */
const MIXED: PropMark[] = [
  { key: "Rushing Yards|A: 20+", label: "A: 20+", pregame_mark: 0.73, current: 0.75 },
  { key: "Rushing Yards|A: 30+", label: "A: 30+", pregame_mark: 0.31, current: 0.33 },
  { key: "Rushing Yards|B: 65+", label: "B: 65+", pregame_mark: null, current: 0.31 },
  { key: "Rushing Yards|B: 90+", label: "B: 90+", pregame_mark: null, current: 0.15 },
];

const script = (items: PropMark[]) =>
  renderToStaticMarkup(<PropsSection items={items} state="script" />);

describe("#4530 THE SCRIPT folds the rows it has no opening price for", () => {
  test("the banned chip is gone from the script", () => {
    expect(script(MIXED)).not.toContain("pregame mark pending");
  });

  test("the fold names its own count, in plain English", () => {
    expect(script(MIXED)).toContain("No opening price (2)");
  });

  test("the count is the number of rows actually folded, not the row total", () => {
    const html = script(MIXED);
    expect(html).toContain("No opening price (2)");
    expect(html).not.toContain("No opening price (4)");
  });

  // Green on the parent too (see header): this guards the REFUSED alternative
  // fix — falling back to `current` — not this diff's behaviour.
  test("a folded row never prints its live price as the pregame mark", () => {
    const html = script(MIXED);
    // 0.31 appears as BOTH a real mark (row A: 30+) and a live price (row B:
    // 65+), so 31% alone proves nothing. 15% is only ever row B's `current`.
    expect(html).not.toContain("15%");
  });

  // Collapsed, never dropped (gotcha #43).
  test("the folded rows are still present and reachable, not deleted", () => {
    const html = script(MIXED);
    expect(html).toContain("B: 65+");
    expect(html).toContain("B: 90+");
    expect(html).toContain("<details");
  });

  test("the rows that DO have a mark stay in plain sight, outside the fold", () => {
    const html = script(MIXED);
    // The marked rows and their numbers render before the disclosure opens.
    expect(html.indexOf("A: 20+")).toBeLessThan(html.indexOf("<details"));
    expect(html).toContain("73%");
    expect(html).toContain("31%");
  });

  test("a folded row shows the file's absent-data mark, not a second explanation", () => {
    const html = script(MIXED);
    expect(html).toContain("—");
    // The reason is stated once, by the summary — not repeated per row.
    expect(html.match(/No opening price/g)).toHaveLength(1);
  });

  test("a family with NO marks at all folds entirely rather than emptying", () => {
    const allBare: PropMark[] = [
      { key: "Receptions|C: 2+", label: "C: 2+", pregame_mark: null, current: 0.57 },
      { key: "Receptions|C: 3+", label: "C: 3+", pregame_mark: null, current: 0.34 },
    ];
    const html = script(allBare);
    expect(html).toContain("No opening price (2)");
    expect(html).toContain("C: 2+");
    expect(html).not.toContain("57%");
  });

  test("no fold is rendered when every row carries a mark", () => {
    const allMarked = MIXED.filter((m) => m.pregame_mark != null);
    const html = script(allMarked);
    expect(html).not.toContain("No opening price");
    expect(html).not.toContain("<details");
  });

  // The ungrouped path — golf/combat concept pages key marks by numeric market
  // id, so `groupByPropFamily` yields one unnamed group and the component takes
  // a different branch. Both branches share `partitionScript` so they cannot
  // drift; this is the assertion that proves they did not.
  test("the unnamed-group path folds identically", () => {
    const unnamed: PropMark[] = [
      { key: 101, label: "Top American", pregame_mark: 0.42, current: 0.44 },
      { key: 102, label: "Top European", pregame_mark: null, current: 0.29 },
    ];
    const html = script(unnamed);
    expect(html).toContain("No opening price (1)");
    expect(html).toContain("Top European");
    expect(html).not.toContain("29%");
  });

  // ---- CONTROLS: states and rows the old code already handled correctly ----

  test("CONTROL: THE DIVERGENCE does not fold — a missing mark stays in sight", () => {
    const html = renderToStaticMarkup(<PropsSection items={MIXED} state="divergence" />);
    expect(html).not.toContain("No opening price");
    expect(html).toContain("B: 65+");
  });

  test("CONTROL: WHAT HIT does not fold — a graded row is never hidden", () => {
    const graded: PropMark[] = [
      { key: "F|D", label: "D over", pregame_mark: null, current: 0.5, graded_result: "hit" },
    ];
    const html = renderToStaticMarkup(<PropsSection items={graded} state="graded" />);
    expect(html).not.toContain("No opening price");
    expect(html).toContain("D over");
  });

  test("CONTROL: a pending_label row is an answer, not a hole — it never folds", () => {
    const degenerate: PropMark[] = [
      {
        key: "F|R2",
        label: "Round 2 Leader",
        pregame_mark: null,
        current: null,
        pending_label: "Opens after Round 1",
      },
    ];
    const html = script(degenerate);
    expect(html).toContain("Opens after Round 1");
    expect(html).not.toContain("No opening price");
  });

  test("CONTROL: the section still returns null on an empty list", () => {
    expect(script([])).toBe("");
  });
});
