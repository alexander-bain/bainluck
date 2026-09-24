/**
 * #8230 — a finished game's WHAT HIT board printed every question twice, once
 * green and once red.
 *
 * Production, `/events/15316869` (Red Sox 2 – 3 Guardians, Final), 390px,
 * 2026-09-24 14:50Z, `#props-script` read out of the live DOM:
 *
 *   > DAVID FRY: HOME RUNS O/U 0.5
 *   >   Under   0.0 — hit
 *   >   Over    0.0 — miss
 *   > PAYTON TOLLE: STRIKEOUTS O/U 3.5
 *   >   Under   5.0 — miss
 *   >   Over    5.0 — hit
 *   > … 47 verdict chips: 23 green, 24 red
 *
 * The rows below are the `props_script` entries of that payload verbatim (key,
 * label, marks, verdicts), plus hand-built controls where the specimen has no
 * case. Every positive assertion has a control in which both legs MUST survive
 * (gotcha #43): THE SCRIPT, THE DIVERGENCE, a half-settled family inside a live
 * section, a contradictory pair, a ladder and a three-way winner.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import PropsSection from "../../components/event/PropsSection";
import type { PropMark, PropsState } from "../../components/event/PropsSection";
import { gradedPairDecision } from "../../lib/gradedPropPair";

const FRY = "David Fry: Home Runs O/U 0.5";
const TOLLE_35 = "Payton Tolle: Strikeouts O/U 3.5";
const TOLLE_55 = "Payton Tolle: Strikeouts O/U 5.5";
const STORY = "Trevor Story: Home Runs O/U 0.5";

const leg = (
  family: string,
  side: string,
  pregame_mark: number | null,
  graded_result: PropMark["graded_result"],
  graded_label: string | null,
  extra: Partial<PropMark> = {},
): PropMark => ({
  key: `${family}|${side}`,
  label: side,
  pregame_mark,
  current: null,
  graded_result,
  graded_label,
  settled: true,
  ...extra,
});

/** Verbatim from `/api/events/15316869/game-markets` `props_script`, 14:47Z. */
const SPECIMEN: PropMark[] = [
  leg(FRY, "Under", 0.94, "hit", "0.0 — hit"),
  leg(FRY, "Over", 0.06, "miss", "0.0 — miss"),
  leg(TOLLE_35, "Under", null, "miss", "5.0 — miss"),
  leg(TOLLE_35, "Over", null, "hit", "5.0 — hit"),
  leg(TOLLE_55, "Under", 0.555, "hit", "5.0 — hit"),
  leg(TOLLE_55, "Over", 0.4, "miss", "5.0 — miss"),
  leg(STORY, "Under", 0.9, null, null),
  leg(STORY, "Over", 0.1, null, null),
];

function render(items: PropMark[], state: PropsState): string {
  return renderToStaticMarkup(<PropsSection items={items} state={state} />);
}

// `&amp;` last, so an escaped entity is never decoded twice.
const decode = (t: string) => t.replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, "&");

/**
 * The rows of one family in DOM order, each as its children's text joined by
 * " | ". Markup-level on purpose (no DOM here): a family is everything between
 * its header div and the next header; a row is a `flex items-center` div whose
 * children are spans that do not nest.
 */
function familyRows(html: string, family: string): string[] {
  const HEADER = /<div class="text-\[11px\] font-semibold uppercase[^"]*">([^<]*)<\/div>/g;
  const headers = [...html.matchAll(HEADER)];
  const at = headers.findIndex((h) => decode(h[1]) === family);
  if (at < 0) throw new Error(`no family header "${family}"`);
  const from = headers[at].index! + headers[at][0].length;
  const to = at + 1 < headers.length ? headers[at + 1].index! : html.length;
  const block = html.slice(from, to);
  return [...block.matchAll(/<div class="flex items-center gap-3[^"]*">(.*?)<\/div>/g)].map((row) =>
    [...row[1].matchAll(/<span[^>]*>(.*?)<\/span>/g)].map((c) => decode(c[1])).join(" | "),
  );
}

function chips(html: string): { green: number; red: number } {
  const classes = [...html.matchAll(/<span class="([^"]*rounded-full[^"]*)"/g)].map((m) => m[1]);
  return {
    green: classes.filter((c) => c.includes("text-accent-brand")).length,
    red: classes.filter((c) => c.includes("text-accent-danger")).length,
  };
}

