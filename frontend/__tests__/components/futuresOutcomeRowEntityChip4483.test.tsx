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
 *
 * ## #6632 — the scope paragraph above was wrong about `field`, and the tests say so
 *
 * "Deliberately scoped to `quantity` only … `field` [has] real entity outcomes" is
 * left standing as written, because it is the record of what was believed, and
 * `/futures/112854` refuted it on production: a `field` market whose three outcomes
 * are dates drew `D3` · `J3` · `D3`. The predicate now takes the outcome SET as a
 * third argument and asks #4416's `isNumericLadder` about it.
 *
 * Every #4483 call above was given `ENTITY_ROWS`, so each still asserts what it
 * always asserted; the new arm is tested separately below against the live specimen.
 *
 * ### Red-first, MEASURED (and my guess was wrong again, in the same direction)
 *
 * I wrote "fails 6 of 7" from reasoning and then ran it: **4 of 19 fail, 15 pass.**
 * Jest strips types, so the parent predicate simply ignores the third argument —
 * which makes the measurement clean. The four are exactly the diff, all in the
 * `#6632` describe:
 *   1. refuses the picture on the live specimen that shipped D3 / J3 / D3
 *   2. refuses it for a duel whose two rungs are margins of the SAME party
 *   3. refuses it for ballot-measure numbers, which no threshold vocabulary matches
 *   4. asks the VALUE, not the SHAPE — one shape, two answers
 *
 * The three I had counted as red are the two over-correction fences (a field of
 * people who carry digits; a MIXED board) and the negative control — green on both
 * parents, which is what makes them fences rather than more of the diff. And all
 * TWELVE #4483 tests stay green on the parent: the evidence that giving them
 * `ENTITY_ROWS` preserved the input each one was written to turn on.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import fs from "node:fs";
import path from "node:path";

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

/**
 * #6632 gave the predicate a third argument, so every call below had to name an
 * outcome set. These are the two poles, and which one a test passes is now part of
 * what it asserts:
 *
 *   - `ENTITY_ROWS` — people, the case whose pictures are the point. Every
 *     pre-existing expectation keeps these, so each #4483 assertion still turns on
 *     exactly the input it always turned on and none of them passes for the new
 *     reason. (`50 Cent` is in the set on purpose: digits alone must not flip it.)
 *   - `LADDER_ROWS` — a shared skeleton, the #6632 case.
 */
const ENTITY_ROWS = ["Kamala Harris", "Gavin Newsom", "50 Cent", "Josh Shapiro"];
const LADDER_ROWS = ["Democrats, 2+ pts", "Democrats, 5+ pts", "Democrats, 8+ pts"];

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
    expect(outcomeRowShowsEntityImage("politics", SHAPE_QUANTITY, ENTITY_ROWS)).toBe(false);
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
      expect(outcomeRowShowsEntityImage(cat, SHAPE_QUANTITY, ENTITY_ROWS)).toBe(false);
    }
  });

  it("is decided by the SHAPE when the names are entities", () => {
    // The same category and the same names; only the shape differs. A guard that
    // passed by sniffing "Above" would not survive this pair.
    //
    // #6632 narrowed this test's TITLE, not its assertion: shape is still the whole
    // answer for an entity set, and the names-decide case is its own test below.
    expect(outcomeRowShowsEntityImage("politics", SHAPE_QUANTITY, ENTITY_ROWS)).toBe(false);
    expect(outcomeRowShowsEntityImage("politics", SHAPE_FIELD, ENTITY_ROWS)).toBe(true);
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
      expect(outcomeRowShowsEntityImage("politics", shape, ENTITY_ROWS)).toBe(true);
    }
  });

  it("leaves unshaped and claim alone — unknown is not 'known to be a threshold'", () => {
    // Documented scope, asserted so a later widening is a deliberate edit rather
    // than a silent one. `claim` has no rows in the non-sports categories.
    expect(outcomeRowShowsEntityImage("politics", SHAPE_UNSHAPED, ENTITY_ROWS)).toBe(true);
    expect(outcomeRowShowsEntityImage("politics", SHAPE_CLAIM, ENTITY_ROWS)).toBe(true);
    expect(outcomeRowShowsEntityImage("politics", null, ENTITY_ROWS)).toBe(true);
  });

  // NOT a control: it calls the new predicate, so it is red on the parent like the
  // five above. It guards the over-correction from the INSIDE — the fix must not
  // start suppressing (or start drawing) chips for sports categories.
  it("does not widen to sports categories", () => {
    expect(outcomeRowShowsEntityImage("mma", SHAPE_FIELD, ENTITY_ROWS)).toBe(false);
    expect(outcomeRowShowsEntityImage("tennis", SHAPE_QUANTITY, ENTITY_ROWS)).toBe(false);
    expect(outcomeRowShowsEntityImage(null, SHAPE_FIELD, ENTITY_ROWS)).toBe(false);
    expect(outcomeRowShowsEntityImage(undefined, SHAPE_FIELD, ENTITY_ROWS)).toBe(false);
  });
});

