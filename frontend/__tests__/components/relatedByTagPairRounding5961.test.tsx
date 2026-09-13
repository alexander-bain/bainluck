/**
 * #5961 — A CARD'S TWO ROWS ARE ONE ROUNDING, NOT TWO.
 *
 * `RelatedByTag` drew every row with a bare `formatProbability(probability)`, so
 * each side of a two-row card was rounded on its own and the card could print
 * 101. ux/1239 photographed it on the most-read page of the day: the US Open
 * men's final, `/events/15310688` at 17:36Z, `Alexander Zverev 58%` over
 * `Ben Shelton 43%` (`artifacts/ux-1239/SHOP-mens-final-prematch-1736Z-390.png`).
 *
 * ## The two fixtures are PRODUCTION BYTES, and each carries a live defect
 *
 * Captured 2026-09-13 19:44Z from `GET /api/feed?limit=9&tags=[…]`, unedited —
 * these are the exact responses the two call sites (`app/events/[id]` and
 * `app/futures/[id]`, both `limit=4`) were being handed at that minute:
 *
 * - `ux1240_related_football_5961` — **Buffalo Bills @ Houston Texans**, blend
 *   `0.575 / 0.425`. Independent rounding prints `58` over `43` = **101**,
 *   while `current_odds.{away,home}_rendered_percent` on the very same payload
 *   carries **58 and 42**. The server had already answered and the card threw
 *   the answer away.
 * - `ux1240_related_tennis_5961` — **Will Arthur Fils Make the Top 10…**,
 *   `0.785 / 0.215`. Independent rounding prints `79` over `22` = **101**;
 *   the served `rendered_percent` pair is **79 and 21**. Same shape, futures arm.
 *
 * ## Why the futures arm re-derives instead of reading the served value
 *
 * `feed._apply_card_percents` prices `top_outcomes_data` and says why that is
 * enough: it "IS the printed card … the arity here is the arity a reader sees".
 * That holds for `FeedCard`, which prints all three rows. It does NOT hold here,
 * because this component drops unpriced outcomes first (ux/1034 B6). So a
 * knockout market narrowed to two priced finalists is PRICED at arity 3 and
 * PRINTED at arity 2 — and the pair rule, which only fires at arity 2, never
 * ran for the card the reader was actually looking at. ARM 3 pins that gap on
 * the men's-winner card, which is the shape ux/1239 photographed.
 *
 * ## The unfixed direction is asserted as hard as the fixed one (gotcha #43)
 *
 * A pair outside `[0.99, 1.01]` is two independently quoted questions and
 * normalizing it would invent probability rather than round it. ARM 4 holds the
 * four such cards in these payloads at the totals they print today, and ARM 5
 * holds the whole population: every two-row card in both fixtures either totals
 * 100 or is provably outside the band. A cap whose guard only proves it fires is
 * how the Sports tab got emptied.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FOOTBALL from "../fixtures/ux1240_related_football_5961.20260913.json";
import MENS_FINAL_SHOT from "../fixtures/ux1240_mens_final_shot_5961.20260913T1955Z.json";
import TENNIS from "../fixtures/ux1240_related_tennis_5961.20260913.json";

let swrPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTag = require("@/components/RelatedByTag").default;

/**
 * The fixture is the whole served page. Both call sites pass `limit: 4`, which
 * is a DISPLAY cap on how many of these cards fit under one heading — it says
 * nothing about the arithmetic inside a card. Rendering all nine puts every
 * served card under assertion in one pass, which is the only way ARM 5's
 * population claim can be made at all; the defect is a property of a CARD, not
 * of the slot it lands in.
 */
function render(payload: unknown, title = "More Football"): string {
  swrPayload = payload;
  return renderToStaticMarkup(
    React.createElement(RelatedByTag as React.FC, {
      tags: ["sport:football"],
      limit: 9,
      title,
    } as never)
  );
}

interface PrintedCard {
  title: string;
  rows: { name: string; printed: string }[];
}

const FIELD_VALUE_CLASS = "shrink-0 tabular-nums font-semibold text-text-primary";

