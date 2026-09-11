// #5241 — a prop family whose rows ALL fold left a bold header standing over
// nothing but the toggle.
//
// WHAT A READER SAW, in their terms (Braves–Phillies, MLB pre-match, 390px,
// production 2026-09-11 14:12Z):
//
//     OZZIE ALBIES: HOME RUNS O/U 0.5
//       ▶ More props (2)
//
// Two lines to say what one can, five of them in a row on one screen, and
// **27 of 110 families (25%)** across that day's three pre-match MLB pages.
// Alex's D102 is explicit about the cost model — untraded or vanished props go
// behind a collapsed toggle, "present, openable, *taking no real estate when
// closed*". The fold honours that; the header above it did not.
//
// THE FIX IS OPTION 1 OF THE THREE ON THE ISSUE: when the fold is the family's
// whole content, the family name becomes the disclosure's own label. It keeps
// the family grouping (option 2, one section-wide fold, loses it) and it is the
// minimum reading of D102 rather than a new design — which is why it is built
// rather than parked on a ruling. Option 2 stays available if Alex wants it.
//
// RED-FIRST, measured. Run against the parent commit (`PropFamilyBlock` always
// emitting the header div, `ScriptFold` with no `familyName`) this file imports
// and runs — it reaches the behaviour only through rendered output — and scores
// **4 failed, 7 passed of 11**.
//
// The seven that already passed, named, because "7 passed" is only evidence if
// you can say which seven: the five marked CONTROL (the partially-folded family
// keeping both its header and the neutral wording; the header preceding its own
// rows; the null-family fallback; DIVERGENCE; the reachability of the folded
// rows), plus "the fold still names its own count" and "nothing is promoted out
// of the fold" — both true before and after, and both here because this diff
// moves the label and could plausibly have moved a row.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";

/**
 * The shape the defect lives on: a two-leg O/U family with no baseline on
 * EITHER leg (fully folded) sitting beside a family that has one (partly
 * folded). This is the real page — the same player appears twice, once useful
 * and once not.
 */
const TWO_FAMILIES: PropMark[] = [
  { key: "Total Bases|Albies: 2+", label: "Albies: 2+", pregame_mark: 0.61, current: 0.63 },
  { key: "Total Bases|Albies: 3+", label: "Albies: 3+", pregame_mark: null, current: 0.22 },
  { key: "Home Runs|Albies: Over 0.5", label: "Albies: Over 0.5", pregame_mark: null, current: 0.31 },
  { key: "Home Runs|Albies: Under 0.5", label: "Albies: Under 0.5", pregame_mark: null, current: 0.69 },
];

const script = (items: PropMark[]) =>
  renderToStaticMarkup(<PropsSection items={items} state="script" />);

