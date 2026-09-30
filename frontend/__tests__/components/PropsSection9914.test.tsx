// #9914 — THE DIVERGENCE printed ~41 empty family headers, each over "▸ 2 unchanged".
//
// WHAT A READER SAW. `/events/15321782` (PHI @ ATL, Wild Card G2, LIVE, bottom
// 3rd, 2026-09-30 19:11Z, 390px): about 13 families that moved, then header
// after header carrying nothing but its own drawer ("TREA TURNER: HOME RUNS O/U
// 0.5 · ▸ 2 unchanged"), roughly five phone screens before Bigger Picture.
//
// The fixture is that page's served `props_script` (111 marks), banked from
// `GET /api/events/15321782/game-markets` minutes after the screenshot. The
// component is rendered with it exactly as the event page passes it.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";
import specimen from "../fixtures/props_script_15321782_9914.json";

const MATCHUP = { home: "Atlanta Braves", away: "Philadelphia Phillies" };
const FOLD = "Unchanged props (";
const HEADER = 'font-semibold uppercase tracking-wide text-text-secondary mb-1">';

const served: PropMark[] = specimen.props_script.map((p, i) => ({
  key: p.key ?? i,
  label: p.label,
  pregame_mark: p.pregame_mark ?? null,
  current: p.current ?? null,
  settled: p.settled ?? null,
}));

const render = (items: PropMark[], state: "script" | "divergence" | "graded" = "divergence") =>
  renderToStaticMarkup(<PropsSection items={items} state={state} matchup={MATCHUP} />);

const count = (html: string, needle: string) => html.split(needle).length - 1;

describe("#9914 SHIP: on the served PHI @ ATL page, the wall of empty headers is gone", () => {
  const html = render(served);
  const foldAt = html.indexOf(FOLD);
  const listed = html.slice(0, foldAt);
  const folded = html.slice(foldAt);

  test("one 'Unchanged props (N)' disclosure, after every family that moved", () => {
    expect(count(html, FOLD)).toBe(1);
    expect(foldAt).toBeGreaterThan(-1);
    // It is a closed <details> at the section's foot, so it costs one line.
    expect(html.lastIndexOf("<details", foldAt)).toBeGreaterThan(html.lastIndexOf(HEADER, foldAt));
  });

  test("every family header left in the list has a number in plain sight under it", () => {
    // The defect was a header whose only content is a drawer. Split the listed
    // region at each header: the family's first visible percent must come before
    // its first drawer. Before the fix, 41 chunks failed this on this fixture.
    const families = listed.split(HEADER).slice(1);
    expect(families.length).toBeGreaterThan(0);
    const empty = families.filter((chunk) => {
      const drawer = chunk.indexOf("<details");
      const number = chunk.indexOf("%");
      return drawer > -1 && (number === -1 || number > drawer);
    });
    expect(empty).toEqual([]);
  });

  test("the listed region is short: at most one header per family that moved", () => {
    // 54 questions on this page; the movers are the minority. A regression that
    // stopped folding would put ~50 headers back here.
    expect(count(listed, HEADER)).toBeLessThan(20);
    expect(count(folded, HEADER)).toBeGreaterThan(20);
  });

  test("inside the fold, no second drawer: the reader opened it to see the rows", () => {
    expect(folded).not.toMatch(/\d+ unchanged</);
    // `folded` starts at the summary text, inside the fold's own <details>.
    expect(count(folded, "<details")).toBe(0);
  });

  test("BOTH DIRECTIONS: nothing is dropped — every priced row still renders", () => {
    // Each divergence row prints `pregame → current`. Folding moves rows behind
    // a disclosure; it must not remove one (gotcha #43).
    // #1626: the only rows that leave are the second legs of two-sided
    // complement questions (Over/Under, Yes/No summing to 1 at both ends),
    // counted here independently of the component.
    const pricedMarks = served.filter(
      (m) => m.pregame_mark != null && m.current != null && !m.settled,
    );
    const byQuestion = new Map<string, PropMark[]>();
    for (const m of served) {
      const q = String(m.key).split("|")[0];
      byQuestion.set(q, [...(byQuestion.get(q) ?? []), m]);
    }
    const sides = (a: string, b: string) =>
      [a, b].map((x) => x.toLowerCase()).sort().join("/");
    const complement = (x: number, y: number) => x + y >= 0.99 && x + y <= 1.01;
    const secondLegs = [...byQuestion.values()].filter(
      (legs) =>
        legs.length === 2 &&
        legs.every((l) => l.pregame_mark != null && l.current != null && !l.settled) &&
        ["over/under", "no/yes"].includes(sides(legs[0].label, legs[1].label)) &&
        complement(legs[0].current!, legs[1].current!) &&
        complement(legs[0].pregame_mark!, legs[1].pregame_mark!),
    ).length;
    expect(secondLegs).toBeGreaterThan(40);
    expect(count(html, "→")).toBe(pricedMarks.length - secondLegs);
  });
});

