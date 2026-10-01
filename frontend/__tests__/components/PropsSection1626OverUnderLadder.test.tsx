// #1626 slice 5 — THE SCRIPT prints one row per player O/U ladder.
//
// Browns @ Steelers (`/events/14780550`, scheduled, 390px, 2026-10-01): after
// slices 3 and 4 a player's Over/Under lines were still one FAMILY each — a
// header over a single row — so `MICHAEL PITTMAN JR.: RECEIVING YARDS O/U 59.5 ·
// Under 88%`, `… O/U 69.5 · Under 91%`, `… O/U 79.5 · Under 93%` took six lines
// to ask one question. They are now one family, one row, every line behind its
// disclosure.
//
// The fixture is slice 3's: that page's served `props_script`, banked from
// `GET /api/events/14780550/game-markets` at 06:15Z 10/1.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection, { scriptOverUnderLadders } from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";
import specimen from "../fixtures/props_script_14780550_1626.json";

const MATCHUP = { home: "Pittsburgh Steelers", away: "Cleveland Browns" };

const served: PropMark[] = specimen.props_script.map((p, i) => ({
  key: p.key ?? i,
  label: p.label,
  pregame_mark: p.pregame_mark ?? null,
  current: p.current ?? null,
  settled: p.settled ?? null,
}));

const render = (items: PropMark[], state: "script" | "divergence" | "graded" = "script") =>
  renderToStaticMarkup(<PropsSection items={items} state={state} matchup={MATCHUP} />);

/** Every family header the section prints, in order. */
function headers(html: string): string[] {
  return [...html.matchAll(/uppercase tracking-wide text-text-secondary mb-1">([^<]+)<\/div>/g)].map(
    (m) => m[1],
  );
}

/** The closed ladder rows: subject, threshold, printed percent, "+N more". */
function ladderSummaries(html: string): Array<[string, string, string, string]> {
  return [
    ...html.matchAll(
      /<summary class="flex[^"]*"><span[^>]*>([^<]+)<\/span><span[^>]*>([^<]+)<\/span><span[^>]*>([^<]+)<\/span><span[^>]*>([^<]+)<\/span><\/summary>/g,
    ),
  ].map((m) => [m[1], m[2], m[3], m[4]]);
}

/** The block a family header heads, up to the next header. */
function familyBlock(html: string, name: string): string {
  const at = html.indexOf(`mb-1">${name}</div>`);
  expect(at).toBeGreaterThan(-1);
  const next = html.indexOf('uppercase tracking-wide text-text-secondary mb-1">', at + name.length + 6);
  return html.slice(at, next === -1 ? undefined : next);
}

const ou = (base: string, line: string, under: number, over: number | null, extra: Partial<PropMark> = {}) => {
  const legs: PropMark[] = [
    { key: `${base} O/U ${line}|Under`, label: "Under", pregame_mark: under, current: under, ...extra },
  ];
  if (over != null)
    legs.push({ key: `${base} O/U ${line}|Over`, label: "Over", pregame_mark: over, current: over, ...extra });
  return legs;
};

describe("#1626 SHIP: on the served Browns @ Steelers page, a player's O/U lines are one row", () => {
  const html = render(served);
  const names = headers(html);

  test("Pittman's receiving yards: one family, one row 'Under 59.5 88% +2 more'", () => {
    expect(names).toContain("Michael Pittman Jr.: Receiving Yards O/U");
    expect(names.filter((n) => n.startsWith("Michael Pittman Jr.: Receiving Yards O/U"))).toHaveLength(1);
    expect(ladderSummaries(html)).toContainEqual(["Under", "59.5", "88%", "+2 more"]);
  });

  test("the per-line headers are gone from the page", () => {
    for (const line of ["59.5", "69.5", "79.5"])
      expect(names).not.toContain(`Michael Pittman Jr.: Receiving Yards O/U ${line}`);
    expect(names).not.toContain("Aaron Rodgers: Passing Yards O/U 274.5");
    expect(names).not.toContain("Aaron Rodgers: Passing Yards O/U 299.5");
  });

  test("every line is still on the page, behind the disclosure, saying which line it is", () => {
    const block = familyBlock(html, "Michael Pittman Jr.: Receiving Yards O/U");
    for (const [line, pct] of [
      ["59.5", "88%"],
      ["69.5", "91%"],
      ["79.5", "94%"],
    ]) {
      expect(block).toContain(`>Under ${line}<`);
      expect(block).toContain(`>${pct}<`);
    }
  });

  test("across the page, multi-line O/U families fold to one each", () => {
    const before = render(served, "divergence");
    // The divergence board is unchanged by this slice, so it still counts one
    // header per line — the before figure the script board is measured against.
    const perLine = headers(before).filter((n) => / O\/U \d/.test(n)).length;
    const after = names.filter((n) => / O\/U/.test(n)).length;
    expect(perLine).toBeGreaterThan(after);
    expect(names.filter((n) => / O\/U$/.test(n)).length).toBeGreaterThanOrEqual(10);
  });
});

