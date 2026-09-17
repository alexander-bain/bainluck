// #6803 — A PRICELESS RUNG STOPS DATING A CARD WHOSE EVERY PRICE IS CURRENT.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// Routed by native/207, who measured it on the iOS twin of this helper. Market
// 114175, "Who will be UFC Heavyweight champion", serves 19 outcomes:
//
//     14 priced legs       Gane 65.5% … Kuniev 0.05%   all written 2026-09-17T19:50:18Z
//      5 placeholder rungs Fighter D/E/F/G, Other      all stamped 2026-05-12T16:16:06Z
//
// The floor over all nineteen is MAY 12. The floor over the fourteen that show a
// price is TODAY. The iPhone drew "Updated May 12 at 9:16 AM" over a 66% hero
// whose every price was 35 minutes old — 128 days of understatement bought from
// five rows that display no number at all.
//
// ── WHY IT IS WORSE THAN THE DEFECT #6018 REPLACED ───────────────────────────
//
// #6018's pip OVERSTATED freshness. This UNDERSTATES it, which tells a reader to
// distrust a number that is current. `renderedPricesAsOf` returning `null` — the
// card then rendering nothing — is honest; "May 12" over today's price is not.
//
// ── THE RULE ─────────────────────────────────────────────────────────────────
//
// The floor doctrine is a claim about what the reader can SEE: *nothing you can
// see here is older than this*. A row with `probability: null` shows no price,
// so it has no age that sentence is about and it cannot vote. This is the
// helper's own SCOPED-TO-THE-DRAWN-ROWS paragraph arriving through a door it did
// not cover: on `/api/events/search` the server's `served`/`top_outcomes` scope
// already keeps the dead tail out, but `/api/futures/{id}` hands the card the
// WHOLE ladder and there is no such scope, so it is re-stated here.
//
// ── THE SEAM THIS SUITE IS POINTED AT ────────────────────────────────────────
//
// `probability != null`, and NOT a truthiness check. `0` is a price and must
// keep its vote. `it("0% is a price…")` below is the whole reason the test for
// the specimen is not enough on its own: `if (!row.probability)` passes the
// specimen and silently hands the floor to whichever leg was refreshed last,
// which is the flattering half of #6018 all over again.
//
// The #6018 suite next door is the control and is unchanged — every double there
// carries `probability: 0.5`, so a priced stale rung still ages the card.

import { renderedPricesAsOf } from "@/lib/futuresCardPriceAge";
import type { FuturesOutcome } from "@/lib/types";
import specimen from "./fixtures/futures114175PricelessTail6803.json";

const PRICED_FLOOR = "2026-09-17T19:50:18.481Z";
const PRICELESS_TAIL = "2026-05-12T16:16:06.970Z";

const leg = (
  last_updated: string | null,
  probability: number | null,
  over: Partial<FuturesOutcome> = {},
): FuturesOutcome =>
  ({
    id: 1,
    name: "Leg",
    probability,
    american_odds: null,
    rank: null,
    rank_change_24h: null,
    probability_change_24h: null,
    movement: null,
    opening_probability: null,
    opening_american_odds: null,
    is_winner: false,
    last_updated,
    ...over,
  }) as FuturesOutcome;

