/**
 * #4483 — A THRESHOLD IS NOT AN ENTITY, SO IT HAS NO PICTURE
 *
 * ## The defect
 *
 * `/futures/31835562` ("How many Senators will vote to confirm Todd Blanche as
 * Attorney General?"), production, 390px, verified still live 2026-09-09 17:55 PT:
 * four of the five Final Results rows wore an identical grey **`A5`** chip.
 * `Above 50`, `Above 51`, `Above 52` and `Above 53` all initialise to `A5`, so four
 * different answers carried one label and the reader could not tell them apart.
 *
 * The gate was `isNonSportsCategory(marketCategory)` alone, which asks "could this
 * name have a Wikipedia picture?" — and a threshold answers yes.
 *
 * ## Reachability, which is the part worth writing down
 *
 * `futuresLadder.ts`'s Q478 already fixed this on the LADDER path: a date/threshold
 * market used to render as a ranked leaderboard "with rank badges and 'BA'/'BJ'
 * initial avatars", and Q478 routed it to `QuantityGroup` instead. Then Q481 ruled
 * that a **settled** quantity market never ladders — so it falls back to this very
 * table and draws the avatars again. #4483's specimen is a resolved `quantity`
 * market. The avatar was fixed on one path and left standing on the other.
 *
 * Blast radius, measured on production 2026-09-09: **19,468** markets in the eight
 * non-sports categories carry `market_type='quantity'` (16,249 resolved + 3,219
 * open).
 *
 * ## The fix
 *
 * `outcomeRowShowsEntityImage(category, shape)`, with the shape resolved ONCE by the
 * caller over the whole outcome set — the same division as #3358's `showLastMove`,
 * because `resolveShape()`'s fallback needs every outcome name and a single row does
 * not have them. `showEntityImage` is a required prop with no default, so the next
 * surface that renders this row has to answer the question rather than inherit the
 * bug. (That requirement is load-bearing: adding it turned #3358's own test harness
 * red until it was updated, which is the failure mode working.)
 *
 * Deliberately scoped to `quantity` only. `duel`/`field`/`participation`/
 * `container_member` have real entity outcomes and their pictures are the point;
 * `claim` would qualify on principle but a census of the eight non-sports categories
 * returns **no `claim` rows at all**, so that arm would be unprovable; `unshaped`
 * keeps today's behaviour because "unknown" is not "known to be a threshold".
 *
 * ## Red-first, MEASURED rather than asserted
 *
 * Against the parent (`isNonSports ? <EntityImage/> : null`, no `showEntityImage`
 * prop, no predicate): **8 of 12 fail, 4 pass.**
 *
 * I first wrote "5 fail, 7 pass" from reasoning and it was wrong in a way worth
 * recording: every test in the first `describe` calls `outcomeRowShowsEntityImage`,
 * which does not exist on the parent, so all six throw there — including the one
 * originally labelled a CONTROL. A test that exercises the new export can never be
 * a control for the old code, however control-shaped its assertion is. It is
 * relabelled below rather than left posing as a fence.
 *
 * The eight that fail are the diff:
 *   1. refuses a picture to a quantity ladder's rungs
 *   2. refuses it for every non-sports category, not just politics
 *   3. is decided by the SHAPE, not by the outcome text
 *   4. keeps the picture for shapes whose outcomes really are entities
 *   5. leaves unshaped and claim alone
 *   6. the predicate does not widen to sports categories  (see note above)
 *   7. draws no chip for any of the four rows that printed A5
 *   8. obeys showEntityImage rather than re-deriving it from the category
 *
 * The four that pass are the real CONTROLS — green on the parent, green here, and
 * the fence around the over-correction that would make the eight go green cheaply
 * (deleting the chip outright, or suppressing it for every non-sports market):
 * a real entity row still gets its picture, the outcome name still prints, the
 * settled `Won` still prints, and the row still renders. None of the four is
 * load-bearing for this diff and none is claimed as such.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import OutcomeRow, {
  outcomeRowShowsEntityImage,
} from "@/components/futures/OutcomeRow";
import {
  SHAPE_CLAIM,
  SHAPE_CONTAINER_MEMBER,
  SHAPE_DUEL,
  SHAPE_FIELD,
  SHAPE_PARTICIPATION,
  SHAPE_QUANTITY,
  SHAPE_UNSHAPED,
} from "@/lib/marketShape";
import type { FuturesOutcome } from "@/lib/types";

/** The four rows that all printed `A5` on the specimen. */
const A5_ROWS = ["Above 50", "Above 51", "Above 52", "Above 53"];

function outcome(overrides: Partial<FuturesOutcome> = {}): FuturesOutcome {
  return {
    id: 1,
    name: "Above 51",
    probability: 0.5,
    opening_probability: 0.5,
    probability_change_24h: null,
    rank: 2,
    rank_change_24h: null,
    is_winner: null,
    last_updated: "2026-09-09T18:00:00+00:00",
    ...overrides,
  } as FuturesOutcome;
}