describe("#1626 controls: what this slice must not touch", () => {
  const html = render(served);
  const names = headers(html);

  test("a player with one O/U line keeps its own family, line in the header", () => {
    expect(names).toContain("Harold Fannin Jr.: Receptions O/U 6.5");
    expect(familyBlock(html, "Harold Fannin Jr.: Receptions O/U 6.5")).not.toContain("<details");
  });

  test("slice 4's threshold ladders are unchanged", () => {
    expect(ladderSummaries(html)).toContainEqual(["Aaron Rodgers", "200+", "58%", "+7 more"]);
  });

  test("THE DIVERGENCE keeps one family per line", () => {
    const div = headers(render(served, "divergence"));
    expect(div).toContain("Michael Pittman Jr.: Receiving Yards O/U 59.5");
    expect(div).toContain("Michael Pittman Jr.: Receiving Yards O/U 69.5");
  });

  test("WHAT HIT keeps one family per line", () => {
    const graded = served.map((p) => ({ ...p, settled: true, current: p.current != null ? (p.current >= 0.5 ? 1 : 0) : null }));
    const what = headers(render(graded, "graded"));
    expect(what.some((n) => n === "Michael Pittman Jr.: Receiving Yards O/U 59.5")).toBe(true);
  });
});

describe("#1626 the rule, on synthetic families", () => {
  const base = "Pat Example: Rushing Yards";

  test("headline: the highest line the Over is favoured at, printing the leg slice 3 kept", () => {
    const items = [...ou(base, "40.5", 0.3, 0.7), ...ou(base, "50.5", 0.45, 0.55), ...ou(base, "60.5", 0.8, 0.2)];
    expect(ladderSummaries(render(items))).toContainEqual(["Over", "50.5", "55%", "+2 more"]);
  });

  test("headline: no line favours the Over → the lowest line", () => {
    const items = [...ou(base, "60.5", 0.8, 0.2), ...ou(base, "70.5", 0.9, 0.1)];
    expect(ladderSummaries(render(items))).toContainEqual(["Under", "60.5", "80%", "+1 more"]);
  });

  test("a pair slice 3 could not reduce (not a complement) stays its own family", () => {
    const items = [...ou(base, "40.5", 0.3, 0.5), ...ou(base, "50.5", 0.45, 0.55), ...ou(base, "60.5", 0.8, 0.2)];
    // One player only, so the section strips the shared "Pat Example: " prefix.
    const names = headers(render(items));
    expect(names).toEqual(["Rushing Yards O/U 40.5", "Rushing Yards O/U"]);
    expect(ladderSummaries(render(items))).toContainEqual(["Over", "50.5", "55%", "+1 more"]);
  });

  test("a settled line never joins", () => {
    const groups = [
      { name: `${base} O/U 40.5`, items: ou(base, "40.5", 0.3, null, { settled: true }) },
      { name: `${base} O/U 50.5`, items: ou(base, "50.5", 0.45, null) },
    ];
    expect(scriptOverUnderLadders(groups).map((g) => g.name)).toEqual([`${base} O/U 40.5`, `${base} O/U 50.5`]);
  });

  test("different statistics for one player are different ladders", () => {
    const groups = [
      { name: "P: Rushing Yards O/U 40.5", items: ou("P: Rushing Yards", "40.5", 0.6, null) },
      { name: "P: Receiving Yards O/U 20.5", items: ou("P: Receiving Yards", "20.5", 0.6, null) },
    ];
    expect(scriptOverUnderLadders(groups).every((g) => g.ladder == null)).toBe(true);
  });

  test("the merged family sits where its first line was; nothing else moves", () => {
    const groups: Array<{ name: string; items: PropMark[] }> = [
      { name: "A", items: [{ key: "A|x", label: "x", pregame_mark: 0.5, current: 0.5 }] },
      { name: `${base} O/U 40.5`, items: ou(base, "40.5", 0.6, null) },
      { name: "B", items: [{ key: "B|y", label: "y", pregame_mark: 0.5, current: 0.5 }] },
      { name: `${base} O/U 50.5`, items: ou(base, "50.5", 0.7, null) },
    ];
    const out = scriptOverUnderLadders(groups);
    expect(out.map((g) => g.name)).toEqual(["A", `${base} O/U`, "B"]);
    expect(out[1].items.map((i) => i.label)).toEqual(["Under 40.5", "Under 50.5"]);
  });
});
