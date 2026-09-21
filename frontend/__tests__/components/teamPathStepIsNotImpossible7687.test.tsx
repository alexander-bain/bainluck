/**
 * #7687 — A TEAM PAGE'S CHAMPIONSHIP-PATH STEP STOPS PRINTING 0% FOR A CLUB
 * THAT CAN STILL GET THERE.
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * `GET /api/teams/{id}` for all 30 MLB clubs, 2026-09-21. Twenty-three of the
 * thirty carried a `championship_path` step whose served probability was
 * strictly inside (0, 1) and which this component printed as `0%`:
 *
 *     Baltimore, Kansas City, the Angels, Miami, the Mets, Washington
 *                                     Division   0.001   ->  0%
 *     Boston, Toronto                 Division   0.003   ->  0%
 *     Miami                           Championship 0.0008 -> 0%
 *     …and fourteen more
 *
 * `0%` does not read as "unlikely" — it reads as "cannot happen". Each of
 * these numbers is a LINK to the very market pricing the outcome as possible,
 * so the step told a reader an outcome was impossible and then offered to sell
 * them the market on it.
 *
 * This is UX-P046's defect, in a component UX-P046 never reached: the step was
 * a bare `Math.round(p * 100)`. The rule has been the site's since 2026-08-10
 * and is stated once in `lib/probabilityDisplay` — rounding may never move a
 * probability across a boundary it is not on.
 *
 * ═══ THE BAR IS NOT THE NUMBER (gotcha: two uses, one expression) ═══
 *
 * `pct` fed BOTH the printed text and the progress bar's width. Only the text
 * is a claim; a 0.3% bar rounded to a 0px-wide sliver misleads nobody. So the
 * rounding stays for the width and the print is routed, and the control below
 * pins that split — a fix that routed the width too would be drawing a 1%-wide
 * bar for a 0.001 step, which is a different wrong picture.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * "No step prints 0%" is passed perfectly by a component that prints nothing,
 * and by one that has started printing an em dash over real numbers. So every
 * suppression arm is paired with a control: ordinary steps keep their plain
 * integers, a genuinely absent probability still renders the dash it always
 * did, and a served 0 — which the payload is entitled to mean — still prints
 * `0%`.
 *
 * Markers are asserted on RAW MARKUP: React escapes `<` to `&lt;`, and that
 * one character is the whole difference between "unlikely" and "impossible".
 *
 *   npx jest --testPathPatterns=teamPathStepIsNotImpossible7687
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { TeamChampionshipPath } from "../../components/TeamChampionshipPath";
import type { ChampionshipPathEntry } from "../../lib/api";

/** Backend tiers: 4 = Division, 2 = Conference/Pennant, 1 = Championship. */
const DIVISION = 4;
const CONFERENCE = 2;
const CHAMPIONSHIP = 1;

function entry(over: Partial<ChampionshipPathEntry>): ChampionshipPathEntry {
  return {
    tier: DIVISION,
    label: "Division",
    probability: 0.003,
    market_id: 4242,
    movement: null,
    ...over,
  } as ChampionshipPathEntry;
}

function draw(entries: ChampionshipPathEntry[]): string {
  return renderToStaticMarkup(
    React.createElement(TeamChampionshipPath, { entries, color: "#bd3039" }),
  );
}

/**
 * The step's printed values, and ONLY those.
 *
 * Assertions here must not read the whole markup: the bar's inline style
 * carries `width:100%` and `width:0%`, so a bare `not.toContain("100%")` or
 * `not.toContain("%")` fails against a component printing the right thing —
 * and, worse, the mirror-image assertion would PASS on the strength of a CSS
 * declaration. This pulls the text out of the value span, so every arm below
 * is about what a reader sees. (Both mistakes were made writing this file.)
 */
function printed(html: string): string[] {
  return [...html.matchAll(/text-2xl leading-none tabular-nums"[^>]*>([^<]*)</g)].map(
    (m) => m[1],
  );
}

describe("#7687 a path step never rounds a live chance into an impossible one", () => {
  test("Boston's served 0.003 for its division does not print 0%", () => {
    const html = draw([entry({ probability: 0.003 })]);
    // The control first — the step must be on the page for the rest to mean
    // anything.
    expect(html).toContain("Division");
    expect(printed(html)).toEqual(["&lt;1%"]);
  });

  test("the whole 0.001 cohort — six clubs' division steps — is covered", () => {
    const html = draw([entry({ probability: 0.001 })]);
    expect(printed(html)).toEqual(["&lt;1%"]);
  });

  test("the other end is guarded too", () => {
    // No MLB club served one this week, but the step takes the same numbers the
    // event page's rungs do, where 0.9972 was live. A component guarded at one
    // end only is what #7670 found and is the shape this rule exists to refuse.
    const html = draw([entry({ probability: 0.9972 })]);
    expect(printed(html)).toEqual(["&gt;99%"]);
  });

  test("CONTROL: an ordinary step keeps its plain integer and no marker", () => {
    const html = draw([
      entry({ tier: CONFERENCE, label: "Conference", probability: 0.1207 }),
    ]);
    expect(printed(html)).toEqual(["12%"]);
  });

  test("CONTROL: the absolutes the payload is entitled to state still print", () => {
    expect(printed(draw([entry({ probability: 0 })]))).toEqual(["0%"]);
    expect(printed(draw([entry({ probability: 1 })]))).toEqual(["100%"]);
  });

  test("CONTROL: a null probability still renders the dash, not a number", () => {
    const html = draw([entry({ probability: null })]);
    expect(printed(html)).toEqual(["—"]);
  });

  test("CONTROL: the BAR still rounds — only the printed number is routed", () => {
    // A 0.3% step's bar is `width:0%`, which is the honest picture of a sliver
    // too small to draw. If this ever reads `width:1%` the routing went one
    // expression too far and the bar is now overstating what the text bounds.
    const html = draw([entry({ probability: 0.003 })]);
    expect(html).toContain("width:0%");
  });

  test("CONTROL: a full path still renders every step it was given", () => {
    const html = draw([
      entry({ tier: DIVISION, label: "Division", probability: 0.003, market_id: 1 }),
      entry({ tier: CONFERENCE, label: "Conference", probability: 0.1207, market_id: 2 }),
      entry({ tier: CHAMPIONSHIP, label: "Championship", probability: 0.0545, market_id: 3 }),
    ]);
    expect(html).toContain("Division");
    expect(html).toContain("Conference");
    expect(html).toContain("Championship");
    // Order is the component's own easiest -> hardest progression.
    expect(printed(html)).toEqual(["&lt;1%", "12%", "5%"]);
  });
});