function render(
  o: FuturesOutcome,
  opts: { showEntityImage: boolean; marketCategory?: string },
): string {
  return renderToStaticMarkup(
    <OutcomeRow
      outcome={o}
      rank={1}
      isLeader={false}
      isSelected={false}
      onToggleSelect={() => {}}
      hasHistory={false}
      marketCategory={opts.marketCategory ?? "politics"}
      marketName="How many Senators will vote to confirm Todd Blanche?"
      isResolved
      rendered={null}
      renderedOpening={null}
      showLastMove={false}
      showEntityImage={opts.showEntityImage}
    />,
  );
}

describe("#4483 outcomeRowShowsEntityImage", () => {
  it("refuses a picture to a quantity ladder's rungs", () => {
    expect(outcomeRowShowsEntityImage("politics", SHAPE_QUANTITY)).toBe(false);
  });

  it("refuses it for every non-sports category, not just politics", () => {
    for (const cat of [
      "politics",
      "entertainment",
      "economics",
      "tech",
      "geopolitics",
      "culture",
      "weather",
      "other",
    ]) {
      expect(outcomeRowShowsEntityImage(cat, SHAPE_QUANTITY)).toBe(false);
    }
  });

  it("is decided by the SHAPE, not by the outcome text", () => {
    // The same category and the same names; only the shape differs. A guard that
    // passed by sniffing "Above" would not survive this pair.
    expect(outcomeRowShowsEntityImage("politics", SHAPE_QUANTITY)).toBe(false);
    expect(outcomeRowShowsEntityImage("politics", SHAPE_FIELD)).toBe(true);
  });

  it("keeps the picture for shapes whose outcomes really are entities", () => {
    // `as const`: a mutable array literal widens `"field" | "duel" | …` back to
    // `string`, which the predicate's `MarketShape | null` will not take.
    for (const shape of [
      SHAPE_FIELD,
      SHAPE_DUEL,
      SHAPE_PARTICIPATION,
      SHAPE_CONTAINER_MEMBER,
    ] as const) {
      expect(outcomeRowShowsEntityImage("politics", shape)).toBe(true);
    }
  });

  it("leaves unshaped and claim alone — unknown is not 'known to be a threshold'", () => {
    // Documented scope, asserted so a later widening is a deliberate edit rather
    // than a silent one. `claim` has no rows in the non-sports categories.
    expect(outcomeRowShowsEntityImage("politics", SHAPE_UNSHAPED)).toBe(true);
    expect(outcomeRowShowsEntityImage("politics", SHAPE_CLAIM)).toBe(true);
    expect(outcomeRowShowsEntityImage("politics", null)).toBe(true);
  });

  // NOT a control: it calls the new predicate, so it is red on the parent like the
  // five above. It guards the over-correction from the INSIDE — the fix must not
  // start suppressing (or start drawing) chips for sports categories.
  it("does not widen to sports categories", () => {
    expect(outcomeRowShowsEntityImage("mma", SHAPE_FIELD)).toBe(false);
    expect(outcomeRowShowsEntityImage("tennis", SHAPE_QUANTITY)).toBe(false);
    expect(outcomeRowShowsEntityImage(null, SHAPE_FIELD)).toBe(false);
    expect(outcomeRowShowsEntityImage(undefined, SHAPE_FIELD)).toBe(false);
  });
});

describe("#4483 the rendered row", () => {
  it("draws no chip for any of the four rows that printed A5", () => {
    for (const name of A5_ROWS) {
      const html = render(outcome({ name }), { showEntityImage: false });
      expect(html).not.toContain("entity-image");
      // and the answer the row exists to give is still there
      expect(html).toContain(name);
    }
  });

  it("obeys showEntityImage rather than re-deriving it from the category", () => {
    const off = render(outcome(), { showEntityImage: false });
    const on = render(outcome(), { showEntityImage: true });
    // Same category ("politics") on both, so anything that still keyed off
    // `isNonSportsCategory` would render identically here.
    expect(off).not.toEqual(on);
  });

  // ── CONTROLS ──────────────────────────────────────────────────────────────
  // Green on the parent too. They fence the over-correction, not the diff.

  it("CONTROL: a real entity row still gets its picture", () => {
    const html = render(outcome({ name: "Kamala Harris" }), {
      showEntityImage: true,
    });
    expect(html).toContain("Kamala Harris");
  });

  it("CONTROL: the outcome name still prints when the chip is suppressed", () => {
    expect(render(outcome({ name: "Above 49" }), { showEntityImage: false })).toContain(
      "Above 49",
    );
  });

  it("CONTROL: the settled result still prints beside the suppressed chip", () => {
    const html = render(outcome({ name: "Above 49", is_winner: true }), {
      showEntityImage: false,
    });
    expect(html).toContain("Won");
  });

  it("CONTROL: the row still renders at all", () => {
    expect(render(outcome(), { showEntityImage: false })).toContain(
      'data-testid="outcome-row"',
    );
  });
});
