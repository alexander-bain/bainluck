/**
 * ux/1034 B6 — "MORE TENNIS" IS A CARD GRID.
 *
 * Alex, on `/events/15293830` while the US Open was on: the section at the
 * bottom of the page is **"formatted horribly"**, and — "make it the same card
 * grid the hub uses."
 *
 * What he was looking at, from the live payload banked beside this file: two
 * full-width strips, each a 12px market name on the left and `Carlos Alcaraz
 * 33%` crushed against the right edge. On a desktop that is ~900px of nothing
 * between a question and its answer. And it discarded most of what the payload
 * carries — `top_outcomes` holds three names per market and the strip printed
 * one.
 *
 * ## What is asserted, and why each one is here
 *
 * - **The chassis is the hub's.** A card per item, two-up from `sm`, the hub's
 *   section rule on the heading. Asserted through the class strings because
 *   "looks like the hub" is otherwise a claim nothing can hold.
 * - **The field is the field.** Three outcomes per card on the live payload,
 *   not one — and `+30 more`, because a three-row card over a 33-runner market
 *   otherwise reads as the whole answer.
 * - **A card never invents a number.** An unpriced outcome is dropped rather
 *   than printed as a dash, and a card with nothing priced renders its title
 *   and no field. This is the assertion that stops "show more rows" from
 *   turning into "show more rows of `-`".
 * - **The BEFORE is stated on the same payload**, so the improvement is a
 *   measured difference rather than a claim: the old strip printed one name per
 *   market and this one prints three.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import SERVED from "../fixtures/uxp1034_related_tennis.20260902.json";

let swrPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTag = require("@/components/RelatedByTag").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTagLegacy = require("../fixtures/uxp177RelatedByTagLegacy").default;

function render(Component: unknown, payload: unknown, title = "More Tennis"): string {
  swrPayload = payload;
  return renderToStaticMarkup(
    React.createElement(Component as React.FC, {
      tags: ["sport:tennis"],
      excludeId: 15293830,
      excludeType: "event",
      limit: 4,
      title,
    } as never)
  );
}

function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/** How many outcome rows the whole section drew. */
function fieldRows(markup: string): number {
  return (markup.match(/<li class="flex items-baseline justify-between gap-3 text-\[12px\]"/g) ?? [])
    .length;
}

describe("ux/1034 B6 — the related section is a card grid", () => {
  it("draws the hub's chassis on the live More Tennis payload", () => {
    const html = render(RelatedByTag, SERVED);

    // Two cards, in a grid that is two-up from `sm` — not a stack of strips.
    expect(html).toContain('data-testid="related-by-tag-grid"');
    expect(html).toContain("grid gap-2 sm:grid-cols-2");
    expect(html.match(/data-testid="related-card"/g)).toHaveLength(2);
    expect(html).toContain("rounded-2xl border border-surface-border bg-surface-card");

    // The hub's section rule, with the count beside it.
    expect(html).toContain("text-xs font-bold uppercase tracking-[0.07em] text-text-muted");
    expect(visibleText(html)).toContain("More Tennis · 2");
  });

  it("prints the field, not just the leader", () => {
    const html = render(RelatedByTag, SERVED);
    const text = visibleText(html);

    // Both markets, each with the three outcomes the payload actually carries.
    expect(text).toContain("US Open Men's Singles Winner");
    expect(text).toContain("US Open Women's Singles Winner");
    expect(fieldRows(html)).toBe(6);

    // And the card says how much of the draw is NOT on it. 33 runners, 3 shown.
    expect(text).toContain("+30 more");
    expect(text).toContain("+20 more");
  });

  /** The measured before/after on one payload — not a claim, a difference. */
  it("says more than the strip it replaces, on the same payload", () => {
    const before = render(RelatedByTagLegacy, SERVED);
    const after = render(RelatedByTag, SERVED);

    // The strip printed one name per market and no count of the rest.
    expect(visibleText(before)).not.toContain("+30 more");
    expect(fieldRows(before)).toBe(0);
    expect(fieldRows(after)).toBeGreaterThan(fieldRows(before));

    // Nothing the strip published is lost: same links, same leaders.
    expect(after.match(/href="[^"]*"/g)).toEqual(before.match(/href="[^"]*"/g));
    expect(visibleText(after)).toContain("Carlos Alcaraz");
  });

  /**
   * A CARD NEVER INVENTS A NUMBER. `formatProbability` renders `-` for a null,
   * so "list more outcomes" without this gate would have printed a column of
   * dashes under a market nobody has priced.
   */
  it("drops unpriced outcomes rather than printing a dash", () => {
    const html = render(RelatedByTag, {
      items: [
        {
          type: "futures",
          data: {
            id: 900,
            name: "Nobody has quoted this",
            outcome_count: 2,
            top_outcomes: [
              { name: "Priced", probability: 0.4 },
              { name: "Unpriced", probability: null },
            ],
          },
        },
        {
          type: "futures",
          data: {
            id: 901,
            name: "Nothing priced at all",
            outcome_count: 1,
            top_outcomes: [{ name: "Unpriced", probability: null }],
          },
        },
      ],
    });

    expect(fieldRows(html)).toBe(1);
    expect(visibleText(html)).toContain("Priced 40%");
    expect(visibleText(html)).not.toContain("-");
    // The unpriced card still exists and still names its question.
    expect(visibleText(html)).toContain("Nothing priced at all");
    expect(html).toContain("/futures/901");
  });

  /** An event and a concept get the same card, because they are the same thing
   *  to a reader: something else worth looking at. */
  it("gives an event and a concept the same card as a market", () => {
    const html = render(RelatedByTag, {
      items: [
        {
          type: "event",
          data: {
            id: 41,
            away_team: "Jelena Ostapenko",
            home_team: "Tatjana Maria",
            status: "live",
            home_score: 1,
            away_score: 0,
            current_odds: { home_probability: 0.62, away_probability: 0.38 },
          },
        },
        {
          type: "concept",
          data: {
            key: "event:ufc:26aug29",
            domain: "ufc",
            name: "UFC 320",
            leader: { name: "Khamzat Chimaev", probability: 0.62 },
          },
        },
      ],
    });

    expect(html.match(/data-testid="related-card"/g)).toHaveLength(2);
    expect(html).toContain('data-kind="event"');
    expect(html).toContain('data-kind="concept"');
    // Both sides of the game, in the order the title names them.
    const text = visibleText(html);
    expect(text).toContain("Jelena Ostapenko @ Tatjana Maria");
    expect(text.indexOf("Jelena Ostapenko 38%")).toBeLessThan(
      text.indexOf("Tatjana Maria 62%")
    );
    expect(html).toContain("/event/ufc/26aug29");
  });
});
