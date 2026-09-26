/**
 * #8833 — a finished MLB game's WHAT HIT had no bound.
 *
 * Production, `/events/15318645` (Astros @ Athletics, Final 6–5), 390px,
 * 2026-09-26 14:40Z: `#props-script` was 43,828px of a 49,402px page. It held
 * 549 graded rows and no disclosure at all, under a rail that already
 * summarised them as "5 of 234". The payload carries 1,051 `props_script`
 * entries: 401 families, 724 rows after #8230's pairing. One family, the
 * venue's `1+ … 5+` ladder for "Houston vs A's: Hits + Runs + RBIs", held 90
 * rows by itself.
 *
 * The fixture has the specimen's shape: two-legged O/U families (one row each
 * after #8230) with a big single-sided ladder family second. Keys and labels
 * are written the way that payload writes them.
 *
 * What is guarded, both directions (gotcha #43):
 *   - FLOOD: the rows a reader sees without opening anything are bounded (6
 *     families, at most 3 rows each), and every folded row is still in the DOM
 *     behind a `<details>` whose summary states its count.
 *   - CONTROLS: a WHAT HIT at the caps plus one (7 families, 4-row family) is
 *     unchanged, with no disclosure drawn to hide a single line. THE SCRIPT and
 *     THE DIVERGENCE get no new fold from the same flood.
 *
 * RED-FIRST, measured: against the parent commit this file scores 3 failed,
 * 4 passed of 7. The three flood assertions fail (70 visible rows, no
 * summaries). The four controls pass, as they must.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import PropsSection from "../../components/event/PropsSection";
import type { PropMark, PropsState } from "../../components/event/PropsSection";

const LADDER = "Houston vs A's: Hits + Runs + RBIs";

const ouFamily = (i: number): string => `Player${i} Surname: Hits O/U 0.5`;

/** One two-sided O/U question, graded. Over hit, the script favoured Over. */
const ouLegs = (i: number, extra: Partial<PropMark> = {}): PropMark[] => [
  {
    key: `${ouFamily(i)}|Over`,
    label: "Over",
    pregame_mark: 0.6,
    current: null,
    graded_result: "hit",
    graded_label: "1.0 — hit",
    settled: true,
    ...extra,
  },
  {
    key: `${ouFamily(i)}|Under`,
    label: "Under",
    pregame_mark: 0.4,
    current: null,
    graded_result: "miss",
    graded_label: "1.0 — miss",
    settled: true,
    ...extra,
  },
];

/** One rung of the venue's single-sided ladder family. */
const rung = (i: number, extra: Partial<PropMark> = {}): PropMark => ({
  key: `${LADDER}|Ladderman${i}: 1+`,
  label: `Ladderman${i}: 1+`,
  pregame_mark: 0.7,
  current: null,
  graded_result: i % 2 ? "hit" : "miss",
  graded_label: i % 2 ? "2.0 — hit" : "0.0 — miss",
  settled: true,
  ...extra,
});

const range = (n: number) => Array.from({ length: n }, (_, i) => i);

/** 40 O/U questions with a 30-rung ladder second: 41 families, 70 WHAT HIT rows. */
function flood(extra: Partial<PropMark> = {}): PropMark[] {
  return [
    ...ouLegs(0, extra),
    ...range(30).map((i) => rung(i, extra)),
    ...range(39).flatMap((i) => ouLegs(i + 1, extra)),
  ];
}

function render(items: PropMark[], state: PropsState): string {
  return renderToStaticMarkup(<PropsSection items={items} state={state} />);
}

const ROW = /<div class="flex items-center gap-3[^"]*">/g;
const rowCount = (html: string) => [...html.matchAll(ROW)].length;

/** The markup with every `<details>` removed, nested ones included — what a
 *  reader sees before opening anything. */
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

describe("#8833 WHAT HIT is bounded", () => {
  const html = render(flood(), "graded");

  it("a reader sees 6 families and at most 3 rows of each before opening anything", () => {
    // Family 1: one O/U row. Family 2: the ladder, first 3 rungs. Families
    // 3–6: one O/U row each. 1 + 3 + 4 = 8, against 70 before.
    expect(rowCount(closed(html))).toBe(8);
    const visible = closed(html);
    expect(visible).toContain("Ladderman0: 1+");
    expect(visible).toContain("Ladderman2: 1+");
    expect(visible).not.toContain("Ladderman3: 1+");
  });

  it("every folded row is still in the DOM, behind a disclosure that states its count", () => {
    expect(rowCount(html)).toBe(70);
    for (const i of range(30)) expect(html).toContain(`Ladderman${i}: 1+`);
    // The ladder's own fold (27 = 30 − 3), then the section's (35 = 39 O/U
    // families − the 4 that fit in the first six).
    expect(summaries(html)).toEqual(["More props (27)", "More props (35)"]);
  });

  it("the folded families keep their headers inside the section's disclosure", () => {
    expect(closed(html)).toContain(ouFamily(1));
    expect(closed(html)).not.toContain(ouFamily(39));
    expect(html).toContain(ouFamily(39));
  });
});

describe("#8833 controls: what the bound must NOT touch", () => {
  it("7 families (the cap plus one) render whole, with no disclosure for a single family", () => {
    const items = range(7).flatMap((i) => ouLegs(i));
    const html = render(items, "graded");
    expect(html).not.toContain("<details");
    expect(rowCount(html)).toBe(7);
  });

  it("a 4-row family (the cap plus one) renders whole, with no disclosure for a single row", () => {
    const html = render(range(4).map((i) => rung(i)), "graded");
    expect(html).not.toContain("<details");
    expect(rowCount(html)).toBe(4);
  });

  it("THE SCRIPT gets no new fold from the same flood", () => {
    const html = render(flood({ graded_result: null, graded_label: null, settled: null }), "script");
    expect(html).not.toContain("<details");
  });

  it("THE DIVERGENCE gets no new fold from the same flood", () => {
    // Every row moved, so its own "N unchanged" fold has nothing to take.
    const items = flood({ graded_result: null, graded_label: null, settled: null }).map((m) => ({
      ...m,
      current: (m.pregame_mark ?? 0) + 0.1,
    }));
    const html = render(items, "divergence");
    expect(html).not.toContain("<details");
  });
});
