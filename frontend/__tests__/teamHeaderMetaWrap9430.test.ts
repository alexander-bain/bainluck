/**
 * #9430 — the team header split its record across two lines at phone width.
 *
 * `/sport/football/nfl/team/denver-broncos` at 390px read:
 *
 *     2-      American Football      #3 in AFC
 *     1       Conference             West
 *
 * The meta row (record · conference · rank) was `flex items-center gap-3`
 * with no wrap, so flex SHRANK all three spans into the ~290px column and each
 * one broke inside itself. Every NFL team carries a long conference name.
 *
 * The page fetches on mount, so — as #5652/#5669 do for this file — the guard
 * reads the source. It asserts both halves: the row wraps between items, AND
 * the record and rank refuse to break inside. Either half alone ships a
 * version of the defect (wrap without nowrap still lets a squeezed `2-1`
 * split when it lands on a line with a long neighbour; nowrap without wrap
 * overflows the card).
 */

import fs from "node:fs";
import path from "node:path";

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "app/sport/[sport]/[league]/team/[team]/page.tsx"),
  "utf8",
);

function metaRowClass(): string {
  // The row is the div that directly holds the record span.
  const i = SRC.indexOf("{team.record && <span");
  expect(i).toBeGreaterThan(-1);
  const open = SRC.lastIndexOf("<div className=\"", i);
  const end = SRC.indexOf("\"", open + '<div className="'.length);
  return SRC.slice(open + '<div className="'.length, end);
}

describe("#9430 — the team header meta row wraps whole items", () => {
  test("the row is a wrapping flex row", () => {
    const cls = metaRowClass().split(/\s+/);
    expect(cls).toContain("flex");
    expect(cls).toContain("flex-wrap");
  });

  test("the record never breaks inside ('2-' over '1')", () => {
    expect(SRC).toMatch(/\{team\.record && <span className="[^"]*\bwhitespace-nowrap\b[^"]*">\{team\.record\}<\/span>\}/);
  });

  test("both rank spellings never break inside ('#3 in AFC' over 'West')", () => {
    // The JSX text, not the comment above it that also says "in conference".
    const conf = SRC.indexOf(")} in conference");
    const div = SRC.indexOf('" in division"');
    expect(conf).toBeGreaterThan(-1);
    expect(div).toBeGreaterThan(-1);
    for (const at of [conf, div]) {
      const span = SRC.lastIndexOf("<span", at);
      const tag = SRC.slice(span, SRC.indexOf(">", span) + 1);
      expect(tag).toContain("whitespace-nowrap");
    }
  });
});