describe("#8230 WHAT HIT: one row per two-sided question", () => {
  const html = render(SPECIMEN, "graded");

  it("prints the side the script favoured, with its pregame number, graded", () => {
    expect(familyRows(html, FRY)).toEqual(["Under | 94% | 0.0 — hit"]);
    expect(familyRows(html, TOLLE_55)).toEqual(["Under | 56% | 5.0 — hit"]);
  });

  it("with no pregame number on either side, prints the side that happened and no number", () => {
    expect(familyRows(html, TOLLE_35)).toEqual(["Over | 5.0 — hit"]);
  });

  it("an ungraded question says 'grading unavailable' once, not twice", () => {
    const rows = familyRows(html, STORY);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toBe("Under | Resolved · grading unavailable");
  });

  it("the board is no longer half red by construction", () => {
    // Before: 3 green + 3 red across the three graded pairs (+2 grey). After:
    // one chip per question, coloured by whether the script's side happened.
    expect(chips(html)).toEqual({ green: 3, red: 0 });
  });

  it("an upset reads red: the favoured side that did not happen is the row", () => {
    const upset = [
      leg(TOLLE_55, "Under", 0.4, "hit", "5.0 — hit"),
      leg(TOLLE_55, "Over", 0.6, "miss", "5.0 — miss"),
    ];
    const out = render(upset, "graded");
    expect(familyRows(out, TOLLE_55)).toEqual(["Over | 60% | 5.0 — miss"]);
    expect(chips(out)).toEqual({ green: 0, red: 1 });
  });

  it("the graded number is the number THE SCRIPT printed for that side before the game", () => {
    // #2060's specimen shape: 0.925 / 0.08 is a complement pair carrying vig
    // (sum 1.005). THE SCRIPT normalises it and prints 92; rounding the kept leg
    // on its own would print 93, a number the reader never saw before the game.
    const pair = [
      leg(TOLLE_55, "Under", 0.925, "hit", "5.0 — hit"),
      leg(TOLLE_55, "Over", 0.08, "miss", "5.0 — miss"),
    ];
    const script = familyRows(render(pair, "script"), TOLLE_55);
    const graded = familyRows(render(pair, "graded"), TOLLE_55);
    const underPregame = script.find((r) => r.startsWith("Under"))!.split(" | ")[1];
    expect(graded).toEqual([`Under | ${underPregame} | 5.0 — hit`]);
    expect(underPregame).toBe("92%");
  });
});

describe("#8230 controls — both legs MUST survive", () => {
  it("THE SCRIPT prints both sides (two real numbers)", () => {
    // FRY alone: a markless family (TOLLE_35) folds whole in THE SCRIPT (#5241)
    // and has no header div for `familyRows` to stop at.
    const pre = SPECIMEN.slice(0, 2).map((m) => ({ ...m, settled: false, graded_result: null, graded_label: null }));
    expect(familyRows(render(pre, "script"), FRY)).toEqual(["Under | 94%", "Over | 6%"]);
  });

  it("THE DIVERGENCE prints both sides", () => {
    const live = SPECIMEN.map((m) => ({
      ...m,
      settled: false,
      graded_result: null,
      graded_label: null,
      current: m.pregame_mark,
    }));
    expect(familyRows(render(live, "divergence"), FRY)).toHaveLength(2);
  });

  it("a live section where only ONE leg is settled keeps both", () => {
    const half = [
      leg(FRY, "Under", 0.94, "hit", "0.0 — hit"),
      leg(FRY, "Over", 0.06, null, null, { settled: false, current: 0.05 }),
    ];
    expect(familyRows(render(half, "divergence"), FRY)).toHaveLength(2);
  });

  it("two hits on one question is a data defect and stays visible", () => {
    const both = [leg(FRY, "Under", 0.94, "hit", "0.0 — hit"), leg(FRY, "Over", 0.06, "hit", "1.0 — hit")];
    expect(familyRows(render(both, "graded"), FRY)).toHaveLength(2);
  });

  it("a ladder family (different questions per row) is untouched", () => {
    const ladder: PropMark[] = [
      { key: "Riley Greene: Home Runs|1+", label: "1+", pregame_mark: 0.2, current: null, graded_result: "miss", settled: true },
      { key: "Riley Greene: Home Runs|2+", label: "2+", pregame_mark: 0.03, current: null, graded_result: "miss", settled: true },
    ];
    expect(familyRows(render(ladder, "graded"), "Riley Greene: Home Runs")).toHaveLength(2);
  });
});

describe("gradedPairDecision", () => {
  const L = (key: string, label: string, pregame_mark: number | null, graded_result: "hit" | "miss" | "push" | null) => ({
    key,
    label,
    pregame_mark,
    graded_result,
  });

  it("Yes/No pairs collapse like Over/Under", () => {
    expect(gradedPairDecision([L("a", "No", 0.3, "hit"), L("b", "Yes", 0.7, "miss")])).toEqual({
      keep: "b",
      drop: "a",
      showMark: true,
    });
  });

  it("a dead 50/50 names no favourite: the side that happened, no number", () => {
    expect(gradedPairDecision([L("a", "Over", 0.5, "miss"), L("b", "Under", 0.5, "hit")])).toEqual({
      keep: "b",
      drop: "a",
      showMark: false,
    });
  });

  it("refuses three legs, non-sided labels and mismatched verdicts", () => {
    expect(gradedPairDecision([L("a", "Over", 0.6, "hit"), L("b", "Under", 0.4, "miss"), L("c", "Draw", 0.1, "miss")])).toBeNull();
    expect(gradedPairDecision([L("a", "Red Sox", 0.6, "hit"), L("b", "Guardians", 0.4, "miss")])).toBeNull();
    expect(gradedPairDecision([L("a", "Over", 0.6, "hit"), L("b", "Under", 0.4, null)])).toBeNull();
    expect(gradedPairDecision([L("a", "Over", 0.6, "miss"), L("b", "Under", 0.4, "miss")])).toBeNull();
  });

  it("both pushed is one question, one row", () => {
    expect(gradedPairDecision([L("a", "Over", 0.6, "push"), L("b", "Under", 0.4, "push")])?.keep).toBe("a");
  });
});
