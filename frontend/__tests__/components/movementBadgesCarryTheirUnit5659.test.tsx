/**
 * #5659 — the movement badge that prints a bare number.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * Discover page one at 390px, production Heroku v4466 `71d2915f`, the
 * "BP Monthly Credit Card Spend in September" card (ECONOMICS, TRENDING):
 *
 *     Above 98      ▲45.0   ███████░░   89%
 *     Above 101     ▲59.5   ██████░░░   83%
 *     Above 103.5   ▲61.0   ██████░░░   79%
 *     Above 105.5           ████░░░░░   65%
 *
 * `▲45.0` has NO UNIT AT ALL, in a column between a label and a number that is
 * a percent. The served payload says what it means:
 *
 *     {"id": 222337108, "name": "Above 98", "probability": 0.885,
 *      "rank": 1, "movement": 0.45, "rendered_percent": 89}
 *
 * `movement` is a probability delta in 0-1 units, so `45.0` is 45 percentage
 * POINTS — a move further than the whole remaining distance to certainty —
 * printed as a bare number beside an 89%.
 *
 * ═══ THE FAMILY, AND WHY THIS IS A DIFFERENT DEFECT FROM #5666's ═══
 *
 * The six surfaces of the points-vs-percent family (#4066, #5619, #5608,
 * #5623, #5669, #5666) all spelled the unit WRONG — `8.5%` over 8.5 points.
 * `movementPointsFamilyClosed5666`'s class scan is built from that shape:
 * the formatter's output with a `%` next to it. It is structurally blind to
 * output with NOTHING next to it, which is the one variant where the reader
 * cannot even guess, and three live sites sat inside its scanned population,
 * green, the whole time:
 *
 *   components/QuantityGroup.tsx        `▲45.0`   ← filed as #5659
 *   components/TeamChampionshipPath.tsx `+9.7`    ← found by this ship
 *   components/discover/FuturesCard.tsx `↑ 9.7`   ← found by this ship
 *
 * The scan is widened in that file to the invariant the family actually has:
 * the formatter's output is never rendered without its unit. THIS file is the
 * rendered half — the class scan reads source text, and source text is not
 * what a reader looks at.
 *
 * ═══ THE LABEL WAS THE SPEC SITTING NEXT TO THE BUG ═══
 *
 * All three surfaces already described the unit correctly to a screen reader:
 * `aria-label="up 45.0 points"` on the rung, `movementTitle` = "Up 9.7 points
 * in the last 24h" on the card. #4066's own comment made this exact point one
 * card over. Each arm below asserts the visible text AND the accessible name,
 * because the defect is precisely that they disagreed.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import QuantityGroup, { type QuantityRung } from "@/components/QuantityGroup";
import { TeamChampionshipPath } from "@/components/TeamChampionshipPath";
import type { ChampionshipPathEntry } from "@/lib/api";

/** Strip tags so an assertion reads the words a fan reads, not the markup. */
function visibleText(html: string): string {
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

/**
 * A direction glyph followed by a magnitude and NOT followed by a unit —
 * the rendered signature of the defect, applied to whole visible text.
 *
 * `(?![\d.])` is load-bearing and was not in the first draft. Without it the
 * magnitude backtracks: against the REPAIRED "▲45.0 pts" the engine matches
 * just "45", the unit lookahead then sees ".0 pts", and the pattern reports
 * the defect on the fix. A detector that fires on the repaired string would
 * have failed this suite into looking correct for the wrong reason.
 */
const BARE_BADGE = /[▲▼↑↓]\s?\d{1,3}(?:\.\d)?(?![\d.])(?!\s*(?:pts|points?))/;

describe("#5659 the detector itself", () => {
  test("BARE_BADGE fires on the photographed defect and not on its repair", () => {
    // Every `expect(BARE_BADGE.test(...)).toBe(false)` below is worth exactly
    // what this arm is worth.
    expect(BARE_BADGE.test("Above 98 ▲45.0 89%")).toBe(true);
    expect(BARE_BADGE.test("▼12.0")).toBe(true);
    expect(BARE_BADGE.test("↑ 9.7")).toBe(true);
    expect(BARE_BADGE.test("Above 98 ▲45.0 pts 89%")).toBe(false);
    expect(BARE_BADGE.test("▼12.0 pts")).toBe(false);
    expect(BARE_BADGE.test("↑ 9.7 points")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Surface one — the ladder rung in the photograph
// ---------------------------------------------------------------------------

/** The served payload from the issue body, rung for rung. */
const bpCreditCardLadder: QuantityRung[] = [
  { key: 222337108, label: "Above 98", probability: 0.885, value: 98, movement: 0.45 },
  { key: 222337109, label: "Above 101", probability: 0.83, value: 101, movement: 0.595 },
  { key: 222337110, label: "Above 103.5", probability: 0.79, value: 103.5, movement: 0.61 },
  { key: 222337111, label: "Above 105.5", probability: 0.65, value: 105.5 },
];

describe("#5659 surface one — QuantityGroup ladder rungs", () => {
  const html = renderToStaticMarkup(
    <QuantityGroup sort={false} rungs={bpCreditCardLadder} />,
  );
  const text = visibleText(html);

  test("the production specimen's rung reads '▲45.0 pts', not a bare '▲45.0'", () => {
    expect(text).toContain("▲45.0 pts");
    expect(BARE_BADGE.test(text)).toBe(false);
  });

  test("every moving rung on the card carries the unit — not just the first", () => {
    // A partial fix that moved one rung and left its neighbours is the exact
    // shape this family keeps producing.
    expect(text).toContain("▲45.0 pts");
    expect(text).toContain("▲59.5 pts");
    expect(text).toContain("▲61.0 pts");
  });

  test("a faller keeps its arrow and gains the unit too", () => {
    const falling = visibleText(
      renderToStaticMarkup(
        <QuantityGroup
          sort={false}
          rungs={[{ key: "a", label: "Above 98", probability: 0.4, value: 98, movement: -0.12 }]}
        />,
      ),
    );
    expect(falling).toContain("▼12.0 pts");
    expect(BARE_BADGE.test(falling)).toBe(false);
  });

  test("the visible text and the accessible name now agree on the unit", () => {
    // They always disagreed: the aria-label has read "points" since UX-1052.
    expect(html).toContain('aria-label="up 45.0 points"');
    expect(text).toContain("▲45.0 pts");
  });

  test("ONE DECIMAL is kept, so the gate that admits a badge still prints one", () => {
    // `isRenderedMove` decides whether a badge renders by asking whether the
    // move survives toFixed(1). Rounding the display to whole points to match
    // `MovementBadge`'s "18 pts" would print "▲0 pts" for every admitted move
    // under half a point — a badge saying the move was nothing.
    const halfPoint = visibleText(
      renderToStaticMarkup(
        <QuantityGroup
          sort={false}
          rungs={[{ key: "a", label: "Above 98", probability: 0.4, value: 98, movement: 0.005 }]}
        />,
      ),
    );
    expect(halfPoint).toContain("▲0.5 pts");
    expect(halfPoint).not.toContain("▲0 pts");
  });

  test("this guard cannot pass by rendering no badge at all", () => {
    // gotcha #43's other direction: every assertion above is satisfied by a
    // component that draws nothing.
    expect(html.match(/▲/g)?.length).toBe(3);
  });

  test("a ladder with no movers is byte-for-byte unchanged by this ship", () => {
    const still = renderToStaticMarkup(
      <QuantityGroup
        sort={false}
        rungs={[
          { key: "a", label: "Above 98", probability: 0.885, value: 98 },
          { key: "b", label: "Above 101", probability: 0.83, value: 101 },
        ]}
      />,
    );
    expect(still).not.toContain("pts");
    expect(still).not.toContain("▲");
  });
});

// ---------------------------------------------------------------------------
// Surface two — the championship path step, the worst-placed of the three
// ---------------------------------------------------------------------------

const pathEntry = (movement: number | null): ChampionshipPathEntry => ({
  tier: 1,
  label: "Championship",
  market_name: "NBA Championship 2026-27",
  market_id: 1234,
  probability: 0.097,
  rank: 4,
  movement,
  season: "2026-27",
});

describe("#5659 surface two — TeamChampionshipPath step", () => {
  test("the bare number sat in the SAME row as a percentage, and now carries its unit", () => {
    // This is the worst-placed member of the family: `{pct}%` is rendered at
    // text-2xl in the same flex row, so the bare "+9.7" read as a percentage by
    // direct association with the number beside it, not merely by column.
    const text = visibleText(
      renderToStaticMarkup(
        <TeamChampionshipPath entries={[pathEntry(0.097)]} color="#007A33" />,
      ),
    );
    expect(text).toContain("10%");
    expect(text).toContain("+9.7 pts");
    expect(BARE_BADGE.test(text)).toBe(false);
  });

  test("a falling step keeps its sign and gains the unit", () => {
    const text = visibleText(
      renderToStaticMarkup(
        <TeamChampionshipPath entries={[pathEntry(-0.043)]} color="#007A33" />,
      ),
    );
    expect(text).toContain("-4.3 pts");
  });

  test("UX-P275 survives: a sub-rounding drift is still no badge, and no unit", () => {
    const text = visibleText(
      renderToStaticMarkup(
        <TeamChampionshipPath entries={[pathEntry(0.00003)]} color="#007A33" />,
      ),
    );
    expect(text).not.toContain("pts");
    expect(text).toContain("10%");
  });

  test("a step with no movement at all is unchanged", () => {
    const text = visibleText(
      renderToStaticMarkup(
        <TeamChampionshipPath entries={[pathEntry(null)]} color="#007A33" />,
      ),
    );
    expect(text).not.toContain("pts");
  });
});