describe("#9914 CONTROLS: what the fold must not touch", () => {
  const MOVER: PropMark = { key: "M: Hits|A: 2+", label: "A: 2+", pregame_mark: 0.4, current: 0.6 };
  const still = (fam: string): PropMark[] => [
    { key: `M: ${fam}|Over`, label: "Over", pregame_mark: 0.3, current: 0.3 },
    { key: `M: ${fam}|Under`, label: "Under", pregame_mark: 0.7, current: 0.7 },
  ];

  test("ONE wholly unchanged family keeps today's per-family drawer", () => {
    const html = render([MOVER, ...still("Home Runs O/U 0.5")]);
    expect(html).not.toContain(FOLD);
    // #1626: one leg per complement pair, so the drawer holds that one row.
    expect(html).toContain("1 unchanged");
  });

  test("TWO wholly unchanged families: both leave the list for the one fold", () => {
    const html = render([MOVER, ...still("Home Runs O/U 0.5"), ...still("Total Bases O/U 1.5")]);
    // #1626: one leg per complement pair — two families, two rows.
    expect(html).toContain(`${FOLD}2)`);
    expect(html).not.toMatch(/\d+ unchanged</);
    // The mover stays above the fold and out of any drawer.
    expect(html.indexOf("A: 2+")).toBeLessThan(html.indexOf("<details"));
  });

  test("a PARTLY moved family stays listed, its moved leg above the fold", () => {
    // Only a family where NOTHING moved leaves. One moved leg keeps the whole
    // family in the list, with its own "1 unchanged" drawer as before.
    const partly: PropMark[] = [
      { key: "M: Strikeouts O/U 6.5|Over", label: "Over", pregame_mark: 0.42, current: 0.45 },
      { key: "M: Strikeouts O/U 6.5|Under", label: "Under", pregame_mark: 0.5, current: 0.5 },
    ];
    const html = render([
      ...partly,
      ...still("Home Runs O/U 0.5"),
      ...still("Total Bases O/U 1.5"),
    ]);
    expect(html.indexOf("Strikeouts O/U 6.5")).toBeLessThan(html.indexOf(FOLD));
    expect(html.indexOf("45%")).toBeLessThan(html.indexOf(FOLD));
    expect(html).toContain("1 unchanged");
    // #1626: the partly moved family (0.45 + 0.50) is not a complement and keeps
    // both legs; the two unchanged complement families keep one each.
    expect(html).toContain(`${FOLD}2)`);
  });

  test("a family with a markless row is not 'unchanged' and stays listed", () => {
    // #5408: a row with no baseline makes no claim about movement.
    const markless: PropMark[] = [
      { key: "M: Strikeouts O/U 6.5|Over", label: "Over", pregame_mark: null, current: 0.45 },
      { key: "M: Strikeouts O/U 6.5|Under", label: "Under", pregame_mark: null, current: 0.55 },
    ];
    const html = render([
      MOVER,
      ...markless,
      ...still("Home Runs O/U 0.5"),
      ...still("Total Bases O/U 1.5"),
    ]);
    expect(html.indexOf("Strikeouts O/U 6.5")).toBeLessThan(html.indexOf(FOLD));
  });

  test("THE SCRIPT and WHAT HIT have no notion of movement and never fold for it", () => {
    for (const state of ["script", "graded"] as const) {
      expect(render(served, state)).not.toContain(FOLD);
    }
  });
});
