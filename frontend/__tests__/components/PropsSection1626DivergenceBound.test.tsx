// #1626 slice 8 — THE DIVERGENCE prints each family's biggest movers and folds
// the rest.
//
// Live Steelers @ Browns (`/events/14780550`, 390px, 2026-10-02 00:2xZ, Q1): the
// section listed every moved row — RUSHING YARDS alone 41 — and the page was
// ~24,000px. The fixture is that page's served `props_script`, banked from
// `GET /api/events/14780550/game-markets` at 00:23:14Z.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark, PropsState } from "../../components/event/PropsSection";
import specimen from "../fixtures/props_divergence_14780550_1626s8.json";

const MATCHUP = { home: "Cleveland Browns", away: "Pittsburgh Steelers" };
const RUSH = "Pittsburgh vs Cleveland: Rushing Yards";

const served: PropMark[] = specimen.props_script.map((p) => ({
  key: p.key,
  label: p.label,
  pregame_mark: p.pregame_mark ?? null,
  current: p.current ?? null,
  graded_result: (p.graded_result ?? null) as PropMark["graded_result"],
  graded_label: p.graded_label ?? null,
  settled: p.settled ?? null,
}));

const render = (items: PropMark[], state: PropsState = "divergence") =>
  renderToStaticMarkup(<PropsSection items={items} state={state} matchup={MATCHUP} />);

/** The markup with every `<details>` removed — what a reader sees unopened. */
function closed(html: string): string {
  let out = "";
  let depth = 0;
  for (const part of html.split(/(<details[^>]*>|<\/details>)/)) {
    if (part.startsWith("<details")) depth++;
    else if (part === "</details>") depth--;
    else if (depth === 0) out += part;
  }
  return out;
}

const summaries = (html: string) =>
  [...html.matchAll(/<summary[^>]*>(.*?)<\/summary>/g)].map((m) => m[1].replace(/<!-- -->/g, ""));

/** One family's slice of the markup: from its header to the next header. */
function familyBlock(html: string, header: string): string {
  const start = html.indexOf(`>${header}<`);
  expect(start).toBeGreaterThan(-1);
  const next = html.indexOf('uppercase tracking-wide text-text-secondary mb-1">', start + header.length);
  return html.slice(start, next === -1 ? undefined : next);
}

const rushRows = served.filter((m) => String(m.key).startsWith(`${RUSH}|`));
const moveOf = (m: PropMark) => Math.abs((m.current ?? 0) - (m.pregame_mark ?? 0));

describe("#1626 slice 8 SHIP: on the live Browns @ Steelers page, each statistic shows its biggest moves first", () => {
  const html = render(served);
  const rush = familyBlock(html, "Rushing Yards");

  test("RUSHING YARDS shows its 5 biggest movers in sight and folds the rest behind 'More props (N)'", () => {
    expect(rushRows.length).toBeGreaterThan(30);
    const top5 = [...rushRows].sort((a, b) => moveOf(b) - moveOf(a)).slice(0, 5);
    const sightRush = closed(rush);
    for (const m of top5) expect(sightRush).toContain(`>${m.label}<`);
    // And the smallest mover is NOT in sight.
    const last = [...rushRows].filter((m) => moveOf(m) > 0.005).sort((a, b) => moveOf(a) - moveOf(b))[0];
    expect(sightRush).not.toContain(`>${last.label}<`);
    const fold = summaries(rush).find((s) => s.startsWith("More props ("));
    expect(fold).toBeDefined();
    expect(Number(/\((\d+)\)/.exec(fold!)![1])).toBeGreaterThan(20);
  });

  test("the whole section a reader sees unopened is a fraction of what it was", () => {
    const before = served.filter((m) => m.pregame_mark != null && m.current != null).length;
    const rows = (h: string) => (h.match(/<div class="flex items-center gap-3[^"]*">/g) ?? []).length;
    expect(rows(closed(html))).toBeLessThan(before / 2);
  });

  test("every mark is still on the page (collapsed, never dropped)", () => {
    for (const m of rushRows) expect(html).toContain(m.label);
  });

  test("the movers' fold sits above the family's 'N unchanged' drawer", () => {
    const fam = summaries(rush);
    const a = fam.findIndex((x) => x.startsWith("More props ("));
    const b = fam.findIndex((x) => / unchanged$/.test(x));
    expect(a).toBeGreaterThan(-1);
    expect(b).toBeGreaterThan(-1);
    expect(a).toBeLessThan(b);
  });
});

const fam = (n: number, family = "X vs Y: Rushing Yards"): PropMark[] =>
  Array.from({ length: n }, (_, i) => ({
    key: `${family}|Player${i}: ${10 + i}+`,
    label: `Player${i}: ${10 + i}+`,
    pregame_mark: 0.5,
    current: 0.5 + 0.01 * (n - i),
  }));

describe("#1626 slice 8 CONTROLS", () => {
  test("a family of 6 moved rows (the bound plus one) renders whole — no fold to hide one line", () => {
    const html = render(fam(6));
    expect(html).not.toContain("More props");
  });

  test("7 moved rows fold 2, and the 5 in sight are the 5 biggest", () => {
    const html = render(fam(7));
    expect(summaries(html)).toContain("More props (2)");
    const sight = closed(html);
    for (const i of [0, 1, 2, 3, 4]) expect(sight).toContain(`Player${i}: ${10 + i}+`);
    for (const i of [5, 6]) expect(sight).not.toContain(`Player${i}: ${10 + i}+`);
  });

  test("THE SCRIPT and WHAT HIT are untouched by the divergence bound", () => {
    expect(render(fam(12), "script")).not.toContain("More props");
  });
});