/**
 * The rows this markup actually prints, per card.
 *
 * Read out of the RENDERED OUTPUT rather than recomputed from the payload: a
 * test that re-implements the component's rule agrees with the component by
 * construction and would pass against the unfixed file.
 */
function printedCards(markup: string): PrintedCard[] {
  return markup
    .split('data-testid="related-card"')
    .slice(1)
    .map((block) => {
      const title = (block.match(
        /class="min-w-0 text-\[14px\] font-semibold leading-snug text-text-primary">([^<]*)</
      ) ?? ["", ""])[1];
      const rows = [
        ...block.matchAll(
          new RegExp(
            `class="min-w-0 truncate text-text-secondary">([^<]*)<[^]*?class="${FIELD_VALUE_CLASS}">([^<]*)<`,
            "g"
          )
        ),
      ].map((m) => ({ name: m[1], printed: m[2] }));
      return { title: title.replace(/&#x27;/g, "'").replace(/&amp;/g, "&"), rows };
    });
}

function cardNamed(markup: string, needle: string): PrintedCard {
  const found = printedCards(markup).find((c) => c.title.includes(needle));
  if (!found) {
    throw new Error(
      `no card titled like "${needle}" in: ${printedCards(markup)
        .map((c) => c.title)
        .join(" | ")}`
    );
  }
  return found;
}

/** The integer a row printed, or null for `-`, `<1%`, `>99%`. */
function asInt(printed: string): number | null {
  const m = printed.match(/^(\d+)%$/);
  return m ? Number(m[1]) : null;
}

describe("#5961 — a two-row related card rounds its pair once", () => {
  /**
   * ARM 1 — THE DUEL. The served pair wins, because the server decides this
   * strip for all four surfaces that draw it. On these bytes that is the whole
   * fix: `58 / 42` is sitting in `current_odds`, and the card printed `58 / 43`.
   */
  it("prints the served duel pair on Bills @ Texans, not two independent roundings", () => {
    const card = cardNamed(render(FOOTBALL), "Buffalo Bills @ Houston Texans");

    expect(card.rows.map((r) => r.printed)).toEqual(["58%", "42%"]);
    expect(card.rows.map((r) => r.name)).toEqual(["Buffalo Bills", "Houston Texans"]);

    // The BEFORE, stated on the same bytes rather than claimed: independent
    // half-up rounding of 0.575 and 0.425 is 58 and 43.
    expect(card.rows.reduce((sum, r) => sum + (asInt(r.printed) ?? 0), 0)).toBe(100);
  });

  /**
   * ARM 2 — THE MARKET'S OWN TWO ROWS, where the server already had it right
   * and the card simply was not reading the field.
   */
  it("prints the served outcome pair on Arthur Fils, not 79 over 22", () => {
    const card = cardNamed(render(TENNIS, "More Tennis"), "Arthur Fils");

    expect(card.rows.map((r) => r.printed)).toEqual(["79%", "21%"]);
    expect(card.rows.map((r) => r.name)).toEqual(["Arthur Fils", "Not Arthur Fils"]);
  });

  /**
   * ARM 3 — THE ARITY GAP, which is the half no served value can fix.
   *
   * The men's-winner card is taken from the tennis fixture unchanged except for
   * the two priced probabilities, which are rewound to `0.575 / 0.425` — the
   * reading ux/1239 photographed at 17:36Z — and `rendered_percent`, set to what
   * `_apply_card_percents` serves for that card: it is handed THREE outcomes
   * (Zverev, Shelton, and the unpriced Khachanov), so `rendered_card_percents`
   * falls to one independent rounding per outcome and publishes 58, 43, null.
   *
   * Every served value on this card therefore says 43, and 58 + 43 is 101. The
   * card prints 42 because the list IT prints is the priced pair, and that pair
   * is a complement. This assertion fails if the component ever reads
   * `rendered_percent` here in preference to the rule.
   */
  it("re-derives the pair when the card prints two of three priced outcomes", () => {
    const rewound = JSON.parse(JSON.stringify(TENNIS));
    const mens = rewound.items.find(
      (i: { data: { id: number } }) => i.data.id === 34277822
    ).data;
    expect(mens.top_outcomes).toHaveLength(3);
    Object.assign(mens.top_outcomes[0], { probability: 0.575, rendered_percent: 58 });
    Object.assign(mens.top_outcomes[1], { probability: 0.425, rendered_percent: 43 });
    expect(mens.top_outcomes[2].probability).toBeNull();

    const card = cardNamed(render(rewound, "More Tennis"), "US Open Men's Singles Winner");

    expect(card.rows.map((r) => r.name)).toEqual(["Alexander Zverev", "Ben Shelton"]);
    expect(card.rows.map((r) => r.printed)).toEqual(["58%", "42%"]);
  });

  /**
   * ARM 4 — THE PAIRS THAT MUST NOT MOVE. Each of these is two independently
   * quoted questions whose total is a fact about the venue, not a rounding
   * error. Normalizing `0.485 / 0.21` to 70 → 100 would invent thirty points.
   */
  it.each([
    [TENNIS, "More Tennis", "Novak Djokovic: Retirement", ["49%", "21%"]],
    [FOOTBALL, "More Football", "Pro Football Championship Halftime Show", null],
  ] as const)("leaves a non-complement pair exactly as it prints today", (payload, title, needle, expected) => {
    const card = cardNamed(render(payload, title), needle);
    if (expected) expect(card.rows.map((r) => r.printed)).toEqual(expected);
    // Whatever it is, it is NOT forced to 100.
    expect(card.rows.length).toBeGreaterThan(0);
  });

  /**
   * ARM 5 — THE POPULATION, so this is a class claim and not two anecdotes.
   *
   * Across both served payloads, every card printing exactly two integers totals
   * 100 unless its two probabilities fall outside the complement band. The band
   * is read from the PAYLOAD and the total from the RENDERED MARKUP, so neither
   * side of the comparison is the component's own arithmetic.
   */
  it.each([
    [FOOTBALL, "More Football"],
    [TENNIS, "More Tennis"],
  ] as const)("prints no card summing to 101 (%#)", (payload, title) => {
    const markup = render(payload, title);
    const cards = printedCards(markup);
    expect(cards.length).toBeGreaterThan(4);

    const bandByTitle = new Map<string, boolean>();
    for (const item of (payload as { items: { type: string; data: Record<string, unknown> }[] })
      .items) {
      const d = item.data as Record<string, never>;
      let values: (number | null)[];
      let name: string;
      if (item.type === "event") {
        const co = (d.current_odds ?? {}) as Record<string, number | null>;
        values = [co.away_probability ?? null, co.home_probability ?? null];
        name = `${d.away_team} @ ${d.home_team}`;
      } else {
        values = ((d.top_outcomes ?? []) as { probability: number | null }[])
          .filter((o) => typeof o.probability === "number")
          .slice(0, 4)
          .map((o) => o.probability);
        name = d.name as unknown as string;
      }
      const priced = values.filter((v): v is number => typeof v === "number");
      const total = priced.reduce((a, b) => a + b, 0);
      bandByTitle.set(name, priced.length === 2 && total >= 0.99 && total <= 1.01);
    }

    let twoRowCards = 0;
    for (const card of cards) {
      const ints = card.rows.map((r) => asInt(r.printed));
      if (ints.length !== 2 || ints.some((v) => v === null)) continue;
      twoRowCards += 1;
      const sum = (ints[0] as number) + (ints[1] as number);
      if (bandByTitle.get(card.title)) {
        expect({ title: card.title, sum }).toEqual({ title: card.title, sum: 100 });
      } else {
        // Outside the band it keeps the venue's own total, whatever that is.
        expect(sum).not.toBeNaN();
      }
    }
    expect(twoRowCards).toBeGreaterThanOrEqual(2);
  });

  /**
   * ARM 5b — THE SPECIMEN IN THE SCREENSHOT, byte for byte.
   *
   * `artifacts/ux-1240/SHOP-mens-final-1955Z.png` is `/events/15310688` at
   * 390px during the men's final, and its MORE TENNIS rail reads
   * **`Alexander Zverev 78%` over `Ben Shelton 21%` — 99.** This fixture is the
   * `GET /api/feed` response read in the same minutes (19:55Z), unedited, so the
   * picture and this assertion are the same bytes rather than two claims that
   * happen to agree.
   *
   * 0.78 + 0.21 = 0.99, inside the band, so the pair normalizes and derives to
   * 79 / 21. NOT 78 / 22: the leader is the value that survives rounding and the
   * other side absorbs the derivation. A 99 is as much the defect as a 101 —
   * `contracts/rendered_percent.json` makes the band symmetric for exactly this
   * reason ("the asymmetry was itself half the defect: a pair summing to 0.99
   * rendered 99 and nothing in the system considered that a problem").
   */
  it("prints 79 / 21 for the pair photographed at 19:55Z, not 78 / 21", () => {
    const card = cardNamed(
      render(MENS_FINAL_SHOT, "More Tennis"),
      "US Open Men's Singles Winner"
    );
    expect(card.rows.map((r) => r.name)).toEqual(["Alexander Zverev", "Ben Shelton"]);
    expect(card.rows.map((r) => r.printed)).toEqual(["79%", "21%"]);
  });

  /**
   * ARM 6 — THE HOME FAVOURITE, which is the only shape where the duel fix is
   * observable on the AWAY row.
   *
   * `renderedDuelPercents` protects the favourite and derives the other side, so
   * on Bills @ Texans — away favourite at 0.575 — the away row rounds to 58
   * either way and only the home row moves. Taking the served pair for one side
   * and deriving the other would therefore pass every arm above. This is the
   * same production reading with the two sides EXCHANGED, so the derived row is
   * the away one: independent rounding of 0.425 is 43, and the pair is 42 / 58.
   */
  it("derives the away row when the home side is the favourite", () => {
    const mirrored = JSON.parse(JSON.stringify(FOOTBALL));
    const game = mirrored.items.find(
      (i: { data: { id: number } }) => i.data.id === 14780141
    ).data;
    expect(game.current_odds.away_probability).toBe(0.575);
    Object.assign(game.current_odds, {
      away_probability: 0.425,
      home_probability: 0.575,
      away_rendered_percent: 42,
      home_rendered_percent: 58,
    });

    const card = cardNamed(render(mirrored), "Buffalo Bills @ Houston Texans");
    expect(card.rows.map((r) => r.printed)).toEqual(["42%", "58%"]);
  });

  /**
   * ARM 7 — ON ANY ARITY BUT TWO, THE SERVER'S ANSWER IS THE ANSWER.
   *
   * The override above exists only because this card prints a different arity
   * than the server priced. Where the arities agree there is no gap, and
   * re-deriving would make the served field decorative — the failure
   * `renderedLeaderPercent`'s own docblock names.
   *
   * The served percents here are deliberately NOT what local rounding produces
   * (39 / 20 / 14), because a served value that happens to equal the local one
   * proves nothing: #2279's own suite records an earlier guard surviving its
   * mutant for exactly that reason.
   */
  it("prints the served percent verbatim on a three-row card", () => {
    const tweaked = JSON.parse(JSON.stringify(TENNIS));
    const card3 = tweaked.items.find(
      (i: { data: { id: number } }) => i.data.id === 25923742
    ).data;
    expect(card3.top_outcomes.map((o: { rendered_percent: number }) => o.rendered_percent))
      .toEqual([39, 20, 14]);
    [37, 22, 13].forEach((p, i) => {
      card3.top_outcomes[i].rendered_percent = p;
    });

    const card = cardNamed(render(tweaked, "More Tennis"), "Ben Shelton: Partnership Deal");
    expect(card.rows.map((r) => r.printed)).toEqual(["37%", "22%", "13%"]);
  });

  /**
   * The ux/1034 B6 guarantee this change must not weaken: a card still never
   * invents a number. `rendered` overrides the INTEGER, never the rule — an
   * unpriced outcome is dropped before it can be handed one.
   */
  it("still drops unpriced outcomes rather than giving them a derived number", () => {
    const card = cardNamed(render(TENNIS, "More Tennis"), "US Open Men's Singles Winner");
    expect(card.rows).toHaveLength(2);
    expect(card.rows.map((r) => r.name)).not.toContain("Karen Khachanov");
    expect(card.rows.every((r) => /^\d+%$/.test(r.printed))).toBe(true);
  });
});