describe("#5241 a fully folded prop family costs one line, not two", () => {
  test("the family name IS the disclosure's label, with the count", () => {
    expect(script(TWO_FAMILIES)).toContain("Home Runs (2)");
  });

  test("no header is left standing above the fold it cannot fill", () => {
    const html = script(TWO_FAMILIES);
    // Anchored to the MARKUP, not to document order. The first draft of this
    // assertion was `indexOf("Home Runs") > indexOf("<details")` and it passed
    // on the parent: the first `<details` on the page is the PARTLY folded
    // family's, which opens before the Home Runs header ever renders. An
    // ordering test over a two-family fixture measures the other family.
    expect(html).not.toContain(">Home Runs</div>"); // the header div
    expect(html).toContain("Home Runs (2)</summary>"); // the disclosure's label
    // And exactly once: relabelled, not duplicated into both places.
    expect(html.match(/Home Runs/g)).toHaveLength(1);
  });

  test("the neutral wording is not printed twice over one family", () => {
    const html = script(TWO_FAMILIES);
    // "More props" survives on the PARTLY folded family (Total Bases, 1 row) and
    // nowhere else — the fully folded one now names itself.
    expect(html.match(/More props/g)).toHaveLength(1);
    expect(html).toContain("More props (1)");
    expect(html).not.toContain("More props (2)");
  });

  test("a section of nothing but fully folded families prints no bare headers", () => {
    // Four families, every one of them baseline-less on both legs — five in a
    // row was what made the section look broken on the live page.
    const allBare: PropMark[] = [
      { key: "Home Runs|Albies: Over 0.5", label: "Albies: Over 0.5", pregame_mark: null, current: 0.31 },
      { key: "Home Runs|Albies: Under 0.5", label: "Albies: Under 0.5", pregame_mark: null, current: 0.69 },
      { key: "Hits + Runs + RBIs|Schwarber: Over 3.5", label: "Schwarber: Over 3.5", pregame_mark: null, current: 0.44 },
      { key: "Hits + Runs + RBIs|Schwarber: Under 3.5", label: "Schwarber: Under 3.5", pregame_mark: null, current: 0.56 },
    ];
    const html = script(allBare);
    expect(html).toContain("Home Runs (2)");
    expect(html).toContain("Hits + Runs + RBIs (2)");
    expect(html).not.toContain("More props");
    // One <details> per family, and no header div for either of them.
    expect(html.match(/<details/g)).toHaveLength(2);
    expect(html).not.toContain(">Home Runs</div>");
    expect(html).not.toContain(">Hits + Runs + RBIs</div>");
  });

  test("the fold still names its own count", () => {
    // Green before and after: the count is what makes the disclosure honest, and
    // moving the label is exactly the kind of edit that drops it.
    const html = script(TWO_FAMILIES);
    expect(html).toContain("(2)");
    expect(html).toContain("(1)");
  });

  test("nothing is promoted out of the fold by the relabel", () => {
    // Green before and after (gotcha #43, the other direction): a folded row
    // still shows the absent-data mark, never its live price.
    const html = script(TWO_FAMILIES);
    expect(html).not.toContain("31%");
    expect(html).not.toContain("69%");
    expect(html).not.toContain("22%");
  });

  // ---- CONTROLS: shapes this diff must leave exactly as they were ----

  test("CONTROL: a partly folded family keeps its header and the neutral label", () => {
    const html = script(TWO_FAMILIES);
    expect(html).toContain("Total Bases");
    expect(html).toContain("More props (1)");
    // Its header still precedes its own listed row.
    expect(html.indexOf("Total Bases")).toBeLessThan(html.indexOf("Albies: 2+"));
    expect(html).toContain("61%");
  });

  test("CONTROL: the folded rows are still present and reachable, not deleted", () => {
    const html = script(TWO_FAMILIES);
    expect(html).toContain("Albies: Over 0.5");
    expect(html).toContain("Albies: Under 0.5");
    expect(html).toContain("Albies: 3+");
  });

  test("CONTROL: a family-less remainder falls back to the neutral wording", () => {
    // `groupByPropFamily` trails family-less items in a `{ name: null }` group.
    // Fully folded, that group has no name to promote — it must print the D111
    // label, never an empty string or the word "null".
    const withRemainder: PropMark[] = [
      { key: "Total Bases|Albies: 2+", label: "Albies: 2+", pregame_mark: 0.61, current: 0.63 },
      { key: "Top American", label: "Top American", pregame_mark: null, current: 0.29 },
    ];
    const html = script(withRemainder);
    expect(html).toContain("More props (1)");
    expect(html).not.toContain("null (1)");
    expect(html).not.toContain(">  (1)");
  });

  test("CONTROL: the single unnamed-group path is untouched", () => {
    // Golf/combat concept pages key marks by numeric market id and take the
    // other render branch entirely — it has no header to remove.
    const unnamed: PropMark[] = [
      { key: 101, label: "Top American", pregame_mark: 0.42, current: 0.44 },
      { key: 102, label: "Top European", pregame_mark: null, current: 0.29 },
    ];
    const html = script(unnamed);
    expect(html).toContain("More props (1)");
    expect(html).toContain("Top European");
  });

  test("CONTROL: THE DIVERGENCE is unaffected — it does not fold on a missing mark", () => {
    const html = renderToStaticMarkup(
      <PropsSection items={TWO_FAMILIES} state="divergence" />,
    );
    expect(html).not.toContain("More props");
    expect(html).not.toContain("Home Runs (2)");
    // The header is back, because nothing folded.
    expect(html.indexOf("Home Runs")).toBeLessThan(html.indexOf("Albies: Over 0.5"));
  });
});
