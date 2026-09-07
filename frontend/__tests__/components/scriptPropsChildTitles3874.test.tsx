// #3874 — THE SCRIPT * Props stops printing nine rows that all read the same
// clipped string.
//
// Measured on production, `GET /api/events/15305579/game-markets` (Andreeva v
// Potapova, US Open, status `scheduled`): `props_script` carried 12 marks, NINE
// of which had `label` = the card's own header verbatim plus a remainder the
// phone clipped away. Nine different percentages, one repeated string, nothing
// on screen saying what any number was about.
//
// The payload below is that response's `props_script` array, byte-for-byte.
//
// The rows are dropped rather than de-prefixed, which is the decision
// `otherMarketGroups.buildMarketSection` already made for the SAME row class on
// the Additional Markets card one section lower on the SAME page: the text names
// a question and no side of it, and the side is not in the wire to recover.

import { readFileSync } from "fs";
import { join } from "path";

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import PropsSection, { type PropMark } from "@/components/event/PropsSection";
import { isChildTitleMark } from "@/lib/propFamily";

/** Verbatim `props_script` from the production response. */
const WIRE = [
    {
      "key": "US Open WTA: Mirra Andreeva vs Anastasia Potapova|Mirra Andreeva",
      "label": "Mirra Andreeva",
      "pregame_mark": 0.825,
      "current": 0.84,
      "graded_result": null,
      "graded_label": null
    },
    {
      "key": "US Open WTA: Mirra Andreeva vs Anastasia Potapova|US Open WTA: Mirra Andreeva vs Anastasia Potapova Set 1 Winner",
      "label": "US Open WTA: Mirra Andreeva vs Anastasia Potapova Set 1 Winner",
      "pregame_mark": 0.75,
      "current": 0.795,
      "graded_result": null,
      "graded_label": null
    },
    {
      "key": "US Open WTA: Mirra Andreeva vs Anastasia Potapova|US Open WTA: Mirra Andreeva vs Anastasia Potapova Set Handicap +/-1.5",
      "label": "US Open WTA: Mirra Andreeva vs Anastasia Potapova Set Handicap +/-1.5",
      "pregame_mark": 0.64,
      "current": 0.645,
      "graded_result": null,
      "graded_label": null
    },
    {
      "key": "US Open WTA: Mirra Andreeva vs Anastasia Potapova|US Open WTA: Mirra Andreeva vs Anastasia Potapova Set 2 Winner",
      "label": "US Open WTA: Mirra Andreeva vs Anastasia Potapova Set 2 Winner",
      "pregame_mark": 0.76,
      "current": 0.645,
      "graded_result": null,
      "graded_label": null
    },
    {
      "key": "US Open WTA: Mirra Andreeva vs Anastasia Potapova|US Open WTA: Mirra Andreeva vs Anastasia Potapova Total Sets: O/U 2.5",
      "label": "US Open WTA: Mirra Andreeva vs Anastasia Potapova Total Sets: O/U 2.5",
      "pregame_mark": 0.28,
      "current": 0.285,
      "graded_result": null,
      "graded_label": null
    },
    {
      "key": "US Open WTA: Mirra Andreeva vs Anastasia Potapova|US Open WTA: Mirra Andreeva vs Anastasia Potapova Game Spread +/-5.5",
      "label": "US Open WTA: Mirra Andreeva vs Anastasia Potapova Game Spread +/-5.5",
      "pregame_mark": 0.515,
      "current": 0.285,
      "graded_result": null,
      "graded_label": null
    },
    {
      "key": "US Open WTA: Mirra Andreeva vs Anastasia Potapova|US Open WTA: Mirra Andreeva vs Anastasia Potapova Set 1 O/U 8.5",
      "label": "US Open WTA: Mirra Andreeva vs Anastasia Potapova Set 1 O/U 8.5",
      "pregame_mark": 0.585,
      "current": 0.285,
      "graded_result": null,
      "graded_label": null
    },
    {
      "key": "US Open WTA: Mirra Andreeva vs Anastasia Potapova|US Open WTA: Mirra Andreeva vs Anastasia Potapova Set 1 O/U 9.5",
      "label": "US Open WTA: Mirra Andreeva vs Anastasia Potapova Set 1 O/U 9.5",
      "pregame_mark": 0.415,
      "current": 0.285,
      "graded_result": null,
      "graded_label": null
    },
    {
      "key": "US Open WTA: Mirra Andreeva vs Anastasia Potapova|US Open WTA: Mirra Andreeva vs Anastasia Potapova Set 1 O/U 10.5",
      "label": "US Open WTA: Mirra Andreeva vs Anastasia Potapova Set 1 O/U 10.5",
      "pregame_mark": 0.205,
      "current": 0.205,
      "graded_result": null,
      "graded_label": null
    },
    {
      "key": "US Open WTA: Mirra Andreeva vs Anastasia Potapova|US Open WTA: Mirra Andreeva vs Anastasia Potapova Match O/U 21.5",
      "label": "US Open WTA: Mirra Andreeva vs Anastasia Potapova Match O/U 21.5",
      "pregame_mark": 0.415,
      "current": 0.205,
      "graded_result": null,
      "graded_label": null
    },
    {
      "key": "US Open WTA: Mirra Andreeva vs Anastasia Potapova|Yes",
      "label": "Yes",
      "pregame_mark": 0.825,
      "current": 0.85,
      "graded_result": null,
      "graded_label": null
    },
    {
      "key": "US Open WTA: Mirra Andreeva vs Anastasia Potapova|No",
      "label": "No",
      "pregame_mark": 0.825,
      "current": 0.845,
      "graded_result": null,
      "graded_label": null
    }
  ] as Array<{
  key: string;
  label: string;
  pregame_mark: number | null;
  current: number | null;
  graded_result: "hit" | "miss" | "push" | null;
  graded_label: string | null;
}>;

