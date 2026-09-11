// #5191 — the graded-window rungs truncate at 390px and restate their own header.
//
// WHAT A READER SAW (`/events/15308050`, Tampa Bay @ Atlanta, 390px, production):
//
//     FIRST 5 INNINGS TOTAL
//     Over 0.5 runs in the first 5 inn…      7 runs — hit
//     Over 1.5 runs in the first 5 inn…      7 runs — hit
//     …seven of them, near-identical, the only distinguishing part surviving.
//
// MEASURED, not eyeballed. `artifacts/ux-1200/truncation-probe.mjs` asks the
// browser which labels are ACTUALLY clipped (`scrollWidth > clientWidth` on the
// span carrying `truncate`) rather than re-deriving the renderer's arithmetic:
// 7 of 7 rungs of that family clipped, 23 of 269 labels page-wide.
//
// The rule and its guards live in `lib/propFamily.sharedLabelSuffix` and are
// tested there. THIS file tests the wiring — that the strip reaches the row a
// reader looks at, in every state and on both row components, and that the
// families it must not touch reach the page unchanged.
//
// RED-FIRST, measured. Against the parent commit (`PropRow` printing
// `item.label`, `BinaryBarRow` printing `item.question ?? item.label`) this file
// imports and runs and scores 6 failed, 5 passed of 11. The five that already
// passed are exactly the ones marked CONTROL — the header survives, no row is
// lost, `question` still wins, the player family is untouched, the unnamed group
// is untouched — and every one of them is something this diff could have broken.
// The spread's handicap is NOT a control: on base that row reads "Atlanta -1.5
// first 5 innings", so the assertion that it reads "Atlanta -1.5" is red there
// too. It is the guard and the fix in one row.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";

const RAYS_AT_BRAVES = { home: "Atlanta Braves", away: "Tampa Bay Rays" };

/** Verbatim from `/api/events/15308050/game-markets`, 2026-09-11. */
const WINDOW_RUNGS: PropMark[] = [0.5, 1.5, 2.5].map((n, i) => ({
  key: `Tampa Bay vs Atlanta: First 5 Innings Total|Over ${n} runs in the first 5 innings`,
  label: `Over ${n} runs in the first 5 innings`,
  pregame_mark: 0.9 - i * 0.1,
  current: 0.95 - i * 0.1,
  graded_result: "hit",
  graded_label: "7 runs — hit",
  settled: true,
}));

/** Also verbatim: the family whose handicap must survive the strip. */
const SPREAD_LEGS: PropMark[] = [
  ["Atlanta", "-1.5"],
  ["Atlanta", "-2.5"],
  ["Tampa Bay", "-1.5"],
].map(([side, line]) => ({
  key: `Tampa Bay vs Atlanta: First 5 Spread|${side} ${line} first 5 innings`,
  label: `${side} ${line} first 5 innings`,
  pregame_mark: 0.5,
  current: 0.5,
}));

/** And the cohort #4866 taught us to protect: a player's own name is the row. */
const PLAYER_RUNGS: PropMark[] = ["6+", "7+", "9+"].map((n) => ({
  key: `Tampa Bay vs Atlanta: Strikeouts|Griffin Jax: ${n}`,
  label: `Griffin Jax: ${n}`,
  pregame_mark: 0.3,
  current: 0.05,
}));

const render = (items: PropMark[], state: "script" | "divergence" | "graded") =>
  renderToStaticMarkup(
    <PropsSection items={items} state={state} matchup={RAYS_AT_BRAVES} />,
  );

describe("#5191 — a rung does not restate the header standing over it", () => {
  test("THE FILED DEFECT: the seven rungs read their threshold and nothing else", () => {
    const html = render(WINDOW_RUNGS, "graded");
    expect(html).toContain(">Over 0.5<");
    expect(html).toContain(">Over 1.5<");
    expect(html).toContain(">Over 2.5<");
    expect(html).not.toContain("runs in the first 5 innings");
  });

  test("CONTROL: the header still says what the rungs stopped saying", () => {
    expect(render(WINDOW_RUNGS, "graded")).toContain("First 5 Innings Total");
  });

  test("CONTROL: every row is still on the page", () => {
    const html = render(WINDOW_RUNGS, "graded");
    expect(html.match(/7 runs — hit/g) ?? []).toHaveLength(3);
  });

  test("in THE SCRIPT too — the words are redundant in every state", () => {
    const html = render(WINDOW_RUNGS, "script");
    expect(html).toContain(">Over 0.5<");
    expect(html).not.toContain("runs in the first 5 innings");
  });

  test("in THE DIVERGENCE too, including rows inside the unchanged fold", () => {
    // Identical mark and current on every leg ⇒ all three fold behind
    // "N unchanged", which is exactly where a long label is easiest to miss.
    const unmoved = WINDOW_RUNGS.map((r) => ({ ...r, settled: false, pregame_mark: 0.5, current: 0.5 }));
    const html = render(unmoved, "divergence");
    expect(html).toContain("3 unchanged");
    expect(html).toContain(">Over 0.5<");
    expect(html).not.toContain("runs in the first 5 innings");
  });

  test("the binary bar row is stripped too — same header, same argument", () => {
    const bars = WINDOW_RUNGS.map((r) => ({ ...r, kind: "binary" as const, settled: false }));
    const html = render(bars, "divergence");
    expect(html).toContain(">Over 0.5<");
    expect(html).not.toContain("runs in the first 5 innings");
  });

  test("CONTROL: `question` still wins on a mark that carries one", () => {
    const bars = WINDOW_RUNGS.map((r) => ({
      ...r,
      kind: "binary" as const,
      settled: false,
      question: "Runs in the first five?",
    }));
    expect(render(bars, "divergence")).toContain("Runs in the first five?");
  });

  test("THE GUARD: the spread loses the window and keeps its handicap", () => {
    const html = render(SPREAD_LEGS, "script");
    expect(html).toContain(">Atlanta -1.5<");
    expect(html).toContain(">Atlanta -2.5<");
    expect(html).toContain(">Tampa Bay -1.5<");
  });

  test("CONTROL: a player family reaches the page exactly as it arrived", () => {
    const html = render(PLAYER_RUNGS, "script");
    for (const item of PLAYER_RUNGS) expect(html).toContain(`>${item.label}<`);
  });

  test("CONTROL: the unnamed group never strips — there is no header to lean on", () => {
    // The golf/combat concept page builds marks with a NUMERIC market id, so no
    // family is recovered, no header is drawn, and the words have nowhere to go.
    const numeric: PropMark[] = WINDOW_RUNGS.map((r, i) => ({ ...r, key: 900 + i }));
    const html = render(numeric, "graded");
    expect(html).toContain("Over 0.5 runs in the first 5 innings");
  });

  test("two families on one page are decided independently", () => {
    const html = render([...WINDOW_RUNGS, ...SPREAD_LEGS], "script");
    expect(html).toContain(">Over 0.5<");
    expect(html).toContain(">Atlanta -1.5<");
  });
});
