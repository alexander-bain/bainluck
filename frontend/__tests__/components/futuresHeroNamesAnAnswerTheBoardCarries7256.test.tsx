/**
 * #7256 — the futures hero names the outcome it is showing, not "Yes".
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `https://bainluck.com/futures/55674185` — *2027 CONCACAF Gold Cup Champion*, a
 * 23-outcome mutually-exclusive field, 2026-09-19:
 *
 *     41%
 *     Yes
 *
 * and directly beneath it, All Outcomes: `USA 41% · Mexico 38% · Canada 18% …`,
 * with the chart legend reading `Canada · Mexico · USA`. No row anywhere on the
 * page is called "Yes". The 41% is USA's, and the page said so twice — just not
 * in the largest type on the screen.
 *
 * Alex filed the second member on `/futures/58776433` — *"When will the Danube
 * River return to normal levels?"*, a 3-rung date ladder whose hero read
 * **55% / Yes** over the rung `October 1 - 31, 2026`:
 *
 *   *"`Yes` is not an answer to a 'when' question, and no row on the page carries
 *   it … the predicate is not 'large field' but 'the market is not binary'."*
 *
 * ═══ WHY THE GUARD RENDERS THE COMPONENT INSTEAD OF CALLING THE HELPER ═══
 *
 * `futuresHeroNeverCrownsTheOppositeSide5997.test.ts` unit-tests
 * `boardOutcomeLabel` and is the right place for the predicate's own arms. It
 * cannot see this defect's shape, because what a reader met was a COMPOSITION:
 * the page computes the label with one function and `FuturesHero` decides
 * whether and where to draw it. A hero that dropped `outcomeName` entirely, or
 * gated it behind a falsy check that swallowed a legitimate name, would leave
 * every unit arm green and the reader looking at a bare `41%`.
 *
 * So this file asserts on rendered markup, with the label computed exactly the
 * way `app/futures/[id]/page.tsx` computes it, and it asserts BOTH directions:
 * the board's own answer is present, AND the word the board does not carry is
 * absent. Both renderings of the component are covered — UX-P233 found a
 * mutation battery surviving `futuresBaselineRender.test.tsx` because that
 * harness only ever fed the plain variant.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { FuturesHero } from "../../components/FuturesHero";
import { boardOutcomeLabel } from "@/lib/futuresDetailDisplay";

/** Both renderings of the same props: [label, sparklinePoints]. */
const RENDERINGS: [string, number[] | undefined][] = [
  ["ambient", [0.33, 0.36, 0.38, 0.4, 0.41, 0.41]],
  ["plain", undefined],
];

/**
 * The two filed specimens, verbatim from their production payloads, plus the
 * short-token case that is the largest arm of the measured population.
 *
 * `USA` is the one that shows why the old predicate could not be narrowed by
 * tuning a length: it is three characters, and so are `TCU`, `BYU`, `LSU`,
 * `PSG` and `SEC`. #4627 added a hand-picked label so a hero would say "PSG"
 * rather than the fragment "Germain"; the substitution then replaced "PSG" with
 * "Yes".
 */
const SPECIMENS: { market: string; leader: string; probability: number }[] = [
  { market: "2027 CONCACAF Gold Cup Champion", leader: "USA", probability: 0.41 },
  {
    market: "When will the Danube River return to normal levels?",
    leader: "October 1 - 31, 2026",
    probability: 0.55,
  },
  { market: "Which KPop groups will release songs in 2026?", leader: "IVE", probability: 0.62 },
  { market: "WTI Crude Oil (WTI) closes above ___ on September 21?", leader: "$92", probability: 0.48 },
];

/**
 * 🪤 `outcomeName` takes no default, for the reason the #6760 harness records: a
 * default parameter fires on an explicitly passed `undefined`, which would make
 * the no-name case render a name and fail on a correct component.
 */
function hero(points: number[] | undefined, outcomeName: string | undefined, probability: number) {
  return renderToStaticMarkup(
    <FuturesHero
      name="2027 CONCACAF Gold Cup Champion"
      probability={probability}
      outcomeName={outcomeName}
      movementLabel="last move · Sep 19"
      sparklinePoints={points}
      isMultiOutcome
    />,
  );
}

describe("#7256 — the hero names an answer the board actually carries", () => {
  describe.each(RENDERINGS)("%s rendering", (_label, points) => {
    test.each(SPECIMENS)(
      "$market: the hero says $leader, never \"Yes\"",
      ({ leader, probability }) => {
        const html = hero(points, boardOutcomeLabel(leader), probability);

        // The name is drawn, and is addressable — without this the negative
        // assertion below would pass on a hero that drew no name at all.
        expect(html).toContain('data-testid="hero-outcome-name"');
        expect(html).toContain(leader);

        // 🔴 THE DEFECT. Scoped to the name slot rather than the whole document:
        // `name` and `movementLabel` are reader-visible strings that could
        // legitimately contain these letters, and a document-wide `not.toContain`
        // would be asserting something this issue never claimed.
        expect(nameSlot(html)).toBe(leader);
        expect(nameSlot(html)).not.toBe("Yes");
      },
    );
  });

  test("a binary board still reads `Yes`, because `Yes` is its own row's name", () => {
    // The population this ship must NOT move. `statesItsOwnSide` has returned
    // these verbatim since #5997 and still does; retiring the substitution
    // cannot reach them, and a reader on a binary market sees no change.
    for (const served of ["Yes", "No", "Over 5.5", "Under 100"]) {
      const html = hero(undefined, boardOutcomeLabel(served), 0.6);
      expect(nameSlot(html)).toBe(served);
    }
  });

  test("a blank name leaves the slot empty rather than inventing one", () => {
    // Measured 0 leading outcomes with a blank name across 43,510 open markets,
    // so this is the unreachable direction — asserted because the old
    // substitution's last defensible case was exactly "the name says nothing",
    // and the honest answer to that is silence, not "Yes" (notice 34 / D102).
    const html = hero(undefined, boardOutcomeLabel("   "), 0.6);
    expect(html).not.toContain('data-testid="hero-outcome-name"');
    expect(html).not.toContain(">Yes<");
  });
});

/**
 * The text content of the hero's outcome-name element, or `""` when the hero
 * drew none. Reads the rendered markup the same way a reader identifies the
 * slot — by the testid the component puts on it.
 */
function nameSlot(html: string): string {
  const at = html.indexOf('data-testid="hero-outcome-name"');
  if (at === -1) return "";
  const open = html.indexOf(">", at);
  const close = html.indexOf("<", open);
  return html.slice(open + 1, close);
}