const MATCH = "US Open WTA: Mirra Andreeva vs Anastasia Potapova";

/** The mapping `app/events/[id]/page.tsx` applies, filter included. */
function buildMarks(): PropMark[] {
  return WIRE.map((p, i): PropMark => ({
    key: p.key ?? i,
    label: p.label,
    pregame_mark: p.pregame_mark ?? null,
    current: p.current ?? null,
  })).filter((mark) => !isChildTitleMark(mark));
}

/** Visible text of the rendered card, one entry per text node. */
function renderedText(
  items: PropMark[],
  state: "script" | "divergence" = "script",
): string[] {
  const html = renderToStaticMarkup(<PropsSection items={items} state={state} />);
  return html
    .replace(/<[^>]+>/g, "\n")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

describe("THE SCRIPT props, real US Open wire (#3874)", () => {
  test("BEFORE: the unfiltered payload really does print nine repeats", () => {
    // The positive control. Without it, a filter that dropped nothing would
    // still pass every assertion below by accident.
    const unfiltered: PropMark[] = WIRE.map((p, i) => ({
      key: p.key ?? i,
      label: p.label,
      pregame_mark: p.pregame_mark ?? null,
      current: p.current ?? null,
    }));
    const repeats = renderedText(unfiltered).filter(
      (line) => line.startsWith(MATCH) && line !== MATCH,
    );
    expect(repeats).toHaveLength(9);
  });

  test("AFTER: no row restates the card's own header", () => {
    const rows = renderedText(buildMarks()).filter(
      (line) => line.startsWith(MATCH) && line !== MATCH,
    );
    expect(rows).toEqual([]);
  });

  test("the rows that carry an answer survive", () => {
    const text = renderedText(buildMarks());
    // The headline outcome is the whole point of the card and must never be
    // collateral damage of the filter.
    expect(text).toContain("Mirra Andreeva");
    expect(buildMarks()).toHaveLength(3);
  });

  test("exactly the nine child titles are dropped, named one by one", () => {
    const dropped = WIRE.filter((p) => isChildTitleMark(p)).map((p) =>
      p.label.slice(MATCH.length).trim(),
    );
    expect(dropped).toEqual([
      "Set 1 Winner",
      "Set Handicap +/-1.5",
      "Set 2 Winner",
      "Total Sets: O/U 2.5",
      "Game Spread +/-5.5",
      "Set 1 O/U 8.5",
      "Set 1 O/U 9.5",
      "Set 1 O/U 10.5",
      "Match O/U 21.5",
    ]);
  });

  test("the row that disagrees with the sided row above it is gone", () => {
    // `Set 2 Winner` is priced 0.645 here and 0.775 in the SAME response's
    // `other[]`, which the Additional Markets card renders as "Andreeva wins
    // Set 2 - 78%": one question, two numbers, 13 points apart.
    //
    // Pregame the split is masked, because THE SCRIPT renders `pregame_mark`
    // (0.76 -> 76%) rather than `current`. It becomes visible the moment the
    // match goes live and the section switches to divergence — which is why
    // this row must not be on the page in EITHER state, not just the live one.
    expect(renderedText(buildMarks(), "script").join("|")).not.toContain("Set 2 Winner");
    expect(renderedText(buildMarks(), "divergence").join("|")).not.toContain("Set 2 Winner");
  });

  test("the live state is the one that showed the 13-point split — pin it", () => {
    // Positive control for the test above: UNFILTERED and live, the card really
    // does print 65% for a question the card above it prices at 78%. Without
    // this, "not.toContain" could pass because the state never renders anything.
    //
    // 65, not 64: `0.645 * 100` is exactly 64.5 and rounds up. The 64% row on
    // the production screenshot is `Set Handicap +/-1.5` (pregame 0.64), a
    // DIFFERENT row that happens to sit two lines above.
    const unfiltered: PropMark[] = WIRE.map((p, i) => ({
      key: p.key ?? i,
      label: p.label,
      pregame_mark: p.pregame_mark ?? null,
      current: p.current ?? null,
    }));
    const live = renderedText(unfiltered, "divergence");
    const i = live.findIndex((line) => line.endsWith("Set 2 Winner"));
    expect(i).toBeGreaterThanOrEqual(0);
    expect(live.slice(i, i + 4).join(" ")).toContain("65%");
  });
});

describe("the page is actually wired to the filter (#3874)", () => {
  test("the props_script mapping in app/events/[id]/page.tsx filters child titles", () => {
    // Guards the gap the tests above cannot see: they prove the FILTER is right,
    // not that the page still calls it.
    const src = readFileSync(
      join(process.cwd(), "app", "events", "[id]", "page.tsx"),
      "utf8",
    );
    expect(src).toContain("isChildTitleMark");
    expect(src).toMatch(/\.filter\(\(mark\) => !isChildTitleMark\(mark\)\)/);
  });
});
