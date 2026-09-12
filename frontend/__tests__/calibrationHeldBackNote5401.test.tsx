// CAL-P1136 / #5401 — the accuracy page's one honest line about the groups it
// is NOT grading.
//
// klm = A (Alex, 2026-09-12): three source-and-category groups — kalshi/golf,
// kalshi/entertainment, polymarket/golf — are built on Kalshi opening prices
// that no order book ever stood behind, so they are held back from the score
// and named on the page until the prices are repaired and the groups recounted.
//
// WHAT THIS FILE IS FOR, given the backend already has a guard. The server
// guard (backend/tests/test_calibration_held_back_cells_5401.py) proves the
// cells leave the NEEDLE. It cannot prove a reader is told. These two claims
// have failed apart before — a payload can carry a perfectly honest field that
// no surface renders — so the render is asserted against the real props.
//
// The assertions are deliberately about BEHAVIOUR AT THE BOUNDARIES rather than
// about copy: the exact sentence is Alex's to change, but "renders nothing when
// nothing is held back" and "names every cell it was given" are the properties
// that make the line honest, and those are pinned.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import CalibrationHeldBackNote, {
  joinNames,
} from "../components/CalibrationHeldBackNote";

const SOURCE_LABELS: Record<string, string> = {
  kalshi: "Kalshi",
  polymarket: "Polymarket",
};
const sourceLabel = (s: string) => SOURCE_LABELS[s] ?? s;
const categoryLabel = (c: string) =>
  c.charAt(0).toUpperCase() + c.slice(1);

/** The three cells exactly as the served scorecard orders them (n desc). */
const THREE = [
  { cell: "kalshi/golf", source: "kalshi", category: "golf", n: 22191 },
  { cell: "polymarket/golf", source: "polymarket", category: "golf", n: 4362 },
  {
    cell: "kalshi/entertainment",
    source: "kalshi",
    category: "entertainment",
    n: 3866,
  },
];

const render = (cells: typeof THREE | null | undefined) =>
  renderToStaticMarkup(
    <CalibrationHeldBackNote
      cells={cells}
      sourceLabel={sourceLabel}
      categoryLabel={categoryLabel}
    />
  );

describe("the held-back line", () => {
  it("names every group it was handed, in the payload's own order", () => {
    const html = render(THREE);
    expect(html).toContain("Kalshi Golf");
    expect(html).toContain("Polymarket Golf");
    expect(html).toContain("Kalshi Entertainment");
    // The order is the server's (largest first), not re-sorted here — two
    // surfaces sorting the same list differently is how they start disagreeing.
    expect(html.indexOf("Kalshi Golf")).toBeLessThan(
      html.indexOf("Polymarket Golf")
    );
  });

  it("says why, in the words the ruling used", () => {
    const html = render(THREE);
    expect(html).toContain("held back while we repair prices we should never have stored");
  });

  it("renders NOTHING when nothing is held back", () => {
    // The state the day #5401 lands. The section must disappear on its own,
    // with no follow-up ship to remove it — otherwise an empty honest line
    // outlives the thing it was honest about.
    expect(render([])).toBe("");
  });

  it("renders NOTHING on an unscored board", () => {
    // `null` is the unavailable scorecard; `undefined` is a fallback payload
    // banked before the field existed. Neither is "nothing is held back", and
    // neither may render a claim.
    expect(render(null)).toBe("");
    expect(render(undefined)).toBe("");
  });

  it("publishes the counts a probe needs as data, not as prose", () => {
    // Notice 34: the numbers exist for the rail, and they do not appear in the
    // sentence a reader reads.
    const html = render(THREE);
    expect(html).toContain('data-held-back-count="3"');
    expect(html).toContain(
      'data-held-back-cells="kalshi/golf,polymarket/golf,kalshi/entertainment"'
    );
    expect(html).toContain('data-held-back-outcomes="30419"');

    // The diagnostic numbers are NOT in the sentence. Asserted by COUNTING
    // occurrences rather than by stripping tags: a `replace(/<[^>]*>/g, "")`
    // here reads to CodeQL as an incomplete HTML sanitizer (it flagged exactly
    // that, high severity, on the first push of this file), and counting is the
    // stronger claim anyway — "appears once, in the attribute" rather than
    // "does not appear in whatever my regex decided the text was".
    const occurrences = (needle: string) => html.split(needle).length - 1;
    expect(occurrences("30419")).toBe(1); // the data attribute, and nowhere else
    expect(occurrences("22191")).toBe(0); // a per-cell count reaches no surface
    expect(occurrences("</strong> are held back")).toBe(1);
  });

  it("reads as a sentence for one group as well as three", () => {
    // Singular/plural is the kind of thing that only breaks once the repair
    // lands partially — which is exactly when nobody is looking at this line.
    const one = render([THREE[0]]);
    expect(one).toContain("Kalshi Golf</strong> is held back");
    expect(render(THREE)).toContain("</strong> are held back");
  });

  it("uses the payload's source vocabulary rather than the raw key", () => {
    // CAL-P1025: a source this page has no opinion about arrives named. A raw
    // machine key reaching a reader is the defect notice 33 is about.
    const html = render(THREE);
    expect(html).not.toContain("kalshi Golf");
    expect(html).not.toContain("polymarket Golf");
  });
});

describe("joinNames", () => {
  it("joins the way a person writes a list", () => {
    expect(joinNames([])).toBe("");
    expect(joinNames(["A"])).toBe("A");
    expect(joinNames(["A", "B"])).toBe("A and B");
    expect(joinNames(["A", "B", "C"])).toBe("A, B and C");
  });
});
