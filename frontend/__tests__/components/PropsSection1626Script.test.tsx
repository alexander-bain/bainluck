// #1626 slice 3 — THE SCRIPT prints one row per two-sided question.
//
// Browns @ Steelers (`/events/14780550`, scheduled, 390px, 2026-10-01): THE
// SCRIPT printed every O/U pair twice — `AARON RODGERS: PASSING YARDS O/U 274.5`
// as `Under 89%` over `Over 11%` — 48 such pairs on a page 20,059px tall.
// Slice 1 (PR #9950) made THE DIVERGENCE print one leg; this is the same rule
// for the pregame board, keeping the leg the script favours by the number it
// prints.
//
// The fixture is that page's served `props_script`, banked from
// `GET /api/events/14780550/game-markets` at 06:15Z 10/1.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";
import specimen from "../fixtures/props_script_14780550_1626.json";

const MATCHUP = { home: "Pittsburgh Steelers", away: "Cleveland Browns" };
const HEADER = 'font-semibold uppercase tracking-wide text-text-secondary mb-1">';

const served: PropMark[] = specimen.props_script.map((p, i) => ({
  key: p.key ?? i,
  label: p.label,
  pregame_mark: p.pregame_mark ?? null,
  current: p.current ?? null,
  settled: p.settled ?? null,
}));

const render = (items: PropMark[], state: "script" | "divergence" | "graded" = "script") =>
  renderToStaticMarkup(<PropsSection items={items} state={state} matchup={MATCHUP} />);

/** The family block printed under one header (it ends where its last row,
 *  its row list and the block close together). */
function familyChunk(html: string, family: string): string {
  const at = html.indexOf(`${HEADER}${family}<`);
  if (at === -1) return "";
  const end = html.indexOf("</span></div></div></div>", at);
  return html.slice(at, end === -1 ? undefined : end + "</span>".length);
}

/** The row labels printed under one family header. */
function familyRows(html: string, family: string): string[] {
  return [...familyChunk(html, family).matchAll(/line-clamp-2">([^<]+)<\/span>/g)].map((m) => m[1]);
}

const pair = (fam: string, over: number | null, under: number | null): PropMark[] => [
  { key: `P: ${fam}|Over`, label: "Over", pregame_mark: over, current: over },
  { key: `P: ${fam}|Under`, label: "Under", pregame_mark: under, current: under },
];

describe("#1626 SHIP: on the served Browns @ Steelers page, THE SCRIPT prints one row per O/U question", () => {
  const html = render(served);

  test("AARON RODGERS: PASSING YARDS O/U 274.5 prints Under only — 89%, the side the script favours", () => {
    expect(familyRows(html, "Aaron Rodgers: Passing Yards O/U 274.5")).toEqual(["Under"]);
    expect(familyChunk(html, "Aaron Rodgers: Passing Yards O/U 274.5")).toContain(">89%<");
  });

  test("every complement O/U and Yes/No family prints exactly one row", () => {
    const fams = new Map<string, PropMark[]>();
    for (const m of served) {
      const fam = String(m.key).split("|")[0];
      fams.set(fam, [...(fams.get(fam) ?? []), m]);
    }
    const twoSided = [...fams.entries()].filter(([, legs]) => {
      const labels = legs.map((l) => l.label.toLowerCase()).sort().join("/");
      const total = legs.reduce((n, l) => n + (l.current ?? NaN), 0);
      return (
        legs.length === 2 &&
        (labels === "over/under" || labels === "no/yes") &&
        legs.every((l) => l.pregame_mark != null) &&
        total >= 0.99 &&
        total <= 1.01
      );
    });
    expect(twoSided.length).toBe(48);
    const printed = twoSided.map(([fam]) => familyRows(html, fam));
    const located = printed.filter((rows) => rows.length > 0);
    expect(located.length).toBeGreaterThan(40);
    for (const rows of located) expect(rows).toHaveLength(1);
  });
});

describe("#1626 slice 3 CONTROLS", () => {
  test("the kept leg is the script's favourite, whichever side it is", () => {
    const html = render(pair("Hits O/U 0.5", 0.72, 0.28));
    expect(familyRows(html, "P: Hits O/U 0.5")).toEqual(["Over"]);
    expect(html).toContain(">72%<");
  });

  test("a non-complement pair keeps both legs", () => {
    expect(familyRows(render(pair("Hits O/U 0.5", 0.55, 0.52)), "P: Hits O/U 0.5")).toHaveLength(2);
  });

  test("a pair with an unmarked leg is left whole (the unmarked leg folds, D102)", () => {
    const legs = pair("Hits O/U 0.5", 0.6, 0.4);
    legs[1] = { ...legs[1], pregame_mark: null };
    const html = render(legs);
    expect(html).toContain(">Over<");
    expect(html).toContain(">Under<");
  });

  test("a leg with a pending_label leaves its family whole", () => {
    const legs = pair("Hits O/U 0.5", 0.6, 0.4);
    legs[1] = { ...legs[1], pending_label: "Void" } as PropMark;
    expect(render(legs)).toContain(">Under<");
  });

  test("a ladder family is untouched", () => {
    const ladder: PropMark[] = [
      { key: "M: Passing Yards|A: 150+", label: "A: 150+", pregame_mark: 0.8, current: 0.8 },
      { key: "M: Passing Yards|A: 175+", label: "A: 175+", pregame_mark: 0.2, current: 0.2 },
    ];
    expect(familyRows(render(ladder), "M: Passing Yards")).toHaveLength(2);
  });

  test("WHAT HIT and THE DIVERGENCE are unchanged by this rule (their own one-leg rules still decide)", () => {
    const legs: PropMark[] = [
      { key: "P: Hits O/U 0.5|Over", label: "Over", pregame_mark: 0.4, current: 0.72 },
      { key: "P: Hits O/U 0.5|Under", label: "Under", pregame_mark: 0.6, current: 0.28 },
    ];
    // DIVERGENCE keeps the PREGAME favourite (Under), not the script's live one.
    expect(familyRows(render(legs, "divergence"), "P: Hits O/U 0.5")).toEqual(["Under"]);
  });
});