describe("#6803 the production specimen, as served", () => {
  // The fixture is `/api/futures/114175` captured 2026-09-17T23:05Z, trimmed to
  // the four fields this helper reads. Not hand-written: 19 rows, 14 priced.
  const outcomes = specimen.outcomes as unknown as FuturesOutcome[];

  it("the fixture really is the defect's shape, or the rest of this file proves nothing", () => {
    expect(outcomes).toHaveLength(19);
    const priceless = outcomes.filter((o) => o.probability == null);
    expect(priceless).toHaveLength(5);
    expect(priceless.map((o) => o.name).sort()).toEqual([
      "Fighter D",
      "Fighter E",
      "Fighter F",
      "Fighter G",
      "Other",
    ]);
    // Every priceless rung is OLDER than every priced one — without that the
    // filter could not change the answer and a green bar would mean nothing.
    const oldestPriced = Math.min(
      ...outcomes
        .filter((o) => o.probability != null)
        .map((o) => new Date(o.last_updated as string).getTime()),
    );
    const newestPriceless = Math.max(
      ...priceless.map((o) => new Date(o.last_updated as string).getTime()),
    );
    expect(newestPriceless).toBeLessThan(oldestPriced);
  });

  it("dates the card by its fourteen prices, not by five rows that show none", () => {
    const asOf = renderedPricesAsOf({
      outcomes,
      top_outcomes: undefined,
    });
    expect(asOf).toBe(PRICED_FLOOR);
    // The whole point, stated as a difference rather than a value: the card no
    // longer wears the placeholder tail's date.
    expect(asOf).not.toBe(PRICELESS_TAIL);
  });

  it("serves no `prices_updated_at`, so the row walk IS the live path here", () => {
    // native/207's open question. If this payload carried the server's
    // arithmetic the helper would short-circuit to it and the fix would be inert
    // on exactly the surface it was filed about (My Stuff / Preferences, which
    // fetch `/api/futures/{id}`). It does not, so it is not.
    expect(specimen.prices_updated_at).toBeNull();
  });
});

describe("#6803 what a priceless row may and may not do", () => {
  it("0% is a price and keeps its vote — the truthiness trap", () => {
    // A `0` rung is a real quote, not an absence (see `pct`: "no number" and
    // "0%" are different statements). `if (!row.probability)` would drop this
    // row and answer with the fresh leg, which is the flattering direction.
    const asOf = renderedPricesAsOf({
      outcomes: [
        leg("2026-09-17T19:50:18.481Z", 0.655, { id: 1 }),
        leg("2026-05-12T16:16:06.970Z", 0, { id: 2, name: "Nobody" }),
      ],
      top_outcomes: undefined,
    });
    expect(asOf).toBe(PRICELESS_TAIL);
  });

  it("a row with no price at all cannot lower the floor", () => {
    const asOf = renderedPricesAsOf({
      outcomes: [
        leg("2026-09-17T19:50:18.481Z", 0.655, { id: 1 }),
        leg("2026-05-12T16:16:06.970Z", null, { id: 2, name: "Other" }),
      ],
      top_outcomes: undefined,
    });
    expect(asOf).toBe(PRICED_FLOOR);
  });

  it("an ABSENT probability key is priceless too, not a price of `undefined`", () => {
    const row = leg("2026-05-12T16:16:06.970Z", null, { id: 2, name: "Other" });
    delete (row as Partial<FuturesOutcome>).probability;
    const asOf = renderedPricesAsOf({
      outcomes: [leg("2026-09-17T19:50:18.481Z", 0.655, { id: 1 }), row],
      top_outcomes: undefined,
    });
    expect(asOf).toBe(PRICED_FLOOR);
  });

  it("a wholly priceless ladder says NOTHING rather than claiming the tail's date", () => {
    // Withholding is the designed answer (notice 34) — and it is the honest one:
    // a card drawing no prices has no price age. It must not fall through to the
    // stamps it just refused to count.
    expect(
      renderedPricesAsOf({
        outcomes: [
          leg("2026-05-12T16:16:06.970Z", null, { id: 1, name: "Fighter D" }),
          leg("2026-05-12T16:16:06.970Z", null, { id: 2, name: "Other" }),
        ],
        top_outcomes: undefined,
      }),
    ).toBeNull();
  });

  it("still prefers the server's arithmetic, which is already row-scoped", () => {
    // `_served_prices_as_of` computes its floor over `served_ids` — the rows the
    // card draws — so the client must not second-guess it. Unchanged by #6803.
    expect(
      renderedPricesAsOf({
        prices_updated_at: PRICELESS_TAIL,
        outcomes: [leg("2026-09-17T19:50:18.481Z", 0.655, { id: 1 })],
        top_outcomes: undefined,
      }),
    ).toBe(PRICELESS_TAIL);
  });
});