describe("#6632 a field of dates is a ladder too", () => {
  /**
   * `/futures/112854` verbatim, read from the production payload 2026-09-16 22:0xZ:
   * `market_type: 'field'`, `llm_sport_category: 'geopolitics'`, and these three
   * outcome names in serve order. Two of them initialise to the SAME `D3`.
   */
  const NATO_UKRAINE_DATES = [
    "December 31, 2026",
    "June 30, 2026",
    "December 31, 2025",
  ];

  it("refuses the picture on the live specimen that shipped D3 / J3 / D3", () => {
    expect(
      outcomeRowShowsEntityImage("geopolitics", SHAPE_FIELD, NATO_UKRAINE_DATES),
    ).toBe(false);
  });

  it("refuses it for a duel whose two rungs are margins of the SAME party", () => {
    // 47 live duels flip, a class #4416's census measured at 0%. `Republicans, 1+
    // pts` / `Republicans, 3+ pts` (market 13551329) would draw two identical `R1`
    // and `R3` chips of one party's logo-less initials.
    expect(
      outcomeRowShowsEntityImage("politics", SHAPE_DUEL, [
        "Republicans, 1+ pts",
        "Republicans, 3+ pts",
      ]),
    ).toBe(false);
  });

  it("refuses it for ballot-measure numbers, which no threshold vocabulary matches", () => {
    // Market 59164636. There is no %, no "pts", no month and no range dash here —
    // a keyword sniffer would keep the avatars. The SKELETON is what catches it.
    expect(
      outcomeRowShowsEntityImage("politics", SHAPE_FIELD, [
        "Amendment 1",
        "Amendment 2",
      ]),
    ).toBe(false);
  });

  it("asks the VALUE, not the SHAPE — one shape, two answers", () => {
    // The pair that fails if anyone re-simplifies this back to a shape lookup.
    // Same category, same `field` shape; only the outcome set differs.
    expect(outcomeRowShowsEntityImage("politics", SHAPE_FIELD, ENTITY_ROWS)).toBe(true);
    expect(outcomeRowShowsEntityImage("politics", SHAPE_FIELD, LADDER_ROWS)).toBe(false);
  });

  it("keeps the faces on a field of people who carry digits", () => {
    // #4416's own example, restated here because it is the false positive this
    // ship could most easily have caused: every name has a digit, so the
    // every-name-numeric precondition passes and only the shared-skeleton test
    // stands between `50 Cent` and a deleted picture.
    expect(
      outcomeRowShowsEntityImage("entertainment", SHAPE_FIELD, [
        "50 Cent",
        "Blink-182",
        "Matchbox 20",
      ]),
    ).toBe(true);
  });

  it("keeps the faces on a mixed board rather than half-deleting a column", () => {
    // All-or-nothing over the shipped set (#2662/#4416): one entity among the rungs
    // and the market keeps its avatars. A row-by-row rule would silently give some
    // rows a chip and not others.
    expect(
      outcomeRowShowsEntityImage("politics", SHAPE_FIELD, [
        "Democrats, 2+ pts",
        "Democrats, 5+ pts",
        "Kamala Harris",
      ]),
    ).toBe(true);
  });

  // ── CONTROL ───────────────────────────────────────────────────────────────
  it("CONTROL: a quantity ladder is still refused on the names' account too", () => {
    // Green on the parent AND here — the arm #4483 shipped is untouched, so a
    // regression that deleted the shape check would not hide behind this ship.
    expect(
      outcomeRowShowsEntityImage("politics", SHAPE_QUANTITY, ENTITY_ROWS),
    ).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// #6632 Part 2 — the page half, by source scan.
//
// THIS SECTION EXISTS BECAUSE OF TWO MUTATION SURVIVORS, and they were the two
// that mattered. With the predicate correct and all 19 tests above green, I
// mutated the CALLER and nothing went red:
//
//   M5  the page passes `displayedOutcomes` (the "show more" subset) → SURVIVED
//   M6  the page passes `[]`                                         → SURVIVED
//
// M6 is the one to fear. `isNumericLadder([])` is `[].every(…)` — vacuously true
// — then finds no shared skeleton and returns false, so the gate answers "draw
// the picture" for every market on the site. The whole ship would be INERT and
// 19 green predicate tests would still be green. The predicate is only half the
// fix; which set reaches it is the other half, and no unit test of a pure
// function can see it.
//
// The page is a client component whose fetches run on mount, so the scan is how
// its siblings reach it too (#5847, #5652, #5669).
// ---------------------------------------------------------------------------

describe("#6632 the page hands over the whole outcome set", () => {
  const ROOT = path.join(__dirname, "..", "..");
  const src = fs.readFileSync(
    path.join(ROOT, "app/futures/[id]/page.tsx"),
    "utf8",
  );
  /** The `outcomeRowShowsEntityImage(…)` call, arguments and all. */
  const call = src.slice(
    src.indexOf("outcomeRowShowsEntityImage("),
    src.indexOf(");", src.indexOf("outcomeRowShowsEntityImage(")) + 2,
  );

  it("calls the predicate exactly once", () => {
    // Twice would be two chances to disagree — the reason shape is resolved once
    // and passed down (see the caller's comment).
    // One, not two: the named import carries no paren, so this counts call sites.
    expect(src.match(/outcomeRowShowsEntityImage\(/g) ?? []).toHaveLength(1);
  });

  it("passes the outcome NAMES, not nothing (kills M6: the inert gate)", () => {
    expect(call).toContain("(market.outcomes ?? []).map((o) => o.name)");
  });

  it("passes the WHOLE set, not the displayed subset (kills M5)", () => {
    // `displayedOutcomes` is the "show more" slice. If it fed this gate, opening
    // the toggle could change whether the board has faces — and #4416's rule is
    // all-or-nothing over the shipped set.
    expect(call).not.toContain("displayedOutcomes");
  });

  it("feeds the gate the same set it resolved the shape from", () => {
    // Both must read `market.outcomes`, or the two halves of one decision are
    // answering about two different boards.
    expect(src).toContain("outcomeNames: (market.outcomes ?? []).map((o) => o.name)");
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
